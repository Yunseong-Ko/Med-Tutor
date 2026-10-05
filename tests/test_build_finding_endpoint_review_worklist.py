from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.build_finding_endpoint_review_worklist import build, write_or_check


SECRET_STEM = "PRIVATE QUESTION STEM MUST NEVER APPEAR"


def write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def fixture_files(tmp_path: Path, *, reverse: bool = False) -> dict[str, Path]:
    qbank_items = [
        {
            "id": "private-item-1",
            "stem": SECRET_STEM,
            "choices": ["private choice"],
            "disease_concept_id": ["disease_a"],
            "finding_tags": ["Elevated_FSH", "drug_x"],
        },
        {
            "id": "private-item-2",
            "explanation": "private explanation",
            "disease_concept_id": "disease_b",
            "finding_tags": ["elevated_fsh", "drug_x", "novel_tag"],
        },
    ]
    endpoint_items = [
        {"id": "drug_x", "edge_types": {"treated_with": 4}, "total": 4},
        {"id": "mystery_exposure", "edge_types": {"caused_by": 1}, "total": 1},
    ]
    if reverse:
        qbank_items.reverse()
        endpoint_items.reverse()
    return {
        "qbank": write(tmp_path / "qbank.json", {"total": 2, "items": qbank_items}),
        "concepts": write(
            tmp_path / "concepts.json",
            {"concepts": {"disease_a": {"node_type": "disease"}, "drug_x": {"node_type": "disease"}}},
        ),
        "findings": write(
            tmp_path / "findings.json",
            {
                "total": 1,
                "findings": [
                    {
                        "finding_id": "elevated_fsh",
                        "hpo_id": "HP:0008232",
                        "needs_review": True,
                    }
                ],
            },
        ),
        "endpoint_unresolved": write(
            tmp_path / "endpoint_unresolved.json",
            {"total": 2, "items": endpoint_items},
        ),
        "endpoint_types": write(
            tmp_path / "endpoint_types.json",
            {
                "source": "heuristic+llm",
                "total": 2,
                "types": {"elevated_FSH": "finding", "drug_x": "drug_substance"},
            },
        ),
    }


def build_fixture(paths: dict[str, Path]) -> dict:
    return build(
        qbank_path=paths["qbank"],
        concept_registry_path=paths["concepts"],
        finding_registry_path=paths["findings"],
        endpoint_unresolved_path=paths["endpoint_unresolved"],
        endpoint_types_path=paths["endpoint_types"],
    )


def test_finding_tags_are_aggregated_without_private_question_content(tmp_path: Path) -> None:
    payload = build_fixture(fixture_files(tmp_path))
    serialized = json.dumps(payload, ensure_ascii=False)
    finding = next(row for row in payload["finding_worklist"] if row["normalized_tag_id"] == "elevated_fsh")

    assert SECRET_STEM not in serialized
    assert "private-item-1" not in serialized
    assert "private choice" not in serialized
    assert "private explanation" not in serialized
    assert payload["privacy"]["tag_and_identifier_aggregates_only"] is True
    assert payload["summary"]["finding"]["distinct_raw_tags"] == 4
    assert payload["summary"]["finding"]["finding_registry_rows"] == 1
    assert payload["summary"]["finding"]["finding_registry_rows_with_hpo"] == 1
    assert finding["frequency"] == 2
    assert finding["linked_disease_count"] == 2
    assert finding["linked_disease_concept_ids"] == ["disease_a", "disease_b"]
    assert finding["existing_in_finding_registry"] is True
    assert finding["hpo_status"] == "existing_hpo_id_needs_review"
    assert finding["hpo_ids"] == ["HP:0008232"]
    assert finding["proposed_action"] == "review_before_promote"
    assert finding["promotion_eligible"] is False
    assert finding["review_decision"]["decision"] is None


def test_nonfinding_endpoint_type_makes_tag_a_p0_review_candidate(tmp_path: Path) -> None:
    payload = build_fixture(fixture_files(tmp_path))
    finding = next(row for row in payload["finding_worklist"] if row["normalized_tag_id"] == "drug_x")

    assert finding["priority"] == "P0"
    assert finding["priority_reason"] == "tag_role_conflicts_with_current_endpoint_type"
    assert finding["current_endpoint_types"] == ["drug_substance"]
    assert finding["candidate_only"] is True
    assert finding["medical_approval"] is False


def test_endpoint_rows_report_current_typing_and_candidate_only_review_class(tmp_path: Path) -> None:
    payload = build_fixture(fixture_files(tmp_path))
    typed = next(row for row in payload["endpoint_worklist"] if row["endpoint_id"] == "drug_x")
    untyped = next(row for row in payload["endpoint_worklist"] if row["endpoint_id"] == "mystery_exposure")

    assert typed["current_typing_status"] == "present_needs_review"
    assert typed["current_endpoint_types"] == ["drug_substance"]
    assert typed["controlled_vocabulary_review_class"] == "drug_or_substance_candidate"
    assert typed["classification_basis"] == "current_endpoint_type"
    assert typed["controlled_vocabulary_id"] is None
    assert typed["in_concept_registry"] is True
    assert typed["priority"] == "P1"

    assert untyped["current_typing_status"] == "missing"
    assert untyped["controlled_vocabulary_review_class"] == "cause_exposure_or_agent_candidate"
    assert untyped["classification_basis"] == "edge_role_only"
    assert untyped["controlled_vocabulary_id"] is None
    assert untyped["priority"] == "P0"
    assert untyped["needs_review"] is True
    assert untyped["medical_approval"] is False


def test_output_is_deterministic_when_source_rows_are_reordered(tmp_path: Path) -> None:
    first = fixture_files(tmp_path / "a")
    second = fixture_files(tmp_path / "b", reverse=True)
    payload_a = build_fixture(first)
    payload_b = build_fixture(second)

    # Input paths are intentionally different; provenance aside, every derived
    # summary and review row must be independent of source row order.
    payload_a = copy.deepcopy(payload_a)
    payload_b = copy.deepcopy(payload_b)
    payload_a.pop("generated_from")
    payload_b.pop("generated_from")
    assert payload_a == payload_b


def test_write_or_check_detects_drift(tmp_path: Path) -> None:
    payload = build_fixture(fixture_files(tmp_path / "inputs"))
    output = tmp_path / "worklist.json"

    assert write_or_check(payload, output, check=False)
    assert write_or_check(payload, output, check=True)
    output.write_text("{}\n", encoding="utf-8")
    assert not write_or_check(payload, output, check=True)
