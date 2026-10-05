#!/usr/bin/env python3
"""Build deterministic finding-tag and endpoint review worklists.

Only tag/identifier aggregates are emitted.  Question stems, answer choices,
explanations, and source item identifiers are deliberately ignored.  Candidate
classes are routing hints for human terminology review, not medical mappings,
controlled-vocabulary links, or approval decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
CURRICULUM = DP / "curriculum"
DEFAULT_QBANK = DP / "embedding" / "qbank_relabeled.json"
DEFAULT_CONCEPT_REGISTRY = DP / "concept_registry.json"
DEFAULT_FINDING_REGISTRY = CURRICULUM / "finding_registry.json"
DEFAULT_ENDPOINT_UNRESOLVED = CURRICULUM / "endpoint_types_unresolved.json"
DEFAULT_ENDPOINT_TYPES = CURRICULUM / "endpoint_types.json"
DEFAULT_OUTPUT = CURRICULUM / "finding_endpoint_review_worklist_20260712.json"


TYPE_REVIEW_CLASSES = {
    "disorder": "disorder_candidate",
    "drug_substance": "drug_or_substance_candidate",
    "finding": "finding_candidate",
    "organism_agent": "organism_or_agent_candidate",
    "test_procedure": "test_or_procedure_candidate",
}
EDGE_REVIEW_CLASSES = {
    "caused_by": "cause_exposure_or_agent_candidate",
    "diagnosed_by": "test_or_finding_candidate",
    "differential_of": "disorder_or_finding_candidate",
    "treated_with": "treatment_or_intervention_candidate",
}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def normalized_id(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[^0-9a-z가-힣]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def stable_review_id(kind: str, entity_id: str) -> str:
    digest = hashlib.sha1(f"{kind}|{entity_id}".encode("utf-8")).hexdigest()[:16]
    return f"review:{kind}:{digest}"


def pending_decision() -> dict[str, Any]:
    return {
        "status": "pending",
        "decision": None,
        "reviewer_id": None,
        "reviewed_at": None,
        "rationale": None,
        "controlled_vocabulary_id": None,
    }


def extract_disease_ids(value: object) -> set[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return {str(item).strip() for item in values if isinstance(item, str) and item.strip()}


def build_type_index(endpoint_types: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"raw_ids": set(), "types": set()})
    for raw_id, endpoint_type in (endpoint_types.get("types") or {}).items():
        nid = normalized_id(raw_id)
        if not nid or not isinstance(endpoint_type, str) or not endpoint_type.strip():
            continue
        grouped[nid]["raw_ids"].add(str(raw_id))
        grouped[nid]["types"].add(endpoint_type.strip())
    return {
        nid: {
            "raw_ids": sorted(values["raw_ids"], key=lambda value: (value.casefold(), value)),
            "types": sorted(values["types"]),
        }
        for nid, values in sorted(grouped.items())
    }


def build_finding_index(finding_registry: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in finding_registry.get("findings") or []:
        if not isinstance(row, dict) or not row.get("finding_id"):
            continue
        grouped[normalized_id(row["finding_id"])].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row.get("finding_id") or ""))
    return dict(sorted(grouped.items()))


def finding_priority(
    *,
    existing: bool,
    endpoint_types: list[str],
    frequency: int,
    linked_disease_count: int,
) -> tuple[str, str]:
    if len(endpoint_types) > 1 or any(value != "finding" for value in endpoint_types):
        return "P0", "tag_role_conflicts_with_current_endpoint_type"
    if not existing and (endpoint_types == ["finding"] or frequency >= 2 or linked_disease_count >= 2):
        return "P1", "repeated_or_finding_typed_candidate_requires_review"
    if existing:
        return "P2", "existing_registry_entry_still_needs_review"
    return "P2", "single_observation_candidate"


def build_finding_worklist(
    qbank: dict[str, Any],
    finding_index: dict[str, list[dict[str, Any]]],
    type_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    aggregates: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"tag_variants": set(), "frequency": 0, "disease_ids": set()}
    )
    occurrence_count = 0
    for item in qbank.get("items") or []:
        if not isinstance(item, dict):
            continue
        disease_ids = extract_disease_ids(item.get("disease_concept_id"))
        per_item: dict[str, set[str]] = defaultdict(set)
        for raw_tag in item.get("finding_tags") or []:
            if not isinstance(raw_tag, str) or not raw_tag.strip():
                continue
            nid = normalized_id(raw_tag)
            if not nid:
                continue
            occurrence_count += 1
            per_item[nid].add(raw_tag.strip())
        for nid, variants in per_item.items():
            aggregates[nid]["tag_variants"].update(variants)
            aggregates[nid]["frequency"] += 1
            aggregates[nid]["disease_ids"].update(disease_ids)

    rows: list[dict[str, Any]] = []
    for nid, aggregate in sorted(aggregates.items()):
        registry_rows = finding_index.get(nid, [])
        registry_ids = sorted({str(row.get("finding_id")) for row in registry_rows if row.get("finding_id")})
        hpo_ids = sorted({str(row.get("hpo_id")) for row in registry_rows if row.get("hpo_id")})
        type_record = type_index.get(nid) or {"raw_ids": [], "types": []}
        current_types = list(type_record["types"])
        existing = bool(registry_rows)
        frequency = int(aggregate["frequency"])
        disease_ids = sorted(aggregate["disease_ids"])
        priority, priority_reason = finding_priority(
            existing=existing,
            endpoint_types=current_types,
            frequency=frequency,
            linked_disease_count=len(disease_ids),
        )
        if hpo_ids:
            hpo_status = "existing_hpo_id_needs_review"
        elif existing:
            hpo_status = "existing_without_hpo"
        else:
            hpo_status = "not_in_finding_registry"
        variants = sorted(aggregate["tag_variants"], key=lambda value: (value.casefold(), value))
        rows.append(
            {
                "review_id": stable_review_id("finding_tag", nid),
                "priority": priority,
                "priority_reason": priority_reason,
                "tag": variants[0],
                "normalized_tag_id": nid,
                "tag_variants": variants,
                "frequency": frequency,
                "linked_disease_count": len(disease_ids),
                "linked_disease_concept_ids": disease_ids,
                "existing_in_finding_registry": existing,
                "existing_finding_ids": registry_ids,
                "registry_match_method": "normalized_id_exact" if existing else "none",
                "hpo_status": hpo_status,
                "hpo_ids": hpo_ids,
                "current_endpoint_typing_status": (
                    "ambiguous_needs_review"
                    if len(current_types) > 1
                    else "present_needs_review"
                    if current_types
                    else "missing"
                ),
                "current_endpoint_types": current_types,
                "endpoint_type_source_ids": list(type_record["raw_ids"]),
                "proposed_action": "review_before_promote",
                "promotion_eligible": False,
                "candidate_only": True,
                "needs_review": True,
                "medical_approval": False,
                "review_decision": pending_decision(),
            }
        )

    rows.sort(
        key=lambda row: (
            PRIORITY_ORDER[row["priority"]],
            -row["frequency"],
            -row["linked_disease_count"],
            row["normalized_tag_id"],
        )
    )
    summary = {
        "source_tag_occurrences": occurrence_count,
        "distinct_normalized_tags": len(rows),
        "existing_finding_registry_matches": sum(row["existing_in_finding_registry"] for row in rows),
        "existing_with_hpo": sum(bool(row["hpo_ids"]) for row in rows),
        "not_in_finding_registry": sum(not row["existing_in_finding_registry"] for row in rows),
    }
    return rows, summary


def endpoint_review_class(current_types: list[str], edge_types: dict[str, int]) -> tuple[str, str]:
    if len(current_types) == 1:
        return TYPE_REVIEW_CLASSES.get(current_types[0], "other_typed_candidate"), "current_endpoint_type"
    if len(current_types) > 1:
        return "ambiguous_typed_candidate", "conflicting_current_endpoint_types"
    roles = sorted(edge_types)
    if len(roles) == 1:
        return EDGE_REVIEW_CLASSES.get(roles[0], "other_role_candidate"), "edge_role_only"
    if len(roles) > 1:
        return "mixed_role_candidate", "edge_roles_only"
    return "unclassified_candidate", "no_current_type_or_edge_role"


def endpoint_priority(current_types: list[str], edge_types: dict[str, int], frequency: int) -> tuple[str, str]:
    if not current_types or len(current_types) > 1:
        return "P0", "current_typing_missing_or_ambiguous"
    if len(edge_types) > 1 or frequency >= 3:
        return "P1", "repeated_or_multi_role_endpoint_requires_review"
    return "P2", "single_role_low_frequency_endpoint"


def build_endpoint_worklist(
    endpoint_unresolved: dict[str, Any],
    type_index: dict[str, dict[str, Any]],
    concept_ids: set[str],
    finding_index: dict[str, list[dict[str, Any]]],
    *,
    typing_source: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    for source_row in endpoint_unresolved.get("items") or []:
        if not isinstance(source_row, dict) or not source_row.get("id"):
            continue
        endpoint_id = str(source_row["id"]).strip()
        nid = normalized_id(endpoint_id)
        raw_edge_types = source_row.get("edge_types") or {}
        edge_types = {
            str(key): int(value)
            for key, value in sorted(raw_edge_types.items())
            if isinstance(key, str) and isinstance(value, int) and value >= 0
        }
        frequency = int(source_row.get("total") or sum(edge_types.values()))
        type_record = type_index.get(nid) or {"raw_ids": [], "types": []}
        current_types = list(type_record["types"])
        review_class, classification_basis = endpoint_review_class(current_types, edge_types)
        priority, priority_reason = endpoint_priority(current_types, edge_types, frequency)
        finding_rows = finding_index.get(nid, [])
        hpo_ids = sorted({str(row.get("hpo_id")) for row in finding_rows if row.get("hpo_id")})
        rows.append(
            {
                "review_id": stable_review_id("endpoint", nid),
                "priority": priority,
                "priority_reason": priority_reason,
                "endpoint_id": endpoint_id,
                "normalized_endpoint_id": nid,
                "frequency": frequency,
                "edge_types": edge_types,
                "edge_type_count": len(edge_types),
                "current_typing_status": (
                    "ambiguous_needs_review"
                    if len(current_types) > 1
                    else "present_needs_review"
                    if current_types
                    else "missing"
                ),
                "current_endpoint_types": current_types,
                "current_type_source": typing_source if current_types else None,
                "current_type_source_ids": list(type_record["raw_ids"]),
                "typing_is_medically_verified": False,
                "controlled_vocabulary_review_class": review_class,
                "classification_basis": classification_basis,
                "controlled_vocabulary_id": None,
                "in_concept_registry": nid in concept_ids,
                "in_finding_registry": bool(finding_rows),
                "existing_finding_ids": sorted(
                    {str(row.get("finding_id")) for row in finding_rows if row.get("finding_id")}
                ),
                "existing_hpo_ids": hpo_ids,
                "proposed_action": "review_before_controlled_vocabulary_link",
                "candidate_only": True,
                "needs_review": True,
                "medical_approval": False,
                "review_decision": pending_decision(),
            }
        )

    rows.sort(
        key=lambda row: (
            PRIORITY_ORDER[row["priority"]],
            -row["frequency"],
            row["normalized_endpoint_id"],
        )
    )
    type_counts = Counter(
        row["current_endpoint_types"][0]
        if len(row["current_endpoint_types"]) == 1
        else "ambiguous"
        if row["current_endpoint_types"]
        else "untyped"
        for row in rows
    )
    summary = {
        "legacy_unresolved_rows": len(rows),
        "currently_typed_needs_review": sum(row["current_typing_status"] == "present_needs_review" for row in rows),
        "currently_ambiguous": sum(row["current_typing_status"] == "ambiguous_needs_review" for row in rows),
        "still_untyped": sum(row["current_typing_status"] == "missing" for row in rows),
        "current_type_counts": dict(sorted(type_counts.items())),
    }
    return rows, summary


def build(
    *,
    qbank_path: Path = DEFAULT_QBANK,
    concept_registry_path: Path = DEFAULT_CONCEPT_REGISTRY,
    finding_registry_path: Path = DEFAULT_FINDING_REGISTRY,
    endpoint_unresolved_path: Path = DEFAULT_ENDPOINT_UNRESOLVED,
    endpoint_types_path: Path = DEFAULT_ENDPOINT_TYPES,
) -> dict[str, Any]:
    qbank = load_json(qbank_path)
    concept_registry = load_json(concept_registry_path)
    finding_registry = load_json(finding_registry_path)
    endpoint_unresolved = load_json(endpoint_unresolved_path)
    endpoint_types = load_json(endpoint_types_path)

    type_index = build_type_index(endpoint_types)
    finding_index = build_finding_index(finding_registry)
    concept_ids = {normalized_id(value) for value in (concept_registry.get("concepts") or {})}
    finding_rows, finding_summary = build_finding_worklist(qbank, finding_index, type_index)
    source_finding_rows = [
        row for row in finding_registry.get("findings") or [] if isinstance(row, dict)
    ]
    finding_summary.update(
        {
            "distinct_raw_tags": sum(len(row["tag_variants"]) for row in finding_rows),
            "finding_registry_rows": len(source_finding_rows),
            "finding_registry_rows_with_hpo": sum(bool(row.get("hpo_id")) for row in source_finding_rows),
        }
    )
    endpoint_rows, endpoint_summary = build_endpoint_worklist(
        endpoint_unresolved,
        type_index,
        concept_ids,
        finding_index,
        typing_source=str(endpoint_types.get("source") or "unknown_needs_review"),
    )
    endpoint_summary["current_typing_catalog_rows"] = len(endpoint_types.get("types") or {})
    finding_priority_counts = Counter(row["priority"] for row in finding_rows)
    endpoint_priority_counts = Counter(row["priority"] for row in endpoint_rows)
    return {
        "schema_version": "finding_endpoint_review_worklist.v1",
        "status": "human_review_required_no_automatic_promotion",
        "generated_from": {
            "qbank": relative(qbank_path),
            "concept_registry": relative(concept_registry_path),
            "finding_registry": relative(finding_registry_path),
            "endpoint_unresolved": relative(endpoint_unresolved_path),
            "endpoint_types": relative(endpoint_types_path),
        },
        "privacy": {
            "question_stems_emitted": False,
            "answer_choices_emitted": False,
            "explanations_emitted": False,
            "source_item_ids_emitted": False,
            "tag_and_identifier_aggregates_only": True,
        },
        "review_policy": {
            "deterministic": True,
            "automatic_medical_mapping_performed": False,
            "automatic_standard_id_creation_performed": False,
            "automatic_medical_approval_performed": False,
            "all_candidate_classes_are_routing_hints_only": True,
            "review_required": True,
            "medical_approval": False,
        },
        "summary": {
            "qbank_items_scanned": len(qbank.get("items") or []),
            "finding": {
                **finding_summary,
                "priorities": {key: finding_priority_counts.get(key, 0) for key in ("P0", "P1", "P2")},
                "pending_decisions": len(finding_rows),
            },
            "endpoint": {
                **endpoint_summary,
                "priorities": {key: endpoint_priority_counts.get(key, 0) for key in ("P0", "P1", "P2")},
                "pending_decisions": len(endpoint_rows),
            },
        },
        "finding_worklist": finding_rows,
        "endpoint_worklist": endpoint_rows,
    }


def write_or_check(payload: dict[str, Any], output: Path, *, check: bool) -> bool:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if check:
        return output.exists() and output.read_text(encoding="utf-8") == rendered
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qbank", type=Path, default=DEFAULT_QBANK)
    parser.add_argument("--concept-registry", type=Path, default=DEFAULT_CONCEPT_REGISTRY)
    parser.add_argument("--finding-registry", type=Path, default=DEFAULT_FINDING_REGISTRY)
    parser.add_argument("--endpoint-unresolved", type=Path, default=DEFAULT_ENDPOINT_UNRESOLVED)
    parser.add_argument("--endpoint-types", type=Path, default=DEFAULT_ENDPOINT_TYPES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = build(
        qbank_path=args.qbank,
        concept_registry_path=args.concept_registry,
        finding_registry_path=args.finding_registry,
        endpoint_unresolved_path=args.endpoint_unresolved,
        endpoint_types_path=args.endpoint_types,
    )
    if not write_or_check(payload, args.output, check=args.check):
        raise SystemExit(f"finding_endpoint_worklist_mismatch: {args.output}")
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
