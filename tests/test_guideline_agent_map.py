from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api_server import app
from src.services.guideline_agent_map import (
    CLAIM_RELATIVE_PATH,
    DEFAULT_ROOT,
    MAP_RELATIVE_PATH,
    get_guideline_agent_map_status,
    load_guideline_agent_assets,
    route_guideline_sources,
)


def test_source_map_and_claim_pilot_are_fail_closed() -> None:
    source_map, claims = load_guideline_agent_assets()
    summary = source_map["summary"]
    assert summary["sources"] == 81
    assert summary["jurisdictions"] == {"KR": 65, "US": 16}
    assert summary["concept_routes"] == 89
    assert summary["unresolved_concept_routes"] == 0
    assert summary["runtime_text_ingest_allowed_sources"] == 0
    assert summary["canonical_ontology_mutations"] == 0

    us_sources = [item for item in source_map["sources"] if item["jurisdiction"] == "US"]
    assert len(us_sources) == 16
    assert all(item["access"]["runtime_text_ingest_allowed"] is False for item in us_sources)
    assert all(item["review_state"]["medical_approval"] is False for item in us_sources)
    assert any(
        route["mapping_method"] == "kr_title_rule_review_candidate"
        for source in source_map["sources"]
        if source["jurisdiction"] == "KR"
        for route in source["concept_routes"]
    )

    assert claims["summary"]["candidates"] == 36
    assert claims["summary"]["candidates_by_pilot"] == {
        "amr_2024": 12,
        "diabetes_2026": 12,
        "dyslipidemia_2026": 12,
    }
    assert claims["summary"]["source_text_stored"] == 0
    assert all(
        candidate["provenance"]["paraphrase_only"] is True
        and candidate["provenance"]["source_text_stored"] is False
        and candidate["review_state"]["runtime_answer_eligible"] is False
        and candidate["review_state"]["medical_approval"] is False
        for candidate in claims["candidates"]
    )
    assert any(
        not candidate["concept_ids"] and candidate["topic_tags"]
        for candidate in claims["candidates"]
        if candidate["pilot_id"] == "amr_2024"
    )


def test_routing_modes_keep_jurisdictions_separate() -> None:
    korean = route_guideline_sources(
        concept_id="type_2_diabetes",
        clinical_axis="treatment",
        mode="korean_clinical_learning",
        include_candidate_claims=True,
    )
    assert korean["sources"]
    assert korean["sources"][0]["jurisdiction"] == "KR"
    assert all(
        item["role"] == ("primary" if item["jurisdiction"] == "KR" else "comparison")
        for item in korean["sources"]
    )
    assert korean["boundary"]["candidate_claims_used_for_answer"] == 0
    assert korean["boundary"]["released_claims_included"] == 0
    assert korean["boundary"]["silent_cross_jurisdiction_merge"] is False
    assert korean["candidate_claim_count"] == 8

    us_exam = route_guideline_sources(
        concept_id="type_2_diabetes",
        clinical_axis="treatment",
        mode="us_exam",
    )
    assert us_exam["sources"]
    assert {item["jurisdiction"] for item in us_exam["sources"]} == {"US"}
    assert {item["role"] for item in us_exam["sources"]} == {"primary"}

    research = route_guideline_sources(
        concept_id="dyslipidemia",
        mode="research_comparison",
    )
    assert {item["jurisdiction"] for item in research["sources"]} == {"KR", "US"}
    assert {item["role"] for item in research["sources"]} == {"parallel"}


def test_input_hash_drift_fails_closed(tmp_path: Path) -> None:
    source_map = json.loads((DEFAULT_ROOT / MAP_RELATIVE_PATH).read_text(encoding="utf-8"))
    paths = [MAP_RELATIVE_PATH, CLAIM_RELATIVE_PATH]
    paths.extend(Path(ref["path"]) for ref in source_map["inputs"].values())
    for relative in paths:
        source = DEFAULT_ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    load_guideline_agent_assets(root=tmp_path)
    concept_path = tmp_path / source_map["inputs"]["concept_registry"]["path"]
    concept_path.write_text(concept_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash가 달라"):
        load_guideline_agent_assets(root=tmp_path)


def test_faculty_route_api_exposes_navigation_not_private_paths() -> None:
    client = TestClient(app)
    status = client.get("/api/faculty/guideline-map/status")
    assert status.status_code == 200
    assert status.json()["counts"]["atomic_claim_candidates"] == 36

    response = client.get(
        "/api/faculty/guideline-map/route",
        params={
            "concept_id": "type_2_diabetes",
            "clinical_axis": "treatment",
            "mode": "research_comparison",
            "include_candidate_claims": "true",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_claim_count"] == 8
    assert payload["boundary"]["medical_answer_generated"] is False
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "relative_path" not in serialized
    assert "source_files/latest" not in serialized
    assert "sha256" not in serialized
    assert '"source_text":' not in serialized

    invalid = client.get(
        "/api/faculty/guideline-map/route", params={"mode": "silent_merge"}
    )
    assert invalid.status_code == 400


def test_status_reports_no_runtime_release() -> None:
    status = get_guideline_agent_map_status()
    assert status["ready"] is True
    assert status["boundary"] == {
        "source_map_is_medical_evidence": False,
        "candidate_claims_are_medically_approved": False,
        "candidate_claims_runtime_answer_eligible": False,
        "automatic_cross_jurisdiction_merge": False,
        "student_or_generation_release": 0,
    }
