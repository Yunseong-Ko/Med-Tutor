#!/usr/bin/env python3
"""Export the private ontology into a Neo4j CSV/Cypher import bundle."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

try:
    from scripts.build_typed_entity_registry import load_active_entities
    from scripts.serve_ontology_graph import (
        EXTERNAL_KG_CANDIDATES,
        MAX_EXTERNAL_NODES,
        external_candidate_overlay,
    )
except ModuleNotFoundError:  # direct script execution
    from build_typed_entity_registry import load_active_entities
    from serve_ontology_graph import EXTERNAL_KG_CANDIDATES, MAX_EXTERNAL_NODES, external_candidate_overlay


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
REGISTRY = DP / "concept_registry.json"
FINDINGS = DP / "curriculum" / "finding_registry.json"
AXES = DP / "curriculum" / "axis_registry.json"
TYPED_ENTITIES = DP / "curriculum" / "typed_entity_registry.json"
DEFAULT_OUT = DP / "neo4j_import"
IMAGE = "neo4j:2026.05.0"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def label(node: dict, fallback: str) -> str:
    for alias in node.get("aliases", []):
        if any("가" <= ch <= "힣" for ch in str(alias)):
            return str(alias)
    return fallback.replace("_", " ")


def rel_type(value: str) -> str:
    return re.sub(r"[^A-Z0-9_]+", "_", value.upper())


def export(
    out: Path,
    *,
    external_candidates: Path | None = None,
    external_limit: int = MAX_EXTERNAL_NODES,
) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(exist_ok=True)
    if external_candidates is None:
        # An opt-in export may have populated these files in the same output
        # directory.  Remove them on a canonical-only rebuild so stale
        # candidates cannot be mistaken for the current bundle.
        for stale_name in ("external_nodes.csv", "external_candidate_relationships.csv"):
            (out / stale_name).unlink(missing_ok=True)
    registry = load(REGISTRY)
    all_concepts = registry["concepts"]
    typed_entities = load_active_entities(TYPED_ENTITIES)
    concepts = {cid: row for cid, row in all_concepts.items() if cid not in typed_entities}
    finding_rows = load(FINDINGS).get("findings", [])
    findings = {row["finding_id"]: row for row in finding_rows}
    axis_payload = load(AXES) if AXES.exists() else {"nodes": [], "relationships": []}

    nodes: dict[str, dict] = {}
    for cid, node in concepts.items():
        evidence = node.get("evidence") or {}
        h = evidence.get("harrison") or {}
        x = evidence.get("ontology_xref") or {}
        nodes[f"d:{cid}"] = {
            "id": f"d:{cid}", "concept_id": cid, "name": label(node, cid),
            "kind": "classification" if node.get("node_type") == "category" else "disease",
            "node_type": node.get("node_type") or "disease", "specialty": node.get("specialty") or "",
            "source": node.get("source") or "", "harrison_chapter": h.get("chapter") or "",
            "harrison_page": h.get("page") or "", "harrison_title": h.get("title") or "",
            "mondo_id": x.get("mondo_id") or "", "needs_review": "true",
            "clinical_axes": str(bool(node.get("clinical_axes"))).lower(),
            "axis_type": "", "dimension": "",
        }
    for cid, row in typed_entities.items():
        entity_id = row["entity_id"]
        nodes[entity_id] = {
            "id": entity_id, "concept_id": cid, "name": row.get("label") or cid.replace("_", " "),
            "kind": row.get("entity_type") or "typed_entity",
            "node_type": row.get("entity_type") or "typed_entity",
            "specialty": row.get("destination_layer") or "", "source": "typed_entity_registry",
            "harrison_chapter": "", "harrison_page": "", "harrison_title": "", "mondo_id": "",
            "needs_review": "true", "clinical_axes": "false", "axis_type": "",
            "dimension": row.get("entity_subtype") or "",
        }
    for fid, row in findings.items():
        nodes[f"f:{fid}"] = {
            "id": f"f:{fid}", "concept_id": fid, "name": row.get("hpo_label") or fid.replace("_", " "),
            "kind": "finding", "node_type": "finding", "specialty": row.get("body_system") or "",
            "source": row.get("source") or "", "harrison_chapter": "", "harrison_page": "",
            "harrison_title": "", "mondo_id": row.get("hpo_id") or "", "needs_review": "true",
            "clinical_axes": "false",
            "axis_type": "", "dimension": "symptom_or_finding",
        }
    for row in axis_payload.get("nodes", []):
        aid = row["axis_id"]
        nodes[aid] = {
            "id": aid, "concept_id": row.get("canonical_id") or aid,
            "name": row.get("label") or aid, "kind": row.get("axis_type") or "axis",
            "node_type": row.get("axis_type") or "axis", "specialty": "",
            "source": ",".join(row.get("sources") or []), "harrison_chapter": "",
            "harrison_page": "", "harrison_title": "", "mondo_id": "",
            "needs_review": "true", "clinical_axes": "false",
            "axis_type": row.get("axis_type") or "axis", "dimension": row.get("dimension") or "",
            "claim_id": row.get("claim_id") or "",
            "review_status": row.get("review_status") or "draft_unreviewed",
            "medical_approval": str(bool(row.get("medical_approval"))).lower(),
            "applicability": row.get("applicability") or "unknown",
            "claim_entailment": (row.get("provenance") or {}).get("claim_entailment") or "unverified",
        }

    relationships: dict[tuple[str, str, str], dict] = {}
    for cid, node in concepts.items():
        start = f"d:{cid}"
        for parent in node.get("is_a", []):
            tid = parent["id"]
            if tid in concepts:
                key = f"d:{tid}"
                relation_source = parent.get("source") or "ontology"
            else:
                key = f"t:{tid}"
                relation_source = "MONDO"
                nodes.setdefault(key, {
                    "id": key, "concept_id": tid, "name": parent.get("label") or tid, "kind": "taxonomy",
                    "node_type": "taxonomy", "specialty": "MONDO", "source": "MONDO", "harrison_chapter": "",
                    "harrison_page": "", "harrison_title": "", "mondo_id": tid, "needs_review": "true",
                    "clinical_axes": "false",
                    "axis_type": "", "dimension": "taxonomy",
                })
            relationships[(start, key, "IS_A")] = {
                "start": start, "end": key, "relation": "IS_A", "source": relation_source
            }

        for relation, values in (node.get("edges") or {}).items():
            rtype = rel_type(relation)
            for edge in values if isinstance(values, list) else []:
                target = edge.get("id") if isinstance(edge, dict) else edge
                if target in concepts:
                    end = f"d:{target}"
                elif target in typed_entities:
                    end = typed_entities[target]["entity_id"]
                elif target in findings:
                    end = f"f:{target}"
                else:
                    continue
                relationships[(start, end, rtype)] = {
                    "start": start, "end": end, "relation": rtype,
                    "source": edge.get("source", "ontology") if isinstance(edge, dict) else "ontology",
                }

    for fid, row in findings.items():
        for cid in row.get("presented_by", []):
            if cid in concepts:
                relationships[(f"d:{cid}", f"f:{fid}", "PRESENTS_WITH")] = {
                    "start": f"d:{cid}", "end": f"f:{fid}", "relation": "PRESENTS_WITH", "source": "finding_registry"
                }

    for row in axis_payload.get("relationships", []):
        start = f"d:{row.get('disease_concept_id')}"
        end = row.get("axis_id")
        rtype = rel_type(row.get("relation") or "")
        if start in nodes and end in nodes and rtype:
            relationships[(start, end, rtype)] = {
                "start": start, "end": end, "relation": rtype,
                "source": row.get("source") or "axis_registry",
                "claim_id": row.get("claim_id") or "",
                "review_status": row.get("review_status") or "draft_unreviewed",
                "medical_approval": str(bool(row.get("medical_approval"))).lower(),
                "applicability": row.get("applicability") or "unknown",
                "claim_entailment": (row.get("provenance") or {}).get("claim_entailment") or "unverified",
            }

    node_fields = ["id", "concept_id", "name", "kind", "node_type", "specialty", "source", "harrison_chapter", "harrison_page", "harrison_title", "mondo_id", "needs_review", "clinical_axes", "axis_type", "dimension", "claim_id", "review_status", "medical_approval", "applicability", "claim_entailment"]
    with (out / "nodes.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=node_fields)
        writer.writeheader()
        writer.writerows(nodes[key] for key in sorted(nodes))
    with (out / "relationships.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["start", "end", "relation", "source", "claim_id", "review_status", "medical_approval", "applicability", "claim_entailment"])
        writer.writeheader()
        writer.writerows(relationships[key] for key in sorted(relationships))

    external_overlay = None
    if external_candidates is not None:
        external_overlay = external_candidate_overlay(
            concepts,
            path=external_candidates,
            limit=external_limit,
        )
        external_node_fields = [
            "id", "external_id", "name", "node_type", "source", "review_status",
            "medical_approval", "claim_entailment", "needs_review",
        ]
        with (out / "external_nodes.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=external_node_fields)
            writer.writeheader()
            for row in external_overlay["nodes"]:
                data = row["data"]
                writer.writerow({
                    "id": data["id"],
                    "external_id": data["external_id"],
                    "name": data["label"],
                    "node_type": data["node_type"],
                    "source": data["source"],
                    "review_status": "external_candidate",
                    "medical_approval": "false",
                    "claim_entailment": "unverified",
                    "needs_review": "true",
                })
        external_edge_fields = [
            "start", "end", "relation", "candidate_predicate", "candidate_edge_id",
            "candidate_source", "polarity", "direction", "undirected", "provenance",
            "snapshot_id", "artifact_sha256", "source_record_id", "source_record_sha256",
            "license", "redistribution_status", "source_url",
            "review_status", "medical_approval", "claim_entailment",
        ]
        with (out / "external_candidate_relationships.csv").open(
            "w", newline="", encoding="utf-8"
        ) as fh:
            writer = csv.DictWriter(fh, fieldnames=external_edge_fields)
            writer.writeheader()
            for row in external_overlay["edges"]:
                data = row["data"]
                writer.writerow({
                    "start": data["source"],
                    "end": data["target"],
                    "relation": "EXTERNAL_CANDIDATE",
                    "candidate_predicate": data.get("candidate_predicate") or "",
                    "candidate_edge_id": data.get("candidate_edge_id") or "",
                    "candidate_source": data.get("candidate_source") or "",
                    "polarity": data.get("polarity") or "unknown",
                    "direction": data.get("direction") or "unknown",
                    "undirected": str(bool(data.get("undirected"))).lower(),
                    "provenance": data.get("provenance") or "",
                    "snapshot_id": data.get("snapshot_id") or "",
                    "artifact_sha256": data.get("artifact_sha256") or "",
                    "source_record_id": data.get("source_record_id") or "",
                    "source_record_sha256": data.get("source_record_sha256") or "",
                    "license": data.get("license") or "",
                    "redistribution_status": data.get("redistribution_status") or "unknown",
                    "source_url": data.get("source_url") or "",
                    "review_status": "external_candidate",
                    "medical_approval": "false",
                    "claim_entailment": "unverified",
                })

    relation_types = sorted({row["relation"] for row in relationships.values()})
    cypher = [
        "CREATE CONSTRAINT ontology_node_id IF NOT EXISTS FOR (n:OntologyNode) REQUIRE n.id IS UNIQUE;",
        # A canonical-only reload must also remove an overlay imported by an
        # earlier opt-in run.  Otherwise unconnected ExternalKGNode records
        # survive and make the database appear to contain external candidates
        # even when the current export did not request them.
        "MATCH (n:ExternalKGNode) DETACH DELETE n;",
        "MATCH (n:OntologyNode) DETACH DELETE n;",
        "LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row",
        "MERGE (n:OntologyNode {id: row.id})",
        "SET n.concept_id = row.concept_id, n.name = row.name, n.kind = row.kind, n.node_type = row.node_type,",
        "    n.specialty = row.specialty, n.source = row.source, n.harrison_title = row.harrison_title,",
        "    n.mondo_id = row.mondo_id, n.needs_review = (row.needs_review = 'true'),",
        "    n.clinical_axes = (row.clinical_axes = 'true'), n.axis_type = row.axis_type, n.dimension = row.dimension,",
        "    n.claim_id = row.claim_id, n.review_status = row.review_status,",
        "    n.medical_approval = (row.medical_approval = 'true'), n.applicability = row.applicability,",
        "    n.claim_entailment = row.claim_entailment,",
        "    n.harrison_chapter = CASE WHEN row.harrison_chapter = '' THEN null ELSE toInteger(row.harrison_chapter) END,",
        "    n.harrison_page = CASE WHEN row.harrison_page = '' THEN null ELSE toInteger(row.harrison_page) END;",
    ]
    for rtype in relation_types:
        cypher.extend([
            "LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row",
            f"WITH row WHERE row.relation = '{rtype}'",
            "MATCH (a:OntologyNode {id: row.start}), (b:OntologyNode {id: row.end})",
            f"MERGE (a)-[r:{rtype}]->(b)",
            "SET r.source = row.source, r.needs_review = (row.review_status <> 'approved'),",
            "    r.claim_id = row.claim_id, r.review_status = row.review_status,",
            "    r.medical_approval = (row.medical_approval = 'true'), r.applicability = row.applicability,",
            "    r.claim_entailment = row.claim_entailment;",
        ])
    if external_overlay is not None:
        cypher.extend([
            "CREATE CONSTRAINT external_kg_node_id IF NOT EXISTS FOR (n:ExternalKGNode) REQUIRE n.id IS UNIQUE;",
            "LOAD CSV WITH HEADERS FROM 'file:///external_nodes.csv' AS row",
            "MERGE (n:ExternalKGNode {id: row.id})",
            "SET n.external_id = row.external_id, n.name = row.name, n.node_type = row.node_type,",
            "    n.source = row.source, n.review_status = 'external_candidate',",
            "    n.medical_approval = false, n.claim_entailment = 'unverified', n.needs_review = true,",
            "    n.external_candidate = true;",
            "LOAD CSV WITH HEADERS FROM 'file:///external_candidate_relationships.csv' AS row",
            "MATCH (a:OntologyNode {id: row.start}), (b:ExternalKGNode {id: row.end})",
            "MERGE (a)-[r:EXTERNAL_CANDIDATE {candidate_edge_id: row.candidate_edge_id}]->(b)",
            "SET r.candidate_predicate = row.candidate_predicate, r.candidate_source = row.candidate_source,",
            "    r.polarity = row.polarity, r.direction = row.direction,",
            "    r.undirected = (row.undirected = 'true'), r.provenance = row.provenance,",
            "    r.snapshot_id = row.snapshot_id, r.artifact_sha256 = row.artifact_sha256,",
            "    r.source_record_id = row.source_record_id, r.source_record_sha256 = row.source_record_sha256,",
            "    r.license = row.license, r.redistribution_status = row.redistribution_status,",
            "    r.source_url = row.source_url,",
            "    r.review_status = 'external_candidate', r.medical_approval = false,",
            "    r.claim_entailment = 'unverified', r.needs_review = true, r.external_candidate = true;",
        ])
    (out / "load.cypher").write_text("\n".join(cypher) + "\n", encoding="utf-8")

    compose = f"""services:
  neo4j:
    image: {IMAGE}
    container_name: med-tutor-neo4j
    restart: unless-stopped
    environment:
      NEO4J_AUTH: none
      NEO4J_server_default__listen__address: 0.0.0.0
      NEO4J_server_default__advertised__address: localhost
    ports:
      - \"127.0.0.1:7474:7474\"
      - \"127.0.0.1:7687:7687\"
    volumes:
      - ./data:/data
      - ./:/var/lib/neo4j/import
