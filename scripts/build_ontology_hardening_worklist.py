#!/usr/bin/env python3
"""Build deterministic Stage X ontology hardening worklists.

The output is a review queue, not a medical correction. It summarizes where
generation lacks axes, evidence, or distractors and where endpoint typing is
still unresolved. No concept or clinical claim is approved by this script.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.build_typed_entity_registry import load_active_entities
    from scripts.generation_grounding import build_evidence_pack, is_scope_groundable, load_registry
except ModuleNotFoundError:  # direct script execution
    from build_typed_entity_registry import load_active_entities
    from generation_grounding import build_evidence_pack, is_scope_groundable, load_registry


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
CURRICULUM = DP / "curriculum"
REGISTRY_PATH = DP / "concept_registry.json"
AXIS_REGISTRY_PATH = CURRICULUM / "axis_registry.json"
TYPED_ENTITY_REGISTRY_PATH = CURRICULUM / "typed_entity_registry.json"
ENDPOINT_UNRESOLVED_PATH = CURRICULUM / "endpoint_types_unresolved.json"
CLINICAL_AUDIT_PATH = CURRICULUM / "clinical_axes_audits" / "clinical_axes_map_20260712.audit.json"
DEFAULT_OUTPUT = CURRICULUM / "ontology_hardening_worklist_20260712.json"
ACTIVE_DISEASE_TYPES = {"disease", "neoplasm", "syndrome"}
REQUIRED_GENERATION_AXIS_TYPES = {
    "symptom",
    "diagnosis",
    "pathophysiology",
    "risk_factor",
    "prognosis",
    "epidemiology",
    "treatment",
    "indication",
    "contraindication",
    "etiology",
}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def build_axis_index(axis_registry: dict[str, Any]) -> tuple[dict[str, set[str]], Counter[str]]:
    nodes = {
        str(row.get("axis_id")): row
        for row in axis_registry.get("nodes") or []
        if isinstance(row, dict) and row.get("axis_id")
    }
    disease_types: dict[str, set[str]] = defaultdict(set)
    type_diseases: dict[str, set[str]] = defaultdict(set)
    for relationship in axis_registry.get("relationships") or []:
        if not isinstance(relationship, dict):
            continue
        disease_id = str(relationship.get("disease_concept_id") or "").strip()
        node = nodes.get(str(relationship.get("axis_id") or ""))
        axis_type = str((node or {}).get("axis_type") or "").strip()
        if not disease_id or not axis_type:
            continue
        disease_types[disease_id].add(axis_type)
        type_diseases[axis_type].add(disease_id)
    return disease_types, Counter({key: len(value) for key, value in type_diseases.items()})


def generation_gap_rows(
    concepts: dict[str, Any],
    active_ids: list[str],
    disease_axis_types: dict[str, set[str]],
    *,
    axis_registry_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    missing_axis: list[dict[str, Any]] = []
    missing_evidence: list[dict[str, Any]] = []
    deficient_distractors: list[dict[str, Any]] = []
    incomplete_axis_types: list[dict[str, Any]] = []

    for concept_id in active_ids:
        concept = concepts[concept_id]
        groundable = is_scope_groundable(concept)
        axis_types = sorted(disease_axis_types.get(concept_id, set()))
        base = {
            "disease_concept_id": concept_id,
            "label": next(iter(concept.get("aliases") or []), concept_id),
            "node_type": concept.get("node_type"),
            "specialty": concept.get("specialty"),
            "generation_groundable": groundable,
            "generation_grounding_status": concept.get("generation_grounding_status") or "legacy_needs_review",
            "needs_review": True,
        }
        if not axis_types:
            missing_axis.append(
                {
                    **base,
                    "disposition": (
                        "retain_generation_quarantine_and_review_scope_split"
                        if not groundable
                        else "review_type_scope_then_author_or_mark_not_applicable"
                    ),
                }
            )
        if not groundable:
            continue

        pack = build_evidence_pack(concept_id, concepts, axis_registry_path)
        if not pack:
            continue
        if not pack.get("evidence_available"):
            missing_evidence.append({**base, "disposition": "attach_authoritative_source_before_generation"})
        distractor_count = len(pack.get("distractor_pool") or [])
        if distractor_count < 4:
            deficient_distractors.append(
                {
                    **base,
                    "distractor_pool_count": distractor_count,
                    "disposition": "author_reviewed_same_domain_distractors_required",
                }
            )

        missing_types = sorted(REQUIRED_GENERATION_AXIS_TYPES - set(axis_types))
        if missing_types:
            incomplete_axis_types.append(
                {
                    **base,
                    "present_axis_types": axis_types,
                    "missing_or_not_applicable_axis_types": missing_types,
                    "axis_applicability_status": "unknown_requires_human_review",
                }
            )

    key = lambda row: row["disease_concept_id"]
    return (
        sorted(missing_axis, key=key),
        sorted(missing_evidence, key=key),
        sorted(deficient_distractors, key=lambda row: (row["distractor_pool_count"], key(row))),
        sorted(incomplete_axis_types, key=lambda row: (-len(row["missing_or_not_applicable_axis_types"]), key(row))),
    )


def build(
    *,
    registry_path: Path = REGISTRY_PATH,
    axis_registry_path: Path = AXIS_REGISTRY_PATH,
    typed_entity_registry_path: Path = TYPED_ENTITY_REGISTRY_PATH,
    endpoint_unresolved_path: Path = ENDPOINT_UNRESOLVED_PATH,
    clinical_audit_path: Path = CLINICAL_AUDIT_PATH,
) -> dict[str, Any]:
    concepts, registry_meta = load_registry(registry_path, typed_entity_registry_path)
    typed_entities = load_active_entities(typed_entity_registry_path)
    active_ids = sorted(
        concept_id
        for concept_id, concept in concepts.items()
        if concept_id not in typed_entities and concept.get("node_type") in ACTIVE_DISEASE_TYPES
    )
    groundable_ids = [concept_id for concept_id in active_ids if is_scope_groundable(concepts[concept_id])]
    axis_registry = load_json(axis_registry_path, {"nodes": [], "relationships": [], "stats": {}})
    disease_axis_types, type_coverage = build_axis_index(axis_registry)
    missing_axis, missing_evidence, deficient_distractors, incomplete_axis_types = generation_gap_rows(
        concepts,
        active_ids,
        disease_axis_types,
        axis_registry_path=axis_registry_path,
    )

    endpoint_payload = load_json(endpoint_unresolved_path, {"items": [], "total": 0})
    unresolved_endpoints = sorted(
        (row for row in endpoint_payload.get("items") or [] if isinstance(row, dict)),
        key=lambda row: (-int(row.get("total") or 0), str(row.get("id") or "")),
    )
    audit_payload = load_json(clinical_audit_path, {"summary": {}, "issues": []})
    audit_summary = audit_payload.get("summary") or {}
    issue_codes = Counter(
        str(row.get("code") or "unknown")
        for row in audit_payload.get("issues") or []
        if isinstance(row, dict)
    )
    relationship_rows = axis_registry.get("relationships") or []
    unverified_relationships = sum(
        1
        for row in relationship_rows
        if ((row.get("provenance") or {}).get("claim_entailment") or "unverified") != "verified"
    )
    draft_nodes = sum(
        1 for row in axis_registry.get("nodes") or [] if row.get("review_status") != "approved"
    )

    return {
        "schema_version": "1.0.0",
        "status": "review_worklist_not_medical_approval",
        "generated_from": [
            relative(registry_path),
            relative(axis_registry_path),
            relative(typed_entity_registry_path),
            relative(endpoint_unresolved_path),
            relative(clinical_audit_path),
        ],
        "review_policy": {
            "automatic_medical_approval_performed": False,
            "all_rows_require_human_review": True,
            "axis_applicability_values": ["applicable", "not_applicable", "unknown_requires_human_review"],
        },
        "summary": {
            "registry_status": registry_meta.get("status"),
            "active_disease_like_concepts": len(active_ids),
            "generation_groundable_concepts": len(groundable_ids),
            "generation_quarantined_concepts": len(active_ids) - len(groundable_ids),
            "axis_diseases_covered": len(disease_axis_types),
            "axis_missing_all": len(missing_axis),
            "axis_missing_generation_groundable": sum(1 for row in missing_axis if row["generation_groundable"]),
            "evidence_missing_generation_groundable": len(missing_evidence),
            "distractor_pool_lt_4": len(deficient_distractors),
            "distractor_pool_zero": sum(1 for row in deficient_distractors if row["distractor_pool_count"] == 0),
            "axis_nodes_not_approved": draft_nodes,
            "axis_relationships_entailment_not_verified": unverified_relationships,
            "clinical_axis_review_warnings": int(audit_summary.get("warnings") or len(audit_payload.get("issues") or [])),
            "unresolved_endpoint_ids": int(endpoint_payload.get("total") or len(unresolved_endpoints)),
        },
        "axis_type_disease_coverage": dict(sorted(type_coverage.items())),
        "clinical_issue_codes": dict(sorted(issue_codes.items())),
        "worklists": {
            "axis_missing": missing_axis,
            "evidence_missing": missing_evidence,
            "distractor_pool_lt_4": deficient_distractors,
            "axis_type_applicability_review": incomplete_axis_types,
            "endpoint_typing": unresolved_endpoints,
        },
    }


def write_or_check(payload: dict[str, Any], output: Path, *, check: bool) -> bool:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if check:
        return output.exists() and output.read_text(encoding="utf-8") == rendered
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build()
    ok = write_or_check(payload, args.output, check=args.check)
    if not ok:
        raise SystemExit(f"hardening_worklist_mismatch: {args.output}")
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
