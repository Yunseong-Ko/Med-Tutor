from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_clinical_axes_expansion import audit_document
from scripts.serve_ontology_graph import graph_payload


ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "data_private" / "curriculum"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_scope_split_concepts_are_integrated_and_parents_remain_quarantined() -> None:
    registry = load(ROOT / "data_private" / "concept_registry.json")
    patch = load(CURRICULUM / "clinical_axes_scope_split_concepts_20260712.json")
    concepts = registry["concepts"]
    assert set(patch["concepts"]).issubset(concepts)
    assert registry["_meta"]["clinical_scope_split"]["added"] == 25
    for parent_id in patch["quarantined_parents"]:
        assert concepts[parent_id]["generation_grounding_status"] == "quarantined_scope_ambiguous"
    for cid, row in patch["concepts"].items():
        integrated = concepts[cid]
        assert integrated["needs_review"] is True
        assert integrated["generation_grounding_status"] == row["generation_grounding_status"]
        assert integrated["is_a"][0]["id"] == row["parent_id"]


def test_scope_split_leaf_axes_have_authority_scoped_evidence_and_zero_blockers() -> None:
    axes_map = load(CURRICULUM / "clinical_axes_map.json")
    batch = load(CURRICULUM / "clinical_axes_scope_split_batch_20260712.json")
    worklist = load(CURRICULUM / "clinical_axes_worklist.json")
    for cid in batch["axes"]:
        integrated = axes_map["axes"][cid]
        assert integrated["needs_review"] is True
        assert integrated["evidence_refs"]
        assert all(ref["entailment_status"] == "needs_human_review" for ref in integrated["evidence_refs"])
    report = audit_document(axes_map, source="clinical_axes_map.json", worklist_data=worklist)
    assert report["summary"]["blocking_issues"] == 0
    assert report["medical_approval"] is False


def test_scope_split_parent_is_a_uses_concept_node_not_duplicate_taxonomy_node() -> None:
    graph = graph_payload()
    node_ids = {row["data"]["id"] for row in graph["nodes"]}
    assert "d:adult_diffuse_glioma_by_integrated_diagnosis" in node_ids
    assert "t:adult_diffuse_glioma_by_integrated_diagnosis" not in node_ids
    assert any(
        row["data"]["source"] == "d:glioblastoma_idh_wildtype"
        and row["data"]["target"] == "d:adult_diffuse_glioma_by_integrated_diagnosis"
        and row["data"]["relation"] == "is_a"
        for row in graph["edges"]
    )
    assert graph["stats"]["classification_nodes"] == 4
    assert graph["stats"]["typed_entities"] == 41
