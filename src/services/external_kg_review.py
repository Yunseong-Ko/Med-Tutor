"""Read-only faculty view over fail-closed external KG review artifacts.

This module is intentionally outside generation grounding, learner feedback, and
analytics.  It validates immutable worklists, verifies their referenced local
artifacts, and returns an allow-listed projection suitable for faculty review.
Reviewer decisions remain a separate overlay and still cannot approve or
promote a canonical ontology claim.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from scripts.build_external_kg_review_worklist import derive_review_worklist


ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_KG_DIR = ROOT / "data_private" / "external_kg" / "primekg"
WORKLIST_SCHEMA = ROOT / "schemas" / "external_kg_review_worklist.schema.json"
DECISIONS_SCHEMA = ROOT / "schemas" / "external_kg_review_decisions.schema.json"
VALIDATION_SCHEMA = ROOT / "schemas" / "external_kg_validation_report.schema.json"
CANDIDATE_GRAPH_SCHEMA = ROOT / "schemas" / "external_kg_candidate_graph.schema.json"
CROSSWALK_SCHEMA = ROOT / "schemas" / "external_kg_crosswalk.schema.json"

PROFILE_CONFIG: dict[str, dict[str, Any]] = {
    "core20": {
        "label": "PrimeKG 혈액종양 핵심 20",
        "root": EXTERNAL_KG_DIR,
        "scope_id": "core20",
    },
    "heme_onc_full": {
        "label": "PrimeKG 혈액종양 전체 감사 범위",
        "root": EXTERNAL_KG_DIR / "heme_onc_full",
        "scope_id": "heme_onc_full",
    },
}
DEFAULT_PROFILE = "core20"
MAX_PAGE_SIZE = 100

FAIL_CLOSED_GATE = {
    "status": "human_review_required",
    "needs_review": True,
    "medical_approval": False,
    "student_visible": False,
    "analytics_eligible": False,
    "promotion_status": "not_promoted",
}

PUBLIC_SAFETY_BOUNDARY = {
    "role": "faculty_external_validation_review_only",
    "human_review_required": True,
    "medical_approval": False,
    "student_visible": False,
    "analytics_eligible": False,
    "generation_eligible": False,
    "canonical_ontology_mutation": False,
    "automatic_promotion": False,
    "promotion_status": "not_promoted",
}

SOURCE_FILENAMES = {
    "validation_report": "heme_onc_validation_report.json",
    "candidate_graph": "heme_onc_phenotype_candidate_graph.json",
    "crosswalk": "heme_onc_mondo_crosswalk.json",
}
SOURCE_SCHEMAS = {
    "validation_report": VALIDATION_SCHEMA,
    "candidate_graph": CANDIDATE_GRAPH_SCHEMA,
    "crosswalk": CROSSWALK_SCHEMA,
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _profile(profile: str | None) -> tuple[str, dict[str, Any]]:
    key = str(profile or "").strip() or DEFAULT_PROFILE
    if key not in PROFILE_CONFIG:
        raise ValueError(f"unsupported_external_kg_profile:{key}")
    return key, PROFILE_CONFIG[key]


def _validator(path: Path) -> Draft202012Validator:
    return Draft202012Validator(
        _load_json(path),
        format_checker=FormatChecker(),
    )


def _safe_worklist(profile: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return only a schema-valid, internally fail-closed, checksum-bound worklist."""
    _, config = _profile(profile)
    root = Path(config["root"])
    path = root / "review_worklist.json"
    if not path.is_file():
        return None, "review_worklist_missing"
    try:
        payload = _load_json(path)
        _validator(WORKLIST_SCHEMA).validate(payload)
    except Exception as exc:
        # The API is fail-closed.  Do not leak parser/schema internals to clients.
        return None, f"review_worklist_invalid:{type(exc).__name__}"

    boundary = payload.get("decision_boundary") or {}
    if any(
        (
            boundary.get("automatic_medical_approval") is not False,
            boundary.get("automatic_promotion") is not False,
            boundary.get("canonical_ontology_mutation") is not False,
            boundary.get("student_exposure") is not False,
        )
    ):
        return None, "review_worklist_unsafe_boundary"
    if any((row.get("review_gate") or {}) != FAIL_CLOSED_GATE for row in payload.get("items") or []):
        return None, "review_worklist_unsafe_item"

    expected_by_role = {
        row.get("role"): row.get("artifact_sha256")
        for row in payload.get("source_artifacts") or []
    }
    for role, filename in SOURCE_FILENAMES.items():
        source_path = root / filename
        if not source_path.is_file():
            return None, f"source_artifact_missing:{role}"
        if expected_by_role.get(role) != _sha256(source_path):
            return None, f"source_artifact_checksum_mismatch:{role}"
        try:
            _validator(SOURCE_SCHEMAS[role]).validate(_load_json(source_path))
        except Exception:
            return None, f"source_artifact_schema_invalid:{role}"
    try:
        expected = derive_review_worklist(
            validation_report_path=root / SOURCE_FILENAMES["validation_report"],
            candidate_graph_path=root / SOURCE_FILENAMES["candidate_graph"],
            crosswalk_path=root / SOURCE_FILENAMES["crosswalk"],
            scope_id=str(config.get("scope_id") or profile),
        )
    except Exception:
        return None, "review_worklist_source_derivation_failed"
    if payload != expected:
        return None, "review_worklist_source_binding_mismatch"
    return payload, None


