"""임상종합평가 70문항 시연 Overlay의 완결성과 노출 경계를 검증한다."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api_server
from scripts import build_pma70_enrichment_overlay as builder
from src.services import qbank_enrichment


ROOT = Path(__file__).resolve().parents[1]
QBANK = ROOT / "data_private" / "student" / "qbank.json"
TARGET_EXAM = builder.TARGET_EXAM
pytestmark = pytest.mark.skipif(not QBANK.exists(), reason="private student qbank not present")


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, dict):
        return "segment_text" in value or any(_contains_forbidden_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def test_builder_produces_complete_bounded_overlay(tmp_path, monkeypatch):
    draft = tmp_path / "draft.json"
    releases = tmp_path / "releases.json"
    monkeypatch.setattr(builder, "DRAFT_PATH", draft)
    monkeypatch.setattr(builder, "RELEASES_PATH", releases)

    summary = builder.build(
        reviewed_at="2026-07-23T15:00:00+00:00",
        reviewer_id="owner:goyunseong",
    )
    assert summary == {
        "exam": TARGET_EXAM,
        "questions": 70,
        "registry_concepts": 62,
        "curriculum_topic_nodes": 8,
        "axis_assigned": 70,
        "anki_cards": 70,
        "connected_media": 40,
        "text_sufficient_visuals": 2,
        "qbank_sha256": "80ab19d3e6bcb611ea4b24437a0bacd4bdb2819ac13ac61d52fcaea106907c29",
    }
    rows = json.loads(releases.read_text(encoding="utf-8"))["releases"]
    target = {qid: row for qid, row in rows.items() if row.get("source", {}).get("exam") == TARGET_EXAM}
    assert len(target) == 70
    assert all(row.get("explanation") for row in target.values())
    assert all(row.get("structured_explanation") for row in target.values())
    assert all(row["structured_explanation"].get("schema_version") == "paccine.structured_explanation.v1" for row in target.values())
    assert all(row["structured_explanation"].get("conclusion") for row in target.values())
    assert all(row["structured_explanation"].get("correct_answer") for row in target.values())
    assert all(row["structured_explanation"].get("correct_answer_rationale") for row in target.values())
    assert all(row["structured_explanation"].get("clinical_reasoning") for row in target.values())
    assert all(row["structured_explanation"].get("key_points") for row in target.values())
    assert all(row["structured_explanation"].get("axis_focus", {}).get("message") for row in target.values())
    assert all(len(row.get("choice_explanations") or []) == 5 for row in target.values())
    assert all(row.get("concept_id") and row.get("target_axis_type") in builder.AXIS_LABELS for row in target.values())
    assert all(row.get("anki_cards") for row in target.values())
    assert sum(len(row.get("connected_media") or []) for row in target.values()) == 40
    assert sum(row.get("media_requirement_satisfied_by_text") is True for row in target.values()) == 2
    assert all(row.get("medical_approval") is False for row in target.values())
    assert all(row.get("needs_real_faculty_review") is True for row in target.values())
    assert not _contains_forbidden_key(target)


def test_owner_demo_requires_explicit_full_demo_profile(monkeypatch):
    entry = {
        "approved": True,
        "medical_approval": False,
        "curated_demo_release": True,
        "demo_release": True,
        "needs_real_faculty_review": True,
        "reviewer_id": "owner:goyunseong",
        "reviewed_at": "2026-07-23T15:00:00+00:00",
    }
    monkeypatch.delenv("PACCINE_REQUIRE_FULL_DEMO", raising=False)
    assert not qbank_enrichment.is_curated_demo_release_visible(entry)
    monkeypatch.setenv("PACCINE_REQUIRE_FULL_DEMO", "true")
    assert qbank_enrichment.is_curated_demo_release_visible(entry)
    assert not qbank_enrichment.is_student_release_approved(entry)


def test_all_target_questions_are_ready_without_pre_answer_truth_leak(tmp_path, monkeypatch):
    monkeypatch.setenv("PACCINE_REQUIRE_FULL_DEMO", "true")
    monkeypatch.setattr(api_server, "ATTEMPTS_LOG_PATH", tmp_path / "attempts.jsonl")
    releases = qbank_enrichment.load_releases()
    target_questions = [
        question
        for question in json.loads(QBANK.read_text(encoding="utf-8"))["questions"]
        if question.get("exam") == TARGET_EXAM
    ]
    assert len(target_questions) == 70
    public = [
        api_server.public_qbank_question(question, releases.get(question["id"]))
        for question in target_questions
    ]
    forbidden = {
        "answer", "explanation", "choice_explanations", "points", "anki_cards",
        "evidence", "concept_id", "target_axis_type", "structured_explanation",
    }
    assert all(question.get("practice_ready") is True for question in public)
    assert all(not (set(question) & forbidden) for question in public)
    assert all(all(set(choice) == {"n", "text"} for choice in question["choices"]) for question in public)
    assert len(public[2]["imgs"]) == 2
    assert public[14]["media_requirement"] == "described_in_stem"

    client = TestClient(api_server.app)
    selected = str(target_questions[2]["answer"])
    response = client.post(
        f"/api/student/questions/{target_questions[2]['id']}/answer",
        json={"event_id": "pma70-overlay-e2e", "session_id": "pytest", "selected_choices": [selected]},
    )
    assert response.status_code == 200
    feedback = response.json()
    assert feedback["explanation"]
    assert feedback["structured_explanation"]["conclusion"]
    assert feedback["structured_explanation"]["correct_answer_rationale"]
    assert feedback["structured_explanation"]["axis_focus"]["message"]
    assert len(feedback["choice_explanations"]) == 5
    assert feedback["concept_id"]
    assert feedback["target_axis_type"] in builder.AXIS_LABELS
    assert feedback["anki_cards"]
    assert len(feedback["connected_media"]) == 2
    assert feedback["evidence"]
    assert feedback["enrichment_release"]["release_mode"] == "owner_curated_demo"
    assert feedback["enrichment_release"]["needs_real_faculty_review"] is True