"""
    (out / "compose.yaml").write_text(compose, encoding="utf-8")
    (out / "README.md").write_text(
        "# P:accine Neo4j local bundle\n\n"
        "로컬 전용이며 인증을 끈 개발용 구성입니다. 외부 포트로 노출하지 마세요.\n\n"
        "```bash\n"
        "docker compose up -d\n"
        "docker exec -i med-tutor-neo4j cypher-shell -u neo4j -f /var/lib/neo4j/import/load.cypher\n"
        "```\n\n"
        "브라우저: http://localhost:7474\n\n"
        "```cypher\nMATCH p=(n:OntologyNode)-[r]-(m:OntologyNode) RETURN p LIMIT 300;\n```\n"
        "\n질환별 임상 축:\n\n"
        "```cypher\nMATCH p=(d:OntologyNode {concept_id:'asthma'})-[r]->(a:OntologyNode) "
        "WHERE a.axis_type <> '' RETURN p;\n```\n"
        "\n의학검토가 완료된 claim만 조회:\n\n"
        "```cypher\nMATCH p=(d:OntologyNode)-[r]->(a:OntologyNode) "
        "WHERE r.medical_approval = true AND r.claim_entailment = 'verified' RETURN p;\n```\n"
        + (
            "\n외부 2차 검증 후보(명시적으로 포함해 내보낸 경우에만 존재):\n\n"
            "```cypher\nMATCH p=(d:OntologyNode)-[:EXTERNAL_CANDIDATE]->(x:ExternalKGNode) "
            "RETURN p LIMIT 500;\n```\n\n"
            "`ExternalKGNode`와 `EXTERNAL_CANDIDATE`는 미승인 후보층이며 canonical ontology가 아닙니다.\n"
            if external_overlay is not None else ""
        ),
        encoding="utf-8",
    )
    counts = Counter(row["kind"] for row in nodes.values())
    stats = {
        "nodes": len(nodes), "relationships": len(relationships),
        "kinds": dict(counts), "types": relation_types,
    }
    if external_overlay is not None:
        stats["external_overlay"] = {
            "requested": True,
            "available": external_overlay["available"],
            "source": external_overlay["source"],
            "nodes": external_overlay["candidate_nodes"],
            "relationships": external_overlay["candidate_edges"],
            "limit": max(0, min(int(external_limit), MAX_EXTERNAL_NODES)),
            "truncated": external_overlay["truncated"],
        }
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--include-external-candidates",
        action="store_true",
        help="include the separate, unapproved external KG candidate overlay",
    )
    parser.add_argument("--external-candidates", type=Path, default=EXTERNAL_KG_CANDIDATES)
    parser.add_argument("--external-limit", type=int, default=MAX_EXTERNAL_NODES)
    args = parser.parse_args()
    stats = export(
        args.out.expanduser().resolve(),
        external_candidates=args.external_candidates.expanduser().resolve()
        if args.include_external_candidates else None,
        external_limit=args.external_limit,
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