def _safe_decisions(
    root: Path, worklist: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    path = root / "review_decisions.json"
    if not path.is_file():
        return {}, None
    try:
        payload = _load_json(path)
        _validator(DECISIONS_SCHEMA).validate(payload)
    except Exception:
        return None, "review_decisions_invalid"
    worklist_ref = payload.get("worklist_ref") or {}
    worklist_path = root / "review_worklist.json"
    if (
        worklist_ref.get("worklist_id") != worklist.get("worklist_id")
        or worklist_ref.get("artifact_sha256") != _sha256(worklist_path)
    ):
        return None, "review_decisions_worklist_binding_mismatch"
    tasks = {row["review_task_id"]: row for row in worklist.get("items") or []}
    decisions: dict[str, dict[str, Any]] = {}
    decision_ids: set[str] = set()
    for row in payload.get("decisions") or []:
        task = tasks.get(row.get("review_task_id"))
        if task is None:
            return None, "review_decisions_unknown_task"
        if row.get("decision_id") in decision_ids or row.get("review_task_id") in decisions:
            return None, "review_decisions_duplicate_binding"
        if row.get("validation_item_id") != task.get("validation_item_id"):
            return None, "review_decisions_validation_binding_mismatch"
        if sorted(row.get("candidate_edge_ids") or []) != sorted(
            task.get("candidate_edge_ids") or []
        ):
            return None, "review_decisions_edge_binding_mismatch"
        decision_ids.add(str(row.get("decision_id")))
        decisions[str(row["review_task_id"])] = row
    return decisions, None


def _public_source_artifact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": row.get("role"),
        "artifact_id": row.get("artifact_id"),
        "schema_version": row.get("schema_version"),
        "artifact_sha256": row.get("artifact_sha256"),
    }


def _public_item(
    row: dict[str, Any],
    decision: dict[str, Any] | None,
    node_labels: dict[str, str],
) -> dict[str, Any]:
    local = row.get("local") or {}
    external = row.get("external") or {}
    provenance = row.get("provenance") or {}
    snapshots = [
        {
            "snapshot_id": source.get("snapshot_id"),
            "provider": source.get("provider"),
            "dataset_name": source.get("dataset_name"),
            "dataset_version": source.get("dataset_version"),
            "artifact_sha256": source.get("artifact_sha256"),
            "license": source.get("license"),
            "license_url": source.get("license_url"),
            "redistribution_status": source.get("redistribution_status"),
            "source_url": source.get("source_url"),
        }
        for source in provenance.get("external_snapshots") or []
    ]
    source_records = [
        {
            "candidate_edge_id": source.get("candidate_edge_id"),
            "snapshot_id": source.get("snapshot_id"),
            "source_record_id": source.get("source_record_id"),
            "source_record_sha256": source.get("source_record_sha256"),
            "artifact_sha256": source.get("artifact_sha256"),
            "license": source.get("license"),
            "redistribution_status": source.get("redistribution_status"),
            "source_refs": source.get("source_refs") or [],
        }
        for source in provenance.get("source_records") or []
    ]
    decision_view = None
    if decision:
        reviewer = decision.get("reviewer") or {}
        decision_view = {
            "decision_id": decision.get("decision_id"),
            "outcome": decision.get("outcome"),
            # Free-text rationale/evidence refs and reviewer identifiers stay in
            # the private overlay, outside this read-only projection.
            "reviewer": {
                "type": reviewer.get("type"),
                "role": reviewer.get("role"),
                "reviewed_at": reviewer.get("reviewed_at"),
            },
            "still_not_medically_approved": True,
            "separate_curated_promotion_gate_required": True,
        }
    return {
        "review_task_id": row.get("review_task_id"),
        "priority": row.get("priority"),
        "priority_reason": row.get("priority_reason"),
        "validation_item_id": row.get("validation_item_id"),
        "classification": row.get("classification"),
        "evaluation_status": row.get("evaluation_status"),
        "coverage_reason": row.get("coverage_reason"),
        "local": {
            "concept_id": local.get("concept_id"),
            "finding_id": local.get("finding_id"),
            "finding_label": local.get("finding_label"),
            "hpo_curie": local.get("hpo_curie"),
            "claim_ids": local.get("claim_ids") or [],
        },
        "external": {
            "subject_curie": external.get("subject_curie"),
            "subject_label": node_labels.get(str(external.get("subject_curie") or "")),
            "predicate": external.get("predicate"),
            "object_curie": external.get("object_curie"),
            "object_label": node_labels.get(str(external.get("object_curie") or "")),
            "mapped_disease_curies": external.get("mapped_disease_curies") or [],
        },
        "candidate_edge_ids": row.get("candidate_edge_ids") or [],
        "polarities": row.get("polarities") or [],
        "crosswalk_mappings": row.get("crosswalk_mappings") or [],
        "provenance": {
            "validation_item_sha256": provenance.get("validation_item_sha256"),
            "external_snapshots": snapshots,
            "source_records": source_records,
        },
        "review_instructions": row.get("review_instructions") or [],
        "review_gate": dict(FAIL_CLOSED_GATE),
        "decision": decision_view,
    }


