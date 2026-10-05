"""api_server 배선 테스트 — 계약 docs/api/Faculty_Student_Ops_API_Contract_20260906.md §A·§B·§C.

실데이터(data_private/)는 읽지도 쓰지도 않는다: 저장 경로를 전부 임시 디렉터리로 돌리고(환경변수 +
monkeypatch), 모듈 시작 시점의 실파일 해시를 픽스처 종료·마지막 테스트에서 재비교해 무변경을 확인한다.
합성 문항은 원본 기출 텍스트를 포함하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api_server
from src.services import faculty_adjudication as fa
from src.services import qbank_enrichment
from src.services import signup_requests as sr
from src.services import trust_badges as tb


ROOT = Path(__file__).resolve().parents[1]
REAL_PRIVATE = (ROOT / "data_private").resolve()

# 이 테스트 파일이 절대 건드리면 안 되는 실파일. 모듈 시작 시점 스냅샷 → 마지막 테스트에서 재비교.
_GUARDED_REAL_FILES = (
    REAL_PRIVATE / "professor_items" / "generated" / "set_1.json",
    REAL_PRIVATE / "professor_items" / "generated" / "set_2.json",
    REAL_PRIVATE / "professor_items" / "generated" / "set_3.json",
    REAL_PRIVATE / "professor_items" / "generated" / "set_4.json",
    REAL_PRIVATE / "professor_items" / "review" / "faculty_edits.jsonl",
    REAL_PRIVATE / "professor_items" / "review" / "item_actions.json",
    REAL_PRIVATE / "student" / "qbank.json",
    REAL_PRIVATE / "student" / "signup_requests.json",
    REAL_PRIVATE / "student" / "approved_accounts.json",
    REAL_PRIVATE / "learning_analytics" / "attempts.jsonl",
)


def _snapshot(paths=_GUARDED_REAL_FILES) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for path in paths:
        out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    return out


# 모듈 첫 테스트 직전에 채워진다(수집 시점이 아니라 실행 시점 — 다른 테스트 파일의 영향 배제).
_REAL_SNAPSHOT_AT_MODULE_START: dict[str, str | None] = {}

OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "owner-password-for-tests"
ROSTER_SECRET = "test-roster-secret-2026"


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _real_data_guard():
    _REAL_SNAPSHOT_AT_MODULE_START.update(_snapshot())
    yield
    assert _snapshot() == _REAL_SNAPSHOT_AT_MODULE_START, "실데이터(data_private/)가 테스트 중 변경되었다"


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """모든 테스트에서 가입·배지·확정 저장 경로를 임시 디렉터리로 돌린다(실데이터 접근 0)."""
    student_dir = tmp_path / "student"
    generated = tmp_path / "generated"
    review = tmp_path / "review"
    curriculum = tmp_path / "curriculum"
    for d in (student_dir, generated, review, curriculum):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv(sr.SIGNUP_REQUESTS_PATH_ENV, str(student_dir / "signup_requests.json"))
    monkeypatch.setenv(sr.APPROVED_ACCOUNTS_PATH_ENV, str(student_dir / "approved_accounts.json"))
    monkeypatch.setenv(tb.ENV_GENERATED_DIR, str(generated))
    monkeypatch.setenv(tb.ENV_ITEM_ACTIONS_PATH, str(review / "item_actions.json"))
    monkeypatch.setattr(fa, "GENERATED_DIR", generated)
    monkeypatch.setattr(fa, "REVIEW_DIR", review)
    monkeypatch.setattr(fa, "EVIDENCE_ROUTING_PATH", curriculum / "evidence_routing.json")
    monkeypatch.setattr(api_server, "STUDENT_QBANK_PATH", student_dir / "qbank.json")
    monkeypatch.setattr(api_server, "LEARNING_ANALYTICS_DIR", tmp_path / "analytics")
    monkeypatch.setattr(api_server, "ATTEMPTS_LOG_PATH", tmp_path / "analytics" / "attempts.jsonl")
    # enrichment release는 실 qbank checksum에 게이트되어 있어 실파일을 읽게 되므로 함께 격리한다(읽기 전용이지만 결정성 확보).
    monkeypatch.setattr(qbank_enrichment, "RELEASES_PATH", student_dir / "qbank_enrichment.releases.json")
    monkeypatch.setattr(qbank_enrichment, "QBANK_PATH", student_dir / "qbank.json")

    sr._approved_email_snapshot.cache_clear()
    tb.clear_caches()
    fa.clear_caches()
    api_server.load_student_qbank.cache_clear()
    api_server._signup_hits.clear()   # 공개 가입 속도 제한 카운터(프로세스 전역)
    yield
    sr._approved_email_snapshot.cache_clear()
    tb.clear_caches()
    fa.clear_caches()
    api_server.load_student_qbank.cache_clear()


@pytest.fixture
def local_dev_mode(monkeypatch: pytest.MonkeyPatch):
    """게이트 비활성(로컬 개발): paccine_role 쿠키로 역할을 정한다(test_axioma_studio_api 패턴)."""
    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", "")
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", "")
    monkeypatch.setattr(api_server, "_ROSTER_EMAILS", frozenset())
    monkeypatch.setattr(api_server, "_ROSTER_SECRET", "")
    assert not api_server._auth_gate_enabled()


@pytest.fixture
def deployed_gate(monkeypatch: pytest.MonkeyPatch):
    """배포 게이트: 허용 계정(교수) 1개 + 로스터 시크릿만 있고 APP_ROSTER_EMAILS는 비어 있다."""
    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", OWNER_EMAIL)
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", OWNER_PASSWORD)
    monkeypatch.setattr(api_server, "_FACULTY_EMAILS", frozenset({OWNER_EMAIL}))
    monkeypatch.setattr(api_server, "_ROSTER_EMAILS", frozenset())
    monkeypatch.setattr(api_server, "_ROSTER_SECRET", ROSTER_SECRET)
    monkeypatch.setattr(api_server, "_SESSION_SECRET", "test-session-secret-" * 3)
    monkeypatch.setattr(api_server, "_COOKIE_SECURE", False)
    assert api_server._auth_gate_enabled()


def _faculty_client_local() -> TestClient:
    client = TestClient(api_server.app)
    client.cookies.set("paccine_role", "faculty")
    return client


def _login(client: TestClient, email: str, password: str, role: str = "student"):
    return client.post("/api/auth/login", json={"email": email, "password": password, "role": role})


def _owner_faculty_client() -> TestClient:
    client = TestClient(api_server.app)
    response = _login(client, OWNER_EMAIL, OWNER_PASSWORD, role="faculty")
    assert response.status_code == 200 and response.json()["role"] == "faculty"
    return client


def _signup(client: TestClient, email: str, name: str = "홍길동", student_id: str = "202412345", note: str = ""):
    return client.post(
        "/api/auth/signup",
        json={"name": name, "student_id": student_id, "email": email, "note": note},
    )


# 합성 생성 문항(원본 기출 텍스트 없음) — 계약 §B/§C 공용
def _item(no: int, subject: str, **extra) -> dict:
    item = {
        "no": no,
        "mgmt_no": f"M-{no:02d}",
        "subject": subject,
        "concept": f"concept_{no}",
        "axis": "진단",
        "stem": f"{40 + no}세 남자가 3일 전부터 열이 나서 왔다. 가장 가능성 있는 진단은?",
        "lab_box": "",
        "image": "",
        "choices": {"1": "진단 가", "2": "진단 나", "3": "진단 다", "4": "진단 라", "5": "진단 마"},
        "answer": "2",
        "explanation": "정답 근거 해설.",
        "harrison_sources": [
            {"source_id": "H10", "chapter": 10, "printed_page": 100, "entailment_status": "partially_supported"}
        ],
        "choice_explanations": {
            "1": {"why_attractive": "a"},
            "2": {"why_correct": "b"},
            "3": {"why_attractive": "c"},
            "4": {"why_attractive": "d"},
            "5": {"why_attractive": "e"},
        },
        "item_quality": {"hard_rule_failures": [], "manual_review_rules": list(fa.MANUAL_REVIEW_RULES_DEFAULT)},
        "needs_review": True,
        "entailment_verdict": "partially",
    }
    item.update(extra)
    return item


def _review(no: int, who: str, scores, verdict: str, note: str = "") -> dict:
    return {"no": no, "who": who, "scores": list(scores), "verdict": verdict, "note": note}


@pytest.fixture
def synthetic_sets(tmp_path: Path) -> fa.AdjudicationPaths:
    """set_1(2문항)·set_2(2문항) + 리뷰 JSON + 코딩 CSV + evidence_routing — 임시 디렉터리에만 쓴다."""
    paths = fa.AdjudicationPaths.resolve()
    assert REAL_PRIVATE not in paths.generated_dir.resolve().parents
    set_1 = [
        _item(1, "내과", v2_revision={"date": "2026-09-05", "fields": ["해설"], "log": ["해설 보강."]}),
        _item(2, "내과", professor_review_required=True, professor_note="이미지 교체 필요"),
    ]
    set_2 = [
        _item(1, "소아과", v2_revision={"date": "2026-09-05", "fields": ["문두", "정답"], "log": ["정답 1→2"]}),
        _item(2, "소아과"),
    ]
    paths.set_path(1).write_text(json.dumps(set_1, ensure_ascii=False, indent=1), encoding="utf-8")
    paths.set_path(2).write_text(json.dumps(set_2, ensure_ascii=False, indent=1), encoding="utf-8")
    reviews = [
        _review(1, "01", (5, 5, 5), "수정없이 사용"),
        _review(1, "02", (5, 4, 5), "수정없이 사용"),
        _review(1, "03", (5, 5, 4), "수정없이 사용"),
        _review(2, "01", (5, 5, 5), "수정없이 사용"),
        _review(2, "02", (1, 2, 1), "사용 불가", "정답이 없는 문제"),
        _review(2, "03", (4, 4, 4), "소폭 수정하여 사용"),
        _review(81, "04", (3, 1, 2), "대폭 수정 필요", "정답 이의"),
        _review(81, "05", (4, 4, 4), "소폭 수정하여 사용"),
        _review(81, "06", (5, 5, 5), "수정없이 사용"),
        _review(82, "04", (5, 5, 5), "수정없이 사용"),
        _review(82, "05", (3, 3, 3), "수정없이 사용"),
        _review(82, "06", (5, 5, 5), "수정없이 사용"),
    ]
    paths.reviews_path.write_text(json.dumps(reviews, ensure_ascii=False), encoding="utf-8")
    paths.comments_path.write_text(
        "﻿global_no,who,subject,image,note,primary_theme,all_themes\n"
        "2,02,내과,0,정답이 없는 문제,T9,T9;T6\n",
        encoding="utf-8",
    )
    paths.evidence_routing_path.write_text(
        json.dumps(
            {
                "schema": "paccine.evidence_routing.v1",
                "books": {
                    "harrison_22e": {"title": "Harrison 22e", "index": "x"},
                    "nelson_21e": {"title": "Nelson 21e", "index": "y"},
                },
                "routes": {"내과": ["harrison_22e"], "소아과": ["nelson_21e", "harrison_22e"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # 학생 배지용 조치 캐시(계약 §C): 1=그대로, 2=폐기, 81=수정필요 (82는 미검토)
    Path(tb._resolve_path(None, tb.ENV_ITEM_ACTIONS_PATH, tb.ITEM_ACTIONS_PATH)).write_text(
        json.dumps({"1": "그대로", "2": "폐기", "81": "수정필요"}), encoding="utf-8"
    )
    fa.clear_caches()
    tb.clear_caches()
    return paths


def _read_edits(paths: fa.AdjudicationPaths) -> list[dict]:
    if not paths.edits_path.exists():
        return []
    return [json.loads(line) for line in paths.edits_path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# §A. 가입 신청 → 교수 승인 → 승인 계정 로그인 (배포 게이트, 로스터 env 없음)
# ---------------------------------------------------------------------------
def test_signup_approve_login_flow_with_deployed_gate(deployed_gate):
    public = TestClient(api_server.app)

    # 공개 경로: 세션 없이 접수된다(_AUTH_PUBLIC_PATHS). 이메일은 정규화된다.
    submitted = _signup(public, "  Hong@Pusan.AC.KR ", note="본3")
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["status"] == "pending" and len(body["request_id"]) == 12 and body["submitted_at"]
    request_id = body["request_id"]

    assert _signup(public, "hong@pusan.ac.kr").status_code == 409          # 중복 이메일
    assert _signup(public, "no-name@pusan.ac.kr", name="").status_code == 400
    assert public.get("/api/faculty/signups").status_code == 401          # 세션 없음 → 게이트 차단

    # 승인 전에는 승인 계정으로 로그인할 수 없다.
    pending_login = _login(TestClient(api_server.app), "hong@pusan.ac.kr", "anything")
    assert pending_login.status_code == 401

    faculty = _owner_faculty_client()
    listed = faculty.get("/api/faculty/signups", params={"status": "pending"})
    assert listed.status_code == 200, listed.text
    assert listed.json()["counts"] == {"pending": 1, "approved": 0, "rejected": 0}
    (item,) = listed.json()["items"]
    assert item["request_id"] == request_id and item["email"] == "hong@pusan.ac.kr" and item["note"] == "본3"
    assert faculty.get("/api/faculty/signups", params={"status": "bogus"}).status_code == 400
    assert faculty.post("/api/faculty/signups/000000000000/approve", json={}).status_code == 404

    approved = faculty.post(f"/api/faculty/signups/{request_id}/approve", json={"note": "확인"})
    assert approved.status_code == 200, approved.text
    creds = approved.json()
    assert creds["status"] == "approved" and creds["login_email"] == "hong@pusan.ac.kr"
    # 비밀번호는 서버 미저장, 기존 로스터 HMAC 규칙(derive_roster_password)으로 파생
    assert creds["initial_password"] == api_server.derive_roster_password("hong@pusan.ac.kr", ROSTER_SECRET)
    assert len(creds["initial_password"]) == 8
    accounts = json.loads(Path(os.environ[sr.APPROVED_ACCOUNTS_PATH_ENV]).read_text(encoding="utf-8"))
    assert "initial_password" not in json.dumps(accounts)
    assert faculty.get("/api/faculty/signups", params={"status": "pending"}).json()["items"] == []
    decided = faculty.get("/api/faculty/signups", params={"status": "approved"}).json()["items"][0]
    assert decided["decided_by"] == f"faculty:{OWNER_EMAIL}" and decided["decided_at"]

    # 승인 계정 로그인: 로스터 env(APP_ROSTER_EMAILS)가 비어 있어도 approved_accounts만으로 통과
    student = TestClient(api_server.app)
    assert _login(student, "hong@pusan.ac.kr", "wrong-password").status_code == 401
    ok = _login(student, "Hong@pusan.ac.kr", creds["initial_password"])
    assert ok.status_code == 200, ok.text
    assert ok.json()["ok"] is True and ok.json()["role"] == "student" and ok.json()["redirect_to"] == "/student/"
    # 세션이 미들웨어를 통과하고(학생 경로) 교수 경로는 403
    assert student.get("/api/models").status_code == 200
    assert student.get("/api/faculty/signups").status_code == 403
    # 승인 계정은 body로 faculty를 요구해도 학생으로만 들어온다
    again = _login(TestClient(api_server.app), "hong@pusan.ac.kr", creds["initial_password"], role="faculty")
    assert again.status_code == 200 and again.json()["role"] == "student"

    # 반려(승인 취소) → 로그인 불가 + 기존 세션도 즉시 차단
    rejected = faculty.post(f"/api/faculty/signups/{request_id}/reject", json={"reason": "학번 불일치"})
    assert rejected.status_code == 200 and rejected.json() == {"request_id": request_id, "status": "rejected"}
    assert _login(TestClient(api_server.app), "hong@pusan.ac.kr", creds["initial_password"]).status_code == 401
    assert student.get("/api/models").status_code == 401
    # 반려 후 재신청 허용
    assert _signup(public, "hong@pusan.ac.kr").status_code == 200


def test_bulk_approve_and_env_roster_still_works(deployed_gate, monkeypatch):
    public = TestClient(api_server.app)
    ids = [_signup(public, f"s{i}@pusan.ac.kr", student_id=str(i)).json()["request_id"] for i in range(3)]
    faculty = _owner_faculty_client()
    first = faculty.post(f"/api/faculty/signups/{ids[0]}/approve", json={})
    assert first.status_code == 200

    result = faculty.post("/api/faculty/signups/bulk-approve", json={"request_ids": [ids[0], ids[1], ids[2], "nope"]})
    assert result.status_code == 200, result.text
    payload = result.json()
    assert [row["login_email"] for row in payload["approved"]] == ["s1@pusan.ac.kr", "s2@pusan.ac.kr"]
    assert all(row["initial_password"] == api_server.derive_roster_password(row["login_email"]) for row in payload["approved"])
    assert payload["skipped"] == [
        {"request_id": ids[0], "reason": "already_approved"},
        {"request_id": "nope", "reason": "not_found"},
    ]
    assert faculty.post("/api/faculty/signups/bulk-approve", json={"request_ids": "x"}).status_code == 400
    assert faculty.get("/api/faculty/signups", params={"status": "all"}).json()["counts"] == {
        "pending": 0, "approved": 3, "rejected": 0,
    }

    # 기존 동작 불변: env 로스터 이메일은 approved_accounts 없이도 같은 규칙으로 로그인된다.
    monkeypatch.setattr(api_server, "_ROSTER_EMAILS", frozenset({"roster@pusan.ac.kr"}))
    roster = _login(TestClient(api_server.app), "roster@pusan.ac.kr", api_server.derive_roster_password("roster@pusan.ac.kr"))
    assert roster.status_code == 200 and roster.json()["role"] == "student"
    # 시크릿이 없으면 승인 계정이어도 로그인 불가(파생 불가 → fail-closed)
    monkeypatch.setattr(api_server, "_ROSTER_SECRET", "")
    assert _login(TestClient(api_server.app), "s1@pusan.ac.kr", "ABCDEFGH").status_code == 401


def test_signup_endpoints_in_local_dev_mode(local_dev_mode):
    public = TestClient(api_server.app)
    rid = _signup(public, "local@pusan.ac.kr").json()["request_id"]
    assert public.get("/api/faculty/signups").status_code == 403          # 학생 workspace 차단
    faculty = _faculty_client_local()
    assert faculty.get("/api/faculty/signups").json()["counts"]["pending"] == 1
    approved = faculty.post(f"/api/faculty/signups/{rid}/approve")        # body 생략 허용
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert approved.json()["initial_password"] == ""                        # 시크릿 없음 → 빈 문자열(미설정)
    assert faculty.get("/api/faculty/signups", params={"status": "approved"}).json()["items"][0]["decided_by"] == "faculty:local-reviewer"


# ---------------------------------------------------------------------------
# §B. 교수 문항 확정 + 편집
# ---------------------------------------------------------------------------
def test_adjudication_requires_faculty(local_dev_mode, synthetic_sets):
    student = TestClient(api_server.app)
    for method, path in (
        ("GET", "/api/faculty/adjudication/queue"),
        ("GET", "/api/faculty/adjudication/summary"),
        ("GET", "/api/faculty/adjudication/items/AIGEN_1_001"),
        ("PUT", "/api/faculty/adjudication/items/AIGEN_1_001"),
        ("POST", "/api/faculty/adjudication/items/AIGEN_1_001/decision"),
    ):
        response = student.request(method, path, json={"explanation": "x", "decision": "approve"})
        assert response.status_code == 403, (method, path, response.text)


def test_adjudication_queue_get_put_decision_summary(local_dev_mode, synthetic_sets):
    paths = synthetic_sets
    faculty = _faculty_client_local()

    queue = faculty.get("/api/faculty/adjudication/queue")
    assert queue.status_code == 200, queue.text
    body = queue.json()
    assert body["filter"] == "all"
    assert [e["qid"] for e in body["items"]] == ["AIGEN_2_001", "AIGEN_1_002", "AIGEN_2_002", "AIGEN_1_001"]
    assert [e["priority_label"] for e in body["items"]] == ["정답변경", "폐기", "검토자불일치", "기타"]
    first = body["items"][0]
    assert first["global_no"] == 81 and first["review"]["action"] == "수정필요" and first["answer_changed"] is True
    assert first["badge"]["entailment_verdict"] == "partially" and first["badge"]["sources"]
    assert body["counts"]["all"] == 4 and body["counts"]["decided"] == 0
    assert faculty.get("/api/faculty/adjudication/queue", params={"filter": "discard"}).json()["items"][0]["qid"] == "AIGEN_1_002"
    assert faculty.get("/api/faculty/adjudication/queue", params={"filter": "bogus"}).status_code == 400

    item = faculty.get("/api/faculty/adjudication/items/AIGEN_1_002")
    assert item.status_code == 200, item.text
    detail = item.json()
    assert detail["qid"] == "AIGEN_1_002" and detail["global_no"] == 2 and detail["choices"]["2"] == "진단 나"
    assert detail["professor_review_required"] is True and detail["edit_history"] == []
    assert {b["book_id"] for b in detail["available_books"]} == {"harrison_22e", "nelson_21e"}
    assert detail["recommended_book_ids"] == ["harrison_22e"]
    assert any(c["note"] == "정답이 없는 문제" for c in detail["review"]["comments"])
    assert faculty.get("/api/faculty/adjudication/items/AIGEN_9_001").status_code == 404
    assert faculty.get("/api/faculty/adjudication/items/HEME-001").status_code == 404

    # PUT: 허용 필드만, 변경 필드만 이력, editor는 가드가 준 identity
    edited = faculty.put(
        "/api/faculty/adjudication/items/AIGEN_1_002",
        json={"explanation": "교수 수정 해설.", "answer": "2", "textbook_sources": [{"book_id": "harrison_22e", "chapter": 12}]},
    )
    assert edited.status_code == 200, edited.text
    saved = edited.json()
    assert saved["saved"] is True and sorted(saved["changed_fields"]) == ["explanation", "textbook_sources"]
    assert set(saved["gate"]) >= {"failed_rules", "manual_review_rules", "passed_count", "total_count"}
    assert saved["item"]["faculty_edited"] is True and saved["item"]["faculty_edited_at"] == saved["faculty_edited_at"]
    assert saved["item"]["explanation"] == "교수 수정 해설."
    edits = _read_edits(paths)
    assert {e["field"] for e in edits} == {"explanation", "textbook_sources"}
    assert all(e["editor"] == "faculty:local-reviewer" and e["qid"] == "AIGEN_1_002" for e in edits)
    stored = json.loads(paths.set_path(1).read_text(encoding="utf-8"))
    assert stored[1]["explanation"] == "교수 수정 해설." and stored[0]["explanation"] == "정답 근거 해설."
    assert faculty.put("/api/faculty/adjudication/items/AIGEN_1_002", json={"stem": "x", "no": 9}).status_code == 400
    assert faculty.put("/api/faculty/adjudication/items/AIGEN_1_002", json={}).status_code == 400
    assert faculty.put("/api/faculty/adjudication/items/AIGEN_9_001", json={"stem": "x"}).status_code == 404
    unchanged = faculty.put("/api/faculty/adjudication/items/AIGEN_1_002", json={"explanation": "교수 수정 해설."})
    assert unchanged.status_code == 200 and unchanged.json()["saved"] is False and "item" not in unchanged.json()

    # 결정: approve → professor_review_required 해제 + medical_approval 스탬프
    decision = faculty.post("/api/faculty/adjudication/items/AIGEN_1_002/decision", json={"decision": "approve", "note": "확정"})
    assert decision.status_code == 200, decision.text
    assert decision.json()["medical_approval"] is True and decision.json()["professor_review_required"] is False
    assert decision.json()["faculty_decision"]["by"] == "faculty:local-reviewer"
    discard = faculty.post("/api/faculty/adjudication/items/AIGEN_2_001/decision", json={"decision": "discard"})
    assert discard.status_code == 200 and discard.json()["medical_approval"] is False
    assert faculty.post("/api/faculty/adjudication/items/AIGEN_1_001/decision", json={"decision": "maybe"}).status_code == 400
    assert faculty.post("/api/faculty/adjudication/items/AIGEN_9_001/decision", json={"decision": "approve"}).status_code == 404
    stored = json.loads(paths.set_path(1).read_text(encoding="utf-8"))
    assert stored[1]["medical_approval"] is True and "professor_review_required" not in stored[1]

    summary = faculty.get("/api/faculty/adjudication/summary")
    assert summary.status_code == 200, summary.text
    totals = summary.json()
    assert totals["total"] == 4 and totals["decided"] == {"approve": 1, "revise": 0, "discard": 1} and totals["pending"] == 2
    assert totals["answer_changed"] == 1 and totals["faculty_edited"] == 1 and totals["medical_approved"] == 1
    # summary 확장(2026-09-06, F3 리포트): 세트별 같은 모양의 분포 + 7지표 정적 파일
    assert [(row["set"], row["items"]) for row in totals["sets"]] == [(1, 2), (2, 2)]
    set_1, set_2 = totals["sets"]
    assert set_1["decided"] == {"approve": 1, "revise": 0, "discard": 0} and set_1["pending"] == 1
    assert set_2["decided"] == {"approve": 0, "revise": 0, "discard": 1} and set_2["answer_changed"] == 1
    assert set_1["review_actions"] == {"그대로": 1, "경미": 0, "수정필요": 0, "폐기": 1}
    assert set_2["review_actions"] == {"그대로": 0, "경미": 1, "수정필요": 1, "폐기": 0}
    assert totals["review_actions"] == {"그대로": 1, "경미": 1, "수정필요": 1, "폐기": 1}
    assert totals["entailment"] == {"fully": 0, "partially": 4, "not": 0, "unknown": 0}
    assert totals["axis"] == {"진단": 4} and totals["cognitive_level"] == {"미기재": 4}
    # 점수범위≥2 = 문항 2(1~5)·81(1~5)·82(3~5) → 불일치 3
    assert totals["lab_box"] == 0 and totals["image"] == 0 and totals["disagreement"] == 3 and totals["unreviewed"] == 0
    assert totals["quality_metrics"] == {"metrics": [], "source": None, "measured_at": None}   # 파일 없음 → 빈 목록
    paths.quality_metrics_path.write_text(
        json.dumps({"source": "unit", "measured_at": "2026-09-06", "metrics": [
            {"key": "answer_accuracy", "name": "정답 정확도", "value": 89.7, "baseline": 95, "op": ">="},
            {"key": "duplication", "name": "중복률", "value": 5.6, "baseline": 10, "op": "<=", "note": "n"},
            {"key": "broken", "name": "값 없음"},
        ]}, ensure_ascii=False), encoding="utf-8")
    metrics = faculty.get("/api/faculty/adjudication/summary").json()["quality_metrics"]
    assert metrics["source"] == "unit" and metrics["measured_at"] == "2026-09-06"
    assert [(m["key"], m["pass"]) for m in metrics["metrics"]] == [("answer_accuracy", False), ("duplication", True)]
    assert faculty.get("/api/faculty/adjudication/queue").json()["counts"]["decided"] == 2


# ---------------------------------------------------------------------------
# §C. 학생 답안 페이로드 신뢰 배지
# ---------------------------------------------------------------------------
def _qbank_question(qid: str, **extra) -> dict:
    question = {
        "id": qid,
        "exam": "임상종합평가 · 합성",
        "qtype": "single",
        "stem": "45세 남자가 열로 왔다. 가장 가능성 있는 진단은?",
        "choices": [{"n": str(n), "text": f"진단 {n}", "expl": f"선지 {n} 해설"} for n in range(1, 6)],
        "answer": "2",
        "explanation": "서버 해설",
        "points": ["핵심"],
        "imgs": [],
        "anki_cards": [{"front": "앞", "back": "뒤"}],
    }
    question.update(extra)
    return question


@pytest.fixture
def student_qbank(synthetic_sets):
    payload = {"questions": [_qbank_question("AIGEN_1_001"), _qbank_question("AIGEN_1_002"), _qbank_question("AIGEN_2_002"), _qbank_question("Q-LEGACY-1")]}
    api_server.STUDENT_QBANK_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    api_server.load_student_qbank.cache_clear()
    return payload


def _answer(client: TestClient, qid: str):
    return client.post(f"/api/student/questions/{qid}/answer", json={"selected_choices": ["2"]})


def test_student_answer_payload_carries_trust_badges(local_dev_mode, student_qbank):
    student = TestClient(api_server.app)
    response = _answer(student, "AIGEN_1_001")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_correct"] is True and body["status"] == "saved"
    # 기존 필드 유지
    assert body["anki_cards"] == [{"front": "앞", "back": "뒤"}]
    assert body["choice_explanations"]["2"] == "선지 2 해설"
    # 계약 §C 블록
    assert body["trust_badges"] == {
        "evidence_verified": {"level": "partially", "label": "교과서 근거 검증", "mark": "△"},
        "student_reviewed": {"label": "졸업반 3인 검토 통과"},
        "faculty_approved": False,
    }
    assert body["evidence"] == {
        "locators": ["Harrison 22e Ch.10 p.100"],
        "badge": {"level": "partially", "label": "교과서 근거 검증", "mark": "△"},
    }
    assert body["revision_note"] == {"date": "2026-09-05", "summary": "해설 보강.", "fields": ["해설"], "answer_changed": False}

    # 폐기 조치 → student_reviewed 미표시, 수정 이력 없음 → revision_note None
    second = _answer(student, "AIGEN_1_002").json()
    assert second["trust_badges"]["student_reviewed"] is None and second["revision_note"] is None
    # 조치 캐시에 없는 문항 → 미검토(None), 배지 나머지는 정상
    third = _answer(student, "AIGEN_2_002").json()
    assert third["trust_badges"]["student_reviewed"] is None and third["trust_badges"]["evidence_verified"]["level"] == "partially"
    # 시도 로그는 임시 디렉터리에만 남는다
    assert api_server.ATTEMPTS_LOG_PATH.exists() and REAL_PRIVATE not in api_server.ATTEMPTS_LOG_PATH.resolve().parents


def test_public_catalog_carries_tier_and_pre_answer_badges(local_dev_mode, student_qbank):
    """공개 문항 허용목록: difficulty_tier(하/중/상만, 그 외 None) + 답 전 안전 배지(정답·해설·근거 위치 없음)."""
    student = TestClient(api_server.app)
    payload = student_qbank
    payload["questions"][0]["difficulty_tier"] = "중"
    payload["questions"][1]["difficulty_tier"] = "매우어려움"   # 허용 밖 → None
    api_server.STUDENT_QBANK_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    api_server.load_student_qbank.cache_clear()
    catalog = student.get("/api/student/qbank")
    assert catalog.status_code == 200, catalog.text
    by_id = {q["id"]: q for q in catalog.json()["questions"]}
    assert by_id["AIGEN_1_001"]["difficulty_tier"] == "중" and by_id["AIGEN_1_002"]["difficulty_tier"] is None
    assert by_id["AIGEN_1_001"]["trust_badges"]["evidence_verified"]["level"] == "partially"
    assert by_id["AIGEN_1_001"]["trust_badges"]["student_reviewed"] == {"label": "졸업반 3인 검토 통과"}
    assert by_id["AIGEN_1_002"]["trust_badges"]["student_reviewed"] is None            # 폐기 조치
    assert by_id["Q-LEGACY-1"]["trust_badges"] is None and by_id["Q-LEGACY-1"]["difficulty_tier"] is None
    for question in by_id.values():                                                    # 답 전 유출 없음
        assert "answer" not in question and "explanation" not in question and "evidence" not in question and "revision_note" not in question
    # 교수 승인 → 카탈로그 캐시 키(생성 세트 서명)가 바뀌어 다음 조회에서 즉시 반영
    etag = catalog.headers["etag"]
    faculty = _faculty_client_local()
    assert faculty.post("/api/faculty/adjudication/items/AIGEN_1_001/decision", json={"decision": "approve"}).status_code == 200
    refreshed = student.get("/api/student/qbank", headers={"if-none-match": etag})
    assert refreshed.status_code == 200 and refreshed.headers["etag"] != etag
    assert {q["id"]: q for q in refreshed.json()["questions"]}["AIGEN_1_001"]["trust_badges"]["faculty_approved"] is True


def test_faculty_approve_decision_turns_on_student_badge(local_dev_mode, student_qbank):
    student = TestClient(api_server.app)
    assert _answer(student, "AIGEN_1_002").json()["trust_badges"]["faculty_approved"] is False
    faculty = _faculty_client_local()
    assert faculty.post("/api/faculty/adjudication/items/AIGEN_1_002/decision", json={"decision": "approve"}).status_code == 200
    body = _answer(student, "AIGEN_1_002").json()
    assert body["trust_badges"]["faculty_approved"] is True
    # 교수 편집(교과서 근거 추가)도 학생 evidence에 즉시 반영된다(파일 서명 캐시 무효화)
    assert faculty.put(
        "/api/faculty/adjudication/items/AIGEN_1_002",
        json={"textbook_sources": [{"book_id": "nelson_21e", "chapter": 5}]},
    ).status_code == 200
    assert _answer(student, "AIGEN_1_002").json()["evidence"]["locators"] == ["Harrison 22e Ch.10 p.100", "Nelson 21e Ch.5"]


def test_faculty_edits_and_discard_reach_student_qbank(local_dev_mode, student_qbank):
    """감사 2026-09-05 blocker: 콘솔 편집(정답·문두)이 학생 채점에 닿지 않고, 폐기가 학생 큐에서 빠지지 않던 결함."""
    student = TestClient(api_server.app)
    faculty = _faculty_client_local()
    before = student.get("/api/student/qbank")
    assert before.status_code == 200
    original = {q["id"]: q for q in before.json()["questions"]}["AIGEN_1_001"]
    assert original["stem"] == "45세 남자가 열로 왔다. 가장 가능성 있는 진단은?" and original["practice_ready"] is True

    # 콘솔에서 정답 2→3, 문두 수정 (set_1.json 만 갱신되는 PUT)
    edited = faculty.put(
        "/api/faculty/adjudication/items/AIGEN_1_001",
        json={"answer": "3", "stem": "교수가 고친 문두. 가장 가능성 있는 진단은?"},
    )
    assert edited.status_code == 200, edited.text
    assert sorted(edited.json()["changed_fields"]) == ["answer", "stem"]

    # 카탈로그: 재발행 없이 편집본 노출 + ETag 갱신
    after = student.get("/api/student/qbank", headers={"if-none-match": before.headers["etag"]})
    assert after.status_code == 200 and after.headers["etag"] != before.headers["etag"]
    shown = {q["id"]: q for q in after.json()["questions"]}["AIGEN_1_001"]
    assert shown["stem"] == "교수가 고친 문두. 가장 가능성 있는 진단은?"
    assert "answer" not in shown and "faculty_status" not in shown        # 허용목록 유지(내부 필드 비노출)
    # 채점: 옛 정답 2는 오답, 새 정답 3이 정답 — 응답의 개정 이력에 교수 수정이 표시된다
    wrong = _answer(student, "AIGEN_1_001").json()
    assert wrong["is_correct"] is False and wrong["answer_keys"] == ["3"]
    right = student.post("/api/student/questions/AIGEN_1_001/answer", json={"selected_choices": ["3"]}).json()
    assert right["is_correct"] is True
    assert right["revision_note"]["answer_changed"] is True and "정답" in right["revision_note"]["fields"] and "문두" in right["revision_note"]["fields"]
    assert right["revision_note"]["summary"].startswith("해설 보강.")      # v2 이력 + 교수 편집 병합

    # 폐기 결정 → 학생 큐 제외(practice_ready False) + 답안 409 + 준비 문항 수 감소
    ready_before = after.json()["practice_ready_count"]
    assert faculty.post("/api/faculty/adjudication/items/AIGEN_1_002/decision", json={"decision": "discard"}).status_code == 200
    catalog = student.get("/api/student/qbank").json()
    discarded = {q["id"]: q for q in catalog["questions"]}["AIGEN_1_002"]
    assert discarded["practice_ready"] is False and discarded["readiness_reason"] == "faculty_discarded"
    assert catalog["practice_ready_count"] == ready_before - 1
    assert _answer(student, "AIGEN_1_002").status_code == 409
    # 되돌리기(수정 지시)면 다시 학생 큐로
    assert faculty.post("/api/faculty/adjudication/items/AIGEN_1_002/decision", json={"decision": "revise"}).status_code == 200
    assert {q["id"]: q for q in student.get("/api/student/qbank").json()["questions"]}["AIGEN_1_002"]["practice_ready"] is True


def test_signup_queue_cap_and_rate_limit(local_dev_mode, monkeypatch):
    public = TestClient(api_server.app)
    monkeypatch.setenv(sr.MAX_PENDING_ENV, "2")
    assert _signup(public, "a@pusan.ac.kr").status_code == 200
    assert _signup(public, "b@pusan.ac.kr").status_code == 200
    full = _signup(public, "c@pusan.ac.kr")
    assert full.status_code == 503 and "대기열" in full.json()["detail"]
    # 승인으로 대기가 줄면 다시 접수된다
    faculty = _faculty_client_local()
    pending = faculty.get("/api/faculty/signups", params={"status": "pending"}).json()["items"]
    assert faculty.post(f"/api/faculty/signups/{pending[0]['request_id']}/approve", json={}).status_code == 200
    assert _signup(public, "c@pusan.ac.kr").status_code == 200

    # 같은 클라이언트의 연속 신청은 창 안에서 N회로 제한(429). 한도 초과 시 저장소는 건드리지 않는다.
    monkeypatch.setenv(sr.MAX_PENDING_ENV, "1000")
    monkeypatch.setattr(api_server, "_SIGNUP_RATE_LIMIT", 5)
    api_server._signup_hits.clear()
    codes = [_signup(public, f"burst{i}@pusan.ac.kr").status_code for i in range(7)]
    assert codes == [200, 200, 200, 200, 200, 429, 429]
    assert not api_server._signup_rate_limited("someone-else")
    counts = faculty.get("/api/faculty/signups", params={"status": "all"}).json()["counts"]
    assert counts["pending"] == 2 + 5 and counts["approved"] == 1


def test_faculty_source_text_is_faculty_only(local_dev_mode, synthetic_sets, tmp_path, monkeypatch):
    """원문 보기: 교수만 200, 학생 세션은 403, 없는 문항 404. 합성 쪽 인덱스(실 Harrison 텍스트 미접근)."""
    from src.services import textbook_evidence as te

    root = tmp_path / "harrison"
    root.mkdir()
    (root / te.PAGES_FILENAME).write_text(
        "\n".join(json.dumps(r) for r in [
            {"chapter": 10, "printed_page": 99, "pdf_page": 1, "segment_text": "before"},
            {"chapter": 10, "printed_page": 100, "pdf_page": 2, "segment_text": "Fever page: case-fatality rate is 1-2%."},
            {"chapter": 10, "printed_page": 101, "pdf_page": 3, "segment_text": "after"},
        ]) + "\n", encoding="utf-8")
    (root / te.CHAPTER_INDEX_FILENAME).write_text(json.dumps({"chapters": [{"chapter": 10, "filename_title": "Fever"}]}), encoding="utf-8")
    monkeypatch.setenv(te.ENV_HARRISON_DIR, str(root))
    te.clear_caches()

    faculty = _faculty_client_local()
    response = faculty.get("/api/faculty/adjudication/items/AIGEN_1_001/source-text")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["policy"] == "faculty_only_verification_excerpt"
    harrison = body["sources"][0]
    assert harrison["available"] is True and harrison["chapter_title"] == "Fever" and [p["printed_page"] for p in harrison["pages"]] == [99, 100, 101]
    assert next(p for p in harrison["pages"] if p["is_cited"])["text"].startswith("Fever page")
    kinds = [link["kind"] for link in body["library_links"]]
    assert kinds[0] in ("accessmedicine_chapter", "accessmedicine_topic_search") and "msd_professional_search" in kinds
    assert not any(link["url"].startswith("https://lproxy.pusan.ac.kr") for link in body["library_links"])
    assert faculty.get("/api/faculty/adjudication/items/AIGEN_1_001/source-text", params={"context": 0}).json()["sources"][0]["pages"][0]["printed_page"] == 100
    assert faculty.get("/api/faculty/adjudication/items/AIGEN_9_001/source-text").status_code == 404
    # 학생 세션(역할 쿠키 student)은 차단
    student = TestClient(api_server.app)
    student.cookies.set("paccine_role", "student")
    assert student.get("/api/faculty/adjudication/items/AIGEN_1_001/source-text").status_code in (401, 403)
    # 학생 카탈로그·답안 응답에는 원문 텍스트가 실리지 않는다
    te.clear_caches()


def test_attempt_schema_v2_and_attempt_summary(local_dev_mode, student_qbank):
    """2026-09-27: 답안 이벤트에 client_meta(모드·문항 단위 시간·티어)와 trust_snapshot이 남고, 문항별 시도 요약 API가 이를 집계한다."""
    student = TestClient(api_server.app)
    empty = student.get("/api/student/attempt-summary")
    assert empty.status_code == 200 and empty.json()["by_question"] == {} and empty.json()["attempt_count"] == 0

    first = student.post(
        "/api/student/questions/AIGEN_1_001/answer",
        json={"selected_choices": ["1"], "time_ms": 4200, "time_scope": "question", "mode": "exam", "schema_version": 2},
    )
    assert first.status_code == 200 and first.json()["is_correct"] is False
    second = student.post("/api/student/questions/AIGEN_1_001/answer", json={"selected_choices": ["2"], "time_ms": 3100})
    assert second.status_code == 200 and second.json()["is_correct"] is True

    events = [json.loads(line) for line in api_server.ATTEMPTS_LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(events) == 2
    assert events[0]["time_ms"] == 4200
    assert events[0]["client_meta"] == {"schema_version": 2, "mode": "exam", "time_scope": "question", "difficulty_tier": None, "review_pass": False}
    assert events[1]["client_meta"]["mode"] == "study" and events[1]["client_meta"]["time_scope"] == "session"   # 구 클라이언트 기본값
    assert events[0]["trust_snapshot"] == {"evidence_level": "partially", "student_reviewed": True, "faculty_approved": False, "faculty_status": "undecided"}

    summary = student.get("/api/student/attempt-summary").json()
    assert summary["attempt_count"] == 2 and summary["question_count"] == 1
    row = summary["by_question"]["AIGEN_1_001"]
    assert row["attempts"] == 2 and row["correct"] == 1 and row["last_correct"] is True and row["last_answered_at"]
    # 답 전 화면(홈·빌더)이 쓰는 API — 키 화이트리스트로 정답·해설 유출을 막는다
    assert set(summary) == {"user_id", "question_count", "attempt_count", "by_question"}
    assert set(row) == {"attempts", "correct", "last_correct", "last_answered_at"}

    # 리포트 평균 풀이 시간은 문항 단위(time_scope=question) 표본만 쓴다 — 구 이벤트(세션 누적)는 섞지 않는다
    analytics = student.get("/api/practice/analytics/student").json()["summary"]
    assert analytics["avg_time_sample_count"] == 1 and analytics["avg_time_sec"] == 4.2 and analytics["avg_time_scope"] == "question"

    # 교수 승인 후의 시도는 스냅샷에 faculty_approved=True로 남는다(사후 분석용 시점 고정)
    faculty = _faculty_client_local()
    assert faculty.post("/api/faculty/adjudication/items/AIGEN_1_001/decision", json={"decision": "approve"}).status_code == 200
    student.post("/api/student/questions/AIGEN_1_001/answer", json={"selected_choices": ["2"]})
    latest = [json.loads(line) for line in api_server.ATTEMPTS_LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()][-1]
    assert latest["trust_snapshot"]["faculty_approved"] is True and latest["trust_snapshot"]["faculty_status"] == "approve"


def test_attempt_summary_isolated_between_accounts(deployed_gate, student_qbank):
    """배포 게이트: 승인 계정 A의 시도는 B의 attempt-summary·analytics에 보이지 않는다."""
    public = TestClient(api_server.app)
    faculty = _owner_faculty_client()
    clients = {}
    for email in ("a@pusan.ac.kr", "b@pusan.ac.kr"):
        request_id = _signup(public, email, student_id=email[:1]).json()["request_id"]
        creds = faculty.post(f"/api/faculty/signups/{request_id}/approve", json={}).json()
        client = TestClient(api_server.app)
        assert _login(client, email, creds["initial_password"]).status_code == 200
        clients[email] = client
    a, b = clients["a@pusan.ac.kr"], clients["b@pusan.ac.kr"]
    assert a.post("/api/student/questions/AIGEN_1_001/answer", json={"selected_choices": ["2"], "time_ms": 2500, "time_scope": "question"}).status_code == 200
    assert a.get("/api/student/attempt-summary").json()["by_question"]["AIGEN_1_001"]["attempts"] == 1
    other = b.get("/api/student/attempt-summary").json()
    assert other["by_question"] == {} and other["attempt_count"] == 0 and other["user_id"] == "b@pusan.ac.kr"
    assert b.get("/api/practice/analytics/student").json()["summary"]["attempt_count"] == 0
    # 세션 없이 호출하면 게이트가 막는다
    assert TestClient(api_server.app).get("/api/student/attempt-summary").status_code == 401


def test_student_answer_never_fails_on_badge_load(local_dev_mode, student_qbank, monkeypatch):
    student = TestClient(api_server.app)
    # AIGEN이 아닌 문항: 배지 None 폴백, 200
    legacy = _answer(student, "Q-LEGACY-1")
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["trust_badges"] is None and legacy.json()["revision_note"] is None
    assert legacy.json()["anki_cards"] == [{"front": "앞", "back": "뒤"}]

    # 배지 서비스가 예외를 던져도 학생 답안 API는 200 + None 폴백
    def _boom(*_args, **_kwargs):
        raise RuntimeError("badge store unavailable")

    original = tb.student_trust_payload
    monkeypatch.setattr(tb, "student_trust_payload", _boom)
    broken = _answer(student, "AIGEN_1_001")
    assert broken.status_code == 200, broken.text
    assert broken.json()["trust_badges"] is None and broken.json()["is_correct"] is True

    # 생성 파일이 없어도(디렉터리 비어 있음) 200
    monkeypatch.setattr(tb, "student_trust_payload", original)
    for path in fa.AdjudicationPaths.resolve().generated_dir.glob("set_*.json"):
        path.unlink()
    tb.clear_caches()
    missing = _answer(TestClient(api_server.app), "AIGEN_1_001")
    assert missing.status_code == 200 and missing.json()["trust_badges"] is None


# ---------------------------------------------------------------------------
# 가드: 실데이터 무변경 (파일 순서상 마지막에 실행)
# ---------------------------------------------------------------------------
def test_real_private_data_untouched():
    assert _REAL_SNAPSHOT_AT_MODULE_START and _snapshot() == _REAL_SNAPSHOT_AT_MODULE_START
