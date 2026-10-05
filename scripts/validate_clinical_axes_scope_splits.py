#!/usr/bin/env python3
"""Validate quarantined-umbrella split candidates without merging or approval."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "data_private" / "curriculum"
DEFAULT_QUARANTINE = CURRICULUM / "clinical_axes_scope_quarantine_20260712.json"
DEFAULT_CONCEPTS = CURRICULUM / "clinical_axes_scope_split_concepts_20260712.json"
DEFAULT_BATCH = CURRICULUM / "clinical_axes_scope_split_batch_20260712.json"

ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
PRECISE_EPI = re.compile(r"\d+(?:\.\d+)?\s*%|\b\d+\s*:\s*\d+\b|\bper\s+\d+", re.I)
REQUIRED_AXES = ("pathophysiology", "risk_factors", "prognosis", "treatment", "epidemiology")
CLASSIFICATION_ONLY = "classification_only"
DISEASE_LIKE = {"disease", "neoplasm"}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be an object")
    return value


def _issue(
    issues: list[dict[str, Any]],
    code: str,
    severity: str,
    message: str,
    *,
    entity_id: str | None = None,
) -> None:
    row: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "blocking": severity == "error",
        "message": message,
    }
    if entity_id:
        row["id"] = entity_id
    issues.append(row)


def _source_ids(pointers: object) -> list[str]:
    if not isinstance(pointers, list):
        return []
    result: list[str] = []
    for pointer in pointers:
        if isinstance(pointer, str):
            result.append(pointer)
        elif isinstance(pointer, dict) and isinstance(pointer.get("source_id"), str):
            result.append(pointer["source_id"])
    return result


def _find_cycle(concepts: dict[str, dict[str, Any]]) -> list[str] | None:
    for start in concepts:
        path: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in concepts:
            if current in positions:
                return path[positions[current] :] + [current]
            positions[current] = len(path)
            path.append(current)
            parent = concepts[current].get("parent_id")
            if not isinstance(parent, str):
                break
            current = parent
    return None


def validate_documents(
    quarantine: dict[str, Any],
    concept_patch: dict[str, Any],
    batch: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    sources = concept_patch.get("sources") if isinstance(concept_patch.get("sources"), dict) else {}
    concepts_value = concept_patch.get("concepts")
    concepts: dict[str, dict[str, Any]] = concepts_value if isinstance(concepts_value, dict) else {}
    axes_value = batch.get("axes")
    axes: dict[str, dict[str, Any]] = axes_value if isinstance(axes_value, dict) else {}
    quarantine_items = quarantine.get("items") if isinstance(quarantine.get("items"), dict) else {}
    parent_ids = set(quarantine_items)

    if concept_patch.get("medical_approval") is not False or concept_patch.get("needs_review") is not True:
        _issue(issues, "unsafe_patch_status", "error", "Concept patch must remain medical_approval=false and needs_review=true.")
    meta = batch.get("_meta") if isinstance(batch.get("_meta"), dict) else {}
    if meta.get("medical_approval") is not False or meta.get("needs_review") is not True:
        _issue(issues, "unsafe_batch_status", "error", "Batch must remain medical_approval=false and needs_review=true.")
    if set(concept_patch.get("quarantined_parents", [])) != parent_ids:
        _issue(issues, "quarantine_parent_mismatch", "error", "Patch quarantined parent set differs from the source quarantine file.")

    for source_id, source in sources.items():
        if not ID_PATTERN.fullmatch(source_id):
            _issue(issues, "invalid_source_id", "error", "Source id must be lowercase snake_case.", entity_id=source_id)
        if not isinstance(source, dict) or not all(source.get(key) for key in ("title", "authority", "source_type", "url", "accessed_at")):
            _issue(issues, "incomplete_source", "error", "Source metadata is incomplete.", entity_id=source_id)
        if isinstance(source, dict) and source.get("source_type") == "systematic_case_review":
            _issue(issues, "low_evidence_source", "warning", "A record relies on retrospective case evidence and must remain excluded pending specialist review.", entity_id=source_id)

    candidate_leaves: set[str] = set()
    classification_nodes: set[str] = set()
    for cid, concept in concepts.items():
        if not ID_PATTERN.fullmatch(cid):
            _issue(issues, "invalid_concept_id", "error", "Concept id must be lowercase snake_case.", entity_id=cid)
        if not isinstance(concept, dict):
            _issue(issues, "invalid_concept", "error", "Concept must be an object.", entity_id=cid)
            continue
        if concept.get("disease_concept_id") != cid:
            _issue(issues, "concept_id_mismatch", "error", "disease_concept_id must match its map key.", entity_id=cid)
        if concept.get("needs_review") is not True:
            _issue(issues, "concept_needs_review_not_true", "error", "Every split concept must remain needs_review=true.", entity_id=cid)
        parent = concept.get("parent_id")
        if parent not in parent_ids and parent not in concepts:
            _issue(issues, "orphan_parent", "error", f"Unknown parent_id {parent!r}.", entity_id=cid)
        pointer_ids = _source_ids(concept.get("source_pointers"))
        if not pointer_ids:
            _issue(issues, "missing_concept_source", "error", "Concept requires at least one source pointer.", entity_id=cid)
        for source_id in pointer_ids:
            if source_id not in sources:
                _issue(issues, "unknown_concept_source", "error", f"Unknown source pointer {source_id!r}.", entity_id=cid)
        status = concept.get("generation_grounding_status")
        if concept.get("node_type") == "category":
            classification_nodes.add(cid)
            if status != CLASSIFICATION_ONLY:
                _issue(issues, "category_not_classification_only", "error", "Category nodes must be classification_only.", entity_id=cid)
        elif concept.get("node_type") in DISEASE_LIKE:
            candidate_leaves.add(cid)
            if not isinstance(status, str) or not status.startswith("candidate_needs_review"):
                _issue(issues, "leaf_status_invalid", "error", "Disease-like leaf must remain a candidate_needs_review status.", entity_id=cid)
        else:
            _issue(issues, "invalid_node_type", "error", "Split node must be disease, neoplasm, or category.", entity_id=cid)

    cycle = _find_cycle(concepts)
    if cycle:
        _issue(issues, "parent_cycle", "error", "Parent-child cycle detected: " + " -> ".join(cycle))

    for parent_id, item in quarantine_items.items():
        recommended = set(item.get("recommended_split", [])) if isinstance(item, dict) else set()
        direct_children = {cid for cid, row in concepts.items() if row.get("parent_id") == parent_id}
        missing = recommended - direct_children
        if missing:
            _issue(issues, "recommended_split_missing", "error", f"Missing recommended direct children: {sorted(missing)}", entity_id=parent_id)
        if not direct_children:
            _issue(issues, "parent_without_children", "error", "Quarantined parent has no split children.", entity_id=parent_id)

    for forbidden in parent_ids | classification_nodes:
        if forbidden in axes:
            _issue(issues, "non_leaf_has_axes", "error", "Quarantined parent or classification node must not receive generation axes.", entity_id=forbidden)
    for cid in sorted(candidate_leaves - set(axes)):
        _issue(issues, "leaf_missing_axes", "error", "Disease-like split leaf is missing a clinical-axis draft.", entity_id=cid)
    for cid in sorted(set(axes) - candidate_leaves):
        _issue(issues, "axis_without_leaf", "error", "Axis record does not map to a disease-like split leaf.", entity_id=cid)

    for cid, axis in axes.items():
        if not isinstance(axis, dict):
            _issue(issues, "invalid_axis", "error", "Axis must be an object.", entity_id=cid)
            continue
        if axis.get("id") != cid:
            _issue(issues, "axis_id_mismatch", "error", "Axis id must match its map key.", entity_id=cid)
        if axis.get("needs_review") is not True:
            _issue(issues, "axis_needs_review_not_true", "error", "Every axis must remain needs_review=true.", entity_id=cid)
        for name in REQUIRED_AXES:
            if axis.get(name) in (None, "", [], {}):
                _issue(issues, "missing_required_axis", "error", f"Required axis {name!r} is empty.", entity_id=cid)
        path = axis.get("pathophysiology")
        if not isinstance(path, dict) or not isinstance(path.get("summary"), str) or len(path["summary"].strip()) < 60:
            _issue(issues, "invalid_pathophysiology", "error", "Pathophysiology summary is absent or too short.", entity_id=cid)
        elif not isinstance(path.get("key_steps"), list) or len(path["key_steps"]) < 2:
            _issue(issues, "invalid_pathophysiology", "error", "At least two pathophysiology key steps are required.", entity_id=cid)
        if not isinstance(axis.get("risk_factors"), list) or not axis["risk_factors"]:
            _issue(issues, "invalid_risk_factors", "error", "At least one risk-factor or established-no-risk statement is required.", entity_id=cid)
        prognosis = axis.get("prognosis")
        if not isinstance(prognosis, dict) or not isinstance(prognosis.get("factors"), list) or len(prognosis["factors"]) < 2:
            _issue(issues, "invalid_prognosis", "error", "At least two prognosis factors are required.", entity_id=cid)
        elif not all(isinstance(prognosis.get(key), str) and prognosis[key].strip() for key in ("staging_or_grading", "natural_history")):
            _issue(issues, "invalid_prognosis", "error", "Prognosis staging and natural history must be populated.", entity_id=cid)
        treatment = axis.get("treatment")
        if not isinstance(treatment, dict) or not isinstance(treatment.get("principles"), str) or len(treatment["principles"].strip()) < 35:
            _issue(issues, "invalid_treatment", "error", "Treatment principles are absent or too short.", entity_id=cid)
        elif not isinstance(treatment.get("indicated_for"), list) or not treatment["indicated_for"]:
            _issue(issues, "invalid_treatment", "error", "At least one disease-specific indicated treatment is required.", entity_id=cid)
        elif not isinstance(treatment.get("contraindicated_for"), list):
            _issue(issues, "invalid_treatment", "error", "contraindicated_for must be a list, which may be empty.", entity_id=cid)
        else:
            indicated = {str(value).strip().casefold() for value in treatment["indicated_for"]}
            contraindicated = {str(value).strip().casefold() for value in treatment["contraindicated_for"]}
            if indicated & contraindicated:
                _issue(issues, "treatment_overlap", "error", "Identical text occurs in indication and contraindication.", entity_id=cid)
        epi = axis.get("epidemiology")
        if not isinstance(epi, dict) or not all(isinstance(epi.get(key), str) and epi[key].strip() for key in ("age", "sex", "population", "frequency")):
            _issue(issues, "invalid_epidemiology", "error", "Qualitative epidemiology fields are incomplete.", entity_id=cid)
        elif PRECISE_EPI.search(" ".join(epi.values())):
            _issue(issues, "precise_epidemiology", "error", "Precise epidemiology is prohibited in this draft batch.", entity_id=cid)
        pointer_ids = _source_ids(axis.get("source_pointers"))
        if not pointer_ids:
            _issue(issues, "missing_axis_source", "error", "Every axis requires a source pointer.", entity_id=cid)
        for source_id in pointer_ids:
            if source_id not in sources:
                _issue(issues, "unknown_axis_source", "error", f"Unknown source pointer {source_id!r}.", entity_id=cid)
        if not isinstance(axis.get("uncertainty_notes"), list) or not axis["uncertainty_notes"]:
            _issue(issues, "missing_uncertainty_note", "error", "Every split axis requires an uncertainty note.", entity_id=cid)

    issues.sort(key=lambda row: (not row["blocking"], row.get("id", ""), row["code"]))
    counts = Counter(issue["code"] for issue in issues)
    blocking = sum(bool(issue["blocking"]) for issue in issues)
    return {
        "schema_version": "clinical_axes_scope_split_validation.v1",
        "status": "failed" if blocking else "passed_with_review_warnings" if issues else "passed_not_medically_approved",
        "quality_gate_passed": blocking == 0,
        "medical_approval": False,
        "review_required": True,
        "summary": {
            "quarantined_parents": len(parent_ids),
            "new_concepts": len(concepts),
            "classification_nodes": len(classification_nodes),
            "clinical_axis_leaves": len(axes),
            "sources": len(sources),
            "blocking_issues": blocking,
            "warnings": sum(issue["severity"] == "warning" for issue in issues),
            "issue_codes": dict(sorted(counts.items())),
        },
        "disposition": "Candidate patch only. Original umbrella parents remain quarantined; merge and generation use require explicit human medical review.",
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarantine", type=Path, default=DEFAULT_QUARANTINE)
    parser.add_argument("--concepts", type=Path, default=DEFAULT_CONCEPTS)
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if a blocking validation issue exists.")
    args = parser.parse_args()
    report = validate_documents(load(args.quarantine), load(args.concepts), load(args.batch))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and not report["quality_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
