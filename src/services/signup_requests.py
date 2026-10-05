"""학생 가입 신청 → 교수 승인 저장소 (계약 §A, docs/api/Faculty_Student_Ops_API_Contract_20260906.md).

저장 구조(모두 data_private/ 아래, git 제외):
  data_private/student/signup_requests.json    # 신청 레코드 배열 — pending/approved/rejected 전부 보존(감사 이력)
  data_private/student/approved_accounts.json  # 승인된 로그인 이메일 + 승인 메타(로그인 연동 조회용)

핵심 규칙:
- 비밀번호는 어디에도 저장하지 않는다. 승인 시 호출자가 넘긴 파생 함수
  (api_server.derive_roster_password와 동일 HMAC 규칙)로 계산해 응답에만 실어 보내고,
  교수가 학생에게 전달한다. 이 모듈은 파생 규칙을 재구현하지 않는다.
- 이메일은 lower/strip 정규화 후 비교·저장한다.
- 모든 쓰기는 파일 잠금(flock) 아래 read-modify-write → tmp 파일 → os.replace 원자 교체.
  두 파일은 항상 함께 바뀌므로 잠금은 signup_requests.json 기준 하나로 직렬화한다.
- 승인 취소: 승인된 신청을 rejected로 바꾸면 approved_accounts에서도 제거한다.
- 저장 경로 우선순위: 함수 인자 > 환경변수(PACCINE_SIGNUP_REQUESTS_PATH / PACCINE_APPROVED_ACCOUNTS_PATH)
  > 모듈 상수. 테스트는 환경변수 또는 인자로 임시 디렉터리를 지정한다.
- 로그인 경로(is_approved_email)는 파일 시그니처(mtime_ns, size) 캐시로 매 요청 재파싱을 피하고,
  파일 손상 시 fail-closed(아무도 승인되지 않은 것으로 취급)한다.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[2]
STUDENT_DATA_DIR = ROOT / "data_private" / "student"
SIGNUP_REQUESTS_PATH = STUDENT_DATA_DIR / "signup_requests.json"
APPROVED_ACCOUNTS_PATH = STUDENT_DATA_DIR / "approved_accounts.json"
SIGNUP_REQUESTS_PATH_ENV = "PACCINE_SIGNUP_REQUESTS_PATH"
APPROVED_ACCOUNTS_PATH_ENV = "PACCINE_APPROVED_ACCOUNTS_PATH"

ACCOUNTS_SCHEMA_VERSION = "approved_accounts.v1"
REQUEST_STATUSES = ("pending", "approved", "rejected")
LIST_STATUS_FILTERS = REQUEST_STATUSES + ("all",)
REQUEST_ID_LENGTH = 12

# 공개 엔드포인트(POST /api/auth/signup)로 들어오는 입력이므로 길이를 제한한다.
_FIELD_LIMITS = {"name": 100, "student_id": 40, "email": 254, "note": 500}
_FIELD_LABELS = {"name": "이름", "student_id": "학번", "email": "이메일", "note": "메모"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# GET 응답에 노출하는 신청 레코드 필드(계약 §A) + decision_note(승인 메모/반려 사유).
_PUBLIC_ITEM_FIELDS = (
    "request_id",
    "name",
    "student_id",
    "email",
    "note",
    "status",
    "submitted_at",
    "decided_at",
    "decided_by",
    "decision_note",
)

DerivePassword = Callable[[str], str]


class DuplicateEmailError(ValueError):
    """같은 이메일의 pending/approved 신청 또는 승인 계정이 이미 있음(API: 409)."""


class RequestNotFoundError(KeyError):
    """request_id에 해당하는 신청이 없음(API: 404)."""


class SignupQueueFullError(RuntimeError):
    """대기(pending) 신청이 상한(PACCINE_SIGNUP_MAX_PENDING, 기본 300)에 닿았다 — 공개 엔드포인트 남용 가드."""


MAX_PENDING_ENV = "PACCINE_SIGNUP_MAX_PENDING"
DEFAULT_MAX_PENDING = 300


def _max_pending() -> int:
    try:
        return max(1, int(os.environ.get(MAX_PENDING_ENV) or DEFAULT_MAX_PENDING))
    except ValueError:
        return DEFAULT_MAX_PENDING


class SignupStoreError(RuntimeError):
    """저장 파일이 손상되었거나 예상 구조가 아님 — 덮어써서 데이터를 잃지 않도록 중단."""


# ---------------------------------------------------------------------------
# 경로·시간·정규화
# ---------------------------------------------------------------------------


def _resolve_path(explicit: str | os.PathLike[str] | None, env_name: str, default: Path) -> Path:
    if explicit is not None:
        return Path(explicit)
    env_value = str(os.environ.get(env_name) or "").strip()
    return Path(env_value) if env_value else default


def _requests_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    # 모듈 상수는 호출 시점에 읽어 monkeypatch.setattr 오버라이드도 반영되게 한다.
    return _resolve_path(explicit, SIGNUP_REQUESTS_PATH_ENV, SIGNUP_REQUESTS_PATH)


def _accounts_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    return _resolve_path(explicit, APPROVED_ACCOUNTS_PATH_ENV, APPROVED_ACCOUNTS_PATH)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(email: object) -> str:
    """로그인·중복 비교에 쓰는 정규형(lower/strip). 로그인 연동 측도 같은 함수를 쓴다."""
    return str(email or "").strip().lower()


def _clean_text(value: object, field: str, *, required: bool) -> str:
    text = str(value or "").strip()
    label = _FIELD_LABELS[field]
    if required and not text:
        raise ValueError(f"{label}은(는) 필수입니다.")
    if len(text) > _FIELD_LIMITS[field]:
        raise ValueError(f"{label}은(는) {_FIELD_LIMITS[field]}자 이내여야 합니다.")
    return text


def _new_request_id(existing: set[str]) -> str:
    while True:
        candidate = uuid.uuid4().hex[:REQUEST_ID_LENGTH]
        if candidate not in existing:
            return candidate


# ---------------------------------------------------------------------------
# 파일 입출력(잠금·원자 쓰기·캐시)
# ---------------------------------------------------------------------------


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """path 옆의 .lock 파일에 flock(EX). fd가 호출마다 새로 열리므로 스레드·프로세스 모두 직렬화된다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SignupStoreError(f"{path.name} 파싱 실패: {exc}") from exc


