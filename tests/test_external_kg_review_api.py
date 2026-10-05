from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from api_server import app
from src.services import external_kg_review


ROOT = Path(__file__).resolve().parents[1]
CORE20 = ROOT / "data_private" / "external_kg" / "primekg"


def _all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def test_faculty_external_validation_endpoint_is_read_only_and_fail_closed() -> None:
    response = TestClient(app).get(
        "/api/ontology/external-validation",
        params={"profile": "core20", "limit": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "review_only_available"
    assert payload["profile"] == "core20"
    assert payload["page"]["returned"] == 3
    assert payload["summary"]["item_count"] == 181
    assert payload["summary"]["counts_by_priority"] == {"P0": 2, "P1": 11, "P2": 168}
    assert len(payload["source"]["artifacts"]) == 3

    safety = payload["safety_boundary"]
    assert safety["human_review_required"] is True
    for field in (
        "medical_approval",
        "student_visible",
        "analytics_eligible",
        "generation_eligible",
        "canonical_ontology_mutation",
        "automatic_promotion",
    ):
        assert safety[field] is False
    for item in payload["items"]:
        assert item["review_gate"] == external_kg_review.FAIL_CLOSED_GATE
        assert item["decision"] is None

    # The projection contains only identifiers, labels, checksums, and review metadata.
    assert not ({"question_text", "stem", "answer", "student_id", "patient_id"} & set(_all_keys(payload)))


def test_external_validation_priority_filter_and_page_cap() -> None:
    client = TestClient(app)
    p0 = client.get(
        "/api/ontology/external-validation",
        params={"profile": "core20", "priority": "P0", "limit": 1000},
    )
    assert p0.status_code == 200
    payload = p0.json()
    assert payload["page"] == {
        "offset": 0,
        "limit": 100,
        "total": 2,
        "returned": 2,
        "has_more": False,
    }
    assert {row["priority"] for row in payload["items"]} == {"P0"}
    assert {row["priority_reason"] for row in payload["items"]} == {
        "negated_external_new_candidate"
    }
    assert all(
        "negated_relation_is_not_positive_finding" in row["review_instructions"]
        for row in payload["items"]
    )


def test_external_validation_rejects_unknown_profile() -> None:
    response = TestClient(app).get(
        "/api/ontology/external-validation",
        params={"profile": "../../private"},
    )
    assert response.status_code == 400
    assert "unsupported_external_kg_profile" in response.json()["detail"]


def test_external_validation_hides_queue_after_source_checksum_drift(
    tmp_path: Path, monkeypatch
) -> None:
    for filename in (
        "review_worklist.json",
        "heme_onc_validation_report.json",
        "heme_onc_phenotype_candidate_graph.json",
        "heme_onc_mondo_crosswalk.json",
    ):
        shutil.copy2(CORE20 / filename, tmp_path / filename)
    graph_path = tmp_path / "heme_onc_phenotype_candidate_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["scope"]["notes"] += " checksum drift"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(
        external_kg_review.PROFILE_CONFIG,
        "checksum_fixture",
        {"label": "fixture", "root": tmp_path, "scope_id": "core20"},
    )

    payload = external_kg_review.list_external_kg_review(profile="checksum_fixture")

    assert payload["status"] == "unavailable_fail_closed"
    assert payload["unavailable_reason"] == "source_artifact_checksum_mismatch:candidate_graph"
    assert payload["items"] == []
    assert payload["safety_boundary"]["generation_eligible"] is False


def test_schema_valid_worklist_edit_is_rejected_by_source_derivation(
    tmp_path: Path, monkeypatch
) -> None:
    for filename in (
        "review_worklist.json",
        "review_decisions.json",
        "heme_onc_validation_report.json",
        "heme_onc_phenotype_candidate_graph.json",
        "heme_onc_mondo_crosswalk.json",
    ):
        shutil.copy2(CORE20 / filename, tmp_path / filename)
    path = tmp_path / "review_worklist.json"
    worklist = json.loads(path.read_text(encoding="utf-8"))
    worklist["items"][0]["local"]["finding_label"] = "schema-valid forged label"
    path.write_text(json.dumps(worklist, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(
        external_kg_review.PROFILE_CONFIG,
        "worklist_binding_fixture",
        {"label": "fixture", "root": tmp_path, "scope_id": "core20"},
    )

    payload = external_kg_review.list_external_kg_review(
        profile="worklist_binding_fixture"
    )

    assert payload["status"] == "unavailable_fail_closed"
    assert payload["unavailable_reason"] == "review_worklist_source_binding_mismatch"
    assert payload["items"] == []


def test_decision_must_match_its_bound_review_task(
    tmp_path: Path, monkeypatch
) -> None:
    for filename in (
        "review_worklist.json",
        "review_decisions.json",
        "heme_onc_validation_report.json",
        "heme_onc_phenotype_candidate_graph.json",
        "heme_onc_mondo_crosswalk.json",
    ):
        shutil.copy2(CORE20 / filename, tmp_path / filename)
    worklist = json.loads((tmp_path / "review_worklist.json").read_text(encoding="utf-8"))
    overlay_path = tmp_path / "review_decisions.json"
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    task, other = worklist["items"][0], worklist["items"][1]
    overlay["decisions"] = [
        {
            "decision_id": "ekg:d:" + "1" * 24,
            "review_task_id": task["review_task_id"],
            "validation_item_id": other["validation_item_id"],
            "candidate_edge_ids": task["candidate_edge_ids"],
            "outcome": "deferred",
            "rationale": "fixture",
            "evidence_refs": ["fixture:evidence"],
            "reviewer": {
                "type": "human_reviewer",
                "reviewer_id": "fixture-reviewer",
                "role": "test",
                "reviewed_at": "2026-07-13T09:00:00Z",
            },
            "safety_boundary": overlay["safety_boundary"],
        }
    ]
    overlay_path.write_text(json.dumps(overlay, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(
        external_kg_review.PROFILE_CONFIG,
        "decision_binding_fixture",
        {"label": "fixture", "root": tmp_path, "scope_id": "core20"},
    )

    payload = external_kg_review.list_external_kg_review(
        profile="decision_binding_fixture"
    )

    assert payload["status"] == "unavailable_fail_closed"
    assert payload["unavailable_reason"] == "review_decisions_validation_binding_mismatch"
    assert payload["items"] == []


def test_decision_overlay_rejects_invalid_datetime_format(
    tmp_path: Path, monkeypatch
) -> None:
    for filename in (
        "review_worklist.json",
        "review_decisions.json",
        "heme_onc_validation_report.json",
        "heme_onc_phenotype_candidate_graph.json",
        "heme_onc_mondo_crosswalk.json",
    ):
        shutil.copy2(CORE20 / filename, tmp_path / filename)
    overlay_path = tmp_path / "review_decisions.json"
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    overlay["created_at"] = "not-a-date"
    overlay_path.write_text(json.dumps(overlay, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(
        external_kg_review.PROFILE_CONFIG,
        "decision_datetime_fixture",
        {"label": "fixture", "root": tmp_path, "scope_id": "core20"},
    )

    payload = external_kg_review.list_external_kg_review(
        profile="decision_datetime_fixture"
    )

    assert payload["status"] == "unavailable_fail_closed"
    assert payload["unavailable_reason"] == "review_decisions_invalid"
    assert payload["items"] == []
