#!/usr/bin/env python3
"""Audit Ontology v1 draft readiness without reading private question text."""
from __future__ import annotations

import json
import argparse
from pathlib import Path

try:
    from scripts.generation_grounding import build_generation_grounding
except ModuleNotFoundError:
    from generation_grounding import build_generation_grounding


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
REGISTRY = DP / "concept_registry.json"
AXES = DP / "curriculum" / "axis_registry.json"
FINDINGS = DP / "curriculum" / "finding_registry.json"
CLINICAL_AXES = DP / "curriculum" / "clinical_axes_map.json"
CLINICAL_AXES_AUDIT = DP / "curriculum" / "clinical_axes_audits" / "clinical_axes_map_20260712.audit.json"
TYPED_ENTITIES = DP / "curriculum" / "typed_entity_registry.json"
HARDENING_WORKLIST = DP / "curriculum" / "ontology_hardening_worklist_20260712.json"
REVIEW_WORKLIST = DP / "curriculum" / "clinical_axis_review_worklist_20260712.json"
OUT = ROOT / "docs" / "Ontology_V1_Readiness_20260711.json"
PROBES = (
    "asthma",
    "acute_pancreatitis",
    "iron_deficiency_anemia",
    "major_depressive_disorder",
    "multiple_myeloma",
)
REQUIRED_AXIS_TYPES = {
    "symptom",
    "diagnosis",
    "pathophysiology",
    "etiology",
    "risk_factor",
    "prognosis",
    "epidemiology",
    "treatment",
    "indication",
    "contraindication",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def has_harrison(node: dict) -> bool:
    ref = (node.get("evidence") or {}).get("harrison") or {}
    return ref.get("chapter") is not None and ref.get("page") is not None


def audit() -> dict:
    registry = load(REGISTRY)
    concepts = registry.get("concepts") or {}
    typed_entities = (load(TYPED_ENTITIES).get("entities") or {}) if TYPED_ENTITIES.exists() else {}
    active_disease_ids = {
        cid
        for cid, row in concepts.items()
        if cid not in typed_entities and row.get("node_type") in {"disease", "neoplasm", "syndrome"}
    }
    classification_ids = {
        cid for cid, row in concepts.items() if cid not in typed_entities and row.get("node_type") == "category"
    }
    axes = load(AXES)
    findings = load(FINDINGS).get("findings") or []
    clinical_axes = load(CLINICAL_AXES).get("axes") or {}
    clinical_audit = load(CLINICAL_AXES_AUDIT) if CLINICAL_AXES_AUDIT.exists() else {}
    clinical_audit_summary = clinical_audit.get("summary") or {}
    axis_stats = axes.get("stats") or {}
    hardening_summary = (load(HARDENING_WORKLIST).get("summary") or {}) if HARDENING_WORKLIST.exists() else {}
    review_summary = (load(REVIEW_WORKLIST).get("summary") or {}) if REVIEW_WORKLIST.exists() else {}
    axis_claim_total = int(axis_stats.get("nodes") or 0) + int(axis_stats.get("relationships") or 0)
    entailment_counts = axis_stats.get("claim_entailment_statuses") or {}
    unverified_axis_claims = sum(
        int(count or 0)
        for status, count in entailment_counts.items()
        if status != "verified"
    )
    approved_axis_claims = int(axis_stats.get("medical_approval_claims") or 0)
    probes = []
    student_policy_probes = []
    for cid in PROBES:
        grounding = build_generation_grounding(cid, disease_concept_id=cid)
        pack = grounding.get("pack") or {}
        probes.append(
            {
                "disease_concept_id": cid,
                "matched": bool(pack),
                "evidence_available": bool(pack.get("evidence_available")),
                "distractor_pool_count": len(pack.get("distractor_pool") or []),
                "axis_node_count": int((pack.get("axis_context") or {}).get("node_count") or 0),
                "axis_types": sorted(((pack.get("axis_context") or {}).get("types") or {}).keys()),
                "draft_generation_ready": bool(pack.get("draft_generation_ready")),
            }
        )
        student_grounding = build_generation_grounding(
            cid,
            disease_concept_id=cid,
            review_policy="student_approved",
        )
        student_pack = student_grounding.get("pack") or {}
        safe_fail_closed = bool(
            student_grounding.get("review_policy") == "student_approved"
            and not student_grounding.get("fallback_general_generation")
            and (
                (student_grounding.get("blocked") and not student_pack)
                or (
                    not student_grounding.get("blocked")
                    and student_pack.get("policy_ready") is True
                    and (student_grounding.get("concept_review") or {}).get("medically_approved") is True
                )
            )
        )
        student_policy_probes.append(
            {
                "disease_concept_id": cid,
                "review_policy": student_grounding.get("review_policy"),
                "blocked": bool(student_grounding.get("blocked")),
                "block_reasons": student_grounding.get("block_reasons") or [],
                "pack_exposed": bool(student_pack),
                "general_fallback": bool(student_grounding.get("fallback_general_generation")),
                "safe_fail_closed": safe_fail_closed,
            }
        )

    connectivity_gates = {
        "concept_backbone": len(concepts) >= 573,
        "harrison_backbone": sum(has_harrison(row) for row in concepts.values()) >= 500,
        "finding_layer": len(findings) >= 196,
        "axis_layer": int(axis_stats.get("nodes") or 0) >= 10000,
        "axis_relation_layer": int(axis_stats.get("relationships") or 0) >= 12000,
        "required_axis_types": REQUIRED_AXIS_TYPES.issubset(set((axis_stats.get("types") or {}).keys())),
        "generation_probe_match": all(row["matched"] for row in probes),
        "generation_probe_axes": all(row["axis_node_count"] > 0 for row in probes),
        "generation_probe_evidence": all(row["evidence_available"] for row in probes),
        "automatic_outputs_review_gated": all(row.get("needs_review") is True for row in concepts.values()),
    }
    generation_gates = {
        "generation_probe_distractors_ge_4": all(row["distractor_pool_count"] >= 4 for row in probes),
        "generation_probe_draft_ready": all(row["draft_generation_ready"] for row in probes),
        "clinical_axis_quality_blockers_zero": int(clinical_audit_summary.get("blocking_issues") or 0) == 0,
        "axis_claim_provenance_complete": axis_claim_total > 0 and unverified_axis_claims == 0,
        "approved_claim_subset_available": approved_axis_claims > 0,
        "medical_review_policy_enforced": all(row["safe_fail_closed"] for row in student_policy_probes),
    }
    connectivity_ready = all(connectivity_gates.values())
    draft_generation_ready = connectivity_ready and all(generation_gates.values())
    return {
        "status": "v1_connected_draft_not_generation_ready" if connectivity_ready else "v1_incomplete",
        "connectivity_ready": connectivity_ready,
        "draft_generation_ready": draft_generation_ready,
        "technical_gates_passed": draft_generation_ready,
        "medical_approval": False,
        "counts": {
            "concepts": len(concepts),
            "active_disease_concepts": len(active_disease_ids),
            "typed_entities": len(typed_entities),
            "classification_nodes": len(classification_ids),
            "harrison_mapped": sum(has_harrison(row) for row in concepts.values()),
            "findings": len(findings),
            "clinical_axes": len(clinical_axes),
            "clinical_axis_quality_blockers": int(clinical_audit_summary.get("blocking_issues") or 0),
            "axis_nodes": axis_stats.get("nodes"),
            "axis_relationships": axis_stats.get("relationships"),
            "axis_claims_total": axis_claim_total,
            "axis_claims_medically_approved": approved_axis_claims,
            "axis_claims_not_verified": unverified_axis_claims,
            "review_decisions_applied": int(axis_stats.get("review_decisions_applied") or 0),
            "axis_diseases_covered": axis_stats.get("diseases_covered"),
            "axis_types": axis_stats.get("types") or {},
            "hardening_axis_missing_groundable": hardening_summary.get("axis_missing_generation_groundable"),
            "hardening_evidence_missing_groundable": hardening_summary.get("evidence_missing_generation_groundable"),
            "hardening_distractor_pool_lt_4": hardening_summary.get("distractor_pool_lt_4"),
            "review_worklist_items": review_summary.get("review_items"),
            "review_worklist_p0": (review_summary.get("priorities") or {}).get("P0"),
        },
        "connectivity_gates": connectivity_gates,
        "generation_gates": generation_gates,
        "generation_probes": probes,
        "student_approved_policy_probes": student_policy_probes,
        "known_incomplete": [
            "All automatic concepts, axes, and relations remain needs_review drafts.",
            f"Axis claim registry contains {axis_claim_total} claims; {approved_axis_claims} are medically approved and "
            f"{unverified_axis_claims} remain without verified claim entailment.",
            f"Clinical-axis authoring is detailed for {len(clinical_axes)} diseases; derived axis coverage reaches "
            f"{axis_stats.get('diseases_covered')}/{len(active_disease_ids)} active disease-like concepts.",
            f"The full merged clinical-axis map has {int(clinical_audit_summary.get('blocking_issues') or 0)} "
            f"automated blockers and {int(clinical_audit_summary.get('warnings') or 0)} review warnings; zero blockers is not medical approval.",
            "Five scope-ambiguous umbrella concepts and four classification nodes are excluded from generation; leaf concepts remain needs_review.",
            "Pericardial mesothelioma remains low-evidence and requires specialist review before generation use.",
            "Drug/test endpoints still need controlled vocabulary IDs and human review.",
            "student_approved review policy is enforced fail-closed; with an empty decision file it intentionally exposes no ontology pack.",
            "Structure retrieval remains separate from ontology grounding.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit nonzero unless draft-generation gates pass")
    args = parser.parse_args()
    result = audit()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **result["counts"]}, ensure_ascii=False))
    if args.strict and not result["draft_generation_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
