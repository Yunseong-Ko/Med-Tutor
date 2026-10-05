import copy
import csv
import json
from pathlib import Path

import jsonschema
import pytest

from scripts.build_external_kg_review_worklist import (
    DECISION_SAFETY_BOUNDARY,
    assign_priority,
    build_review_worklist,
    json_bytes,
)
from scripts.build_primekg_heme_phenotype_pilot import build_pilot


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def make_pilot(tmp_path: Path) -> Path:
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    concept_registry = source_dir / "concept_registry.json"
    finding_registry = source_dir / "finding_registry.json"
    nodes_path = source_dir / "nodes.tab"
    edges_path = source_dir / "edges.csv"
    write_json(
        concept_registry,
        {
            "concepts": {
                "concept_a": {
                    "aliases": ["질환 A", "Disease A"],
                    "evidence": {
                        "ontology_xref": {
                            "mondo_id": "MONDO:0000123",
                            "mondo_label": "disease A",
                            "name_match": "close",
                        }
                    },
                },
                "concept_grouped": {
                    "aliases": ["Grouped disease"],
                    "evidence": {
                        "ontology_xref": {
                            "mondo_id": "MONDO:0000456",
                            "mondo_label": "grouped disease",
                            "name_match": "exact",
                        }
                    },
                },
            }
        },
    )
    write_json(
        finding_registry,
        {
            "findings": [
                {
                    "finding_id": "fever",
                    "hpo_id": "HP:0000001",
                    "hpo_label": "Fever",
                    "presented_by": ["concept_a"],
                    "needs_review": True,
                },
                {
                    "finding_id": "anemia",
                    "hpo_id": "HP:0000002",
                    "hpo_label": "Anemia",
                    "presented_by": ["concept_a"],
                    "needs_review": True,
                },
                {
                    "finding_id": "edema",
                    "hpo_id": "HP:0000004",
                    "hpo_label": "Edema",
                    "presented_by": ["concept_a"],
                    "needs_review": True,
                },
                {
                    "finding_id": "grouped_finding",
                    "hpo_id": "HP:0000005",
                    "hpo_label": "Grouped finding",
                    "presented_by": ["concept_grouped"],
                    "needs_review": True,
                },
            ]
        },
    )
    with nodes_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(
            ["node_index", "node_id", "node_type", "node_name", "node_source"]
        )
        writer.writerows(
            [
                [0, "123", "disease", "Disease A", "MONDO"],
                [1, "1", "effect/phenotype", "Fever", "HPO"],
                [2, "2", "effect/phenotype", "Anemia", "HPO"],
                [3, "3", "effect/phenotype", "Rash", "HPO"],
                [5, "456_789", "disease", "Grouped disease", "MONDO_grouped"],
                [6, "6", "effect/phenotype", "Absent sign", "HPO"],
            ]
        )
    with edges_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["relation", "display_relation", "x_index", "y_index"])
        writer.writerows(
            [
                ["disease_phenotype_positive", "phenotype present", 0, 1],
                ["disease_phenotype_positive", "phenotype present", 1, 0],
                ["disease_phenotype_negative", "phenotype absent", 0, 2],
                ["disease_phenotype_negative", "phenotype absent", 2, 0],
                ["disease_phenotype_positive", "phenotype present", 0, 3],
                ["disease_phenotype_positive", "phenotype present", 3, 0],
                ["disease_phenotype_positive", "phenotype present", 5, 1],
                ["disease_phenotype_positive", "phenotype present", 1, 5],
                ["disease_phenotype_negative", "phenotype absent", 0, 6],
                ["disease_phenotype_negative", "phenotype absent", 6, 0],
            ]
        )
    pilot_dir = tmp_path / "pilot"
    build_pilot(
        concept_registry_path=concept_registry,
        finding_registry_path=finding_registry,
        nodes_path=nodes_path,
        edges_path=edges_path,
        output_dir=pilot_dir,
        selected_ids=["concept_a", "concept_grouped"],
        verify_official_checksums=False,
    )
    return pilot_dir


def build_fixture(tmp_path: Path, output_name: str = "review"):
    pilot_dir = make_pilot(tmp_path)
    output_dir = tmp_path / output_name
    worklist_path = output_dir / "review_worklist.json"
    decisions_path = output_dir / "review_decisions.json"
    worklist, decisions = build_review_worklist(
        validation_report_path=pilot_dir / "heme_onc_validation_report.json",
        candidate_graph_path=pilot_dir / "heme_onc_phenotype_candidate_graph.json",
        crosswalk_path=pilot_dir / "heme_onc_mondo_crosswalk.json",
        output_path=worklist_path,
        decisions_output_path=decisions_path,
        scope_id="core20",
    )
    return pilot_dir, worklist_path, decisions_path, worklist, decisions


