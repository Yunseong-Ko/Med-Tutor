#!/usr/bin/env python3
"""Run the complete Harrison 22e provenance/revalidation rebuild safely."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_axis_layer, build_concept_registry
from scripts.build_harrison22_snapshot import DEFAULT_SOURCE, build_snapshot
from scripts.normalize_harrison22_mapping_provenance import normalize as normalize_mapping_provenance
from scripts.revalidate_ontology_harrison22 import build as build_revalidation


OUTPUT = ROOT / "data_private" / "harrison" / "22e"
BASELINE_IDENTITY = OUTPUT / "baseline" / "claim_identity_snapshot.json"
NEO4J_NODES = ROOT / "data_private" / "neo4j_import" / "nodes.csv"
NEO4J_RELATIONSHIPS = ROOT / "data_private" / "neo4j_import" / "relationships.csv"
EXPECTED_PBBM_DISEASES = {
    "cold_agglutinin_disease",
    "g6pd_deficiency",
    "lead_poisoning",
    "non_megaloblastic_macrocytosis",
    "sickle_cell_disease",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_axis() -> dict:
    payload = build_axis_layer.build()
    build_axis_layer.OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def load_or_capture_baseline_claims() -> dict:
    """Preserve the pre-rebuild claim IDs from the still-current Neo4j export."""

    if BASELINE_IDENTITY.exists():
        return json.loads(BASELINE_IDENTITY.read_text(encoding="utf-8"))
    if not NEO4J_NODES.exists() or not NEO4J_RELATIONSHIPS.exists():
        return {"claim_ids": [], "nodes": {}, "relationships": {}}
    nodes: dict[str, dict] = {}
    relationships: dict[str, dict] = {}
    with NEO4J_NODES.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            cid = str(row.get("claim_id") or "")
            if cid.startswith("c:axis_node:"):
                nodes[cid] = {
                    "axis_id": row.get("id"),
                    "axis_type": row.get("axis_type"),
                    "label": row.get("name"),
                }
    with NEO4J_RELATIONSHIPS.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            cid = str(row.get("claim_id") or "")
            if cid.startswith("c:axis_relation:"):
                relationships[cid] = {
                    "start": row.get("start"),
                    "end": row.get("end"),
                    "relation": row.get("relation"),
                }
    payload = {
        "schema_version": "ontology_claim_identity_snapshot.v1",
        "source": "pre-rebuild Neo4j derived export",
        "claim_ids": sorted([*nodes, *relationships]),
        "nodes": nodes,
        "relationships": relationships,
    }
    BASELINE_IDENTITY.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_IDENTITY.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def expected_pbbm_source_sync(
    added: set[str], removed: set[str], axis: dict, baseline: dict
) -> bool:
    nodes = {row["claim_id"]: row for row in axis.get("nodes") or []}
    edges = {row["claim_id"]: row for row in axis.get("relationships") or []}
    for cid in added:
        if cid in nodes:
            if not set(nodes[cid].get("disease_ids") or []) <= EXPECTED_PBBM_DISEASES:
                return False
        elif cid in edges:
            if edges[cid].get("disease_concept_id") not in EXPECTED_PBBM_DISEASES:
                return False
        else:
            return False
    for cid in removed:
        row = (baseline.get("relationships") or {}).get(cid) or {}
        if row.get("start") != "d:megaloblastic_anemia":
            return False
    return bool(added or removed)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--skip-pdf-snapshot", action="store_true")
    args = parser.parse_args(argv)

    before_concepts = json.loads(build_concept_registry.OUT_REGISTRY.read_text(encoding="utf-8"))
    before_axis = json.loads(build_axis_layer.OUT.read_text(encoding="utf-8"))
    baseline_identity = load_or_capture_baseline_claims()
    before_concept_ids = set((before_concepts.get("concepts") or {}))
    current_claim_ids = {
        row["claim_id"] for row in [*(before_axis.get("nodes") or []), *(before_axis.get("relationships") or [])]
    }
    before_claim_ids = set(baseline_identity.get("claim_ids") or []) or current_claim_ids

    if not args.skip_pdf_snapshot:
        build_snapshot(args.source, OUTPUT)
    normalize_mapping_provenance()
    build_revalidation(OUTPUT, build_concept_registry.OUT_REGISTRY, build_axis_layer.OUT, OUTPUT)
    build_concept_registry.main()
    write_axis()
    # Recompute candidates against the corrected canonical provenance, then
    # rematerialize once so the registry and overlay converge.
    revalidation_summary = build_revalidation(
        OUTPUT, build_concept_registry.OUT_REGISTRY, build_axis_layer.OUT, OUTPUT
    )
    axis = write_axis()
    concepts = json.loads(build_concept_registry.OUT_REGISTRY.read_text(encoding="utf-8"))
    after_concept_ids = set((concepts.get("concepts") or {}))
    after_claim_ids = {
        row["claim_id"] for row in [*(axis.get("nodes") or []), *(axis.get("relationships") or [])]
    }
    added_claim_ids = after_claim_ids - before_claim_ids
    removed_claim_ids = before_claim_ids - after_claim_ids
    expected_source_sync = expected_pbbm_source_sync(
        added_claim_ids, removed_claim_ids, axis, baseline_identity
    )
    identities_safe = before_concept_ids == after_concept_ids and (
        before_claim_ids == after_claim_ids or expected_source_sync
    )
    report = {
        "schema_version": "harrison22_rebuild_report.v1",
        "status": (
            "complete"
            if before_claim_ids == after_claim_ids and before_concept_ids == after_concept_ids
            else "complete_with_expected_preexisting_source_sync"
            if identities_safe
            else "identity_drift"
        ),
        "snapshot_id": revalidation_summary["snapshot_id"],
        "identity_invariants": {
            "concept_ids_before": len(before_concept_ids),
            "concept_ids_after": len(after_concept_ids),
            "concept_ids_unchanged": before_concept_ids == after_concept_ids,
            "claim_ids_before": len(before_claim_ids),
            "claim_ids_after": len(after_claim_ids),
            "claim_ids_unchanged": before_claim_ids == after_claim_ids,
            "added_claim_ids": sorted(added_claim_ids),
            "removed_claim_ids": sorted(removed_claim_ids),
            "expected_pbbm_source_sync": expected_source_sync,
        },
        "safety_invariants": {
            "medical_approval_claims": axis["stats"]["medical_approval_claims"],
            "automatic_medical_approval_performed": False,
            "all_generated_claims_need_review": bool(axis["needs_review"]),
        },
        "counts": {
            "concepts": len(after_concept_ids),
            "axis_nodes": len(axis.get("nodes") or []),
            "axis_relationships": len(axis.get("relationships") or []),
            "harrison22_candidate_claims": axis["stats"]["harrison22_candidate_claims"],
        },
        "hashes": {
            "concept_registry": sha256(build_concept_registry.OUT_REGISTRY),
            "axis_registry": sha256(build_axis_layer.OUT),
            "source_manifest": sha256(OUTPUT / "snapshot_manifest.json"),
            "claim_overlay": sha256(OUTPUT / "validation" / "claim_support_overlay.json"),
        },
    }
    report_path = OUTPUT / "rebuild_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not identities_safe or axis["stats"]["medical_approval_claims"] != 0:
        raise SystemExit(json.dumps(report, ensure_ascii=False))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
