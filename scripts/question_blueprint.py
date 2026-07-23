#!/usr/bin/env python3
"""Build deterministic educational ontology overlays from a grounding pack.

This module is deliberately a derived consumer.  It does not author medical
facts, approve ontology claims, or infer an assessment target at random.  A
target axis must come from an explicit axis type/axis ID or from an unambiguous
question-type mapping.  Every generated QuestionBlueprint and Misconception
candidate remains an unapproved draft that requires human review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "question_blueprint.v1"

AXIS_TYPE_ORDER = (
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
)

# Only question types with one clear assessment-axis interpretation are mapped.
# Generic formats (clinical_case, image_based, basic_concept, and mixed) are
# intentionally absent so they cannot silently select a medical target.
QUESTION_TYPE_TO_AXIS_TYPE = {
    "mechanism": "pathophysiology",
    "diagnostic": "diagnosis",
    "management": "treatment",
    "symptom": "symptom",
    "diagnosis": "diagnosis",
    "pathophysiology": "pathophysiology",
    "risk_factor": "risk_factor",
    "prognosis": "prognosis",
    "epidemiology": "epidemiology",
    "treatment": "treatment",
    "indication": "indication",
    "contraindication": "contraindication",
    "etiology": "etiology",
}

# These are educational option categories, not new medical claims.
OPTION_DOMAIN_BY_AXIS_TYPE = {
    "symptom": "clinical_finding",
    "diagnosis": "diagnosis",
    "pathophysiology": "mechanism",
    "risk_factor": "risk_factor",
    "prognosis": "prognosis",
    "epidemiology": "epidemiology",
    "treatment": "intervention",
    "indication": "intervention",
    "contraindication": "intervention",
    "etiology": "etiology",
}

AXIS_TYPE_ALIASES = {
    "mechanism": "pathophysiology",
}


def _canonical_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z_]+", "_", str(value or "").strip().casefold()).strip("_")


def _canonical_axis_type(value: Any) -> str:
    normalized = _canonical_text(value)
    return AXIS_TYPE_ALIASES.get(normalized, normalized)


def _stable_id(prefix: str, payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(raw).hexdigest()[:16]}"


def _normalized_ids(values: Iterable[Any] | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        values = [values]
    return sorted({str(value).strip() for value in values if str(value or "").strip()})


def _axis_sort_key(axis_type: str) -> tuple[int, str]:
    try:
        return (AXIS_TYPE_ORDER.index(axis_type), axis_type)
    except ValueError:
        return (len(AXIS_TYPE_ORDER), axis_type)


def _extract_pack(grounding: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Accept either a full generation-grounding envelope or its ``pack``."""

    if not isinstance(grounding, dict):
        raise TypeError("grounding must be an object")
    if "pack" in grounding:
        pack = grounding.get("pack")
        return (
            pack if isinstance(pack, dict) else None,
            {
                "grounding_review_policy": str(grounding.get("review_policy") or "") or None,
                "grounding_blocked": bool(grounding.get("blocked")),
                "grounding_pack_present": isinstance(pack, dict),
            },
        )
    looks_like_pack = "disease_concept_id" in grounding or "axis_context" in grounding
    return (
        grounding if looks_like_pack else None,
        {
            "grounding_review_policy": str(grounding.get("review_policy") or "") or None,
            "grounding_blocked": False,
            "grounding_pack_present": looks_like_pack,
        },
    )


def _axis_index(pack: dict[str, Any] | None) -> tuple[dict[str, list[str]], dict[str, str]]:
    types = (((pack or {}).get("axis_context") or {}).get("types") or {})
    if not isinstance(types, dict):
        return {}, {}
    by_type: dict[str, list[str]] = {}
    type_by_id: dict[str, str] = {}
    for raw_type, raw_rows in types.items():
        axis_type = _canonical_text(raw_type)
        if not axis_type or not isinstance(raw_rows, list):
            continue
        axis_ids = _normalized_ids(
            row.get("axis_id")
            for row in raw_rows
            if isinstance(row, dict) and row.get("axis_id")
        )
        if not axis_ids:
            continue
        by_type[axis_type] = axis_ids
        for axis_id in axis_ids:
            previous = type_by_id.get(axis_id)
            if previous and previous != axis_type:
                raise ValueError(f"axis ID belongs to multiple axis types: {axis_id}")
            type_by_id[axis_id] = axis_type
    return by_type, type_by_id