def _read_requests(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = _read_json(path)
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise SignupStoreError(f"{path.name}은 신청 레코드(dict) 배열이어야 합니다.")
    return payload


def _empty_accounts() -> dict[str, Any]:
    return {"schema_version": ACCOUNTS_SCHEMA_VERSION, "updated_at": None, "accounts": {}}


def _read_accounts(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _empty_accounts()
    payload = _read_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("accounts"), dict):
        raise SignupStoreError(f"{path.name}은 {{accounts: {{email: meta}}}} 구조여야 합니다.")
    return payload


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        # replace 전에 실패했을 때만 남는 잔여 tmp 정리
        tmp_path.unlink(missing_ok=True)
    # 같은 프로세스의 로그인 캐시는 즉시 무효화(시그니처 해상도가 거친 파일시스템 대비).
    _approved_email_snapshot.cache_clear()


def _file_signature(path: Path) -> tuple[str, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return str(path.resolve()), stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=8)
def _approved_email_snapshot(path_value: str, mtime_ns: int, size_bytes: int) -> frozenset[str]:
    del mtime_ns, size_bytes  # 캐시 키 전용
    try:
        payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()  # 손상·누락 → fail-closed
    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, dict):
        return frozenset()
    return frozenset(email for email in (normalize_email(key) for key in accounts) if email)


def _approved_email_set(path: Path) -> frozenset[str]:
    signature = _file_signature(path)
    return _approved_email_snapshot(*signature) if signature else frozenset()


# ---------------------------------------------------------------------------
# 레코드 헬퍼
# ---------------------------------------------------------------------------


def _find_request(records: list[dict[str, Any]], request_id: object) -> dict[str, Any]:
    wanted = str(request_id or "").strip()
    if wanted:
        for record in records:
            if str(record.get("request_id") or "") == wanted:
                return record
    raise RequestNotFoundError(wanted or "(empty request_id)")


def _public_item(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record.get(field) for field in _PUBLIC_ITEM_FIELDS}


def _mark_decided(record: dict[str, Any], status: str, decided_by: str, note: str, now: str) -> None:
    record["status"] = status
    record["decided_at"] = now
    record["decided_by"] = decided_by
    record["decision_note"] = note


