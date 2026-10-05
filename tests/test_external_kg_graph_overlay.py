from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts import export_ontology_neo4j, serve_ontology_graph


ROOT = Path(__file__).resolve().parents[1]
SHA256_A = "a" * 64

FAIL_CLOSED_REVIEW = {
    "status": "external_candidate",
    "needs_review": True,
    "medical_approval": False,
    "student_visible": False,
    "analytics_eligible": False,
    "promotion_status": "not_promoted",
    "reviewer_id": None,
    "reviewed_at": None,
}

SNAPSHOT = {
    "snapshot_id": "external_kg_snapshot:primekg:fixture-bundle",
    "provider": "primekg",
    "dataset_name": "PrimeKG",
    "dataset_version": "fixture",
    "artifact_sha256": SHA256_A,
    "license": "upstream-source-specific",
    "license_url": "https://example.org/license",
    "redistribution_status": "unknown",
    "source_url": "https://example.org/primekg",
}


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def local_sources(tmp_path: Path) -> dict[str, Path]:
    return {
        "registry": write_json(tmp_path / "concept_registry.json", {
            "concepts": {
                "acute_myeloid_leukemia": {
                    "aliases": ["급성 골수성 백혈병"],
                    "node_type": "disease",
                    "edges": {},
                    "evidence": {"ontology_xref": {"mondo_id": "MONDO:0018874"}},
                    "needs_review": True,
                }
            }
        }),
        "typed": write_json(tmp_path / "typed_entity_registry.json", {
            "schema_version": "1.0.0",
            "_meta": {"entity_count": 0, "excluded_disease_concept_ids": []},
            "entities": {},
        }),
        "findings": write_json(tmp_path / "finding_registry.json", {"findings": []}),
        "axes": write_json(tmp_path / "axis_registry.json", {"nodes": [], "relationships": []}),
    }


def node(curie: str, label: str, source_local_id: str, category: str) -> dict:
    return {
        "curie": curie,
        "label": label,
        "categories": [category],
        "source_namespace": "primekg",
        "source_local_id": source_local_id,
    }


def edge(index: int, subject: dict, obj: dict, predicate: str = "phenotype_present") -> dict:
    return {
        "candidate_edge_id": f"ekg:e:{index:024x}",
        "subject": subject,
        "predicate": {
            "canonical": predicate,
            "curie": None,
            "source_label": predicate,
            "source_code": None,
        },
        "object": obj,
        "polarity": "affirmed",
        "direction": "subject_to_object",
        "undirected": False,
        "qualifiers": {},
        "provenance": {
            **SNAPSHOT,
            "source_record_id": f"primekg-row-{index}",
            "source_record_sha256": f"{index:x}".zfill(64),
            "source_refs": [f"primekg-row-{index}"],
            "publications": [],
        },
        "review": dict(FAIL_CLOSED_REVIEW),
    }


def external_artifact(tmp_path: Path) -> Path:
    disease = node(
        "MONDO:0018874", "acute myeloid leukemia", "acute_myeloid_leukemia", "disease"
    )
    phenotype_1 = node("HP:0001875", "neutropenia", "334", "phenotype")
    phenotype_2 = node("HP:0001873", "thrombocytopenia", "335", "phenotype")
    # This label deliberately matches the local disease. It must not fuzzy-link without an ID.
    unknown = node("MONDO:9999999", "급성 골수성 백혈병", "unknown", "disease")
    spoofed_local_id = node(
        "MONDO:9999998", "another unrelated disease", "acute_myeloid_leukemia", "disease"
    )
    unrelated = node("HP:9999999", "unrelated finding", "999", "phenotype")
    return write_json(tmp_path / "external.json", {
        "schema_version": "external_kg_candidate_graph.v1",
        "graph_id": "external_kg_graph:primekg:1111111111111111",
        "generated_at": "2026-07-13T07:51:01Z",
        "snapshot": SNAPSHOT,
        "scope": {
            "local_concept_ids": ["acute_myeloid_leukemia"],
            "external_curie_seeds": ["MONDO:0018874"],
            "max_hops": 1,
            "relation_allowlist": ["phenotype_present"],
            "notes": "Synthetic fail-closed overlay fixture.",
        },
        "review_policy": FAIL_CLOSED_REVIEW,
        "stats": {
            "node_count": 6,
            "edge_count": 4,
            "counts_by_predicate": {"phenotype_present": 4},
            "counts_by_category": {"disease": 3, "phenotype": 3},
            "all_external_candidates": True,
        },
        "nodes": [disease, phenotype_1, phenotype_2, unknown, spoofed_local_id, unrelated],
        "edges": [
            edge(1, disease, phenotype_1),
            edge(2, disease, phenotype_2),
            edge(3, unknown, unrelated),
            edge(4, spoofed_local_id, unrelated),
        ],
    })


