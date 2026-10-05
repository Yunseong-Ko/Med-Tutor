from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_axis_layer
from scripts import build_typed_entity_registry as typed_builder
from scripts import export_ontology_neo4j
from scripts import export_ontology_obsidian
from scripts import generation_grounding
from scripts import recover_typed_entity_quarantine_archive
from scripts import serve_ontology_graph


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def tiny_sources(tmp_path: Path) -> dict[str, Path]:
    registry = {
        "_meta": {"generated_at": "test"},
        "concepts": {
            "asthma": {
                "aliases": ["천식"],
                "node_type": "disease",
                "edges": {"presents_with": [{"id": "chest_pain"}]},
                "evidence": {},
                "needs_review": True,
            },
            "chest_pain": {
                "aliases": ["흉통"],
                "node_type": "disease",
                "edges": {},
                "evidence": {},
                "needs_review": True,
            },
        },
    }
    typed = {
        "schema_version": "1.0.0",
        "_meta": {
            "entity_count": 1,
            "counts_by_entity_type": {"symptom": 1},
            "excluded_disease_concept_ids": ["chest_pain"],
        },
        "entities": {
            "chest_pain": {
                "entity_id": "x:symptom:chest_pain",
                "concept_id": "chest_pain",
                "entity_type": "symptom",
                "entity_subtype": "patient_reported_finding",
                "destination_layer": "finding_registry",
                "label": "흉통",
                "reason": "shared symptom",
                "recommended_relation": {
                    "name": "presents_with",
                    "direction": "disorder -> symptom",
                    "materialized": False,
                },
                "legacy_harrison_pointer": {},
                "needs_review": True,
            }
        },
    }
    return {
        "registry": write_json(tmp_path / "concept_registry.json", registry),
        "typed": write_json(tmp_path / "typed_entity_registry.json", typed),
        "findings": write_json(tmp_path / "finding_registry.json", {"findings": []}),
        "axes": write_json(tmp_path / "axis_registry.json", {"nodes": [], "relationships": []}),
    }


def test_builds_all_41_entities_with_preserved_types() -> None:
    payload = typed_builder.build()
    meta = payload["_meta"]
    assert meta["entity_count"] == 41
    assert meta["counts_by_entity_type"] == {
        "category": 4,
        "clinical_context": 2,
        "content_format": 1,
        "exposure": 3,
        "finding": 3,
        "health_system": 9,
        "intervention": 9,
        "metric": 3,
        "symptom": 7,
    }
    assert payload["entities"]["chest_pain"]["entity_type"] == "symptom"
    assert payload["entities"]["heart_murmur"]["entity_type"] == "finding"
    assert payload["entities"]["robotic_surgery"]["entity_type"] == "intervention"
    assert payload["entities"]["video_based"]["entity_type"] == "content_format"
    assert payload["entities"]["death_certificate"]["entity_type"] == "health_system"
    assert payload["entities"]["screening"]["entity_type"] == "intervention"
    assert payload["entities"]["postmenopausal"]["entity_type"] == "clinical_context"
    assert payload["entities"]["projectile_vomiting"]["entity_type"] == "symptom"
    assert payload["entities"]["fetal_ultrasound"]["entity_type"] == "intervention"
    assert payload["entities"]["sexual_assault"]["entity_type"] == "exposure"
    assert payload["entities"]["motor_developmental_delay"]["entity_type"] == "finding"
    assert payload["entities"]["motor_developmental_delay"]["legacy_node_type"] == "syndrome"
    assert payload["entities"]["infectious_disease_control_act"]["entity_type"] == "health_system"
    assert payload["entities"]["allergic"]["entity_type"] == "category"
    assert payload["entities"]["travel"]["entity_type"] == "clinical_context"
    assert all(row["excluded_from_disease_exports"] for row in payload["entities"].values())
    assert all(not row["recommended_relation"]["materialized"] for row in payload["entities"].values())


def test_axis_builder_excludes_every_typed_entity() -> None:
    payload = build_axis_layer.build()
    typed_ids = set(typed_builder.load_active_entities())
    assert payload["stats"]["typed_entities_excluded_from_disease_axes"] == 41
    assert not typed_ids.intersection(
        row["disease_concept_id"] for row in payload["relationships"]
    )


def test_preserves_seven_existing_axis_records_in_quarantine() -> None:
    typed_payload = typed_builder.build()
    quarantine = typed_builder.build_quarantine(typed_payload)
    assert quarantine["_meta"]["quarantined_count"] == 7
    assert set(quarantine["quarantined_axes"]) == {
        "death_certificate",
        "fetal_ultrasound",
        "motor_developmental_delay",
        "postmenopausal",
        "projectile_vomiting",
        "screening",
        "sexual_assault",
    }
    for row in quarantine["quarantined_axes"].values():
        assert row["original_axes"]
        assert row["axis_layer_eligible"] is False
        assert row["generation_eligible"] is False


def test_immutable_archive_exactly_matches_original_workflow_rows() -> None:
    archive_path = typed_builder.QUARANTINE_ARCHIVE
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    workflow = json.loads(
        recover_typed_entity_quarantine_archive.DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    )
    source_rows = {
        row["id"]: row
        for row in workflow["result"]["results"]
        if row.get("id") in typed_builder.QUARANTINE_REQUIRED_IDS
    }
    assert archive["_meta"]["recovered_count"] == 7
    assert set(archive["quarantined_axes"]) == typed_builder.QUARANTINE_REQUIRED_IDS
    for concept_id, archived in archive["quarantined_axes"].items():
        assert archived["original_axes"] == source_rows[concept_id]


