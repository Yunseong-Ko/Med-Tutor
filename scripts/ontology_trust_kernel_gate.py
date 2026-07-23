#!/usr/bin/env python3
"""Fail-closed release gate for student-facing Ontology surfaces.

The authoring graph, embedded policy strings, and analytics booleans are not
release evidence.  Only an external, hash-pinned Trust Kernel release may open
pre-answer delivery, post-answer feedback, or Ontology analytics.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "ontology_trust_kernel_release.schema.json"


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def question_content_payload(question: dict[str, Any]) -> dict[str, Any]:
    """Fields whose change invalidates a released educational item."""

    return {
        "question_id": question.get("question_id"),
        "stem": question.get("stem"),
        "stimulus": question.get("stimulus"),
        "lab_values": question.get("lab_values") or [],
        "choices": question.get("choices") or {},
        "answer": question.get("generated_answer") or question.get("answer"),
        "explanation": question.get("explanation"),
        "answer_rationale": question.get("answer_rationale"),
        "choice_explanations": question.get("choice_explanations") or {},
        "media_refs": question.get("media_refs")
        or ((question.get("media") or {}).get("media_refs") if isinstance(question.get("media"), dict) else [])
        or [],
        "question_blueprint": question.get("question_blueprint") or {},
    }


def question_content_sha256(question: dict[str, Any]) -> str:
    return canonical_sha256(question_content_payload(question))


def feedback_content_payload(question_release: dict[str, Any]) -> dict[str, Any]:
    return {
        "disease_concept_id": question_release.get("disease_concept_id"),
        "target_axis_type": question_release.get("target_axis_type"),
        "target_axis_ids": question_release.get("target_axis_ids") or [],
        "target_claim_ids": question_release.get("target_claim_ids") or [],
        "choice_bindings": question_release.get("choice_bindings") or [],
        "evidence": question_release.get("evidence") or [],
        "next_action": question_release.get("next_action") or {},
        "media_release": question_release.get("media_release"),
    }


def feedback_content_sha256(question_release: dict[str, Any]) -> str:
    return canonical_sha256(feedback_content_payload(question_release))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_release_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "ontology_trust_kernel_releases.v1", "releases": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _answer_values(question: dict[str, Any]) -> list[str]:
    raw = question.get("generated_answer") or question.get("answer") or []
    values = raw if isinstance(raw, list) else [raw]
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _target_from_question(question: dict[str, Any]) -> tuple[str, str, list[str], str | None]:
    blueprint = question.get("question_blueprint") if isinstance(question.get("question_blueprint"), dict) else {}
    target = blueprint.get("target") if isinstance(blueprint.get("target"), dict) else {}
    concept_id = str(
        question.get("disease_concept_id")
        or blueprint.get("disease_concept_id")
        or target.get("disease_concept_id")
        or ""
    ).strip()
    axis_type = str(
        question.get("target_axis_type")
        or blueprint.get("target_axis_type")
        or target.get("axis_type")
        or ""
    ).strip()
    raw_ids = question.get("target_axis_ids") or target.get("axis_ids") or []
    raw_ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
    axis_ids = sorted({str(value).strip() for value in raw_ids if str(value or "").strip()})
    blueprint_id = str(blueprint.get("blueprint_id") or "").strip() or None
    return concept_id, axis_type, axis_ids, blueprint_id


def _review_value(row: dict[str, Any], key: str, default: Any = None) -> Any:
    if key == "status" and "review_status" in row:
        return row.get("review_status")
    if key in row:
        return row.get(key)
    review = row.get("review") if isinstance(row.get("review"), dict) else {}
    return review.get(key, default)


def _verified_claim(row: dict[str, Any]) -> bool:
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    refs = row.get("evidence_refs") or provenance.get("evidence_refs") or []
    return bool(
        _review_value(row, "status") == "approved"
        and bool(_review_value(row, "medical_approval", False))
        and _review_value(row, "applicability") == "applicable"
        and provenance.get("claim_entailment") == "verified"
        and any(
            isinstance(ref, dict)
            and ref.get("entailment_status") == "verified"
            and ref.get("scope") == "claim_review"
            for ref in refs
        )
    )


def evaluate_release(
    *,
    registry: dict[str, Any],
    exam_id: str,
    question: dict[str, Any],
    surface: str,
    concept_registry: dict[str, Any],
    axis_registry: dict[str, Any],
    source_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return a release decision.  Every failure is a closed gate."""

    reasons: list[str] = []
    current_question_hash = question_content_sha256(question)
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(registry, schema)
    except (OSError, json.JSONDecodeError, jsonschema.ValidationError):
        return {"allowed": False, "release_id": None, "reasons": ["release_registry_invalid"], "item_version": current_question_hash}

    question_id = str(question.get("question_id") or question.get("question_number") or "").strip()
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for release in registry.get("releases") or []:
        for item in release.get("questions") or []:
            if str(item.get("exam_id")) == str(exam_id) and str(item.get("question_id")) == question_id:
                candidates.append((release, item))
    if not candidates:
        return {"allowed": False, "release_id": None, "reasons": ["trust_kernel_release_missing"], "item_version": current_question_hash}
    if len(candidates) != 1:
        return {"allowed": False, "release_id": None, "reasons": ["trust_kernel_release_ambiguous"], "item_version": current_question_hash}

    release, item = candidates[0]
    release_id = release.get("release_id")
    if release.get("status") != "released" or (release.get("release_decision") or {}).get("status") != "released":
        reasons.append("trust_kernel_not_released")
    if surface not in (release.get("surfaces") or []):
        reasons.append("surface_not_released")
    decision = release.get("release_decision") or {}
    if not decision.get("reviewer_id") or not decision.get("reviewed_at"):
        reasons.append("release_reviewer_missing")

    snapshots = release.get("source_snapshots") or {}
    if not source_hashes:
        reasons.append("source_snapshot_unavailable")
    else:
        for key in ("axis_registry_sha256", "review_decisions_sha256"):
            if snapshots.get(key) != source_hashes.get(key):
                reasons.append(f"source_snapshot_mismatch:{key}")

    if item.get("question_content_sha256") != current_question_hash:
        reasons.append("question_content_hash_mismatch")
    if item.get("feedback_content_sha256") != feedback_content_sha256(item):
        reasons.append("feedback_content_hash_mismatch")

    concept_id, axis_type, axis_ids, blueprint_id = _target_from_question(question)
    if item.get("blueprint_id") != blueprint_id:
        reasons.append("blueprint_id_mismatch")
    if item.get("disease_concept_id") != concept_id:
        reasons.append("disease_concept_id_mismatch")
    if item.get("target_axis_type") != axis_type:
        reasons.append("target_axis_type_mismatch")
    if sorted(item.get("target_axis_ids") or []) != axis_ids:
        reasons.append("target_axis_ids_mismatch")

    concepts = concept_registry.get("concepts") or {}
    concept = concepts.get(concept_id) if isinstance(concepts, dict) else None
    if not isinstance(concept, dict) or not (
        _review_value(concept, "status") == "approved"
        and bool(_review_value(concept, "medical_approval", False))
        and concept.get("needs_review") is False
    ):
        reasons.append("concept_not_medically_approved")

    relationships = {
        str(row.get("claim_id")): row
        for row in axis_registry.get("relationships") or []
        if isinstance(row, dict) and row.get("claim_id")
    }
    axis_nodes = {
        str(row.get("axis_id")): row
        for row in axis_registry.get("nodes") or []
        if isinstance(row, dict) and row.get("axis_id")
    }
    target_claim_ids = item.get("target_claim_ids") or []
    for claim_id in target_claim_ids:
        row = relationships.get(claim_id)
        if not row:
            reasons.append(f"target_claim_missing:{claim_id}")
            continue
        if row.get("disease_concept_id") != concept_id or row.get("axis_id") not in axis_ids:
            reasons.append(f"target_claim_scope_mismatch:{claim_id}")
        if not _verified_claim(row):
            reasons.append(f"target_claim_not_approved:{claim_id}")
        axis_node = axis_nodes.get(str(row.get("axis_id")))
        if not axis_node or not _verified_claim(axis_node):
            reasons.append(f"target_axis_node_not_approved:{row.get('axis_id')}")

    choices = question.get("choices") or {}
    choice_keys = {str(key) for key in choices} if isinstance(choices, dict) else {
        str(index + 1) for index, _ in enumerate(choices if isinstance(choices, list) else [])
    }
    bindings = item.get("choice_bindings") or []
    binding_by_choice = {str(row.get("choice")): row for row in bindings if isinstance(row, dict)}
    if set(binding_by_choice) != choice_keys:
        reasons.append("choice_binding_incomplete")
    answers = set(_answer_values(question))
    for choice, binding in binding_by_choice.items():
        expected_role = "answer" if choice in answers else "distractor"
        if binding.get("role") != expected_role:
            reasons.append(f"choice_role_mismatch:{choice}")
        referenced_claims = set(binding.get("feedback_claim_ids") or [])
        rule = binding.get("discriminating_rule") or {}
        if not referenced_claims or not referenced_claims.issubset(set(target_claim_ids)):
            reasons.append(f"choice_claim_mismatch:{choice}")
        if rule.get("claim_id") not in target_claim_ids:
            reasons.append(f"choice_rule_claim_mismatch:{choice}")

    if not all((row or {}).get("status") == "verified" for row in item.get("evidence") or []):
        reasons.append("feedback_evidence_not_verified")
    has_media = bool(
        question.get("media_refs")
        or ((question.get("media") or {}).get("media_refs") if isinstance(question.get("media"), dict) else [])
    )
    expected_media_status = "passed" if has_media else "not_applicable"
    if item.get("media_release") != expected_media_status:
        reasons.append("media_release_not_passed")

    reasons = list(dict.fromkeys(reasons))
    return {
        "allowed": not reasons,
        "release_id": release_id if not reasons else None,
        "candidate_release_id": release_id,
        "reasons": reasons,
        "release_digest": canonical_sha256(release) if not reasons else None,
        "release": release if not reasons else None,
        "question_release": item if not reasons else None,
        "item_version": current_question_hash,
    }
