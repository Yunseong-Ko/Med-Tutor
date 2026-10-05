from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services import signup_requests as sr


def fake_derive(email: str) -> str:
    # api_server.derive_roster_password 대역 — 결정론적이기만 하면 된다.
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:8].upper()


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    requests_path = tmp_path / "signup_requests.json"
    accounts_path = tmp_path / "approved_accounts.json"
    monkeypatch.setenv(sr.SIGNUP_REQUESTS_PATH_ENV, str(requests_path))
    monkeypatch.setenv(sr.APPROVED_ACCOUNTS_PATH_ENV, str(accounts_path))
    sr._approved_email_snapshot.cache_clear()
    return SimpleNamespace(root=tmp_path, requests=requests_path, accounts=accounts_path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# submit_request
# ---------------------------------------------------------------------------


def test_submit_creates_pending_record_with_normalized_email(store: SimpleNamespace) -> None:
    result = sr.submit_request("홍길동", "202412345", "  Hong@Pusan.AC.KR ", note=" 본3 ")

    assert result["status"] == "pending"
    assert re.fullmatch(r"[0-9a-f]{12}", result["request_id"])
    assert result["submitted_at"].endswith("+00:00")

    payload = read_json(store.requests)
    assert isinstance(payload, list) and len(payload) == 1
    record = payload[0]
    assert record["email"] == "hong@pusan.ac.kr"
    assert record["name"] == "홍길동"
    assert record["note"] == "본3"
    assert record["decided_at"] is None and record["decided_by"] is None
    # 승인 계정 파일은 아직 만들어지지 않는다.
    assert not store.accounts.exists()


def test_submit_duplicate_email_raises_value_error_subclass(store: SimpleNamespace) -> None:
    sr.submit_request("A", "1", "dup@pusan.ac.kr")
    with pytest.raises(sr.DuplicateEmailError):
        sr.submit_request("B", "2", "DUP@pusan.ac.kr ")
    assert issubclass(sr.DuplicateEmailError, ValueError)
    assert len(read_json(store.requests)) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "", "student_id": "1", "email": "a@b.co"},
        {"name": "A", "student_id": "", "email": "a@b.co"},
        {"name": "A", "student_id": "1", "email": ""},
        {"name": "A", "student_id": "1", "email": "not-an-email"},
        {"name": "A", "student_id": "1", "email": "a@b.co", "note": "x" * 501},
    ],
)
def test_submit_rejects_invalid_input(store: SimpleNamespace, kwargs: dict) -> None:
    with pytest.raises(ValueError):
        sr.submit_request(**kwargs)
    assert not store.requests.exists()


def test_resubmission_allowed_after_rejection(store: SimpleNamespace) -> None:
    first = sr.submit_request("A", "1", "again@pusan.ac.kr")
    sr.reject_request(first["request_id"], "prof", reason="학번 불일치")
    second = sr.submit_request("A", "1", "again@pusan.ac.kr")

    assert second["request_id"] != first["request_id"]
    listing = sr.list_requests("all")
    assert listing["counts"] == {"pending": 1, "approved": 0, "rejected": 1}


# ---------------------------------------------------------------------------
# list_requests
# ---------------------------------------------------------------------------


def test_list_filters_counts_and_fifo_order(store: SimpleNamespace) -> None:
    ids = [sr.submit_request(f"N{i}", str(i), f"u{i}@pusan.ac.kr")["request_id"] for i in range(3)]
    sr.approve_request(ids[1], "prof", derive_password=fake_derive)
    sr.reject_request(ids[2], "prof", reason="no")

    pending = sr.list_requests()  # 기본값 pending
    assert [item["request_id"] for item in pending["items"]] == [ids[0]]
    assert pending["counts"] == {"pending": 1, "approved": 1, "rejected": 1}

    everything = sr.list_requests("all")
    assert [item["request_id"] for item in everything["items"]] == ids
    assert set(everything["items"][0]) == {
        "request_id", "name", "student_id", "email", "note", "status",
        "submitted_at", "decided_at", "decided_by", "decision_note",
    }
    rejected = sr.list_requests("REJECTED")["items"]
    assert rejected[0]["decision_note"] == "no" and rejected[0]["decided_by"] == "prof"

    with pytest.raises(ValueError):
        sr.list_requests("bogus")