def _dedupe_distractor_sources(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a stable, one-row-per-source view for prompt and trace contracts."""

    candidates.sort(
        key=lambda row: (
            row["source_id"],
            row["provenance"],
            str(row["in_registry"]),
        )
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        if row["source_id"] in seen:
            continue
        seen.add(row["source_id"])
        out.append(row)
    return out


def _disease_distractor_sources(pack: dict[str, Any] | None) -> list[dict[str, Any]]:
    pool = (pack or {}).get("distractor_pool") or []
    candidates: list[dict[str, Any]] = []
    for row in pool if isinstance(pool, list) else []:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("id") or "").strip()
        if not source_id:
            continue
        candidates.append(
            {
                "source_id": source_id,
                "label": str(row.get("label") or source_id).strip(),
                "aliases": _normalized_ids(row.get("aliases") or [row.get("label")]),
                "provenance": str(row.get("provenance") or "").strip(),
                "in_registry": bool(row.get("in_registry")),
            }
        )
    return _dedupe_distractor_sources(candidates)


OPTION_DOMAIN_AXIS_TYPES = {
    "intervention": ("treatment", "indication", "contraindication"),
    "mechanism": ("pathophysiology", "etiology"),
    "clinical_finding": ("symptom",),
    "risk_factor": ("risk_factor", "etiology"),
    "prognosis": ("prognosis",),
    "epidemiology": ("epidemiology",),
    "etiology": ("etiology", "pathophysiology", "risk_factor"),
}


def _axis_distractor_sources(
    pack: dict[str, Any] | None,
    *,
    option_domain: str | None,
) -> list[dict[str, Any]]:
    """Use same-domain axis nodes for non-diagnosis choices.

    Disease differential nodes are valid diagnosis options, but they are not
    valid medication, mechanism, symptom, or prognosis options.  Keeping the
    two registries separate prevents a treatment question from being marked as
    grounded merely because its distractors were linked to unrelated diseases.
    """

    axis_types = OPTION_DOMAIN_AXIS_TYPES.get(str(option_domain or ""), ())
    types = (((pack or {}).get("axis_context") or {}).get("types") or {})
    candidates: list[dict[str, Any]] = []
    for axis_type in axis_types:
        rows = types.get(axis_type) if isinstance(types, dict) else []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("axis_id") or "").strip()
            label = str(row.get("label") or "").strip()
            if not source_id or not label:
                continue
            candidates.append(
                {
                    "source_id": source_id,
                    "label": label,
                    "aliases": _normalized_ids(row.get("aliases") or [label]),
                    "provenance": str(row.get("relation") or axis_type).strip(),
                    "in_registry": True,
                }
            )
    return _dedupe_distractor_sources(candidates)


def _distractor_sources(
    pack: dict[str, Any] | None,
    *,
    option_domain: str | None,
) -> list[dict[str, Any]]:
    if option_domain == "diagnosis" or option_domain not in OPTION_DOMAIN_AXIS_TYPES:
        return _disease_distractor_sources(pack)
    return _axis_distractor_sources(pack, option_domain=option_domain)


def _misconception_candidates(
    *,
    disease_concept_id: str,
    target_axis_type: str,
    option_domain: str,
    distractor_source_ids: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_id in distractor_source_ids:
        identity = {
            "schema_version": SCHEMA_VERSION,
            "kind": "distractor_confusion_candidate",
            "target_disease_concept_id": disease_concept_id,
            "target_axis_type": target_axis_type,
            "option_domain": option_domain,
            "distractor_source_id": source_id,
        }
        rows.append(
            {
                "misconception_id": _stable_id("mc", identity),
                "kind": "distractor_confusion_candidate",
                "target_disease_concept_id": disease_concept_id,
                "target_axis_type": target_axis_type,
                "distractor_source_id": source_id,
                "review_status": "draft_unreviewed",
                "needs_review": True,
                "medical_approval": False,
            }
        )
    return rows


def build_question_blueprint(
    grounding: dict[str, Any],
    *,
    question_type: str | None = None,
    target_axis_type: str | None = None,
    target_axis_ids: Iterable[str] | None = None,
    supporting_axis_types: Iterable[str] | None = None,
    option_domain: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic QuestionBlueprint plus Misconception candidates.

    Selection precedence is strict:

    1. Explicit ``target_axis_type`` (and optional explicit axis IDs).
    2. A single axis type implied by explicit axis IDs.
    3. An unambiguous ``question_type`` mapping.
    4. No selection.  The blueprint is blocked instead of choosing randomly.

    Unknown explicit axis IDs are rejected because silently substituting an
    available axis would change the faculty/user intent.
    """

    pack, source_contract = _extract_pack(grounding)
    axis_by_type, type_by_id = _axis_index(pack)
    question_type_value = _canonical_text(question_type) or None
    explicit_axis_type = _canonical_axis_type(target_axis_type) or None
    explicit_axis_ids = _normalized_ids(target_axis_ids)
    block_reasons: list[str] = []

    unknown_axis_ids = sorted(set(explicit_axis_ids) - set(type_by_id))
    if unknown_axis_ids:
        raise ValueError(
            "explicit target axis IDs are not present in the grounding pack: "
            + ", ".join(unknown_axis_ids)
        )

    explicit_id_types = sorted({type_by_id[axis_id] for axis_id in explicit_axis_ids})
    if len(explicit_id_types) > 1:
        raise ValueError("explicit target axis IDs must belong to exactly one axis type")
    if explicit_axis_type and explicit_id_types and explicit_id_types[0] != explicit_axis_type:
        raise ValueError(
            "explicit target axis type does not match explicit target axis IDs: "
            f"{explicit_axis_type} != {explicit_id_types[0]}"
        )

    if explicit_axis_type:
        resolved_axis_type = explicit_axis_type
        target_axis_source = "explicit_axis_type"
    elif explicit_id_types:
        resolved_axis_type = explicit_id_types[0]
        target_axis_source = "explicit_axis_ids"
    elif question_type_value in QUESTION_TYPE_TO_AXIS_TYPE:
        resolved_axis_type = QUESTION_TYPE_TO_AXIS_TYPE[question_type_value]
        target_axis_source = "question_type_mapping"
    else:
        resolved_axis_type = None
        target_axis_source = "unresolved"

    if explicit_axis_ids:
        resolved_axis_ids = explicit_axis_ids
        target_axis_ids_source = "explicit_axis_ids"
    elif resolved_axis_type:
        resolved_axis_ids = list(axis_by_type.get(resolved_axis_type, []))
        target_axis_ids_source = "grounding_axis_type"
    else:
        resolved_axis_ids = []
        target_axis_ids_source = "unresolved"

    if not resolved_axis_type:
        block_reasons.append("target_axis_type_missing")
    elif not resolved_axis_ids:
        block_reasons.append("target_axis_ids_missing")

    if option_domain and _canonical_text(option_domain):
        resolved_option_domain = _canonical_text(option_domain)
        option_domain_source = "explicit"
    elif resolved_axis_type:
        resolved_option_domain = OPTION_DOMAIN_BY_AXIS_TYPE.get(
            resolved_axis_type,
            resolved_axis_type,
        )
        option_domain_source = "axis_type_default"
    else:
        resolved_option_domain = None
        option_domain_source = "unresolved"
        block_reasons.append("option_domain_missing")

    if resolved_axis_type:
        if supporting_axis_types is None:
            requested_support_types = sorted(
                (axis_type for axis_type in axis_by_type if axis_type != resolved_axis_type),
                key=_axis_sort_key,
            )
        else:
            requested_support_types = sorted(
                {
                    _canonical_axis_type(value)
                    for value in supporting_axis_types
                    if _canonical_axis_type(value) and _canonical_axis_type(value) != resolved_axis_type
                },
                key=_axis_sort_key,
            )
        supporting_axes: list[dict[str, Any]] = []
        for axis_type in requested_support_types:
            axis_ids = axis_by_type.get(axis_type, [])
            if not axis_ids:
                block_reasons.append(f"supporting_axis_type_missing:{axis_type}")
                continue
            supporting_axes.append({"axis_type": axis_type, "axis_ids": list(axis_ids)})
    else:
        supporting_axes = []

    disease_concept_id = str((pack or {}).get("disease_concept_id") or "").strip() or None
    if pack is None:
        block_reasons.append("grounding_pack_missing")
    if not disease_concept_id:
        block_reasons.append("target_disease_concept_id_missing")
    if source_contract["grounding_blocked"]:
        block_reasons.append("grounding_policy_blocked")

    distractor_sources = _distractor_sources(
        pack,
        option_domain=resolved_option_domain,
    )
    distractor_source_ids = [row["source_id"] for row in distractor_sources]
    if len(distractor_source_ids) < 4:
        block_reasons.append("distractor_pool_lt_4")

    misconceptions = (
        _misconception_candidates(
            disease_concept_id=disease_concept_id,
            target_axis_type=resolved_axis_type,
            option_domain=resolved_option_domain,
            distractor_source_ids=distractor_source_ids,
        )
        if disease_concept_id and resolved_axis_type and resolved_option_domain
        else []
    )

    selection = {
        "target_axis_source": target_axis_source,
        "target_axis_ids_source": target_axis_ids_source,
        "option_domain_source": option_domain_source,
    }
    target = {
        "disease_concept_id": disease_concept_id,
        "axis_type": resolved_axis_type,
        "axis_ids": resolved_axis_ids,
    }
    identity = {
        "schema_version": SCHEMA_VERSION,
        "question_type": question_type_value,
        "selection": selection,
        "target": target,
        "supporting_axes": supporting_axes,
        "option_domain": resolved_option_domain,
        "distractor_source_ids": distractor_source_ids,
    }
    unique_block_reasons = sorted(set(block_reasons))
    return {
        "schema_version": SCHEMA_VERSION,
        "blueprint_id": _stable_id("qb", identity),
        "status": "blocked" if unique_block_reasons else "draft_blueprint",
        "question_type": question_type_value,
        "selection": selection,
        "target": target,
        "supporting_axes": supporting_axes,
        "option_domain": resolved_option_domain,
        "distractor_source_ids": distractor_source_ids,
        "distractor_sources": distractor_sources,
        "misconceptions": misconceptions,
        "review_status": "draft_unreviewed",
        "needs_review": True,
        "medical_approval": False,
        "gen_ready": False,
        "block_reasons": unique_block_reasons,
        "source_contract": source_contract,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a deterministic QuestionBlueprint from generation grounding JSON."
    )
    parser.add_argument("grounding_json", type=Path)
    parser.add_argument("--question-type")
    parser.add_argument("--target-axis-type")
    parser.add_argument("--target-axis-id", action="append", default=[])
    parser.add_argument("--supporting-axis-type", action="append")
    parser.add_argument("--option-domain")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    grounding = json.loads(args.grounding_json.read_text(encoding="utf-8"))
    blueprint = build_question_blueprint(
        grounding,
        question_type=args.question_type,
        target_axis_type=args.target_axis_type,
        target_axis_ids=args.target_axis_id,
        supporting_axis_types=args.supporting_axis_type,
        option_domain=args.option_domain,
    )
    rendered = json.dumps(blueprint, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
