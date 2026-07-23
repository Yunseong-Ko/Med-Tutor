#!/usr/bin/env python3
"""Build a deterministic, fail-closed human review queue for external KG claims.

Priority is derived only from validation classification, mapping coverage, and
external edge polarity.  Labels are carried for reviewers but are never used
for lexical medical scoring.  This script cannot medically approve, promote,
expose, or mutate canonical ontology claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTERNAL_DIR = ROOT / "data_private" / "external_kg" / "primekg"
DEFAULT_VALIDATION_REPORT = DEFAULT_EXTERNAL_DIR / "heme_onc_validation_report.json"
DEFAULT_CANDIDATE_GRAPH = (
    DEFAULT_EXTERNAL_DIR / "heme_onc_phenotype_candidate_graph.json"
)
DEFAULT_CROSSWALK = DEFAULT_EXTERNAL_DIR / "heme_onc_mondo_crosswalk.json"
DEFAULT_OUTPUT = DEFAULT_EXTERNAL_DIR / "review_worklist.json"
DEFAULT_DECISIONS_OUTPUT = DEFAULT_EXTERNAL_DIR / "review_decisions.json"

WORKLIST_SCHEMA = ROOT / "schemas" / "external_kg_review_worklist.schema.json"
DECISIONS_SCHEMA = ROOT / "schemas" / "external_kg_review_decisions.schema.json"
VALIDATION_SCHEMA = ROOT / "schemas" / "external_kg_validation_report.schema.json"
GRAPH_SCHEMA = ROOT / "schemas" / "external_kg_candidate_graph.schema.json"
CROSSWALK_SCHEMA = ROOT / "schemas" / "external_kg_crosswalk.schema.json"

SCHEMA_VERSION = "external_kg_review_worklist.v1"
DECISIONS_SCHEMA_VERSION = "external_kg_review_decisions.v1"
SCOPE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}

PRIORITIZATION_POLICY = {
    "rule_set": "external_kg_review_priority.v1",
    "external_conflict_candidate": "P0",
    "negated_external_new_candidate": "P0",
    "externally_concordant": "P1",
    "exact_local_only_not_disproven": "P1",
    "affirmed_external_new_candidate": "P2",
    "unknown_external_new_candidate": "P2",
    "grouped_or_missing_not_evaluable": "P2",
    "lexical_medical_scoring_used": False,
    "absence_is_not_contradiction": True,
    "negated_external_new_is_positive_finding": False,
}

DECISION_BOUNDARY = {
    "reviewer_decisions_embedded": False,
    "decision_overlay_schema": DECISIONS_SCHEMA_VERSION,
    "automatic_medical_approval": False,
    "automatic_promotion": False,
    "canonical_ontology_mutation": False,
    "student_exposure": False,
}

REVIEW_GATE = {
    "status": "human_review_required",
    "needs_review": True,
    "medical_approval": False,
    "student_visible": False,
    "analytics_eligible": False,
    "promotion_status": "not_promoted",
}

DECISION_SAFETY_BOUNDARY = {
    "human_review_only": True,
    "mutates_canonical_ontology": False,
    "medical_approval": False,
    "student_visible": False,
    "analytics_eligible": False,
    "promotion_status": "not_promoted",
    "separate_curated_promotion_gate_required": True,
}


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def load_schema(path: Path) -> dict[str, Any]:
    return load_json(path)


def validate_document(value: dict[str, Any], schema_path: Path) -> None:
    validator = jsonschema.Draft202012Validator(
        load_schema(schema_path),
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(map(str, error.absolute_path)) or "<root>"
        raise ValueError(f"{schema_path.name}:{location}: {error.message}")


def source_artifact(
    role: str,
    value: dict[str, Any],
    path: Path,
    id_field: str,
) -> dict[str, Any]:
    return {
        "role": role,
        "artifact_id": str(value[id_field]),
        "schema_version": str(value["schema_version"]),
        "artifact_sha256": file_sha256(path),
    }


def assign_priority(item: dict[str, Any]) -> tuple[str, str]:
    """Return a structural priority without inspecting labels or medical terms."""

    classification = item["classification"]
    evaluation_status = item["evaluation_status"]
    polarities = set(item.get("external_polarities") or [])

    if classification == "external_conflict_candidate":
        return "P0", "external_conflict_candidate"
    if classification == "external_new_candidate" and "negated" in polarities:
        return "P0", "negated_external_new_candidate"
    if classification == "externally_concordant":
        return "P1", "externally_concordant"
    if (
        classification == "local_only_not_disproven"
        and evaluation_status == "evaluated_exact_mapping"
    ):
        return "P1", "exact_local_only_not_disproven"
    if evaluation_status == "not_evaluable_grouped_mapping":
        return "P2", "grouped_mapping_not_evaluable"
    if evaluation_status == "not_evaluable_missing_mapping":
        return "P2", "missing_mapping_not_evaluable"
    if classification == "external_new_candidate" and "affirmed" in polarities:
        return "P2", "affirmed_external_new_candidate"
    if classification == "external_new_candidate":
        return "P2", "unknown_external_new_candidate"
    raise ValueError(
        "Uncovered review priority combination: "
        f"classification={classification}; evaluation_status={evaluation_status}; "
        f"polarities={sorted(polarities)}"
    )


def snapshot_ref(value: dict[str, Any]) -> dict[str, Any]:
    required = (
        "snapshot_id",
        "provider",
        "dataset_name",
        "dataset_version",
        "artifact_sha256",
        "license",
        "license_url",
        "redistribution_status",
        "source_url",
    )
    return {key: value[key] for key in required}


def mapping_ref(value: dict[str, Any]) -> dict[str, Any]:
    evidence_hashes = sorted(
        {
            str(evidence["source_record_sha256"])
            for evidence in value.get("evidence") or []
        }
    )
    if not evidence_hashes:
        raise ValueError(f"Mapping lacks evidence hashes: {value.get('mapping_id')}")
    return {
        "mapping_id": value["mapping_id"],
        "external_curie": value["external_curie"],
        "external_snapshot_id": value["external_snapshot_id"],
        "mapping_relation": value["mapping_relation"],
        "mapping_method": value["mapping_method"],
        "confidence": value["confidence"],
        "evidence_record_sha256": evidence_hashes,
    }


def source_record_ref(edge: dict[str, Any]) -> dict[str, Any]:
    provenance = edge["provenance"]
    return {
        "candidate_edge_id": edge["candidate_edge_id"],
        "snapshot_id": provenance["snapshot_id"],
        "source_record_id": provenance["source_record_id"],
        "source_record_sha256": provenance["source_record_sha256"],
        "artifact_sha256": provenance["artifact_sha256"],
        "license": provenance["license"],
        "redistribution_status": provenance["redistribution_status"],
        "source_refs": sorted(set(provenance.get("source_refs") or [])),
    }


def unique_sorted(values: Iterable[Any]) -> list[Any]:
    return sorted(set(values))


def review_instructions(item: dict[str, Any]) -> list[str]:
    instructions = [
        "verify_external_source_and_license",
        "review_authoritative_medical_evidence",
        "do_not_promote_without_separate_curated_gate",
    ]
    if item["classification"] == "local_only_not_disproven":
        instructions.append("do_not_treat_absence_as_contradiction")
    if (
        item["classification"] == "external_new_candidate"
        and "negated" in set(item.get("external_polarities") or [])
    ):
        instructions.append("negated_relation_is_not_positive_finding")
    return instructions


def verify_graph_reference(
    validation_report: dict[str, Any],
    candidate_graph: dict[str, Any],
    graph_path: Path,
) -> None:
    actual_hash = file_sha256(graph_path)
    graph_id = candidate_graph["graph_id"]
    matches = [
        ref
        for ref in validation_report["candidate_graph_refs"]
        if ref["graph_id"] == graph_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Validation report must reference candidate graph exactly once: {graph_id}"
        )
    ref = matches[0]
    if ref["artifact_sha256"] != actual_hash:
        raise ValueError(
            "Candidate graph artifact hash mismatch between validation report and file"
        )
    if ref["snapshot_id"] != candidate_graph["snapshot"]["snapshot_id"]:
        raise ValueError(
            "Candidate graph snapshot mismatch between validation report and graph"
        )


def build_item(
    validation_item: dict[str, Any],
    *,
    edge_by_id: dict[str, dict[str, Any]],
    mappings_by_concept: dict[str, list[dict[str, Any]]],
    graph_snapshot: dict[str, Any],
) -> dict[str, Any]:
    priority, reason = assign_priority(validation_item)
    candidate_edge_ids = unique_sorted(validation_item.get("candidate_edge_ids") or [])
    missing_edges = [edge_id for edge_id in candidate_edge_ids if edge_id not in edge_by_id]
    if missing_edges:
        raise ValueError(
            f"Validation item {validation_item['validation_item_id']} references missing "
            f"candidate edges: {missing_edges}"
        )
    edges = [edge_by_id[edge_id] for edge_id in candidate_edge_ids]
    reported_polarities = unique_sorted(
        validation_item.get("external_polarities") or []
    )
    edge_polarities = unique_sorted(edge["polarity"] for edge in edges)
    if reported_polarities != edge_polarities:
        raise ValueError(
            f"Validation item {validation_item['validation_item_id']} polarity mismatch: "
            f"report={reported_polarities}; graph={edge_polarities}"
        )

    concept_id = validation_item.get("local_concept_id")
    mappings = sorted(
        mappings_by_concept.get(str(concept_id), []) if concept_id else [],
        key=lambda value: value["mapping_id"],
    )
    mapping_refs = [mapping_ref(value) for value in mappings]
    mapped_disease_curies = unique_sorted(
        value["external_curie"] for value in mappings
    )

    snapshots_by_id = {
        graph_snapshot["snapshot_id"]: snapshot_ref(graph_snapshot),
    }
    for edge in edges:
        provenance = edge["provenance"]
        snapshots_by_id[provenance["snapshot_id"]] = snapshot_ref(provenance)

    task_identity = {
        "validation_item_id": validation_item["validation_item_id"],
        "classification": validation_item["classification"],
        "evaluation_status": validation_item["evaluation_status"],
        "candidate_edge_ids": candidate_edge_ids,
    }
    return {
        "review_task_id": f"ekg:r:{canonical_sha256(task_identity)[:24]}",
        "priority": priority,
        "priority_reason": reason,
        "validation_item_id": validation_item["validation_item_id"],
        "classification": validation_item["classification"],
        "evaluation_status": validation_item["evaluation_status"],
        "coverage_reason": validation_item["coverage_reason"],
        "local": {
            "concept_id": concept_id,
            "finding_id": validation_item.get("local_finding_id"),
            "finding_label": validation_item.get("local_finding_label"),
            "hpo_curie": validation_item.get("hpo_curie"),
            "claim_ids": unique_sorted(validation_item.get("local_claim_ids") or []),
        },
        "external": {
            "subject_curie": validation_item.get("external_subject_curie"),
            "predicate": validation_item.get("external_predicate"),
            "object_curie": validation_item.get("external_object_curie"),
            "mapped_disease_curies": mapped_disease_curies,
        },
        "candidate_edge_ids": candidate_edge_ids,
        "polarities": reported_polarities,
        "crosswalk_mappings": mapping_refs,
        "provenance": {
            "validation_item_sha256": canonical_sha256(validation_item),
            "external_snapshots": [
                snapshots_by_id[key] for key in sorted(snapshots_by_id)
            ],
            "source_records": [source_record_ref(edge) for edge in edges],
        },
        "review_instructions": review_instructions(validation_item),
        "review_gate": dict(REVIEW_GATE),
        "reviewer_decision_ref": None,
    }


def empty_decisions_overlay(
    worklist: dict[str, Any],
    worklist_artifact_sha256: str,
) -> dict[str, Any]:
    identity = {
        "worklist_id": worklist["worklist_id"],
        "artifact_sha256": worklist_artifact_sha256,
    }
    return {
        "schema_version": DECISIONS_SCHEMA_VERSION,
        "overlay_id": (
            f"external_kg_review_decisions:{worklist['scope']['scope_id']}:"
            f"{canonical_sha256(identity)[:16]}"
        ),
        "created_at": worklist["generated_at"],
        "worklist_ref": identity,
        "safety_boundary": dict(DECISION_SAFETY_BOUNDARY),
        "decisions": [],
    }


def write_decisions_overlay_safely(
    path: Path,
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """Never erase human decisions during a deterministic worklist rebuild."""

    if path.exists():
        existing = load_json(path)
        validate_document(existing, DECISIONS_SCHEMA)
        if existing.get("decisions"):
            if existing.get("worklist_ref") != overlay["worklist_ref"]:
                raise ValueError(
                    "Existing human decisions refer to a different worklist; refusing "
                    f"to overwrite: {path}"
                )
            return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(overlay))
    return overlay


def verify_existing_decisions_compatible(
    path: Path,
    proposed: dict[str, Any],
    worklist: dict[str, Any],
) -> None:
    """Fail before replacing a worklist that has decisions bound to another hash."""

    if not path.exists():
        return
    existing = load_json(path)
    validate_document(existing, DECISIONS_SCHEMA)
    if existing.get("decisions") and existing.get("worklist_ref") != proposed[
        "worklist_ref"
    ]:
        raise ValueError(
            "Existing human decisions refer to a different worklist; refusing "
            f"to replace either artifact: {path}"
        )
    tasks = {item["review_task_id"]: item for item in worklist["items"]}
    for decision in existing.get("decisions") or []:
        task = tasks.get(decision["review_task_id"])
        if task is None:
            raise ValueError(
                "Decision references a review task absent from its bound worklist: "
                f"{decision['review_task_id']}"
            )
        if decision["validation_item_id"] != task["validation_item_id"]:
            raise ValueError(
                f"Decision validation_item_id mismatch: {decision['decision_id']}"
            )
        if sorted(decision["candidate_edge_ids"]) != task["candidate_edge_ids"]:
            raise ValueError(
                f"Decision candidate_edge_ids mismatch: {decision['decision_id']}"
            )


def derive_review_worklist(
    *,
    validation_report_path: Path,
    candidate_graph_path: Path,
    crosswalk_path: Path,
    scope_id: str = "core20",
) -> dict[str, Any]:
    """Reconstruct the immutable worklist entirely from its three source artifacts."""
    if not SCOPE_ID_PATTERN.fullmatch(scope_id):
        raise ValueError(f"Invalid scope_id: {scope_id!r}")

    validation_report = load_json(validation_report_path)
    candidate_graph = load_json(candidate_graph_path)
    crosswalk = load_json(crosswalk_path)
    validate_document(validation_report, VALIDATION_SCHEMA)
    validate_document(candidate_graph, GRAPH_SCHEMA)
    validate_document(crosswalk, CROSSWALK_SCHEMA)
    verify_graph_reference(validation_report, candidate_graph, candidate_graph_path)

    edge_by_id: dict[str, dict[str, Any]] = {}
    for edge in candidate_graph["edges"]:
        edge_id = edge["candidate_edge_id"]
        if edge_id in edge_by_id:
            raise ValueError(f"Duplicate candidate_edge_id: {edge_id}")
        edge_by_id[edge_id] = edge

    mappings_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mapping in crosswalk["mappings"]:
        mappings_by_concept[mapping["local_concept_id"]].append(mapping)

    validation_ids = [item["validation_item_id"] for item in validation_report["items"]]
    duplicate_validation_ids = sorted(
        item_id for item_id, count in Counter(validation_ids).items() if count > 1
    )
    if duplicate_validation_ids:
        raise ValueError(
            f"Duplicate validation_item_id values: {duplicate_validation_ids}"
        )
    items = [
        build_item(
            item,
            edge_by_id=edge_by_id,
            mappings_by_concept=mappings_by_concept,
            graph_snapshot=candidate_graph["snapshot"],
        )
        for item in validation_report["items"]
    ]
    items.sort(
        key=lambda item: (
            PRIORITY_ORDER[item["priority"]],
            item["priority_reason"],
            item["local"]["concept_id"] or "",
            item["local"]["hpo_curie"] or "",
            item["validation_item_id"],
        )
    )

    source_artifacts = [
        source_artifact(
            "validation_report",
            validation_report,
            validation_report_path,
            "report_id",
        ),
        source_artifact(
            "candidate_graph",
            candidate_graph,
            candidate_graph_path,
            "graph_id",
        ),
        source_artifact(
            "crosswalk",
            crosswalk,
            crosswalk_path,
            "crosswalk_id",
        ),
    ]
    worklist_identity = {
        "scope_id": scope_id,
        "source_artifacts": source_artifacts,
        "priority_rule_set": PRIORITIZATION_POLICY["rule_set"],
    }
    priority_counts = Counter(item["priority"] for item in items)
    classification_counts = Counter(item["classification"] for item in items)
    reason_counts = Counter(item["priority_reason"] for item in items)
    worklist = {
        "schema_version": SCHEMA_VERSION,
        "worklist_id": (
            f"external_kg_review_worklist:{scope_id}:"
            f"{canonical_sha256(worklist_identity)[:16]}"
        ),
        "generated_at": validation_report["generated_at"],
        "scope": {
            "scope_id": scope_id,
            "selection_mode": "input_validation_report",
            "local_concept_ids": unique_sorted(
                candidate_graph["scope"].get("local_concept_ids") or []
            ),
        },
        "source_artifacts": source_artifacts,
        "prioritization_policy": dict(PRIORITIZATION_POLICY),
        "decision_boundary": dict(DECISION_BOUNDARY),
        "stats": {
            "item_count": len(items),
            "counts_by_priority": {
                priority: priority_counts.get(priority, 0)
                for priority in ("P0", "P1", "P2")
            },
            "counts_by_classification": {
                classification: classification_counts.get(classification, 0)
                for classification in (
                    "externally_concordant",
                    "external_conflict_candidate",
                    "local_only_not_disproven",
                    "external_new_candidate",
                )
            },
            "counts_by_priority_reason": dict(sorted(reason_counts.items())),
            "all_human_review_required": True,
            "medical_approval_count": 0,
            "promoted_count": 0,
        },
        "items": items,
    }
    validate_document(worklist, WORKLIST_SCHEMA)
    return worklist


def build_review_worklist(
    *,
    validation_report_path: Path,
    candidate_graph_path: Path,
    crosswalk_path: Path,
    output_path: Path,
    decisions_output_path: Path | None = None,
    scope_id: str = "core20",
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    worklist = derive_review_worklist(
        validation_report_path=validation_report_path,
        candidate_graph_path=candidate_graph_path,
        crosswalk_path=crosswalk_path,
        scope_id=scope_id,
    )
    worklist_payload = json_bytes(worklist)
    overlay = None
    if decisions_output_path is not None:
        worklist_hash = hashlib.sha256(worklist_payload).hexdigest()
        proposed = empty_decisions_overlay(worklist, worklist_hash)
        validate_document(proposed, DECISIONS_SCHEMA)
        verify_existing_decisions_compatible(
            decisions_output_path,
            proposed,
            worklist,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(worklist_payload)
    if decisions_output_path is not None:
        overlay = write_decisions_overlay_safely(decisions_output_path, proposed)
    return worklist, overlay


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validation-report",
        type=Path,
        default=DEFAULT_VALIDATION_REPORT,
        help="external_kg_validation_report.v1 input",
    )
    parser.add_argument(
        "--candidate-graph",
        type=Path,
        default=DEFAULT_CANDIDATE_GRAPH,
        help="external_kg_candidate_graph.v1 input",
    )
    parser.add_argument(
        "--crosswalk",
        type=Path,
        default=DEFAULT_CROSSWALK,
        help="external_kg_crosswalk.v1 input",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--decisions-output",
        type=Path,
        default=DEFAULT_DECISIONS_OUTPUT,
        help="Separate empty human-decision overlay; never overwrites decisions",
    )
    parser.add_argument(
        "--scope-id",
        default="core20",
        help="Stable scope slug, e.g. core20 or heme_onc_full",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    worklist, decisions = build_review_worklist(
        validation_report_path=args.validation_report,
        candidate_graph_path=args.candidate_graph,
        crosswalk_path=args.crosswalk,
        output_path=args.output,
        decisions_output_path=args.decisions_output,
        scope_id=args.scope_id,
    )
    print(
        json.dumps(
            {
                "worklist": str(args.output),
                "worklist_id": worklist["worklist_id"],
                "stats": worklist["stats"],
                "decisions_overlay": str(args.decisions_output),
                "decision_count": len((decisions or {}).get("decisions") or []),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