def patch_sources(monkeypatch, paths: dict[str, Path]) -> None:
    for module in (serve_ontology_graph, export_ontology_neo4j):
        monkeypatch.setattr(module, "REGISTRY", paths["registry"])
        monkeypatch.setattr(module, "TYPED_ENTITIES", paths["typed"])
        monkeypatch.setattr(module, "FINDINGS", paths["findings"])
        monkeypatch.setattr(module, "AXES", paths["axes"])


def test_live_graph_external_overlay_is_opt_in_capped_and_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    paths = local_sources(tmp_path)
    artifact = external_artifact(tmp_path)
    patch_sources(monkeypatch, paths)

    default_graph = serve_ontology_graph.graph_payload(external_path=artifact)
    assert {row["data"]["kind"] for row in default_graph["nodes"]} == {"disease"}
    assert "external_overlay" not in default_graph["stats"]
    assert all(row["data"]["relation"] != "EXTERNAL_CANDIDATE" for row in default_graph["edges"])

    graph = serve_ontology_graph.graph_payload(
        include_external=True, external_path=artifact, external_limit=1
    )
    external_nodes = [row["data"] for row in graph["nodes"] if row["data"]["kind"] == "external_candidate"]
    external_edges = [
        row["data"] for row in graph["edges"]
        if row["data"]["relation"] == "EXTERNAL_CANDIDATE"
    ]
    assert len(external_nodes) == 1
    assert len(external_edges) == 1
    assert external_nodes[0]["id"].startswith("external:primekg:")
    assert external_nodes[0]["id"] != "f:HP:0001875"
    assert external_nodes[0]["review_status"] == "external_candidate"
    assert external_nodes[0]["medical_approval"] is False
    assert external_nodes[0]["claim_entailment"] == "unverified"
    assert external_edges[0]["source"] == "d:acute_myeloid_leukemia"
    assert external_edges[0]["medical_approval"] is False
    assert external_edges[0]["claim_entailment"] == "unverified"
    assert external_edges[0]["snapshot_id"] == SNAPSHOT["snapshot_id"]
    assert external_edges[0]["artifact_sha256"] == SHA256_A
    assert len(external_edges[0]["source_record_sha256"]) == 64
    assert external_edges[0]["license"] == "upstream-source-specific"
    assert external_edges[0]["redistribution_status"] == "unknown"
    assert graph["stats"]["external_overlay"]["truncated"] is True
    assert graph["stats"]["external_overlay"]["candidate_nodes"] == 1
    # The matching Korean label on an unknown MONDO identifier was not used as a link.
    assert all(row["external_id"] != "HP:9999999" for row in external_nodes)


def test_malformed_or_approval_bypassing_artifact_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    paths = local_sources(tmp_path)
    artifact = external_artifact(tmp_path)
    patch_sources(monkeypatch, paths)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["edges"][0]["review"]["student_visible"] = True
    write_json(artifact, payload)

    graph = serve_ontology_graph.graph_payload(
        include_external=True, external_path=artifact
    )
    assert graph["stats"]["external_overlay"]["available"] is False
    assert graph["stats"]["external_overlay"]["candidate_nodes"] == 0
    assert all(row["data"].get("external_candidate") is not True for row in graph["nodes"])


def test_missing_external_artifact_is_safe_and_empty(tmp_path: Path) -> None:
    concepts = {
        "acute_myeloid_leukemia": {
            "evidence": {"ontology_xref": {"mondo_id": "MONDO:0018874"}}
        }
    }
    overlay = serve_ontology_graph.external_candidate_overlay(
        concepts, path=tmp_path / "missing.json"
    )
    assert overlay["available"] is False
    assert overlay["nodes"] == []
    assert overlay["edges"] == []


