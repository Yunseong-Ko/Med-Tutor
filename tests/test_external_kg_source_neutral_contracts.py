import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

from src.services.external_kg_adapter import (
    FAIL_CLOSED_REVIEW,
    build_candidate_graph,
    canonical_sha256,
    normalize_optimuskg_record,
    normalize_primekg_row,
)


ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64


def load_schema(name):
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def validate(name, value):
    jsonschema.Draft202012Validator(load_schema(name)).validate(value)


def snapshot_entry(provider="primekg", artifact_format="csv", digest=SHA_A):
    return {
        "snapshot_id": f"external_kg_snapshot:{provider}:2021",
        "provider": provider,
        "dataset_name": "PrimeKG" if provider == "primekg" else "OptimusKG",
        "dataset_version": "2021" if provider == "primekg" else "2026-06",
        "source_url": "https://example.org/external-kg",
        "retrieved_at": "2026-07-13T01:00:00Z",
        "artifact": {
            "format": artifact_format,
            "content_sha256": digest,
            "byte_size": 1234,
        },
        "license": {
            "name": "upstream-source-specific",
            "spdx_id": None,
            "url": "https://example.org/license",
            "redistribution_status": "restricted",
            "notes": "Each upstream component still requires license review.",
        },
        "citation": "Synthetic contract fixture",
        "ingest_policy": {
            "mode": "local_snapshot",
            "external_candidate_only": True,
            "requires_human_review": True,
            "medical_approval": False,
            "student_visible": False,
            "analytics_eligible": False,
        },
    }


def primekg_row():
    return {
        "relation": "disease_phenotype_negative",
        "display_relation": "phenotype absent",
        "x_index": 101,
        "x_id": "9693",
        "x_type": "disease",
        "x_name": "multiple myeloma",
        "x_source": "MONDO",
        "y_index": 202,
        "y_id": "1981",
        "y_type": "effect/phenotype",
        "y_name": "Schistocytosis",
        "y_source": "HPO",
        "edge_id": "primekg:edge:1",
    }


def test_snapshot_manifest_and_crosswalk_contracts_are_fail_closed():
    snapshot = snapshot_entry()
    manifest = {
        "schema_version": "external_kg_snapshot_manifest.v1",
        "manifest_id": "external_kg_manifest:primekg_pilot",
        "created_at": "2026-07-13T01:00:00Z",
        "policy": {
            "external_candidate_only": True,
            "requires_human_review": True,
            "medical_approval": False,
            "student_visible": False,
            "analytics_eligible": False,
        },
        "snapshots": [snapshot],
    }
    validate("external_kg_snapshot_manifest.schema.json", manifest)

    crosswalk = {
        "schema_version": "external_kg_crosswalk.v1",
        "crosswalk_id": "external_kg_crosswalk:primekg_pilot",
        "generated_at": "2026-07-13T01:01:00Z",
        "source_snapshots": [
            {"snapshot_id": snapshot["snapshot_id"], "artifact_sha256": SHA_A}
        ],
        "review_policy": deepcopy(FAIL_CLOSED_REVIEW),
        "mappings": [
            {
                "mapping_id": f"ekg:x:{'1' * 24}",
                "local_concept_id": "multiple_myeloma",
                "external_curie": "MONDO:0009693",
                "external_label": "multiple myeloma",
                "external_snapshot_id": snapshot["snapshot_id"],
                "mapping_relation": "exact_match",
                "mapping_method": "identifier_exact",
                "confidence": 1.0,
                "evidence": [
                    {
                        "source_record_id": "primekg:node:101",
                        "source_record_sha256": SHA_B,
                        "note": "Exact MONDO identifier",
                    }
                ],
                "review": deepcopy(FAIL_CLOSED_REVIEW),
            }
        ],
    }
    validate("external_kg_crosswalk.schema.json", crosswalk)

    unsafe = deepcopy(crosswalk)
    unsafe["mappings"][0]["review"]["medical_approval"] = True
    with pytest.raises(jsonschema.ValidationError):
        validate("external_kg_crosswalk.schema.json", unsafe)


def test_primekg_numeric_mondo_hpo_ids_and_implicit_undirected_contract():
    row = primekg_row()
    edge = normalize_primekg_row(row, snapshot_entry())

    assert edge["subject"]["curie"] == "MONDO:0009693"
    assert edge["subject"]["source_local_id"] == "9693"
    assert edge["object"]["curie"] == "HP:0001981"
    assert edge["object"]["source_local_id"] == "1981"
    assert edge["predicate"] == {
        "canonical": "presents_with",
        "curie": None,
        "source_label": "phenotype absent",
        "source_code": "disease_phenotype_negative",
    }
    assert edge["polarity"] == "negated"
    assert edge["direction"] == "undirected"
    assert edge["undirected"] is True
    assert edge["review"] == FAIL_CLOSED_REVIEW
    assert edge["provenance"]["dataset_version"] == "2021"
    assert edge["provenance"]["artifact_sha256"] == SHA_A
    assert edge["provenance"]["license"] == "upstream-source-specific"
    assert edge["provenance"]["source_record_sha256"] == canonical_sha256(row)


