#!/usr/bin/env python3
"""Materialize reviewed non-disease retyping decisions as an active overlay.

The historical concept registry remains the stable source of IDs and aliases.
This derived registry is the authoritative consumer overlay for concepts that
must not be exported or matched as diseases. Candidate relations are preserved
as metadata only; they are not materialized until their schema is approved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
CURRICULUM = DP / "curriculum"
REGISTRY = DP / "concept_registry.json"
RETYPE_PLAN = CURRICULUM / "clinical_axes_non_disease_retyping_20260712.json"
RETYPE_ADDENDUM = CURRICULUM / "clinical_axes_non_disease_retyping_addendum_20260712.json"
RETYPE_SCOPE_ADDENDUM = CURRICULUM / "clinical_axes_non_disease_retyping_addendum_scope_20260712.json"
RETYPE_SEED_FLAGS = CURRICULUM / "clinical_axes_non_disease_retyping_seed_flags_20260712.json"
RETYPE_PLANS = (RETYPE_PLAN, RETYPE_ADDENDUM, RETYPE_SCOPE_ADDENDUM, RETYPE_SEED_FLAGS)
CLINICAL_AXES = CURRICULUM / "clinical_axes_map.json"
OUT = CURRICULUM / "typed_entity_registry.json"
QUARANTINE_OUT = CURRICULUM / "typed_entity_clinical_axes_quarantine_20260712.json"
QUARANTINE_ARCHIVE = CURRICULUM / "typed_entity_clinical_axes_quarantine_archive_20260712.json"

# These records existed in clinical_axes_map before retyping. Their full source
# payload must remain recoverable even after the active map deletes them.
QUARANTINE_REQUIRED_IDS = frozenset(
    {
        "death_certificate",
        "fetal_ultrasound",
        "motor_developmental_delay",
        "postmenopausal",
        "projectile_vomiting",
        "screening",
        "sexual_assault",
    }
)

ALLOWED_ENTITY_TYPES = {
    "category",
    "clinical_context",
    "content_format",
    "exposure",
    "finding",
    "health_system",
    "intervention",
    "metric",
    "symptom",
}
DISEASE_LIKE_CURRENT_TYPES = {"disease", "neoplasm", "syndrome", "non_disease_flagged"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def typed_node_id(entity_type: str, concept_id: str) -> str:
    """Return a collision-resistant ID shared by every graph consumer."""
    return f"x:{entity_type}:{concept_id}"


def load_active_entities(path: Path = OUT) -> dict[str, dict[str, Any]]:
    """Load the active overlay, returning an empty map before first build."""
    if not path.exists():
        return {}
    payload = load(path)
    entities = payload.get("entities") or {}
    if not isinstance(entities, dict):
        raise ValueError(f"typed entity registry has invalid entities map: {path}")
    return entities


def _label(concept_id: str, concept: dict[str, Any]) -> str:
    aliases = concept.get("aliases") or []
    for alias in aliases:
        if any("가" <= char <= "힣" for char in str(alias)):
            return str(alias)
    return concept_id.replace("_", " ")


def build(
    plan_paths: tuple[Path, ...] = RETYPE_PLANS,
    registry_path: Path = REGISTRY,
) -> dict[str, Any]:
    proposals: dict[str, dict[str, Any]] = {}
    declared_counts: Counter[str] = Counter()
    for plan_path in plan_paths:
        plan = load(plan_path)
        plan_proposals = plan.get("proposals") or {}
        if not isinstance(plan_proposals, dict) or not plan_proposals:
            raise ValueError(f"retyping plan has no proposals: {plan_path}")
        expected_count = (plan.get("_meta") or {}).get("proposal_count")
        if expected_count is not None and int(expected_count) != len(plan_proposals):
            raise ValueError(
                f"proposal_count mismatch in {plan_path}: metadata={expected_count} actual={len(plan_proposals)}"
            )
        overlap = set(proposals).intersection(plan_proposals)
        if overlap:
            raise ValueError(f"duplicate retyping targets across plans: {sorted(overlap)}")
        proposals.update(plan_proposals)
        declared_counts.update(plan.get("counts_by_proposed_type") or {})

    concepts = (load(registry_path).get("concepts") or {})
    if not isinstance(concepts, dict):
        raise ValueError("concept registry has no concepts map")

    entities: dict[str, dict[str, Any]] = {}
    type_counts: Counter[str] = Counter()
    for concept_id, proposal in sorted(proposals.items()):
        if concept_id not in concepts:
            raise ValueError(f"retyping target missing from concept registry: {concept_id}")
        entity_type = str(proposal.get("proposed_type") or "").strip()
        if entity_type not in ALLOWED_ENTITY_TYPES:
            raise ValueError(f"unsupported proposed_type for {concept_id}: {entity_type!r}")
        current_type = str(proposal.get("current_type") or "").strip().casefold()
        if current_type not in DISEASE_LIKE_CURRENT_TYPES:
            raise ValueError(f"unexpected current_type for {concept_id}: {proposal.get('current_type')!r}")

        concept = concepts[concept_id]
        harrison = ((concept.get("evidence") or {}).get("harrison") or {})
        recommended_relation = dict(proposal.get("recommended_relation") or {})
        recommended_relation["materialized"] = False
        recommended_relation["materialization_reason"] = (
            "candidate relation retained as metadata pending schema review"
        )
        generation_policy = dict(proposal.get("generation_policy") or {})
        generation_policy["eligible_as_disease_answer"] = False
        generation_policy["eligible_for_disease_axis_grounding"] = False
        entities[concept_id] = {
            "entity_id": typed_node_id(entity_type, concept_id),
            "concept_id": concept_id,
            "entity_type": entity_type,
            "entity_subtype": proposal.get("proposed_subtype") or "",
            "legacy_node_type": current_type,
            "destination_layer": proposal.get("destination_layer") or "",
            "label": _label(concept_id, concept),
            "aliases": list(concept.get("aliases") or []),
            "reason": proposal.get("reason") or "",
            "recommended_relation": recommended_relation,
            "generation_policy": generation_policy,
            "source_axis_quarantine_proposal": proposal.get("axis_quarantine"),
            "legacy_source": concept.get("source") or "concept_registry",
            "legacy_harrison_pointer": {
                "chapter": harrison.get("chapter"),
                "page": harrison.get("page"),
                "title": harrison.get("title"),
                "scope": "curriculum_pointer_only_not_disease_assertion",
            },
            "migration_status": "active_typed_overlay",
            "excluded_from_disease_exports": True,
            "needs_review": True,
            "medical_approval": False,
        }
        type_counts[entity_type] += 1

    if dict(sorted(type_counts.items())) != dict(sorted(declared_counts.items())):
        raise ValueError(
            "type counts do not match the retyping plan: "
            f"declared={dict(declared_counts)} actual={dict(type_counts)}"
        )

    return {
        "schema_version": "1.0.0",
        "_meta": {
            "generated_by": "scripts/build_typed_entity_registry.py",
            "generated_from": [
                *[
                    str(plan_path.relative_to(ROOT)) if plan_path.is_relative_to(ROOT) else str(plan_path)
                    for plan_path in plan_paths
                ],
                str(registry_path.relative_to(ROOT)) if registry_path.is_relative_to(ROOT) else str(registry_path),
            ],
            "status": "active_typed_overlay",
            "entity_count": len(entities),
            "counts_by_entity_type": dict(sorted(type_counts.items())),
            "excluded_disease_concept_ids": sorted(entities),
            "candidate_relations_materialized": 0,
            "all_needs_review": True,
            "medical_approval": False,
        },
        "entities": entities,
    }


def build_quarantine(
    typed_payload: dict[str, Any],
    clinical_axes_path: Path = CLINICAL_AXES,
    archive_path: Path = QUARANTINE_ARCHIVE,
) -> dict[str, Any]:
    """Preserve mis-typed axes, falling back to the immutable archive.

    The active clinical axes map intentionally no longer contains retyped
    records. The archive is therefore an input only and is never written by
    this builder.
    """
    source_axes = (load(clinical_axes_path).get("axes") or {}) if clinical_axes_path.exists() else {}
    entities = typed_payload.get("entities") or {}
    archived_axes: dict[str, Any] = {}
    archive_sha256 = None
    if archive_path.exists():
        archive_raw = archive_path.read_bytes()
        archive_sha256 = hashlib.sha256(archive_raw).hexdigest()
        archive_payload = json.loads(archive_raw)
        archived_axes = archive_payload.get("quarantined_axes") or {}
        if not isinstance(archived_axes, dict):
            raise ValueError(f"invalid immutable quarantine archive: {archive_path}")
    quarantined: dict[str, dict[str, Any]] = {}
    recovered_from_archive: list[str] = []
    for concept_id in sorted(set(entities).intersection(set(source_axes) | set(archived_axes))):
        entity = entities[concept_id]
        if concept_id in source_axes:
            original_axes = source_axes[concept_id]
            preservation_source = "active_clinical_axes_map"
        else:
            archived_row = archived_axes[concept_id]
            original_axes = archived_row.get("original_axes") if isinstance(archived_row, dict) else None
            if not isinstance(original_axes, dict) or not original_axes:
                raise ValueError(f"archive record has no original_axes: {concept_id}")
            preservation_source = "immutable_quarantine_archive"
            recovered_from_archive.append(concept_id)
        quarantined[concept_id] = {
            "concept_id": concept_id,
            "entity_id": entity["entity_id"],
            "entity_type": entity["entity_type"],
            "quarantine_reason": "clinical axes were authored under an invalid disease typing",
            "generation_eligible": False,
            "axis_layer_eligible": False,
            "migration_status": "preserved_not_materialized",
            "preservation_source": preservation_source,
            "original_axes": original_axes,
            "needs_review": True,
            "medical_approval": False,
        }
    missing_required = sorted(QUARANTINE_REQUIRED_IDS - set(quarantined))
    if missing_required:
        raise ValueError(
            "required quarantined clinical axes are unavailable from both active map and immutable archive: "
            + ", ".join(missing_required)
        )
    return {
        "schema_version": "1.0.0",
        "_meta": {
            "generated_by": "scripts/build_typed_entity_registry.py",
            "generated_from": str(clinical_axes_path.relative_to(ROOT))
            if clinical_axes_path.is_relative_to(ROOT)
            else str(clinical_axes_path),
            "status": "quarantined_non_disease_axes",
            "quarantined_count": len(quarantined),
            "quarantined_ids": sorted(quarantined),
            "active_source_records": len(set(quarantined).intersection(source_axes)),
            "recovered_from_archive": len(recovered_from_archive),
            "recovered_from_archive_ids": recovered_from_archive,
            "immutable_archive": str(archive_path.relative_to(ROOT))
            if archive_path.is_relative_to(ROOT)
            else str(archive_path),
            "immutable_archive_sha256": archive_sha256,
            "archive_write_policy": "read_only_never_overwrite",
            "source_records_deleted": len(recovered_from_archive),
            "axis_layer_materialized": 0,
            "all_needs_review": True,
            "medical_approval": False,
        },
        "quarantined_axes": quarantined,
    }


def validate_output_paths(
    registry_out: Path,
    quarantine_out: Path,
    archive_inputs: tuple[Path, ...] = (QUARANTINE_ARCHIVE,),
) -> None:
    """Reject any attempt to use an immutable archive as a mutable output."""
    protected = {path.expanduser().resolve() for path in archive_inputs}
    collisions = protected.intersection(
        {registry_out.expanduser().resolve(), quarantine_out.expanduser().resolve()}
    )
    if collisions:
        raise ValueError(
            "refusing to use immutable quarantine archive as builder output: "
            + ", ".join(str(path) for path in sorted(collisions))
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, action="append", help="repeat to merge multiple retyping plans")
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--clinical-axes", type=Path, default=CLINICAL_AXES)
    parser.add_argument("--quarantine-out", type=Path, default=QUARANTINE_OUT)
    parser.add_argument("--quarantine-archive", type=Path, default=QUARANTINE_ARCHIVE)
    parser.add_argument("--check", action="store_true", help="validate output without rewriting it")
    args = parser.parse_args()
    plan_paths = tuple(path.expanduser().resolve() for path in (args.plan or RETYPE_PLANS))
    payload = build(plan_paths, args.registry.expanduser().resolve())
    quarantine = build_quarantine(
        payload,
        args.clinical_axes.expanduser().resolve(),
        args.quarantine_archive.expanduser().resolve(),
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    quarantine_rendered = json.dumps(quarantine, ensure_ascii=False, indent=2) + "\n"
    out = args.out.expanduser().resolve()
    quarantine_out = args.quarantine_out.expanduser().resolve()
    validate_output_paths(
        out,
        quarantine_out,
        (QUARANTINE_ARCHIVE, args.quarantine_archive.expanduser().resolve()),
    )
    if args.check:
        if not out.exists() or out.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"typed entity registry is stale: {out}")
        if not quarantine_out.exists() or quarantine_out.read_text(encoding="utf-8") != quarantine_rendered:
            raise SystemExit(f"typed entity axes quarantine is stale: {quarantine_out}")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        quarantine_out.parent.mkdir(parents=True, exist_ok=True)
        quarantine_out.write_text(quarantine_rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "entities": payload["_meta"]["entity_count"],
                "types": payload["_meta"]["counts_by_entity_type"],
                "candidate_relations_materialized": 0,
                "clinical_axes_quarantined": quarantine["_meta"]["quarantined_count"],
                "mode": "check" if args.check else "write",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