def list_external_kg_review(
    *,
    profile: str = DEFAULT_PROFILE,
    priority: str = "",
    classification: str = "",
    evaluation_status: str = "",
    polarity: str = "",
    query: str = "",
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Return a paginated, read-only and non-promotable faculty review projection."""
    profile_key, config = _profile(profile)
    worklist, unavailable_reason = _safe_worklist(profile_key)
    normalized_offset = max(0, int(offset))
    normalized_limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    base = {
        "schema_version": "external_kg_review_api.v1",
        "profile": profile_key,
        "profile_label": config["label"],
        "safety_boundary": dict(PUBLIC_SAFETY_BOUNDARY),
    }
    if worklist is None:
        return {
            **base,
            "status": "unavailable_fail_closed",
            "unavailable_reason": unavailable_reason,
            "source": {},
            "summary": {},
            "filters": {},
            "page": {
                "offset": normalized_offset,
                "limit": normalized_limit,
                "total": 0,
                "returned": 0,
                "has_more": False,
            },
            "items": [],
        }

    root = Path(config["root"])
    decisions, decisions_error = _safe_decisions(root, worklist)
    if decisions is None:
        return {
            **base,
            "status": "unavailable_fail_closed",
            "unavailable_reason": decisions_error,
            "source": {},
            "summary": {},
            "filters": {},
            "page": {
                "offset": normalized_offset,
                "limit": normalized_limit,
                "total": 0,
                "returned": 0,
                "has_more": False,
            },
            "items": [],
        }
    candidate_graph = _load_json(root / SOURCE_FILENAMES["candidate_graph"])
    node_labels = {
        str(row.get("curie")): str(row.get("label"))
        for row in candidate_graph.get("nodes") or []
        if row.get("curie") and row.get("label")
    }
    filters = {
        "priority": str(priority or "").strip(),
        "classification": str(classification or "").strip(),
        "evaluation_status": str(evaluation_status or "").strip(),
        "polarity": str(polarity or "").strip(),
        "query": str(query or "").strip(),
    }
    rows: list[dict[str, Any]] = []
    query_lower = filters["query"].lower()
    for row in worklist.get("items") or []:
        if filters["priority"] and row.get("priority") != filters["priority"]:
            continue
        if filters["classification"] and row.get("classification") != filters["classification"]:
            continue
        if filters["evaluation_status"] and row.get("evaluation_status") != filters["evaluation_status"]:
            continue
        if filters["polarity"] and filters["polarity"] not in (row.get("polarities") or []):
            continue
        if query_lower:
            local = row.get("local") or {}
            external = row.get("external") or {}
            haystack = " ".join(
                str(value or "")
                for value in (
                    local.get("concept_id"),
                    local.get("finding_id"),
                    local.get("finding_label"),
                    local.get("hpo_curie"),
                    external.get("subject_curie"),
                    node_labels.get(str(external.get("subject_curie") or "")),
                    external.get("predicate"),
                    external.get("object_curie"),
                    node_labels.get(str(external.get("object_curie") or "")),
                )
            ).lower()
            if query_lower not in haystack:
                continue
        rows.append(row)

    rows.sort(
        key=lambda row: (
            {"P0": 0, "P1": 1, "P2": 2}.get(row.get("priority"), 9),
            str((row.get("local") or {}).get("concept_id") or ""),
            str(row.get("validation_item_id") or ""),
        )
    )
    page_rows = rows[normalized_offset : normalized_offset + normalized_limit]
    public_items = [
        _public_item(
            row,
            decisions.get(str(row.get("review_task_id"))),
            node_labels,
        )
        for row in page_rows
    ]
    filtered_priority_counts = Counter(row.get("priority") for row in rows)
    return {
        **base,
        "status": "review_only_available",
        "unavailable_reason": None,
        "source": {
            "worklist_id": worklist.get("worklist_id"),
            "generated_at": worklist.get("generated_at"),
            "scope": worklist.get("scope") or {},
            "artifacts": [
                _public_source_artifact(row)
                for row in worklist.get("source_artifacts") or []
            ],
            "decision_overlay_loaded": (root / "review_decisions.json").is_file(),
        },
        "summary": {
            **(worklist.get("stats") or {}),
            "filtered_item_count": len(rows),
            "filtered_counts_by_priority": {
                key: int(filtered_priority_counts.get(key, 0)) for key in ("P0", "P1", "P2")
            },
            "decision_count": len(decisions),
        },
        "filters": filters,
        "page": {
            "offset": normalized_offset,
            "limit": normalized_limit,
            "total": len(rows),
            "returned": len(public_items),
            "has_more": normalized_offset + len(public_items) < len(rows),
        },
        "items": public_items,
    }
