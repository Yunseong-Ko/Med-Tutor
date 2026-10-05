"""학생 신뢰 배지 — 교수 문항(AIGEN)의 근거검증·졸업반검토·교수승인 상태를 학생 payload 배지로 환산.

데이터 소스(모두 data_private/ 아래, 원본 기출 텍스트 접근 없음):
  data_private/professor_items/generated/set_{1..4}.json           # 문항 원천 (qid = AIGEN_{set}_{no:03d})
  data_private/professor_items/review/reviews_1cha_normalized.json # 졸업반 검토 정규화 행 [{no, who, scores, verdict, note}]
  data_private/professor_items/review/item_actions.json            # 본 모듈이 빌드하는 캐시 {global_no: 조치}

배지 규칙(계약 §C, docs/api/Faculty_Student_Ops_API_Contract_20260906.md):
- evidence_verified : entailment_verdict ∈ {fully, partially} + 근거 포인터 존재 → "교과서 근거 검증" (fully=✓, partially=△)
- student_reviewed  : 검토 조치 ∈ {그대로, 경미} → "졸업반 3인 검토 통과"; 수정필요/폐기 → None(내부 review_pending)
- faculty_approved  : medical_approval is True → "교수 승인"

조치(그대로/경미/수정필요/폐기)는 scripts/aggregate_review_feedback.aggregate 와 **동일 규칙**
(한 명이라도 '사용 불가' → 폐기 / '대폭 수정' 또는 최저점 ≤2 → 수정필요 / '소폭 수정' 또는 점수범위 ≥2 → 경미 / 나머지 → 그대로)을
그대로 옮긴 것이며, tests/test_trust_badges.py 가 두 구현의 문항별 결과 일치를 교차검증한다.
(스크립트를 직접 import 하지 않는 이유: openpyxl 의존 + xlsx 저장 부수효과.)

경로 우선순위: 함수 인자 > 환경변수 > 모듈 상수 (테스트용 오버라이드). 쓰기는 item_actions.json 하나뿐이다.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROFESSOR_ITEMS_DIR = ROOT / "data_private" / "professor_items"
GENERATED_DIR = PROFESSOR_ITEMS_DIR / "generated"
REVIEW_DIR = PROFESSOR_ITEMS_DIR / "review"
REVIEWS_PATH = REVIEW_DIR / "reviews_1cha_normalized.json"
ITEM_ACTIONS_PATH = REVIEW_DIR / "item_actions.json"

# 환경변수 오버라이드 키(테스트·임시 디렉터리용).
ENV_REVIEWS_PATH = "PACCINE_REVIEWS_NORMALIZED_PATH"
ENV_ITEM_ACTIONS_PATH = "PACCINE_ITEM_ACTIONS_PATH"
ENV_GENERATED_DIR = "PACCINE_PROFESSOR_GENERATED_DIR"

# 번호 체계: 1~320 = 1교시 1~80, 2교시 81~160, 3교시 161~240, 4교시 241~320 (build_student_review_books 와 동일).
SET_SIZE = 80
QID_RE = re.compile(r"^AIGEN_(\d+)_(\d{3})$")

# 검토 판정 서열(aggregate_review_feedback.VERDICT_ORDER 와 동일 — 뒤로 갈수록 나쁨).
VERDICT_ORDER = ["수정없이 사용", "소폭 수정하여 사용", "대폭 수정 필요", "사용 불가"]
VERDICT_RANK = {v: i for i, v in enumerate(VERDICT_ORDER)}

# 조치 라벨: 집계 스크립트의 긴 라벨 ↔ 계약(§B action)의 짧은 라벨.
ACTION_KEEP, ACTION_MINOR, ACTION_REVISE, ACTION_DISCARD = "그대로", "경미", "수정필요", "폐기"
ACTION_ORDER = (ACTION_KEEP, ACTION_MINOR, ACTION_REVISE, ACTION_DISCARD)
ACTION_SHORT = {
    "그대로 사용": ACTION_KEEP,
    "경미 수정": ACTION_MINOR,
    "수정 필요": ACTION_REVISE,
    "폐기 검토": ACTION_DISCARD,
}
ACTION_LONG = {short: long for long, short in ACTION_SHORT.items()}
STUDENT_REVIEW_PASS_ACTIONS = frozenset({ACTION_KEEP, ACTION_MINOR})

# 배지 라벨·근거 마크(계약 §C).
EVIDENCE_LABEL = "교과서 근거 검증"
STUDENT_REVIEW_LABEL = "졸업반 3인 검토 통과"
FACULTY_APPROVED_LABEL = "교수 승인"
EVIDENCE_VERIFIED_LEVELS = ("fully", "partially")
EVIDENCE_MARK = {"fully": "✓", "partially": "△"}

# 과별 교과서 표기(scripts/build_student_review_books.BOOK_TITLES 와 동일하게 유지 — 테스트가 교차검증).
HARRISON_TITLE = "Harrison 22e"
BOOK_TITLES = {
    "harrison_22e": HARRISON_TITLE, "sabiston_21e": "Sabiston 21e",
    "nelson_21e": "Nelson 21e", "williams_ob_25e": "Williams Obstetrics 25e",
    "berek_novak_16e": "Berek & Novak 16e", "speroff_9e": "Speroff",
    "kr_psychiatry_3e": "신경정신의학 3판",
}

REVISION_SUMMARY_LINES = 2
REVISION_LINE_LIMIT = 120


# ── 경로·캐시 유틸 ────────────────────────────────────────────────────────────
def _resolve_path(explicit: str | os.PathLike | None, env_name: str, default: Path) -> Path:
    """함수 인자 > 환경변수 > 모듈 상수."""
    if explicit:
        return Path(explicit)
    env_value = str(os.environ.get(env_name) or "").strip()
    return Path(env_value) if env_value else default


def _file_signature(path: Path) -> tuple[str, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return str(path.resolve()), stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=32)
def _load_json_snapshot(path_value: str, mtime_ns: int, size_bytes: int) -> Any:
    del mtime_ns, size_bytes
    path = Path(path_value)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_json(path: Path) -> Any:
    signature = _file_signature(path)
    return _load_json_snapshot(*signature) if signature else None


def clear_caches() -> None:
    """파일 서명 캐시 초기화(테스트용)."""
    _load_json_snapshot.cache_clear()
    _generated_items_snapshot.cache_clear()


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# ── qid ↔ global_no 매핑 ─────────────────────────────────────────────────────
def parse_qid(qid: Any) -> tuple[int, int] | None:
    """'AIGEN_{set}_{no:03d}' → (set, no). 형식이 아니면 None."""
    match = QID_RE.match(str(qid or "").strip())
    if not match:
        return None
    set_no, item_no = int(match.group(1)), int(match.group(2))
    if set_no < 1 or item_no < 1:
        return None
    return set_no, item_no


def qid_to_global_no(qid: Any, set_size: int = SET_SIZE) -> int | None:
    """학생 qbank 문항 id(= AIGEN qid) → 전역 문항번호(1~320). 학생 qbank.json 의 id 필드가 곧 AIGEN qid 다."""
    parsed = parse_qid(qid)
    if parsed is None:
        return None
    set_no, item_no = parsed
    if item_no > set_size:
        return None
    return (set_no - 1) * set_size + item_no


def global_no_to_qid(global_no: Any, set_size: int = SET_SIZE) -> str | None:
    """전역 문항번호 → AIGEN qid. 정수가 아니거나 1 미만이면 None."""
    try:
        n = int(global_no)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    set_no, item_no = divmod(n - 1, set_size)
    return f"AIGEN_{set_no + 1}_{item_no + 1:03d}"


# ── 검토 조치 계산(aggregate_review_feedback 동일 규칙) ───────────────────────
def normalize_action(value: Any) -> str | None:
    """긴 라벨('그대로 사용')·짧은 라벨('그대로') 모두 짧은 라벨로 정규화. 모르는 값은 None."""
    text = str(value or "").strip()
    if not text:
        return None
    if text in ACTION_LONG:
        return text
    return ACTION_SHORT.get(text)


def classify_action(rows: list[dict[str, Any]]) -> str:
    """문항 하나의 검토 행들([{scores, verdict}, ...]) → 조치(짧은 라벨).

    aggregate_review_feedback.aggregate 의 분기와 문자 그대로 같다:
      한 명이라도 '사용 불가'            → 폐기
      '대폭 수정 필요' 또는 최저점 ≤2      → 수정필요
      '소폭 수정하여 사용' 또는 점수범위 ≥2 → 경미
      나머지                              → 그대로
    """
    all_scores: list[int] = []
    for row in rows:
        for value in (row.get("scores") or [])[:3]:
            try:
                all_scores.append(int(value))
            except (TypeError, ValueError):
                continue
    worst = min(all_scores) if all_scores else None
    score_range = (max(all_scores) - min(all_scores)) if all_scores else 0
    verdicts = [str(row.get("verdict") or "").strip() for row in rows]
    verdicts = [v for v in verdicts if v]
    worst_verdict = max(verdicts, key=lambda v: VERDICT_RANK.get(v, -1)) if verdicts else ""

    if worst_verdict == "사용 불가":
        return ACTION_DISCARD
    if worst_verdict == "대폭 수정 필요" or (worst is not None and worst <= 2):
        return ACTION_REVISE
    if worst_verdict == "소폭 수정하여 사용" or score_range >= 2:
        return ACTION_MINOR
    return ACTION_KEEP


def _group_reviews(rows: Any) -> dict[int, list[dict[str, Any]]]:
    by_item: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            no = int(row.get("no"))
        except (TypeError, ValueError):
            continue
        by_item[no].append(row)
    return by_item


def build_item_actions(
    reviews_path: str | os.PathLike | None = None,
    out_path: str | os.PathLike | None = None,
) -> dict[str, Any]:
    """reviews_1cha_normalized.json → review/item_actions.json ({global_no: 조치}) 캐시 빌드.

    반환: {"path": str, "items": int, "counts": {조치: n}, "actions": {global_no(int): 조치}}
    저장 파일은 계약대로 순수 매핑({"1": "경미", ...}) 이며 전역번호 오름차순이다.
    """
    src = _resolve_path(reviews_path, ENV_REVIEWS_PATH, REVIEWS_PATH)
    dst = _resolve_path(out_path, ENV_ITEM_ACTIONS_PATH, ITEM_ACTIONS_PATH)
    rows = json.loads(Path(src).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"정규화 검토 JSON은 배열이어야 합니다: {src}")

    by_item = _group_reviews(rows)
    actions = {no: classify_action(by_item[no]) for no in sorted(by_item)}
    counts = {label: 0 for label in ACTION_ORDER}
    for action in actions.values():
        counts[action] += 1

    _atomic_write_json(dst, {str(no): action for no, action in actions.items()})
    return {"path": str(dst), "items": len(actions), "counts": counts, "actions": actions}


def load_item_actions(path: str | os.PathLike | None = None) -> dict[int, str]:
    """item_actions.json 캐시 로드 → {global_no(int): 조치(짧은 라벨)}. 파일이 없거나 깨졌으면 {} (fail-soft).

    파일 서명(mtime·size) 기준으로 메모리 캐시되므로 재빌드 후 재호출하면 새 값을 읽는다.
    """
    src = _resolve_path(path, ENV_ITEM_ACTIONS_PATH, ITEM_ACTIONS_PATH)
    raw = _load_json(src)
    if not isinstance(raw, dict):
        return {}
    out: dict[int, str] = {}
    for key, value in raw.items():
        action = normalize_action(value)
        try:
            no = int(key)
        except (TypeError, ValueError):
            continue
        if action:
            out[no] = action
    return out


def action_for_qid(qid: Any, actions: dict[int, str] | None = None) -> str | None:
    """qid → 검토 조치. actions 를 넘기지 않으면 캐시 파일을 읽는다."""
    global_no = qid_to_global_no(qid)
    if global_no is None:
        return None
    table = actions if actions is not None else load_item_actions()
    return table.get(global_no)


def student_review_status(action: Any) -> str:
    """내부 상태값: passed(그대로/경미) · review_pending(수정필요/폐기) · unreviewed(조치 없음)."""
    normalized = normalize_action(action)
    if normalized is None:
        return "unreviewed"
    return "passed" if normalized in STUDENT_REVIEW_PASS_ACTIONS else "review_pending"


# ── 근거 포인터 ───────────────────────────────────────────────────────────────
def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def evidence_locators(question: dict[str, Any]) -> list[str]:
    """문항 → 근거 포인터 문자열 목록(원문 없음, locator 만).

    Harrison: 'Harrison 22e Ch.350 p.2649' (printed_page 없으면 'Harrison 22e Ch.350')
    과별 교과서: '{BOOK_TITLES[book_id]} Ch.39' (미등록 book_id 는 id 그대로)
    장(chapter) 이 없는 항목은 건너뛰고, 중복은 순서를 유지한 채 제거한다.
    """
    out: list[str] = []
    for src in question.get("harrison_sources") or []:
        if not isinstance(src, dict):
            continue
        chapter = _as_int(src.get("chapter"))
        if chapter is None:
            continue
        page = _as_int(src.get("printed_page"))
        out.append(f"{HARRISON_TITLE} Ch.{chapter}" + (f" p.{page}" if page is not None else ""))
    for src in question.get("textbook_sources") or []:
        if not isinstance(src, dict):
            continue
        chapter = _as_int(src.get("chapter"))
        if chapter is None:
            continue
        book_id = str(src.get("book_id") or "").strip()
        title = BOOK_TITLES.get(book_id, book_id) or "교과서"
        out.append(f"{title} Ch.{chapter}")
    seen: set[str] = set()
    unique = []
    for locator in out:
        if locator not in seen:
            seen.add(locator)
            unique.append(locator)
    return unique


def _evidence_badge(question: dict[str, Any], locators: list[str]) -> dict[str, Any]:
    verdict = str(question.get("entailment_verdict") or "").strip()
    if verdict in EVIDENCE_VERIFIED_LEVELS and locators:
        return {"level": verdict, "label": EVIDENCE_LABEL, "mark": EVIDENCE_MARK[verdict]}
    return {"level": "none", "label": None, "mark": None}


def evidence_summary(question: dict[str, Any]) -> dict[str, Any]:
    """계약의 `evidence:{locators:[...], badge}` 블록."""
    locators = evidence_locators(question)
    return {"locators": locators, "badge": _evidence_badge(question, locators)}


# ── 배지 계산 ─────────────────────────────────────────────────────────────────
def compute_trust_badges(question: dict[str, Any], action: str | None) -> dict[str, Any]:
    """문항 dict + 검토 조치 → 계약 §C 형식.

    {
      "evidence_verified": {"level": "fully"|"partially"|"none", "label": "교과서 근거 검증"|None, "mark": "✓"|"△"|None},
      "student_reviewed": {"label": "졸업반 3인 검토 통과"} | None,
      "faculty_approved": bool,
    }
    action 은 짧은 라벨·긴 라벨 모두 허용. 수정필요/폐기/None → student_reviewed=None (student_review_status 로 내부 상태 조회).
    """
    evidence = _evidence_badge(question, evidence_locators(question))
    reviewed = {"label": STUDENT_REVIEW_LABEL} if student_review_status(action) == "passed" else None
    approved = question.get("medical_approval") is True
    return {
        "evidence_verified": evidence,
        "student_reviewed": reviewed,
        "faculty_approved": approved,
    }


# ── v2 수정 이력 요약 ─────────────────────────────────────────────────────────
def _clip(text: Any, limit: int = REVISION_LINE_LIMIT) -> str:
    """공백 정리 후 limit 자 이내로 자른다. 절반 이후의 절·문장 경계에서 끊고 '…' 을 붙인다."""
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    head = flat[:limit]
    for sep in (". ", "。", "·", ", ", " "):
        idx = head.rfind(sep)
        if idx >= limit // 2:
            head = head[:idx]
            break
    return head.rstrip(" ,·.") + "…"


FACULTY_EDIT_FIELD_LABELS = {
    "stem": "문두",
    "choices": "선지",
    "answer": "정답",
    "explanation": "해설",
    "choice_explanations": "선지해설",
    "lab_box": "검사표",
    "textbook_sources": "근거",
    "harrison_sources": "근거",
}


def _v2_revision_note(question: dict[str, Any]) -> dict[str, Any] | None:
    v2 = question.get("v2_revision")
    if not isinstance(v2, dict):
        return None
    log = [str(line).strip() for line in (v2.get("log") or []) if str(line or "").strip()]
    fields = [str(f).strip() for f in (v2.get("fields") or []) if str(f or "").strip()]
    if not log and not fields:
        return None
    lines = [_clip(line) for line in log[:REVISION_SUMMARY_LINES]]
    if not lines:
        lines = [f"{'·'.join(fields)} 수정"]
    return {
        "date": str(v2.get("date") or "") or None,
        "summary": " ".join(lines),
        "fields": fields,
        "answer_changed": "정답" in fields,
    }


def _faculty_edit_note(question: dict[str, Any]) -> dict[str, Any] | None:
    """교수 검토 콘솔 편집(faculty_edited/faculty_edited_fields/faculty_edited_at) → 학생용 개정 요약."""
    if question.get("faculty_edited") is not True:
        return None
    fields: list[str] = []
    for raw in question.get("faculty_edited_fields") or []:
        label = FACULTY_EDIT_FIELD_LABELS.get(str(raw), str(raw))
        if label not in fields:
            fields.append(label)
    date = str(question.get("faculty_edited_at") or "")[:10] or None
    label = "·".join(fields) if fields else "문항"
    return {
        "date": date,
        "summary": f"교수 검토에서 {label} 수정.",
        "fields": fields,
        "answer_changed": "정답" in fields,
    }


def revision_note(question: dict[str, Any]) -> dict[str, Any] | None:
    """v2_revision.log(+교수 콘솔 편집) → {date, summary, fields, answer_changed}. 수정 이력이 없으면 None.

    summary 는 log 앞 1~2줄을 각각 REVISION_LINE_LIMIT 자로 잘라 공백으로 이은 것이며,
    fields 에 '정답' 이 있으면 answer_changed=True 로 표시한다(학생 UI 강조용).
    교수 콘솔에서 고친 문항은 v2 이력이 없어도 '교수 검토에서 … 수정' 한 줄을 돌려준다.
    """
    v2 = _v2_revision_note(question)
    faculty = _faculty_edit_note(question)
    if v2 and faculty:
        fields = list(v2["fields"]) + [f for f in faculty["fields"] if f not in v2["fields"]]
        return {
            "date": faculty["date"] or v2["date"],
            "summary": f"{v2['summary']} {faculty['summary']}".strip(),
            "fields": fields,
            "answer_changed": bool(v2["answer_changed"] or faculty["answer_changed"]),
        }
    return faculty or v2


# ── 생성 문항 로더 + 학생 payload 조립 ────────────────────────────────────────
def _set_files(generated_dir: Path) -> list[Path]:
    def _index(path: Path) -> int:
        match = re.match(r"^set_(\d+)\.json$", path.name)
        return int(match.group(1)) if match else 0

    files = [p for p in generated_dir.glob("set_*.json") if re.match(r"^set_\d+\.json$", p.name)]
    return sorted(files, key=_index)


@lru_cache(maxsize=4)
def _generated_items_snapshot(signature_key: tuple[tuple[str, int, int], ...]) -> dict[str, dict[str, Any]]:
    """set_*.json 을 교시 순서로 이어붙여 qid → 문항(+qid/set/global_no) 사전으로 만든다."""
    out: dict[str, dict[str, Any]] = {}
    global_no = 0
    for path_value, _mtime, _size in signature_key:
        path = Path(path_value)
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        match = re.match(r"^set_(\d+)\.json$", path.name)
        set_no = int(match.group(1)) if match else 0
        for position, item in enumerate(items if isinstance(items, list) else [], start=1):
            if not isinstance(item, dict):
                continue
            global_no += 1
            item_no = _as_int(item.get("no")) or position
            qid = f"AIGEN_{set_no}_{item_no:03d}"
            record = dict(item)
            record.update({"qid": qid, "set": set_no, "global_no": global_no})
            out[qid] = record
    return out


def load_generated_items(generated_dir: str | os.PathLike | None = None) -> dict[str, dict[str, Any]]:
    """generated/set_{n}.json 전체 → {qid: 문항}. 파일 서명 기준 캐시. 디렉터리가 없으면 {}."""
    root = _resolve_path(generated_dir, ENV_GENERATED_DIR, GENERATED_DIR)
    signatures = tuple(sig for sig in (_file_signature(p) for p in _set_files(root)) if sig)
    if not signatures:
        return {}
    return _generated_items_snapshot(signatures)


def student_trust_payload(
    qid: Any,
    *,
    generated_dir: str | os.PathLike | None = None,
    actions: dict[int, str] | None = None,
    actions_path: str | os.PathLike | None = None,
) -> dict[str, Any] | None:
    """학생 답안 응답에 붙일 블록을 한 번에 조립: {trust_badges, evidence, revision_note}.

    qid 가 AIGEN 문항이 아니거나 생성 파일에 없으면 None (호출측은 필드 생략).
    actions 를 넘기면 그 표를 쓰고, 아니면 actions_path(또는 env/상수)의 캐시 파일을 읽는다.
    """
    item = load_generated_items(generated_dir).get(str(qid or "").strip())
    if item is None:
        return None
    table = actions if actions is not None else load_item_actions(actions_path)
    action = table.get(int(item["global_no"]))
    return {
        "trust_badges": compute_trust_badges(item, action),
        "evidence": evidence_summary(item),
        "revision_note": revision_note(item),
    }