def test_list_on_missing_file_is_empty(store: SimpleNamespace) -> None:
    assert sr.list_requests("all") == {"items": [], "counts": {"pending": 0, "approved": 0, "rejected": 0}}


# ---------------------------------------------------------------------------
# approve / reject
# ---------------------------------------------------------------------------


def test_approve_registers_account_and_never_persists_password(store: SimpleNamespace) -> None:
    rid = sr.submit_request("홍길동", "202412345", "Hong@pusan.ac.kr")["request_id"]

    result = sr.approve_request(rid, "prof@pusan.ac.kr", note="확인", derive_password=fake_derive)

    assert result == {
        "request_id": rid,
        "status": "approved",
        "login_email": "hong@pusan.ac.kr",
        "initial_password": fake_derive("hong@pusan.ac.kr"),
    }
    accounts = read_json(store.accounts)
    assert accounts["schema_version"] == sr.ACCOUNTS_SCHEMA_VERSION
    entry = accounts["accounts"]["hong@pusan.ac.kr"]
    assert entry["request_id"] == rid and entry["approved_by"] == "prof@pusan.ac.kr"
    assert entry["approved_at"] and entry["note"] == "확인"
    # 비밀번호는 두 파일 어디에도 없다.
    for path in (store.requests, store.accounts):
        assert result["initial_password"] not in path.read_text(encoding="utf-8")
    assert sr.is_approved_email(" HONG@pusan.ac.kr ") is True
    record = read_json(store.requests)[0]
    assert record["status"] == "approved" and record["decided_by"] == "prof@pusan.ac.kr"


def test_approve_is_idempotent_and_keeps_original_decision(store: SimpleNamespace) -> None:
    rid = sr.submit_request("A", "1", "idem@pusan.ac.kr")["request_id"]
    first = sr.approve_request(rid, "prof1", derive_password=fake_derive)
    decided_at = read_json(store.requests)[0]["decided_at"]

    second = sr.approve_request(rid, "prof2", derive_password=fake_derive)

    assert second == first
    record = read_json(store.requests)[0]
    assert record["decided_by"] == "prof1" and record["decided_at"] == decided_at
    assert len(read_json(store.accounts)["accounts"]) == 1


def test_approve_without_derive_returns_empty_password(store: SimpleNamespace) -> None:
    rid = sr.submit_request("A", "1", "nopw@pusan.ac.kr")["request_id"]
    assert sr.approve_request(rid, "prof")["initial_password"] == ""


def test_approve_requires_actor_and_known_id(store: SimpleNamespace) -> None:
    rid = sr.submit_request("A", "1", "x@pusan.ac.kr")["request_id"]
    with pytest.raises(ValueError):
        sr.approve_request(rid, "", derive_password=fake_derive)
    with pytest.raises(sr.RequestNotFoundError):
        sr.approve_request("000000000000", "prof", derive_password=fake_derive)
    assert issubclass(sr.RequestNotFoundError, KeyError)
    assert read_json(store.requests)[0]["status"] == "pending"


def test_reject_pending_then_reapprove(store: SimpleNamespace) -> None:
    rid = sr.submit_request("A", "1", "flip@pusan.ac.kr")["request_id"]
    assert sr.reject_request(rid, "prof", reason="서류 미비") == {"request_id": rid, "status": "rejected"}
    assert sr.is_approved_email("flip@pusan.ac.kr") is False

    # 반려 → 승인 번복 허용
    sr.approve_request(rid, "prof", derive_password=fake_derive)
    assert sr.is_approved_email("flip@pusan.ac.kr") is True


def test_reject_approved_revokes_login(store: SimpleNamespace) -> None:
    rid = sr.submit_request("A", "1", "revoke@pusan.ac.kr")["request_id"]
    sr.approve_request(rid, "prof", derive_password=fake_derive)
    assert sr.is_approved_email("revoke@pusan.ac.kr") is True

    sr.reject_request(rid, "prof", reason="승인 취소")

    assert sr.is_approved_email("revoke@pusan.ac.kr") is False
    assert read_json(store.accounts)["accounts"] == {}
    record = read_json(store.requests)[0]
    assert record["status"] == "rejected" and record["decision_note"] == "승인 취소"