def test_builder_reads_but_never_mutates_immutable_archive() -> None:
    archive_path = typed_builder.QUARANTINE_ARCHIVE
    before = archive_path.read_bytes()
    payload = typed_builder.build()
    quarantine = typed_builder.build_quarantine(payload)
    after = archive_path.read_bytes()
    assert before == after
    assert quarantine["_meta"]["recovered_from_archive"] == 7
    assert quarantine["_meta"]["archive_write_policy"] == "read_only_never_overwrite"


def test_builder_refuses_zero_quarantine_when_archive_is_missing(tmp_path: Path) -> None:
    empty_axes = write_json(tmp_path / "clinical_axes_map.json", {"axes": {}})
    payload = typed_builder.build()
    with pytest.raises(ValueError, match="required quarantined clinical axes are unavailable"):
        typed_builder.build_quarantine(payload, empty_axes, tmp_path / "missing_archive.json")


def test_builder_rejects_immutable_archive_as_any_output(tmp_path: Path) -> None:
    archive = typed_builder.QUARANTINE_ARCHIVE
    with pytest.raises(ValueError, match="immutable quarantine archive"):
        typed_builder.validate_output_paths(archive, tmp_path / "live.json")
    with pytest.raises(ValueError, match="immutable quarantine archive"):
        typed_builder.validate_output_paths(tmp_path / "registry.json", archive)


def test_live_graph_replaces_disease_node_with_one_typed_node(tmp_path: Path, monkeypatch) -> None:
    paths = tiny_sources(tmp_path)
    monkeypatch.setattr(serve_ontology_graph, "REGISTRY", paths["registry"])
    monkeypatch.setattr(serve_ontology_graph, "TYPED_ENTITIES", paths["typed"])
    monkeypatch.setattr(serve_ontology_graph, "FINDINGS", paths["findings"])
    monkeypatch.setattr(serve_ontology_graph, "AXES", paths["axes"])

    payload = serve_ontology_graph.graph_payload()
    matches = [n["data"] for n in payload["nodes"] if n["data"]["concept_id"] == "chest_pain"]
    assert len(matches) == 1
    assert matches[0]["id"] == "x:symptom:chest_pain"
    assert matches[0]["kind"] == "symptom"
    assert "d:chest_pain" not in {n["data"]["id"] for n in payload["nodes"]}
    assert any(
        edge["data"]["source"] == "d:asthma"
        and edge["data"]["target"] == "x:symptom:chest_pain"
        for edge in payload["edges"]
    )
    assert payload["stats"]["diseases"] == 1
    assert payload["stats"]["typed_entities"] == 1


def test_neo4j_export_has_no_duplicate_disease_node(tmp_path: Path, monkeypatch) -> None:
    paths = tiny_sources(tmp_path)
    monkeypatch.setattr(export_ontology_neo4j, "REGISTRY", paths["registry"])
    monkeypatch.setattr(export_ontology_neo4j, "TYPED_ENTITIES", paths["typed"])
    monkeypatch.setattr(export_ontology_neo4j, "FINDINGS", paths["findings"])
    monkeypatch.setattr(export_ontology_neo4j, "AXES", paths["axes"])

    out = tmp_path / "neo4j"
    export_ontology_neo4j.export(out)
    with (out / "nodes.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    matches = [row for row in rows if row["concept_id"] == "chest_pain"]
    assert len(matches) == 1
    assert matches[0]["id"] == "x:symptom:chest_pain"
    assert matches[0]["kind"] == "symptom"
    assert not any(row["id"] == "d:chest_pain" for row in rows)


def test_obsidian_export_moves_note_out_of_diseases(tmp_path: Path, monkeypatch) -> None:
    paths = tiny_sources(tmp_path)
    monkeypatch.setattr(export_ontology_obsidian, "REGISTRY", paths["registry"])
    monkeypatch.setattr(export_ontology_obsidian, "TYPED_ENTITIES", paths["typed"])
    monkeypatch.setattr(export_ontology_obsidian, "FINDINGS", paths["findings"])
    monkeypatch.setattr(export_ontology_obsidian, "AXES", paths["axes"])

    out = tmp_path / "vault"
    stats = export_ontology_obsidian.export(out)
    assert stats["diseases"] == 1
    assert stats["typed_entities"] == 1
    assert not (out / "Diseases" / "chest_pain.md").exists()
    note = (out / "Typed Entities" / "chest_pain.md").read_text(encoding="utf-8")
    assert 'node_type: "symptom"' in note
    assert "excluded_from_disease_exports: true" in note


def test_generation_registry_does_not_match_typed_entity_as_disease(tmp_path: Path) -> None:
    paths = tiny_sources(tmp_path)
    concepts, meta = generation_grounding.load_registry(paths["registry"], paths["typed"])
    assert set(concepts) == {"asthma"}
    assert meta["source_concept_count"] == 2
    assert meta["typed_entities_excluded"] == 1
    typed = typed_builder.load_active_entities(paths["typed"])
    match = generation_grounding.match_topic_to_concept("chest pain", concepts, typed)
    assert match["status"] == "non_disease_typed_entity"
    assert match["entity_type"] == "symptom"


def test_every_active_typed_id_is_blocked_before_fuzzy_disease_matching() -> None:
    concepts, _ = generation_grounding.load_registry()
    typed = typed_builder.load_active_entities()
    for concept_id, entity in typed.items():
        match = generation_grounding.match_topic_to_concept(concept_id, concepts, typed)
        assert match["status"] == "non_disease_typed_entity", (concept_id, match)
        assert match["entity_type"] == entity["entity_type"]