def _upsert_account(accounts_payload: dict[str, Any], record: dict[str, Any], now: str) -> bool:
    """승인 계정 등록(멱등). 새로 추가됐을 때만 True."""
    email = normalize_email(record.get("email"))
    accounts = accounts_payload["accounts"]
    if email in accounts:
        return False
    accounts[email] = {
        "email": email,
        "name": record.get("name"),
        "student_id": record.get("student_id"),
        "request_id": record.get("request_id"),
        "approved_at": record.get("decided_at") or now,
        "approved_by": record.get("decided_by"),
        "note": record.get("decision_note") or "",
    }
    accounts_payload["updated_at"] = now
    return True


def _credentials(record: dict[str, Any], derive_password: DerivePassword | None) -> dict[str, Any]:
    """응답 전용 자격 정보 — 파일에는 절대 쓰지 않는다. 파생 함수가 없으면 빈 문자열(미설정)."""
    email = normalize_email(record.get("email"))
    password = str(derive_password(email) or "") if derive_password is not None else ""
    return {
        "request_id": record.get("request_id"),
        "login_email": email,
        "initial_password": password,
    }


def _require_actor(decided_by: object) -> str:
    actor = str(decided_by or "").strip()
    if not actor:
        raise ValueError("decided_by(결정자 식별자)가 필요합니다.")
    return actor


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def submit_request(
    name: str,
    student_id: str,
    email: str,
    note: str = "",
    *,
    requests_path: str | os.PathLike[str] | None = None,
    accounts_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """가입 신청 접수(공개). 반환 {request_id, status:"pending", submitted_at}.

    중복 판정: 같은 정규화 이메일의 pending/approved 신청 또는 승인 계정이 있으면
    DuplicateEmailError(ValueError). rejected 이력만 있으면 재신청을 허용한다.
    """
    name = _clean_text(name, "name", required=True)
    student_id = _clean_text(student_id, "student_id", required=True)
    email = normalize_email(_clean_text(email, "email", required=True))
    note = _clean_text(note, "note", required=False)
    if not _EMAIL_RE.match(email):
        raise ValueError("이메일 형식이 올바르지 않습니다.")

    req_path = _requests_path(requests_path)
    acc_path = _accounts_path(accounts_path)
    with _locked(req_path):
        records = _read_requests(req_path)
        accounts_payload = _read_accounts(acc_path)
        blocked = email in accounts_payload["accounts"] or any(
            normalize_email(record.get("email")) == email
            and record.get("status") in {"pending", "approved"}
            for record in records
        )
        if blocked:
            raise DuplicateEmailError(f"이미 신청되었거나 승인된 이메일입니다: {email}")
        pending = sum(1 for record in records if record.get("status") == "pending")
        if pending >= _max_pending():
            raise SignupQueueFullError(f"대기 중인 가입 신청이 {pending}건으로 상한에 닿았습니다.")
        now = _now_iso()
        record = {
            "request_id": _new_request_id({str(row.get("request_id") or "") for row in records}),
            "name": name,
            "student_id": student_id,
            "email": email,
            "note": note,
            "status": "pending",
            "submitted_at": now,
            "decided_at": None,
            "decided_by": None,
            "decision_note": None,
        }
        records.append(record)
        _write_json_atomic(req_path, records)
    return {"request_id": record["request_id"], "status": "pending", "submitted_at": now}


def list_requests(
    status: str = "pending",
    *,
    requests_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """신청 목록(교수). status ∈ pending|approved|rejected|all. counts는 필터와 무관하게 전체 집계.

    정렬은 submitted_at 오름차순(FIFO — 먼저 신청한 학생부터 처리).
    """
    wanted = str(status or "pending").strip().lower()
    if wanted not in LIST_STATUS_FILTERS:
        raise ValueError(f"status는 {'|'.join(LIST_STATUS_FILTERS)} 중 하나여야 합니다.")
    records = _read_requests(_requests_path(requests_path))
    counts = {name: 0 for name in REQUEST_STATUSES}
    for record in records:
        if record.get("status") in counts:
            counts[str(record["status"])] += 1
    ordered = sorted(
        records,
        key=lambda row: (str(row.get("submitted_at") or ""), str(row.get("request_id") or "")),
    )
    items = [
        _public_item(record)
        for record in ordered
        if wanted == "all" or record.get("status") == wanted
    ]
    return {"items": items, "counts": counts}


def approve_request(
    request_id: str,
    decided_by: str,
    note: str = "",
    derive_password: DerivePassword | None = None,
    *,
    requests_path: str | os.PathLike[str] | None = None,
    accounts_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """단건 승인(교수). 반환 {request_id, status:"approved", login_email, initial_password}.

    - pending/rejected → approved 로 전이하고 approved_accounts에 등록한다.
    - 이미 approved면 결정 메타를 덮어쓰지 않고(멱등) 자격 정보만 다시 계산해 돌려준다.
    - derive_password는 api_server.derive_roster_password 같은 callable; None이면 initial_password="".
    """
    actor = _require_actor(decided_by)
    note = _clean_text(note, "note", required=False)
    req_path = _requests_path(requests_path)
    acc_path = _accounts_path(accounts_path)
    with _locked(req_path):
        records = _read_requests(req_path)
        record = _find_request(records, request_id)
        accounts_payload = _read_accounts(acc_path)
        now = _now_iso()
        if record.get("status") != "approved":
            _mark_decided(record, "approved", actor, note, now)
            _write_json_atomic(req_path, records)
        if _upsert_account(accounts_payload, record, now):
            _write_json_atomic(acc_path, accounts_payload)
    return {"status": "approved", **_credentials(record, derive_password)}


def reject_request(
    request_id: str,
    decided_by: str,
    reason: str = "",
    *,
    requests_path: str | os.PathLike[str] | None = None,
    accounts_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """단건 반려/승인 취소(교수). 반환 {request_id, status:"rejected"}.

    approved 상태에서 호출하면 approved_accounts에서도 제거되어 로그인이 즉시 차단된다.
    이미 rejected면 멱등(사유 덮어쓰지 않음).
    """
    actor = _require_actor(decided_by)
    reason = _clean_text(reason, "note", required=False)
    req_path = _requests_path(requests_path)
    acc_path = _accounts_path(accounts_path)
    with _locked(req_path):
        records = _read_requests(req_path)
        record = _find_request(records, request_id)
        accounts_payload = _read_accounts(acc_path)
        now = _now_iso()
        if record.get("status") != "rejected":
            _mark_decided(record, "rejected", actor, reason, now)
            _write_json_atomic(req_path, records)
        if accounts_payload["accounts"].pop(normalize_email(record.get("email")), None) is not None:
            accounts_payload["updated_at"] = now
            _write_json_atomic(acc_path, accounts_payload)
    return {"request_id": record.get("request_id"), "status": "rejected"}


def bulk_approve(
    request_ids: list[str],
    decided_by: str,
    derive_password: DerivePassword | None,
    *,
    requests_path: str | os.PathLike[str] | None = None,
    accounts_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """일괄 승인(교수). 반환 {approved:[{request_id, login_email, initial_password}], skipped:[{request_id, reason}]}.

    pending만 승인한다(체크리스트 일괄 처리 용도). skipped.reason ∈ not_found | already_approved | rejected | invalid_status.
    입력 id는 순서를 유지한 채 중복 제거하며, 전체가 한 잠금·한 번의 쓰기로 처리된다.
    """
    actor = _require_actor(decided_by)
    ordered_ids: list[str] = []
    for raw in request_ids or []:
        rid = str(raw or "").strip()
        if rid and rid not in ordered_ids:
            ordered_ids.append(rid)

    req_path = _requests_path(requests_path)
    acc_path = _accounts_path(accounts_path)
    approved: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    with _locked(req_path):
        records = _read_requests(req_path)
        by_id = {str(row.get("request_id") or ""): row for row in records}
        accounts_payload = _read_accounts(acc_path)
        now = _now_iso()
        changed = False
        for rid in ordered_ids:
            record = by_id.get(rid)
            if record is None:
                skipped.append({"request_id": rid, "reason": "not_found"})
                continue
            status = record.get("status")
            if status != "pending":
                reason = {"approved": "already_approved", "rejected": "rejected"}.get(str(status), "invalid_status")
                skipped.append({"request_id": rid, "reason": reason})
                continue
            _mark_decided(record, "approved", actor, "", now)
            _upsert_account(accounts_payload, record, now)
            approved.append(_credentials(record, derive_password))
            changed = True
        if changed:
            _write_json_atomic(req_path, records)
            _write_json_atomic(acc_path, accounts_payload)
    return {"approved": approved, "skipped": skipped}


def is_approved_email(
    email: object,
    *,
    accounts_path: str | os.PathLike[str] | None = None,
) -> bool:
    """로그인 연동용: 승인 계정 여부. 파일 시그니처 캐시로 매 요청 재파싱을 피한다."""
    normalized = normalize_email(email)
    if not normalized:
        return False
    return normalized in _approved_email_set(_accounts_path(accounts_path))