def test_neo4j_external_overlay_uses_separate_label_and_relationship(
    tmp_path: Path, monkeypatch
) -> None:
    paths = local_sources(tmp_path)
    artifact = external_artifact(tmp_path)
    patch_sources(monkeypatch, paths)

    canonical_out = tmp_path / "canonical"
    default_stats = export_ontology_neo4j.export(canonical_out)
    assert "external_overlay" not in default_stats
    assert not (canonical_out / "external_nodes.csv").exists()
    default_cypher = (canonical_out / "load.cypher").read_text(encoding="utf-8")
    assert "MATCH (n:ExternalKGNode) DETACH DELETE n;" in default_cypher
    assert "external_nodes.csv" not in default_cypher
    assert "EXTERNAL_CANDIDATE" not in default_cypher

    overlay_out = tmp_path / "overlay"
    stats = export_ontology_neo4j.export(
        overlay_out, external_candidates=artifact, external_limit=1
    )
    with (overlay_out / "external_nodes.csv").open(newline="", encoding="utf-8") as handle:
        node_rows = list(csv.DictReader(handle))
    with (overlay_out / "external_candidate_relationships.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        edge_rows = list(csv.DictReader(handle))
    cypher = (overlay_out / "load.cypher").read_text(encoding="utf-8")

    assert len(node_rows) == 1
    assert len(edge_rows) == 1
    assert node_rows[0]["id"].startswith("external:primekg:")
    assert node_rows[0]["medical_approval"] == "false"
    assert node_rows[0]["review_status"] == "external_candidate"
    assert edge_rows[0]["relation"] == "EXTERNAL_CANDIDATE"
    assert edge_rows[0]["medical_approval"] == "false"
    assert edge_rows[0]["snapshot_id"] == SNAPSHOT["snapshot_id"]
    assert edge_rows[0]["artifact_sha256"] == SHA256_A
    assert edge_rows[0]["license"] == "upstream-source-specific"
    assert edge_rows[0]["redistribution_status"] == "unknown"
    assert "(n:ExternalKGNode {id: row.id})" in cypher
    assert "[r:EXTERNAL_CANDIDATE" in cypher
    assert cypher.count("MATCH (n:ExternalKGNode) DETACH DELETE n;") == 1
    assert cypher.count("external_candidate_relationships.csv") == 1
    assert stats["nodes"] == 1  # canonical count remains separate
    assert stats["external_overlay"]["nodes"] == 1
    assert stats["external_overlay"]["truncated"] is True

    # Rebuilding the same directory without opt-in removes stale overlay files
    # and leaves only an explicit cleanup clause in the load script.
    export_ontology_neo4j.export(overlay_out)
    assert not (overlay_out / "external_nodes.csv").exists()
    assert not (overlay_out / "external_candidate_relationships.csv").exists()
    default_after_overlay = (overlay_out / "load.cypher").read_text(encoding="utf-8")
    assert "MATCH (n:ExternalKGNode) DETACH DELETE n;" in default_after_overlay
    assert "external_nodes.csv" not in default_after_overlay


def test_live_ui_requests_external_candidates_only_after_explicit_toggle() -> None:
    html = (ROOT / "frontend" / "ontology_graph_live.html").read_text(encoding="utf-8")
    checkbox = '<input id="external-overlay" type="checkbox">'
    assert checkbox in html
    assert "include_external=1&external_limit=500" in html
    assert '<option value="heme_onc_full">혈액종양 전체 감사</option>' in html
    assert "external_profile=" in html
    assert "/api/external-validation" in html
    assert "자동 의학승인·Ontology 편입·문항 생성·학생 노출로 이어지지 않습니다" in html
    assert "REVIEW_PAGE_SIZE=50" in html
    assert "page.has_more" in html
    assert 'class="btn queue-page"' in html
    assert "data-offset" in html
    assert 'relation="EXTERNAL_CANDIDATE"' in html
    assert 'edge[relation="EXTERNAL_CANDIDATE"][?undirected]' in html
    assert "PrimeKG 2차 검증 provenance" in html


def test_external_profile_resolution_is_allowlisted() -> None:
    name, config = serve_ontology_graph.external_profile("heme_onc_full")
    assert name == "heme_onc_full"
    assert config["candidate_graph"].name == "heme_onc_phenotype_candidate_graph.json"
    assert config["candidate_graph"].parent.name == "heme_onc_full"

    fallback_name, fallback = serve_ontology_graph.external_profile("../../private")
    assert fallback_name == "core20"
    assert fallback["candidate_graph"] == serve_ontology_graph.EXTERNAL_KG_CANDIDATES
