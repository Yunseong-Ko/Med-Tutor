"""학생 문항은행 감사기 회귀 + 안전 불변식 테스트.

- 감사기가 2026-07-23 실측 기준값을 재현하는지(스키마 이해 고정).
- 제출 전 payload(public_qbank_question)에 정답·해설·선지풀이·포인트가 없는지.
- 감사가 원본 qbank.json을 변경하지 않는지(checksum 불변).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

QBANK = ROOT / "data_private" / "student" / "qbank.json"
pytestmark = pytest.mark.skipif(not QBANK.exists(), reason="student qbank not present")

import audit_student_qbank as audit  # noqa: E402
import api_server  # noqa: E402

# 2026-08-17: 기존 278문항(교재 핸드오프분)을 전량 내리고, 온톨로지 grounding
# 파이프라인이 생성한 320문항으로 교체했다. 아래는 그 데이터셋의 실측 스냅샷이다.
BASELINE = {
    "total": 320,
    "explanation_present": 320,
    "explanation_missing": 0,
    "all_choice_explanations_complete": 320,
    "choice_explanations_present": 1600,
    "choice_explanations_total": 1600,
    "points_present": 320,
    "anki_present": 320,
    "axis_assigned": 320,
    "concept_linked": 313,
    # 2026-09-05 v2 수정 적용 재발행(modality 정정 11건 등)으로 시각자료 참조 문항 77→84. 코드 변경 아님(데이터 스냅샷 갱신).
    "requires_visual": 84,
    "media_connected": 120,
    "media_missing_blocked": 0,
    "practice_ready": 320,
}


def test_audit_reproduces_baseline():
    summary = audit.run_audit()["summary"]
    for key, expected in BASELINE.items():
        assert summary[key] == expected, f"{key}: {summary[key]} != {expected}"


def test_pre_answer_payload_hides_answer_explanation_choiceexpl_points():
    import json
    questions = json.loads(QBANK.read_text(encoding="utf-8"))["questions"]
    payload = api_server.public_qbank_question(questions[0])
    serialized = json.dumps(payload, ensure_ascii=False)
    # 제출 전 금지 필드
    assert "answer" not in payload
    assert "explanation" not in payload
    assert "points" not in payload
    # 선지에 정답 풀이(expl)가 실리면 안 됨
    for choice in payload.get("choices", []):
        assert set(choice.keys()) <= {"n", "text"}
        assert "expl" not in choice
    # 원문 정답 텍스트가 직렬화에 새지 않는지(첫 문항 정답 풀이 일부)
    ans_expl = next((c.get("expl") for c in questions[0]["choices"] if c.get("expl")), "")
    if ans_expl:
        assert ans_expl[:20] not in serialized


def test_audit_does_not_mutate_original_qbank():
    before = audit.sha256_of(QBANK)
    audit.run_audit()
    after = audit.sha256_of(QBANK)
    assert before == after


def test_worklists_cover_blocked_and_gaps(tmp_path, monkeypatch):
    # 미디어 워크리스트 = 미연결차단 수와 일치, enrichment는 gap 있는 문항만
    result = audit.run_audit()
    monkeypatch.setattr(audit, "ENRICH_WORKLIST", tmp_path / "enrich.jsonl")
    monkeypatch.setattr(audit, "MEDIA_WORKLIST", tmp_path / "media.jsonl")
    enrich, media = audit.emit_worklists(result)
    assert media == BASELINE["media_missing_blocked"]
    assert enrich == BASELINE["total"]  # 전 문항이 axis/anki 미할당


def test_overlay_never_merges_draft_and_gates_unapproved():
    from src.services import qbank_enrichment as qe

    base = {"id": "SYNTHETIC_Q001", "explanation": None, "answer": "2"}
    # 승인 안 된 release는 병합되지 않는다.
    unapproved = {"SYNTHETIC_Q001": {"explanation": "미승인 초안", "approved": False}}
    out = qe.apply_release_overlay(base, releases={} if not unapproved else {})
    assert out.get("explanation") is None
    assert out.get("ontology_analytics_approved") is False

    # 승인 release만 화이트리스트 필드를 덮어쓰고 Axis analytics를 연다.
    approved = {"SYNTHETIC_Q001": {
        "approved": True, "medical_approval": True,
        "demo_release": False, "needs_real_faculty_review": False,
        "explanation": "승인 해설", "target_axis_type": "diagnosis",
        "reviewer_id": "faculty:test", "reviewed_at": "2026-07-23T00:00:00Z",
    }}
    out2 = qe.apply_release_overlay(base, releases={k: v for k, v in approved.items() if v.get("approved")})
    assert out2["explanation"] == "승인 해설"
    assert out2["ontology_analytics_approved"] is True
    assert out2["enrichment_release"]["approved"] is True
    assert out2["enrichment_release"]["medical_approval"] is True


def test_demo_release_is_never_student_visible():
    from src.services import qbank_enrichment as qe

    demo = {"Q1": {
        "approved": True,
        "medical_approval": False,
        "demo_release": True,
        "needs_real_faculty_review": True,
        "reviewer_id": "demo:learning-loop-demo",
        "reviewed_at": "2026-07-23T00:00:00Z",
        "explanation": "시연용 미검수 해설",
    }}
    out = qe.apply_release_overlay({"id": "Q1", "explanation": ""}, releases=demo)
    assert out["explanation"] == ""
    assert out["ontology_analytics_approved"] is False


def test_answer_route_is_bound_to_submission_handler():
    routes = [
        route for route in api_server.app.routes
        if getattr(route, "path", "") == "/api/student/questions/{question_id}/answer"
    ]
    assert len(routes) == 1
    assert routes[0].endpoint is api_server.submit_student_qbank_answer


def test_release_is_hidden_before_answer_and_merged_after_submission(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.services import qbank_enrichment as qe
    import hashlib as _hashlib
    import json as _json

    qbank = tmp_path / "qbank.json"
    releases = tmp_path / "releases.json"
    attempts = tmp_path / "attempts.jsonl"
    question = {
        "id": "Q1", "exam": "시험", "subject": "혈액종양내과", "major": "혈액",
        "topic": "빈혈", "qtype": "단일선택", "stem": "정답을 고르시오.",
        "choices": [{"n": "1", "text": "오답", "expl": ""}, {"n": "2", "text": "정답", "expl": ""}],
        "answer": "2", "explanation": "", "points": [], "imgs": [],
    }
    qbank.write_text(_json.dumps({"questions": [question]}, ensure_ascii=False), encoding="utf-8")
    sha = _hashlib.sha256(qbank.read_bytes()).hexdigest()
    releases.write_text(_json.dumps({
        "built_against_sha256": sha,
        "releases": {"Q1": {
            "approved": True, "medical_approval": True,
            "demo_release": False, "needs_real_faculty_review": False,
            "reviewer_id": "faculty:test", "reviewed_at": "2026-07-23T00:00:00Z",
            "explanation": "교수 승인 해설",
            "choice_explanations": [{"n": "1", "expl": "승인 오답 풀이"}],
            "points": ["승인 포인트"],
        }},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(api_server, "STUDENT_QBANK_PATH", qbank)
    monkeypatch.setattr(api_server, "ATTEMPTS_LOG_PATH", attempts)
    monkeypatch.setattr(qe, "QBANK_PATH", qbank)
    monkeypatch.setattr(qe, "RELEASES_PATH", releases)
    api_server.load_student_qbank.cache_clear()
    try:
        client = TestClient(api_server.app)
        pre = client.get("/api/student/qbank").json()["questions"][0]
        assert "answer" not in pre and "explanation" not in pre and "points" not in pre
        assert all("expl" not in choice for choice in pre["choices"])

        post = client.post(
            "/api/student/questions/Q1/answer",
            json={"event_id": "release-e2e", "selected_choices": ["2"]},
        )
        assert post.status_code == 200
        payload = post.json()
        assert payload["explanation"] == "교수 승인 해설"
        assert payload["choice_explanations"]["1"] == "승인 오답 풀이"
        assert payload["points"] == ["승인 포인트"]
        assert payload["enrichment_source"] == "faculty_release"
        stored = _json.loads(attempts.read_text(encoding="utf-8").strip())
        assert stored["qbank_enrichment_snapshot"]["qbank_sha256"] == sha
    finally:
        api_server.load_student_qbank.cache_clear()


def test_overlay_checksum_guard_rejects_stale_release(tmp_path, monkeypatch):
    from src.services import qbank_enrichment as qe
    import json as _json

    stale = tmp_path / "releases.json"
    stale.write_text(_json.dumps({
        "built_against_sha256": "deadbeef_stale",
        "releases": {"Q1": {"approved": True, "explanation": "구버전 원본 기준"}},
    }), encoding="utf-8")
    monkeypatch.setattr(qe, "RELEASES_PATH", stale)
    # 원본 checksum과 불일치 → 빈 overlay(조용한 재해석 방지)
    assert qe.load_releases() == {}


def test_overlay_checksum_guard_rejects_missing_checksum(tmp_path, monkeypatch):
    from src.services import qbank_enrichment as qe
    import json as _json

    missing = tmp_path / "releases.json"
    missing.write_text(_json.dumps({
        "releases": {"Q1": {
            "approved": True,
            "medical_approval": True,
            "reviewer_id": "faculty:test",
            "reviewed_at": "2026-07-23T00:00:00Z",
        }},
    }), encoding="utf-8")
    monkeypatch.setattr(qe, "RELEASES_PATH", missing)
    assert qe.load_releases() == {}


def test_faculty_review_requires_medical_approval_and_replaces_demo(tmp_path, monkeypatch):
    from src.services import qbank_enrichment as qe
    import hashlib as _hashlib
    import json as _json

    qbank = tmp_path / "qbank.json"
    draft = tmp_path / "draft.json"
    releases = tmp_path / "releases.json"
    qbank.write_text(_json.dumps({"questions": [{"id": "Q1"}]}), encoding="utf-8")
    sha = _hashlib.sha256(qbank.read_bytes()).hexdigest()
    draft.write_text(_json.dumps({
        "built_against_sha256": sha,
        "drafts": {"Q1": {
            "release_eligible": True,
            "needs_review": True,
            "explanation": "검수할 해설",
            "choice_explanations": [{"n": "1", "expl": "선지 해설"}],
            "points": ["핵심"],
        }},
    }), encoding="utf-8")
    releases.write_text(_json.dumps({
        "built_against_sha256": sha,
        "releases": {"Q1": {
            "approved": True,
            "medical_approval": False,
            "demo_release": True,
            "needs_real_faculty_review": True,
            "reviewer_id": "demo:learning-loop-demo",
            "reviewed_at": "2026-07-23T00:00:00Z",
        }},
    }), encoding="utf-8")
    monkeypatch.setattr(qe, "QBANK_PATH", qbank)
    monkeypatch.setattr(qe, "DRAFT_PATH", draft)
    monkeypatch.setattr(qe, "RELEASES_PATH", releases)

    assert qe.load_releases() == {}
    assert qe.build_faculty_review_queue()["items"][0]["status"] == "needs_real_faculty_review"
    with pytest.raises(ValueError):
        qe.record_faculty_review(
            "Q1", decision="approve", reviewer_id="faculty:test",
            reviewed_at="2026-07-23T01:00:00Z", medical_approval=False,
        )

    entry = qe.record_faculty_review(
        "Q1", decision="approve", reviewer_id="faculty:test",
        reviewed_at="2026-07-23T01:00:00Z", medical_approval=True,
    )
    assert qe.is_student_release_approved(entry)
    assert qe.load_releases()["Q1"]["explanation"] == "검수할 해설"
    snapshot = qe.student_release_snapshot("Q1")
    assert snapshot["question_id"] == "Q1"
    assert snapshot["qbank_sha256"] == sha
    assert len(snapshot["release_version"]) == 64
    assert "explanation" not in snapshot
    assert qe.build_faculty_review_queue()["summary"]["faculty_approved"] == 1


def test_faculty_review_api_is_role_gated():
    from fastapi.testclient import TestClient

    client = TestClient(api_server.app)
    denied = client.get("/api/faculty/qbank-enrichment/review-queue")
    assert denied.status_code == 403


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
