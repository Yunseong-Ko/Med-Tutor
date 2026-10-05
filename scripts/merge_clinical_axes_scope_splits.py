#!/usr/bin/env python3
"""Merge validated scope-split leaf concepts into the clinical-axis worklist/map."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

try:
    from scripts.audit_clinical_axes_expansion import audit_document
    from scripts.validate_clinical_axes_scope_splits import load, validate_documents
except ModuleNotFoundError:
    from audit_clinical_axes_expansion import audit_document
    from validate_clinical_axes_scope_splits import load, validate_documents


ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "data_private" / "curriculum"
QUARANTINE = CURRICULUM / "clinical_axes_scope_quarantine_20260712.json"
CONCEPT_PATCH = CURRICULUM / "clinical_axes_scope_split_concepts_20260712.json"
BATCH = CURRICULUM / "clinical_axes_scope_split_batch_20260712.json"
WORKLIST = CURRICULUM / "clinical_axes_worklist.json"
AXES_MAP = CURRICULUM / "clinical_axes_map.json"

SOURCE_TYPE_MAP = {
    "clinical_guideline": "professional_society_guideline",
    "living_evidence_summary": "government_evidence_review",
    "systematic_case_review": "peer_reviewed_systematic_review",
    "regulatory_safety_information": "government_clinical_reference",
    "authoritative_classification": "international_authoritative_classification",
}


def evidence_ref(source_id: str, source: dict, supports: list[str]) -> dict:
    scope = ", ".join(supports) if supports else "scope-split clinical-axis record"
    if source.get("evidence_limitation"):
        scope += "; limitation: " + str(source["evidence_limitation"])
    return {
        "ref_id": source_id,
        "source_type": SOURCE_TYPE_MAP.get(source.get("source_type"), "professional_society_educational_review"),
        "authority": source.get("authority") or "",
        "title": source.get("title") or "",
        "url": source.get("url") or "",
        "verified_on": source.get("accessed_at") or "2026-07-12",
        "scope": scope,
        "entailment_status": "needs_human_review",
    }


def prepared_axes(concept_patch: dict, batch: dict) -> dict[str, dict]:
    sources = concept_patch.get("sources") or {}
    result: dict[str, dict] = {}
    for cid, original in (batch.get("axes") or {}).items():
        axis = deepcopy(original)
        refs = []
        for pointer in axis.get("source_pointers") or []:
            source_id = pointer.get("source_id") if isinstance(pointer, dict) else pointer
            source = sources.get(source_id) or {}
            supports = pointer.get("supports") or [] if isinstance(pointer, dict) else []
            refs.append(evidence_ref(str(source_id), source, list(supports)))
        axis["evidence_refs"] = refs
        result[cid] = axis
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    quarantine = load(QUARANTINE)
    concept_patch = load(CONCEPT_PATCH)
    batch = load(BATCH)
    validation = validate_documents(quarantine, concept_patch, batch)
    if not validation["quality_gate_passed"]:
        raise SystemExit("scope-split validator failed")

    axes_to_merge = prepared_axes(concept_patch, batch)
    concepts = concept_patch.get("concepts") or {}
    worklist = load(WORKLIST)
    work_items = worklist.get("items") or []
    work_by_id = {row["id"]: row for row in work_items}
    map_data = load(AXES_MAP)
    active_axes = map_data.get("axes") or {}
    errors: list[str] = []

    for cid, axis in axes_to_merge.items():
        concept = concepts[cid]
        item = {
            "id": cid,
            "ko": concept.get("canonical_label") or cid,
            "node_type": concept.get("node_type") or "disease",
            "specialty": None,
            "harrison": None,
            "top_category": None,
            "has_p2_edges": False,
            "alternate_source_policy": "authority_scoped_scope_split",
        }
        existing_item = work_by_id.get(cid)
        if existing_item is not None and existing_item != item:
            errors.append(f"{cid}: differing worklist record already exists")
        existing_axis = active_axes.get(cid)
        if existing_axis is not None and existing_axis != axis:
            errors.append(f"{cid}: differing clinical-axis record already exists")
        if existing_item is None:
            work_items.append(item)
            work_by_id[cid] = item

    prospective_worklist = {"total": len(work_items), "items": sorted(work_items, key=lambda row: row["id"])}
    prospective_axes = dict(active_axes)
    prospective_axes.update(axes_to_merge)
    prospective_map = {"total": len(prospective_axes), "axes": dict(sorted(prospective_axes.items()))}
    report = audit_document(
        prospective_map,
        source="data_private/curriculum/clinical_axes_map.json",
        worklist_data=prospective_worklist,
    )
    new_ids = set(axes_to_merge)
    for finding in report.get("issues", []):
        if finding.get("blocking") and finding.get("id") in new_ids:
            errors.append(f"{finding.get('id')}: audit {finding.get('code')} at {finding.get('path')}")

    if args.check:
        for cid, axis in axes_to_merge.items():
            if active_axes.get(cid) != axis:
                errors.append(f"{cid}: merged output missing or differs")
            if cid not in {row["id"] for row in load(WORKLIST).get("items", [])}:
                errors.append(f"{cid}: worklist output missing")
    if errors:
        raise SystemExit("\n".join(errors))
    if args.apply:
        WORKLIST.write_text(json.dumps(prospective_worklist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        AXES_MAP.write_text(json.dumps(prospective_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    added = sum(cid not in active_axes for cid in axes_to_merge)
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "check",
                "scope_split_axes": len(axes_to_merge),
                "added": added,
                "clinical_axes_total": len(prospective_axes),
                "worklist_total": len(work_items),
                "validation_warnings": validation["summary"]["warnings"],
                "medical_approval": False,
            }
        )
    )


if __name__ == "__main__":
    main()
