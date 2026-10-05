import csv
import json
from pathlib import Path

import jsonschema
import pytest

from scripts.build_primekg_heme_phenotype_pilot import (
    DEFAULT_HEME_ONC_CONCEPT_IDS,
    PROFILE_HEME_ONC_FULL,
    build_heme_onc_scope_audit,
    build_pilot,
    load_concept_list,
)


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def write_fixture(tmp_path: Path):
    concept_registry = tmp_path / "concept_registry.json"
    finding_registry = tmp_path / "finding_registry.json"
    nodes_path = tmp_path / "nodes.tab"
    edges_path = tmp_path / "edges.csv"
    write_json(
        concept_registry,
        {
            "concepts": {
                "concept_a": {
                    "aliases": ["질환 A", "Disease A"],
                    "source": "heme_onc_curriculum_expansion",
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
                        "harrison": {"part": 4, "chapter": 113, "title": "Lymphoma"},
                        "ontology_xref": {
                            "mondo_id": "MONDO:0000456",
                            "mondo_label": "grouped disease",
                            "name_match": "exact",
                        }
                    },
                },
                "concept_missing": {
                    "aliases": ["Missing disease"],
                    "specialty": "혈액내과",
                    "evidence": {
                        "ontology_xref": {
                            "mondo_id": "MONDO:0000999",
                            "mondo_label": "missing disease",
                            "name_match": "exact",
                        }
                    },
                },
                "concept_outside": {
                    "aliases": ["Outside disease"],
                    "source": "differential_bridge_expansion",
                    "specialty": "신경과",
                    "evidence": {
                        "harrison": {"part": 13, "chapter": 438, "title": "Neurology"},
                        "ontology_xref": {
                            "mondo_id": "MONDO:0000888",
                            "mondo_label": "outside disease",
                            "name_match": "exact",
                        },
                    },
                },
                "concept_no_mondo": {
                    "aliases": ["No MONDO heme disease"],
                    "source": "heme_onc_curriculum_expansion",
                    "evidence": {},
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
        writer.writerow(["node_index", "node_id", "node_type", "node_name", "node_source"])
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
    return concept_registry, finding_registry, nodes_path, edges_path


def run_fixture(tmp_path: Path, output_name: str = "out"):
    concept_registry, finding_registry, nodes_path, edges_path = write_fixture(tmp_path)
    output_dir = tmp_path / output_name
    build_pilot(
        concept_registry_path=concept_registry,
        finding_registry_path=finding_registry,
        nodes_path=nodes_path,
        edges_path=edges_path,
        output_dir=output_dir,
        selected_ids=["concept_a", "concept_grouped"],
        verify_official_checksums=False,
    )
    return output_dir


def test_default_pilot_is_fixed_twenty_concepts():
    assert len(DEFAULT_HEME_ONC_CONCEPT_IDS) == 20
    assert DEFAULT_HEME_ONC_CONCEPT_IDS == sorted(DEFAULT_HEME_ONC_CONCEPT_IDS)


def test_exact_mondo_only_reverse_dedupe_and_provenance(tmp_path):
    output = run_fixture(tmp_path)
    crosswalk = json.loads((output / "heme_onc_mondo_crosswalk.json").read_text(encoding="utf-8"))
    graph = json.loads((output / "heme_onc_phenotype_candidate_graph.json").read_text(encoding="utf-8"))
    mappings = {row["local_concept_id"]: row for row in crosswalk["mappings"]}
    assert mappings["concept_a"]["external_curie"] == "MONDO:0000123"
    assert mappings["concept_a"]["mapping_relation"] == "close_match"
    assert mappings["concept_a"]["mapping_method"] == "identifier_exact"
    assert "curie_exact_name_close" in mappings["concept_a"]["evidence"][0]["note"]
    assert mappings["concept_grouped"]["mapping_relation"] == "member_of_group"
    assert mappings["concept_grouped"]["mapping_method"] == "group_member_candidate"

    assert len(graph["edges"]) == 4
    assert graph["stats"]["edge_count"] == 4
    assert graph["scope"]["relation_allowlist"] == ["presents_with"]
    assert {edge["subject"]["curie"] for edge in graph["edges"]} == {"MONDO:0000123"}
    assert {edge["predicate"]["canonical"] for edge in graph["edges"]} == {"presents_with"}
    assert {edge["polarity"] for edge in graph["edges"]} == {"affirmed", "negated"}
    for edge in graph["edges"]:
        assert edge["candidate_edge_id"].startswith("ekg:e:")
        assert edge["direction"] == "undirected"
        assert edge["undirected"] is True
        assert edge["subject"]["source_local_id"] == "123"
        assert edge["object"]["source_local_id"] in {"1", "2", "3", "6"}
        assert edge["qualifiers"]["verification_status"] == "unverified"
        source = edge["qualifiers"]["primekg_source_record"]
        assert source["reverse_row_observed"] is True
        assert source["observed_orientations"] == [
            "disease_to_phenotype",
            "phenotype_to_disease",
        ]
        assert edge["review"]["status"] == "external_candidate"
        assert edge["review"]["medical_approval"] is False
        assert edge["review"]["student_visible"] is False
        assert edge["review"]["analytics_eligible"] is False
        assert edge["review"]["promotion_status"] == "not_promoted"


def test_second_pass_validation_classifies_union_without_treating_absence_as_conflict(tmp_path):
    output = run_fixture(tmp_path)
    report = json.loads((output / "heme_onc_validation_report.json").read_text(encoding="utf-8"))
    by_hpo = {row["hpo_curie"]: row for row in report["items"]}
    assert by_hpo["HP:0000001"]["classification"] == "externally_concordant"
    assert by_hpo["HP:0000002"]["classification"] == "external_conflict_candidate"
    assert by_hpo["HP:0000003"]["classification"] == "external_new_candidate"
    assert by_hpo["HP:0000004"]["classification"] == "local_only_not_disproven"
    assert by_hpo["HP:0000005"]["classification"] == "local_only_not_disproven"
    assert by_hpo["HP:0000006"]["classification"] == "external_new_candidate"
    assert by_hpo["HP:0000004"]["candidate_edge_ids"] == []
    assert by_hpo["HP:0000004"]["absence_is_not_contradiction"] is True
    assert by_hpo["HP:0000004"]["evaluation_status"] == "evaluated_exact_mapping"
    assert by_hpo["HP:0000004"]["coverage_reason"] == "exact_mapping_no_external_edge"
    assert by_hpo["HP:0000005"]["evaluation_status"] == "not_evaluable_grouped_mapping"
    assert by_hpo["HP:0000005"]["coverage_reason"] == "grouped_mapping_excluded"
    assert by_hpo["HP:0000001"]["local_finding_id"] == "fever"
    assert by_hpo["HP:0000001"]["candidate_edge_ids"]
    assert by_hpo["HP:0000001"]["external_polarities"] == ["affirmed"]
    assert by_hpo["HP:0000002"]["external_polarities"] == ["negated"]
    assert by_hpo["HP:0000006"]["external_polarities"] == ["negated"]
    assert "not a new positive finding candidate" in by_hpo["HP:0000006"]["explanation"]
    assert by_hpo["HP:0000001"]["external_subject_curie"] == "MONDO:0000123"
    assert report["interpretation_policy"]["absence_is_not_contradiction"] is True
    assert report["interpretation_policy"]["review"]["medical_approval"] is False
    assert report["stats"] == {
        "all_needs_review": True,
        "external_conflict_candidate": 1,
        "external_new_candidate": 2,
        "evaluated_exact_mapping": 5,
        "externally_concordant": 1,
        "item_count": 6,
        "local_only_not_disproven": 2,
        "not_evaluable_grouped_mapping": 1,
        "not_evaluable_missing_mapping": 0,
    }
    for comparison in report["items"]:
        assert comparison["review"]["medical_approval"] is False
        assert comparison["review"]["student_visible"] is False
        assert comparison["review"]["analytics_eligible"] is False


def test_outputs_are_deterministic_for_same_inputs(tmp_path):
    first = run_fixture(tmp_path, "first")
    second = tmp_path / "second"
    build_pilot(
        concept_registry_path=tmp_path / "concept_registry.json",
        finding_registry_path=tmp_path / "finding_registry.json",
        nodes_path=tmp_path / "nodes.tab",
        edges_path=tmp_path / "edges.csv",
        output_dir=second,
        selected_ids=["concept_grouped", "concept_a"],
        verify_official_checksums=False,
    )
    for filename in (
        "source_manifest.json",
        "heme_onc_mondo_crosswalk.json",
        "heme_onc_phenotype_candidate_graph.json",
        "heme_onc_validation_report.json",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_official_checksum_guard_fails_closed_for_fixture(tmp_path):
    concept_registry, finding_registry, nodes_path, edges_path = write_fixture(tmp_path)
    with pytest.raises(ValueError, match="checksum mismatch"):
        build_pilot(
            concept_registry_path=concept_registry,
            finding_registry_path=finding_registry,
            nodes_path=nodes_path,
            edges_path=edges_path,
            output_dir=tmp_path / "out",
            selected_ids=["concept_a"],
            verify_official_checksums=True,
        )


def test_concept_list_accepts_json_object_and_text(tmp_path):
    json_path = tmp_path / "concepts.json"
    text_path = tmp_path / "concepts.txt"
    write_json(json_path, {"concept_ids": ["b", "a"]})
    text_path.write_text("b\n\na\n", encoding="utf-8")
    assert load_concept_list(json_path) == ["b", "a"]
    assert load_concept_list(text_path) == ["b", "a"]


def test_all_four_artifacts_validate_against_source_neutral_schemas(tmp_path):
    output = run_fixture(tmp_path)
    pairs = {
        "source_manifest.json": "external_kg_snapshot_manifest.schema.json",
        "heme_onc_mondo_crosswalk.json": "external_kg_crosswalk.schema.json",
        "heme_onc_phenotype_candidate_graph.json": "external_kg_candidate_graph.schema.json",
        "heme_onc_validation_report.json": "external_kg_validation_report.schema.json",
    }
    for artifact_name, schema_name in pairs.items():
        artifact = json.loads((output / artifact_name).read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
        jsonschema.validate(artifact, schema)

    manifest = json.loads((output / "source_manifest.json").read_text(encoding="utf-8"))
    crosswalk = json.loads((output / "heme_onc_mondo_crosswalk.json").read_text(encoding="utf-8"))
    graph = json.loads((output / "heme_onc_phenotype_candidate_graph.json").read_text(encoding="utf-8"))
    snapshots = {row["dataset_name"]: row for row in manifest["snapshots"]}
    assert set(snapshots) == {
        "PrimeKG nodes.csv",
        "PrimeKG edges.csv",
        "PrimeKG nodes+edges logical bundle",
    }
    nodes_snapshot = snapshots["PrimeKG nodes.csv"]
    bundle_snapshot = snapshots["PrimeKG nodes+edges logical bundle"]
    assert crosswalk["source_snapshots"] == [
        {
            "snapshot_id": nodes_snapshot["snapshot_id"],
            "artifact_sha256": nodes_snapshot["artifact"]["content_sha256"],
        }
    ]
    assert graph["snapshot"]["snapshot_id"] == bundle_snapshot["snapshot_id"]
    assert graph["snapshot"]["artifact_sha256"] == bundle_snapshot["artifact"]["content_sha256"]


def test_heme_onc_full_profile_audits_scope_and_remains_fail_closed(tmp_path):
    concept_registry, finding_registry, nodes_path, edges_path = write_fixture(tmp_path)
    concepts = json.loads(concept_registry.read_text(encoding="utf-8"))["concepts"]
    selected, scope_audit = build_heme_onc_scope_audit(concepts)
    assert selected == ["concept_a", "concept_grouped", "concept_missing"]

    output = tmp_path / "heme_onc_full"
    build_pilot(
        concept_registry_path=concept_registry,
        finding_registry_path=finding_registry,
        nodes_path=nodes_path,
        edges_path=edges_path,
        output_dir=output,
        selected_ids=selected,
        verify_official_checksums=False,
        selection_rule="test_heme_onc_full_scope",
        profile=PROFILE_HEME_ONC_FULL,
        scope_audit=scope_audit,
    )

    for filename in (
        "source_manifest.json",
        "heme_onc_mondo_crosswalk.json",
        "heme_onc_phenotype_candidate_graph.json",
        "heme_onc_validation_report.json",
    ):
        schema_name = {
            "source_manifest.json": "external_kg_snapshot_manifest.schema.json",
            "heme_onc_mondo_crosswalk.json": "external_kg_crosswalk.schema.json",
            "heme_onc_phenotype_candidate_graph.json": "external_kg_candidate_graph.schema.json",
            "heme_onc_validation_report.json": "external_kg_validation_report.schema.json",
        }[filename]
        jsonschema.validate(
            json.loads((output / filename).read_text(encoding="utf-8")),
            json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8")),
        )

    audit = json.loads((output / "heme_onc_scope_audit.json").read_text(encoding="utf-8"))
    by_id = {row["local_concept_id"]: row for row in audit["concepts"]}
    assert audit["stats"]["local_registry_concepts"] == 5
    assert audit["stats"]["audited_concepts"] == 5
    assert audit["stats"]["mondo_xref_universe"] == 4
    assert audit["stats"]["heme_onc_scope_signaled"] == 4
    assert audit["stats"]["heme_onc_scope_missing_valid_mondo"] == 1
    assert audit["stats"]["mondo_xref_outside_heme_onc_scope"] == 1
    assert audit["stats"]["included_concepts"] == 3
    assert audit["stats"]["excluded_audit_records"] == 2
    assert audit["stats"]["mapping_status_counts"] == {
        "exact_mondo_id": 1,
        "grouped_mondo_excluded": 1,
        "mondo_not_found": 1,
    }
    assert audit["stats"]["candidate_import_eligible"] == 1
    assert by_id["concept_a"]["inclusion_reasons"] == [
        "source:heme_onc_curriculum_expansion"
    ]
    assert by_id["concept_grouped"]["inclusion_reasons"] == [
        "harrison:part_4_oncology_and_hematology"
    ]
    assert by_id["concept_missing"]["inclusion_reasons"] == ["specialty:contains_혈액"]
    assert by_id["concept_grouped"]["graph_exclusion_reason"] == (
        "grouped_mondo_node_not_auto_merged"
    )
    assert by_id["concept_missing"]["graph_exclusion_reason"] == (
        "mondo_not_found_in_primekg_nodes"
    )
    assert by_id["concept_outside"]["included"] is False
    assert by_id["concept_outside"]["exclusion_reason"] == "no_explicit_heme_onc_scope_signal"
    assert by_id["concept_no_mondo"]["in_heme_onc_scope"] is True
    assert by_id["concept_no_mondo"]["has_valid_mondo_xref"] is False
    assert by_id["concept_no_mondo"]["included"] is False
    assert by_id["concept_no_mondo"]["exclusion_reason"] == (
        "local_mondo_xref_missing_or_invalid"
    )

    graph = json.loads(
        (output / "heme_onc_phenotype_candidate_graph.json").read_text(encoding="utf-8")
    )
    assert graph["scope"]["local_concept_ids"] == selected
    assert not any(
        edge["subject"]["curie"].startswith("PACCINE:") for edge in graph["edges"]
    )
    assert {edge["subject"]["curie"] for edge in graph["edges"]} == {"MONDO:0000123"}
    assert all(edge["review"]["status"] == "external_candidate" for edge in graph["edges"])
    assert all(edge["review"]["medical_approval"] is False for edge in graph["edges"])

    crosswalk = json.loads((output / "heme_onc_mondo_crosswalk.json").read_text(encoding="utf-8"))
    assert crosswalk["crosswalk_id"] == "external_kg_crosswalk:primekg_heme_onc_full_v1"
    assert {row["local_concept_id"] for row in crosswalk["mappings"]} == {
        "concept_a",
        "concept_grouped",
    }
    assert (output / "README.md").exists()


def test_heme_onc_full_profile_requires_scope_audit(tmp_path):
    concept_registry, finding_registry, nodes_path, edges_path = write_fixture(tmp_path)
    with pytest.raises(ValueError, match="requires a machine-readable scope_audit"):
        build_pilot(
            concept_registry_path=concept_registry,
            finding_registry_path=finding_registry,
            nodes_path=nodes_path,
            edges_path=edges_path,
            output_dir=tmp_path / "out",
            selected_ids=["concept_a"],
            verify_official_checksums=False,
            profile=PROFILE_HEME_ONC_FULL,
        )