def test_existing_curie_case_is_preserved_except_standard_mondo_hpo_padding():
    row = primekg_row()
    row["x_id"] = "MONDO:9693"
    row["y_id"] = "customPrefix:AbC-12"
    row["y_source"] = "custom"
    edge = normalize_primekg_row(row, snapshot_entry())
    assert edge["subject"]["curie"] == "MONDO:0009693"
    assert edge["subject"]["source_local_id"] == "MONDO:9693"
    assert edge["object"]["curie"] == "customPrefix:AbC-12"


def test_primekg_reverse_rows_collapse_without_losing_record_provenance():
    forward_row = primekg_row()
    reverse_row = {
        **forward_row,
        "x_index": forward_row["y_index"],
        "x_id": forward_row["y_id"],
        "x_type": forward_row["y_type"],
        "x_name": forward_row["y_name"],
        "x_source": forward_row["y_source"],
        "y_index": forward_row["x_index"],
        "y_id": forward_row["x_id"],
        "y_type": forward_row["x_type"],
        "y_name": forward_row["x_name"],
        "y_source": forward_row["x_source"],
        "edge_id": "primekg:edge:reverse",
    }
    snapshot = snapshot_entry()
    forward = normalize_primekg_row(forward_row, snapshot)
    reverse = normalize_primekg_row(reverse_row, snapshot)

    assert forward["candidate_edge_id"] == reverse["candidate_edge_id"]
    graph = build_candidate_graph(
        [reverse, forward], snapshot, generated_at="2026-07-13T01:02:00Z"
    )
    assert graph["stats"]["edge_count"] == 1
    collapsed = graph["edges"][0]["qualifiers"]
    assert collapsed["collapsed_undirected_rows"] == 2
    assert {row["source_record_id"] for row in collapsed["collapsed_source_records"]} == {
        "primekg:edge:1",
        "primekg:edge:reverse",
    }
    assert {
        (row["subject_curie"], row["object_curie"])
        for row in collapsed["collapsed_source_records"]
    } == {
        ("MONDO:0009693", "HP:0001981"),
        ("HP:0001981", "MONDO:0009693"),
    }

    unsafe_reverse = deepcopy(reverse)
    unsafe_reverse["review"]["medical_approval"] = True
    with pytest.raises(ValueError, match="fail-closed"):
        build_candidate_graph([forward, unsafe_reverse], snapshot)

    spoofed_id = deepcopy(reverse)
    spoofed_id["object"]["curie"] = "HP:9999999"
    with pytest.raises(ValueError, match="assertion identity"):
        build_candidate_graph([forward, spoofed_id], snapshot)


def test_optimuskg_official_from_to_columns_and_explicit_direction_are_preserved():
    snapshot = snapshot_entry("optimuskg", "parquet", SHA_B)
    row = {
        "id": "optimus:edge:1",
        "from": "MONDO:9693",
        "to": "HP:1981",
        "predicate": {
            "id": "biolink:has_phenotype",
            "label": "has phenotype",
        },
        "polarity": "affirmed",
        "direction": "source_to_target",
        "undirected": False,
        "sources": ["infores:hpo-annotations"],
        "publications": ["PMID:123456"],
        "properties": {"frequency": "frequent"},
    }
    lookup = {
        "MONDO:9693": {
            "id": "MONDO:9693",
            "label": "multiple myeloma",
            "categories": ["biolink:Disease"],
        },
        "HP:1981": {
            "id": "HP:1981",
            "label": "Schistocytosis",
            "categories": ["biolink:PhenotypicFeature"],
        },
    }
    edge = normalize_optimuskg_record(row, snapshot, node_lookup=lookup)

    assert edge["subject"]["curie"] == "MONDO:0009693"
    assert edge["object"]["curie"] == "HP:0001981"
    assert edge["predicate"]["curie"] == "biolink:has_phenotype"
    assert edge["predicate"]["canonical"] == "has_phenotype"
    assert edge["direction"] == "subject_to_object"
    assert edge["undirected"] is False
    assert edge["polarity"] == "affirmed"
    assert edge["qualifiers"] == {"frequency": "frequent"}
    assert edge["provenance"]["source_refs"] == ["infores:hpo-annotations"]
    assert edge["provenance"]["publications"] == ["PMID:123456"]