def test_reject_is_idempotent(store: SimpleNamespace) -> None:
    rid = sr.submit_request("A", "1", "twice@pusan.ac.kr")["request_id"]
    sr.reject_request(rid, "prof", reason="first")
    sr.reject_request(rid, "prof2", reason="second")
    record = read_json(store.requests)[0]
    assert record["decision_note"] == "first" and record["decided_by"] == "prof"


# ---------------------------------------------------------------------------
# bulk_approve
# ---------------------------------------------------------------------------


def test_bulk_approve_mixed_ids(store: SimpleNamespace) -> None:
    pending_a = sr.submit_request("A", "1", "a@pusan.ac.kr")["request_id"]
    pending_b = sr.submit_request("B", "2", "b@pusan.ac.kr")["request_id"]
    already = sr.submit_request("C", "3", "c@pusan.ac.kr")["request_id"]
    sr.approve_request(already, "prof", derive_password=fake_derive)
    rejected = sr.submit_request("D", "4", "d@pusan.ac.kr")["request_id"]
    sr.reject_request(rejected, "prof")

    result = sr.bulk_approve(
        [pending_a, pending_b, pending_a, already, rejected, "ffffffffffff", ""],
        "prof",
        fake_derive,
    )

    assert [row["request_id"] for row in result["approved"]] == [pending_a, pending_b]
    assert result["approved"][0] == {
        "request_id": pending_a,
        "login_email": "a@pusan.ac.kr",
        "initial_password": fake_derive("a@pusan.ac.kr"),
    }
    assert result["skipped"] == [
        {"request_id": already, "reason": "already_approved"},
        {"request_id": rejected, "reason": "rejected"},
        {"request_id": "ffffffffffff", "reason": "not_found"},
    ]
    assert set(read_json(store.accounts)["accounts"]) == {"a@pusan.ac.kr", "b@pusan.ac.kr", "c@pusan.ac.kr"}
    assert all(sr.is_approved_email(e) for e in ("a@pusan.ac.kr", "b@pusan.ac.kr"))
    assert sr.list_requests("all")["counts"] == {"pending": 0, "approved": 3, "rejected": 1}


def test_bulk_approve_nothing_to_do_does_not_touch_files(store: SimpleNamespace) -> None:
    rid = sr.submit_request("A", "1", "a@pusan.ac.kr")["request_id"]
    sr.approve_request(rid, "prof", derive_password=fake_derive)
    before = (store.requests.read_bytes(), store.accounts.read_bytes())

    result = sr.bulk_approve([rid, "nope"], "prof", fake_derive)

    assert result["approved"] == [] and len(result["skipped"]) == 2
    assert (store.requests.read_bytes(), store.accounts.read_bytes()) == before


# ---------------------------------------------------------------------------
# is_approved_email — 캐시·fail-closed
# ---------------------------------------------------------------------------


def test_is_approved_email_missing_or_corrupt_file_is_false(store: SimpleNamespace) -> None:
    assert sr.is_approved_email("anyone@pusan.ac.kr") is False
    store.accounts.write_text("{not json", encoding="utf-8")
    assert sr.is_approved_email("anyone@pusan.ac.kr") is False
    assert sr.is_approved_email("") is False


def test_is_approved_email_reflects_external_file_change(store: SimpleNamespace) -> None:
    rid = sr.submit_request("A", "1", "ext@pusan.ac.kr")["request_id"]
    sr.approve_request(rid, "prof", derive_password=fake_derive)
    assert sr.is_approved_email("ext@pusan.ac.kr") is True

    # 다른 프로세스가 파일을 바꾼 상황을 흉내 — 캐시가 시그니처(mtime/size)로 무효화돼야 한다.
    payload = read_json(store.accounts)
    payload["accounts"]["other@pusan.ac.kr"] = dict(payload["accounts"]["ext@pusan.ac.kr"], email="other@pusan.ac.kr")
    store.accounts.write_text(json.dumps(payload), encoding="utf-8")
    assert sr.is_approved_email("other@pusan.ac.kr") is True

    store.accounts.unlink()
    assert sr.is_approved_email("ext@pusan.ac.kr") is False