def test_priority_queue_uses_structural_rules_and_keeps_negation_explicit(tmp_path):
    _, _, _, worklist, decisions = build_fixture(tmp_path)
    by_hpo = {item["local"]["hpo_curie"]: item for item in worklist["items"]}
    assert (by_hpo["HP:0000001"]["priority"], by_hpo["HP:0000001"]["priority_reason"]) == (
        "P1",
        "externally_concordant",
    )
    assert (by_hpo["HP:0000002"]["priority"], by_hpo["HP:0000002"]["priority_reason"]) == (
        "P0",
        "external_conflict_candidate",
    )
    assert (by_hpo["HP:0000003"]["priority"], by_hpo["HP:0000003"]["priority_reason"]) == (
        "P2",
        "affirmed_external_new_candidate",
    )
    assert (by_hpo["HP:0000004"]["priority"], by_hpo["HP:0000004"]["priority_reason"]) == (
        "P1",
        "exact_local_only_not_disproven",
    )
    assert (by_hpo["HP:0000005"]["priority"], by_hpo["HP:0000005"]["priority_reason"]) == (
        "P2",
        "grouped_mapping_not_evaluable",
    )
    assert (by_hpo["HP:0000006"]["priority"], by_hpo["HP:0000006"]["priority_reason"]) == (
        "P0",
        "negated_external_new_candidate",
    )
    assert "negated_relation_is_not_positive_finding" in by_hpo["HP:0000006"][
        "review_instructions"
    ]
    assert worklist["stats"]["counts_by_priority"] == {"P0": 2, "P1": 2, "P2": 2}
    assert worklist["prioritization_policy"]["lexical_medical_scoring_used"] is False
    assert worklist["prioritization_policy"][
        "negated_external_new_is_positive_finding"
    ] is False
    assert decisions["decisions"] == []


def test_worklist_and_empty_decision_overlay_validate_and_are_fail_closed(tmp_path):
    _, _, _, worklist, decisions = build_fixture(tmp_path)
    worklist_schema = json.loads(
        (ROOT / "schemas" / "external_kg_review_worklist.schema.json").read_text()
    )
    decisions_schema = json.loads(
        (ROOT / "schemas" / "external_kg_review_decisions.schema.json").read_text()
    )
    jsonschema.validate(worklist, worklist_schema)
    jsonschema.validate(decisions, decisions_schema)
    assert worklist["decision_boundary"] == {
        "automatic_medical_approval": False,
        "automatic_promotion": False,
        "canonical_ontology_mutation": False,
        "decision_overlay_schema": "external_kg_review_decisions.v1",
        "reviewer_decisions_embedded": False,
        "student_exposure": False,
    }
    for item in worklist["items"]:
        assert item["review_gate"]["medical_approval"] is False
        assert item["review_gate"]["student_visible"] is False
        assert item["review_gate"]["analytics_eligible"] is False
        assert item["review_gate"]["promotion_status"] == "not_promoted"
        assert item["reviewer_decision_ref"] is None
        assert item["provenance"]["external_snapshots"]
        for snapshot in item["provenance"]["external_snapshots"]:
            assert len(snapshot["artifact_sha256"]) == 64
            assert snapshot["license"]
            assert snapshot["snapshot_id"]


def test_outputs_are_deterministic_and_scope_supports_heme_onc_full(tmp_path):
    pilot_dir = make_pilot(tmp_path)
    outputs = []
    for name in ("first", "second"):
        output_dir = tmp_path / name
        worklist_path = output_dir / "worklist.json"
        decisions_path = output_dir / "decisions.json"
        build_review_worklist(
            validation_report_path=pilot_dir / "heme_onc_validation_report.json",
            candidate_graph_path=pilot_dir / "heme_onc_phenotype_candidate_graph.json",
            crosswalk_path=pilot_dir / "heme_onc_mondo_crosswalk.json",
            output_path=worklist_path,
            decisions_output_path=decisions_path,
            scope_id="heme_onc_full",
        )
        outputs.append((worklist_path, decisions_path))
    assert outputs[0][0].read_bytes() == outputs[1][0].read_bytes()
    assert outputs[0][1].read_bytes() == outputs[1][1].read_bytes()
    worklist = json.loads(outputs[0][0].read_text())
    assert worklist["scope"]["scope_id"] == "heme_onc_full"
    assert worklist["worklist_id"].startswith(
        "external_kg_review_worklist:heme_onc_full:"
    )