def test_candidate_graph_validates_and_cannot_embed_an_approved_edge():
    snapshot = snapshot_entry()
    edge = normalize_primekg_row(primekg_row(), snapshot)
    graph = build_candidate_graph(
        [edge],
        snapshot,
        local_concept_ids=["multiple_myeloma"],
        external_curie_seeds=["MONDO:0009693"],
        relation_allowlist=["presents_with"],
        max_hops=1,
        generated_at="2026-07-13T01:02:00Z",
    )
    validate("external_kg_candidate_graph.schema.json", graph)
    assert graph["stats"]["node_count"] == 2
    assert graph["stats"]["edge_count"] == 1
    assert graph["stats"]["counts_by_predicate"] == {"presents_with": 1}

    unsafe = deepcopy(graph)
    unsafe["edges"][0]["review"]["student_visible"] = True
    with pytest.raises(jsonschema.ValidationError):
        validate("external_kg_candidate_graph.schema.json", unsafe)
    with pytest.raises(ValueError, match="fail-closed"):
        build_candidate_graph(unsafe["edges"], snapshot)


def test_adapter_requires_pinned_snapshot_hash_and_license():
    missing_hash = snapshot_entry()
    missing_hash["artifact"]["content_sha256"] = ""
    with pytest.raises(ValueError, match="artifact_sha256"):
        normalize_primekg_row(primekg_row(), missing_hash)

    missing_license = snapshot_entry()
    missing_license["license"]["name"] = ""
    with pytest.raises(ValueError, match="license"):
        normalize_primekg_row(primekg_row(), missing_license)


def test_validation_report_encodes_absence_as_not_contradiction():
    snapshot = snapshot_entry()
    edge = normalize_primekg_row(primekg_row(), snapshot)
    graph = build_candidate_graph(
        [edge],
        snapshot,
        generated_at="2026-07-13T01:02:00Z",
    )
    report = {
        "schema_version": "external_kg_validation_report.v1",
        "report_id": f"external_kg_validation:primekg_pilot:{'2' * 16}",
        "generated_at": "2026-07-13T01:03:00Z",
        "candidate_graph_refs": [
            {
                "graph_id": graph["graph_id"],
                "snapshot_id": snapshot["snapshot_id"],
                "artifact_sha256": SHA_A,
            }
        ],
        "local_ontology_snapshot_sha256": SHA_B,
        "interpretation_policy": {
            "absence_is_not_contradiction": True,
            "review": deepcopy(FAIL_CLOSED_REVIEW),
        },
        "stats": {
            "item_count": 2,
            "externally_concordant": 0,
            "external_conflict_candidate": 1,
            "local_only_not_disproven": 1,
            "external_new_candidate": 0,
            "evaluated_exact_mapping": 2,
            "not_evaluable_grouped_mapping": 0,
            "not_evaluable_missing_mapping": 0,
            "all_needs_review": True,
        },
        "items": [
            {
                "validation_item_id": f"ekg:v:{'3' * 24}",
                "classification": "external_conflict_candidate",
                "evaluation_status": "evaluated_exact_mapping",
                "coverage_reason": "external_edge_present",
                "local_concept_id": "multiple_myeloma",
                "local_finding_id": "finding_schistocytosis",
                "local_finding_label": "Schistocytosis",
                "hpo_curie": "HP:0001981",
                "local_claim_ids": ["c:axis_relation:synthetic"],
                "candidate_edge_ids": [edge["candidate_edge_id"]],
                "external_polarities": ["negated"],
                "external_subject_curie": "MONDO:0009693",
                "external_predicate": "presents_with",
                "external_object_curie": "HP:0001981",
                "explanation": "External negation conflicts with the local present finding; review required.",
                "absence_is_not_contradiction": True,
                "review": deepcopy(FAIL_CLOSED_REVIEW),
            },
            {
                "validation_item_id": f"ekg:v:{'4' * 24}",
                "classification": "local_only_not_disproven",
                "evaluation_status": "evaluated_exact_mapping",
                "coverage_reason": "exact_mapping_no_external_edge",
                "local_concept_id": "multiple_myeloma",
                "local_finding_id": "finding_rouleaux",
                "local_finding_label": "Rouleaux formation",
                "hpo_curie": None,
                "local_claim_ids": ["c:axis_relation:local_only"],
                "candidate_edge_ids": [],
                "external_polarities": [],
                "external_subject_curie": None,
                "external_predicate": None,
                "external_object_curie": None,
                "explanation": "The snapshot has no matching edge; absence is not a contradiction.",
                "absence_is_not_contradiction": True,
                "review": deepcopy(FAIL_CLOSED_REVIEW),
            },
        ],
    }
    validate("external_kg_validation_report.schema.json", report)

    unsafe = deepcopy(report)
    unsafe["items"][1]["absence_is_not_contradiction"] = False
    with pytest.raises(jsonschema.ValidationError):
        validate("external_kg_validation_report.schema.json", unsafe)

    missing_edge = deepcopy(report)
    missing_edge["items"][1]["classification"] = "external_new_candidate"
    with pytest.raises(jsonschema.ValidationError):
        validate("external_kg_validation_report.schema.json", missing_edge)

    false_concordance = deepcopy(report)
    false_concordance["items"][0]["classification"] = "externally_concordant"
    with pytest.raises(jsonschema.ValidationError):
        validate("external_kg_validation_report.schema.json", false_concordance)