# ---------------------------------------------------------------------------
# 저장 경로 오버라이드·원자 쓰기·동시성
# ---------------------------------------------------------------------------


def test_default_paths_live_under_data_private_student() -> None:
    assert sr.SIGNUP_REQUESTS_PATH == sr.ROOT / "data_private" / "student" / "signup_requests.json"
    assert sr.APPROVED_ACCOUNTS_PATH == sr.ROOT / "data_private" / "student" / "approved_accounts.json"


def test_explicit_path_args_override_env(store: SimpleNamespace, tmp_path: Path) -> None:
    other = tmp_path / "elsewhere"
    req = other / "r.json"
    acc = other / "a.json"

    rid = sr.submit_request("A", "1", "arg@pusan.ac.kr", requests_path=req, accounts_path=acc)["request_id"]
    sr.approve_request(rid, "prof", derive_password=fake_derive, requests_path=req, accounts_path=acc)

    assert req.exists() and acc.exists()
    assert not store.requests.exists() and not store.accounts.exists()
    assert sr.is_approved_email("arg@pusan.ac.kr", accounts_path=acc) is True
    assert sr.is_approved_email("arg@pusan.ac.kr") is False  # env 경로에는 없음
    assert sr.list_requests("all", requests_path=req)["counts"]["approved"] == 1


def test_monkeypatched_module_constants_are_honored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(sr.SIGNUP_REQUESTS_PATH_ENV, raising=False)
    monkeypatch.delenv(sr.APPROVED_ACCOUNTS_PATH_ENV, raising=False)
    monkeypatch.setattr(sr, "SIGNUP_REQUESTS_PATH", tmp_path / "req.json")
    monkeypatch.setattr(sr, "APPROVED_ACCOUNTS_PATH", tmp_path / "acc.json")
    sr._approved_email_snapshot.cache_clear()

    rid = sr.submit_request("A", "1", "const@pusan.ac.kr")["request_id"]
    sr.approve_request(rid, "prof", derive_password=fake_derive)

    assert (tmp_path / "req.json").exists() and (tmp_path / "acc.json").exists()
    assert sr.is_approved_email("const@pusan.ac.kr") is True


def test_atomic_write_leaves_no_temp_files(store: SimpleNamespace) -> None:
    rid = sr.submit_request("A", "1", "tmp@pusan.ac.kr")["request_id"]
    sr.approve_request(rid, "prof", derive_password=fake_derive)
    sr.reject_request(rid, "prof")
    assert not list(store.root.glob("*.tmp")) and not list(store.root.glob(".*.tmp"))
    # 잠금 파일만 남는다.
    assert {p.name for p in store.root.iterdir()} == {
        "signup_requests.json", "approved_accounts.json", ".signup_requests.json.lock",
    }


def test_corrupt_store_raises_instead_of_clobbering(store: SimpleNamespace) -> None:
    store.requests.write_text("{not json", encoding="utf-8")
    with pytest.raises(sr.SignupStoreError):
        sr.submit_request("A", "1", "a@pusan.ac.kr")
    assert store.requests.read_text(encoding="utf-8") == "{not json"

    store.requests.write_text("[]", encoding="utf-8")
    store.accounts.write_text('{"accounts": []}', encoding="utf-8")  # 잘못된 구조
    with pytest.raises(sr.SignupStoreError):
        sr.submit_request("A", "1", "a@pusan.ac.kr")


def test_concurrent_submissions_are_serialized(store: SimpleNamespace) -> None:
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            sr.submit_request(f"N{i}", str(i), f"c{i}@pusan.ac.kr")
        except BaseException as exc:  # noqa: BLE001 — 테스트 수집용
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    records = read_json(store.requests)
    assert len(records) == 16
    assert len({r["request_id"] for r in records}) == 16
    assert len({r["email"] for r in records}) == 16