def test_labels_cannot_change_priority_and_unknown_external_is_p2():
    base = {
        "classification": "external_new_candidate",
        "evaluation_status": "evaluated_exact_mapping",
        "external_polarities": ["affirmed"],
        "local_finding_label": "ordinary label",
    }
    renamed = {**base, "local_finding_label": "URGENT FATAL HIGH YIELD"}
    assert assign_priority(base) == assign_priority(renamed) == (
        "P2",
        "affirmed_external_new_candidate",
    )
    assert assign_priority(
        {
            "classification": "external_new_candidate",
            "evaluation_status": "evaluated_exact_mapping",
            "external_polarities": ["unknown"],
        }
    ) == ("P2", "unknown_external_new_candidate")


def test_schemas_reject_approval_embedded_decision_and_priority_bypass(tmp_path):
    _, _, _, worklist, decisions = build_fixture(tmp_path)
    worklist_schema = json.loads(
        (ROOT / "schemas" / "external_kg_review_worklist.schema.json").read_text()
    )
    decisions_schema = json.loads(
        (ROOT / "schemas" / "external_kg_review_decisions.schema.json").read_text()
    )

    approved = copy.deepcopy(worklist)
    approved["items"][0]["review_gate"]["medical_approval"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(approved, worklist_schema)

    embedded = copy.deepcopy(worklist)
    embedded["items"][0]["reviewer_decision"] = {"outcome": "approved"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(embedded, worklist_schema)

    bypass = copy.deepcopy(worklist)
    affirmed = next(
        item
        for item in bypass["items"]
        if item["priority_reason"] == "affirmed_external_new_candidate"
    )
    affirmed["priority"] = "P0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bypass, worklist_schema)

    decision_approval = copy.deepcopy(decisions)
    decision_approval["safety_boundary"]["medical_approval"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(decision_approval, decisions_schema)


def test_graph_hash_integrity_check_fails_closed(tmp_path):
    pilot_dir = make_pilot(tmp_path)
    graph_path = pilot_dir / "heme_onc_phenotype_candidate_graph.json"
    graph = json.loads(graph_path.read_text())
    graph_path.write_text(json.dumps(graph, indent=4), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        build_review_worklist(
            validation_report_path=pilot_dir / "heme_onc_validation_report.json",
            candidate_graph_path=graph_path,
            crosswalk_path=pilot_dir / "heme_onc_mondo_crosswalk.json",
            output_path=tmp_path / "bad" / "worklist.json",
            scope_id="core20",
        )


def test_missing_candidate_edge_integrity_check_fails_closed(tmp_path):
    pilot_dir = make_pilot(tmp_path)
    report_path = pilot_dir / "heme_onc_validation_report.json"
    report = json.loads(report_path.read_text())
    item = next(row for row in report["items"] if row["candidate_edge_ids"])
    item["candidate_edge_ids"] = ["ekg:e:" + "f" * 24]
    altered_report = tmp_path / "altered_validation_report.json"
    altered_report.write_bytes(json_bytes(report))
    with pytest.raises(ValueError, match="references missing candidate edges"):
        build_review_worklist(
            validation_report_path=altered_report,
            candidate_graph_path=pilot_dir
            / "heme_onc_phenotype_candidate_graph.json",
            crosswalk_path=pilot_dir / "heme_onc_mondo_crosswalk.json",
            output_path=tmp_path / "bad" / "worklist.json",
            scope_id="core20",
        )


def test_existing_human_decisions_are_never_overwritten(tmp_path):
    pilot_dir, worklist_path, decisions_path, worklist, decisions = build_fixture(tmp_path)
    task = worklist["items"][0]
    decisions["decisions"].append(
        {
            "decision_id": "ekg:d:" + "a" * 24,
            "review_task_id": task["review_task_id"],
            "validation_item_id": task["validation_item_id"],
            "candidate_edge_ids": task["candidate_edge_ids"],
            "outcome": "insufficient_evidence",
            "rationale": "Authoritative evidence review is still required.",
            "evidence_refs": ["review-note:test"],
            "reviewer": {
                "type": "human_reviewer",
                "reviewer_id": "reviewer-test",
                "role": "clinical_reviewer",
                "reviewed_at": "2026-07-13T09:00:00Z",
            },
            "safety_boundary": dict(DECISION_SAFETY_BOUNDARY),
        }
    )
    decisions_path.write_bytes(json_bytes(decisions))
    before = decisions_path.read_bytes()
    _, returned = build_review_worklist(
        validation_report_path=pilot_dir / "heme_onc_validation_report.json",
        candidate_graph_path=pilot_dir / "heme_onc_phenotype_candidate_graph.json",
        crosswalk_path=pilot_dir / "heme_onc_mondo_crosswalk.json",
        output_path=worklist_path,
        decisions_output_path=decisions_path,
        scope_id="core20",
    )
    assert decisions_path.read_bytes() == before
    assert len(returned["decisions"]) == 1
