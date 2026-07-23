#!/usr/bin/env python3
"""Local concept-registry grounding for the question-generation pipeline.

Only sanitized ontology fields are placed in prompts. Raw exam stems, extracted
question JSON, PDFs, and page text are never read by this module.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.item_quality_check import apply_generation_quality_gate
except ModuleNotFoundError:  # direct script execution
    from item_quality_check import apply_generation_quality_gate

try:
    from scripts.build_typed_entity_registry import load_active_entities
except ModuleNotFoundError:  # direct script execution
    from build_typed_entity_registry import load_active_entities


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data_private" / "concept_registry.json"
BRIDGES_PATH = ROOT / "data_private" / "curriculum" / "distractor_bridges.json"
AXIS_REGISTRY_PATH = ROOT / "data_private" / "curriculum" / "axis_registry.json"
TYPED_ENTITY_REGISTRY_PATH = ROOT / "data_private" / "curriculum" / "typed_entity_registry.json"
REVIEW_DECISIONS_PATH = ROOT / "data_private" / "curriculum" / "ontology_review_decisions.json"

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
AXIS_TYPE_LIMITS = {
    "symptom": 10,
    "diagnosis": 12,
    "pathophysiology": 10,
    "risk_factor": 10,
    "prognosis": 10,
    "epidemiology": 6,
    "treatment": 10,
    "indication": 10,
    "contraindication": 8,
    "etiology": 8,
}
_AXIS_CACHE: dict[str, tuple[int, dict[str, Any], dict[str, Any]]] = {}
NON_GROUNDABLE_SCOPE_STATUSES = {"quarantined_scope_ambiguous", "classification_only"}
DEFAULT_REVIEW_POLICY = "faculty_draft"
REVIEW_POLICIES = frozenset({DEFAULT_REVIEW_POLICY, "student_approved"})
RELATIONSHIP_POLICY_REASON_KEYS = (
    "relationship_review_not_approved",
    "relationship_medical_approval_not_true",
    "relationship_applicability_not_applicable",
    "claim_entailment_not_verified",
    "relationship_reviewer_missing",
    "relationship_reviewed_at_invalid",
)

# Broad classification nodes are useful for navigation but are unsafe item
# targets: an embedding or spelling-tolerant matcher can otherwise map a
# specific disease such as CML to the generic ``leukemia`` node and inherit an
# unrelated distractor set.  These nodes may still be used as taxonomy parents.
GENERIC_PARENT_CONCEPT_IDS = frozenset(
    {
        "anemia",
        "cancer",
        "hematologic_disorder",
        "leukemia",
        "lymphoma",
        "neoplasm",
        "solid_tumor",
        "thrombocytopenia",
    }
)
MEDICAL_EMBEDDING_THRESHOLD = 0.85
MEDICAL_EMBEDDING_MODEL = os.getenv(
    "PACCINE_MEDICAL_EMBEDDING_MODEL",
    "jhgan/ko-sroberta-multitask",
)

# The ontology registry still contains a small number of reviewed routing
# errors.  Corrections here change only the private retrieval route; they do
# not manufacture a claim or mark it medically approved.  The client receives
# only the resulting locator, never ``segment_text``.
HARRISON_LOCATOR_AUDIT_CORRECTIONS: dict[str, dict[str, Any]] = {
    "immune_thrombocytopenia": {
        "chapter": 120,
        "title": "Disorders of Platelets and Vessel Wall",
        "page": 924,
        "confidence": "runtime_locator_audit_correction",
        "status": "locator_audit_corrected_needs_registry_rebuild",
        "pointer_scope": "chapter_routing_seed_not_claim_entailment",
        "medical_approval": False,
        "needs_review": True,
    },
}

SemanticMatcher = Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]]
ContextResolver = Callable[[str, list[dict[str, Any]]], str | dict[str, Any] | None]


@lru_cache(maxsize=2)
def _local_sentence_transformer(model_name: str):
    """Load a cached local medical/Korean encoder without network downloads."""

    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name, local_files_only=True)
    except Exception:
        return None


def _default_semantic_matcher(query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank concept surfaces with the configured *local* embedding model.

    This stage is deliberately optional at runtime: a deployment that does not
    ship the model fails closed and proceeds to the explicit context resolver,
    rather than silently falling back to substring matching.
    """

    model = _local_sentence_transformer(MEDICAL_EMBEDDING_MODEL)
    if model is None or not candidates:
        return []
    try:
        texts = [str(row.get("embedding_text") or "") for row in candidates]
        vectors = model.encode(
            [query, *texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        query_vector = vectors[0]
        rows = [
            {
                **row,
                "similarity": round(float(query_vector @ vector), 6),
                "embedding_model": MEDICAL_EMBEDDING_MODEL,
            }
            for row, vector in zip(candidates, vectors[1:])
        ]
        return sorted(rows, key=lambda row: (-float(row["similarity"]), str(row["concept_id"])))
    except Exception:
        return []


def _default_context_resolver(query: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Resolve an already-short, high-similarity candidate set with an LLM.

    Only the topic and sanitized concept labels/aliases leave the process.  The
    result is accepted only when it is one of the supplied IDs and the model
    emits a high-confidence structured selection; it never carries a medical
    claim or approval state into the item.
    """

    safe_candidates = [
        {
            "concept_id": str(row.get("concept_id") or ""),
            "label": str(row.get("label") or ""),
            "aliases": [str(value) for value in row.get("aliases") or []][:8],
            "similarity": float(row.get("similarity") or 0.0),
        }
        for row in candidates[:5]
        if str(row.get("concept_id") or "") not in GENERIC_PARENT_CONCEPT_IDS
    ]
    allowed = {row["concept_id"] for row in safe_candidates if row["concept_id"]}
    if not allowed:
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import requests

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": os.getenv("PACCINE_COPILOT_MODEL", "claude-sonnet-4-6"),
                "max_tokens": 180,
                "temperature": 0,
                "system": "Select one supplied medical concept ID or null. Return JSON only; do not add medical facts.",
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "topic": str(query or "")[:500],
                                "candidates": safe_candidates,
                                "schema": {
                                    "concept_id": "one supplied ID or null",
                                    "confidence": "0..1",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
            },
            timeout=20,
        )
        if response.status_code >= 400:
            return None
        payload = response.json()
        text = "".join(
            str(block.get("text") or "")
            for block in payload.get("content") or []
            if isinstance(block, dict) and block.get("type") == "text"
        )
        match = re.search(r"\{.*\}", text, re.DOTALL)
        selected = json.loads(match.group(0) if match else text)
        selected_id = str(selected.get("concept_id") or "")
        confidence = float(selected.get("confidence") or 0.0)
        if selected_id in allowed and confidence >= 0.90:
            return {"concept_id": selected_id, "confidence": confidence, "resolver": "anthropic_context"}
    except Exception:
        return None
    return None


def normalize_review_policy(value: Any = DEFAULT_REVIEW_POLICY) -> str:
    """Return a supported, explicit ontology review policy.

    ``student_approved`` is intentionally fail-closed. Missing review or
    entailment metadata is not interpreted as approval.
    """

    policy = str(value or DEFAULT_REVIEW_POLICY).strip().casefold()
    if policy not in REVIEW_POLICIES:
        supported = ", ".join(sorted(REVIEW_POLICIES))
        raise ValueError(f"unsupported ontology review policy: {value!r}; expected one of {supported}")
    return policy


def review_policy_requirements(review_policy: str) -> dict[str, Any]:
    policy = normalize_review_policy(review_policy)
    if policy == "student_approved":
        return {
            "review_status": "approved",
            "medical_approval": True,
            "applicability": "applicable",
            "claim_entailment": "verified",
            "human_reviewer_and_timestamp": "required",
            "missing_metadata": "exclude",
            "general_fallback": "blocked",
            "axis_registry_prerequisite": (
                "rebuild axis_registry with build_axis_layer.py after updating "
                "ontology_review_decisions.json"
            ),
        }
    return {
        "review_status": "draft_allowed",
        "claim_entailment": "unverified_allowed",
        "missing_metadata": "include_as_draft",
        "general_fallback": "allowed_needs_review",
    }


def _claim_entailment_status(row: dict[str, Any]) -> str:
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    return str(row.get("claim_entailment") or provenance.get("claim_entailment") or "").strip().casefold()


def _review_value(row: dict[str, Any], key: str) -> Any:
    if key in row and row.get(key) is not None:
        return row.get(key)
    review = row.get("review") if isinstance(row.get("review"), dict) else {}
    return review.get(key)


def _relationship_policy_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    status = _review_value(row, "review_status") or _review_value(row, "status")
    if str(status or "").strip().casefold() != "approved":
        reasons.append("relationship_review_not_approved")
    if _review_value(row, "medical_approval") is not True:
        reasons.append("relationship_medical_approval_not_true")
    if str(_review_value(row, "applicability") or "").strip().casefold() != "applicable":
        reasons.append("relationship_applicability_not_applicable")
    if _claim_entailment_status(row) != "verified":
        reasons.append("claim_entailment_not_verified")
    if not str(_review_value(row, "reviewer_id") or "").strip():
        reasons.append("relationship_reviewer_missing")
    if not _valid_iso_datetime(_review_value(row, "reviewed_at")):
        reasons.append("relationship_reviewed_at_invalid")
    return reasons


def _axis_policy_reasons(node: dict[str, Any], edge: dict[str, Any]) -> list[str]:
    reasons = _relationship_policy_reasons(edge)
    status = _review_value(node, "review_status") or _review_value(node, "status")
    if str(status or "").strip().casefold() != "approved":
        reasons.insert(0, "axis_review_not_approved")
    if _review_value(node, "medical_approval") is not True:
        reasons.append("axis_medical_approval_not_true")
    if str(_review_value(node, "applicability") or "").strip().casefold() != "applicable":
        reasons.append("axis_applicability_not_applicable")
    if _claim_entailment_status(node) != "verified":
        reasons.append("axis_claim_entailment_not_verified")
    if not str(_review_value(node, "reviewer_id") or "").strip():
        reasons.append("axis_reviewer_missing")
    if not _valid_iso_datetime(_review_value(node, "reviewed_at")):
        reasons.append("axis_reviewed_at_invalid")
    return reasons


def _verified_evidence_refs(row: dict[str, Any]) -> list[dict[str, Any]]:
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    refs = row.get("evidence_refs") or provenance.get("evidence_refs") or []
    return [
        dict(ref)
        for ref in refs
        if isinstance(ref, dict)
        and str(ref.get("entailment_status") or "").strip().casefold() == "verified"
    ]


def load_review_decisions(
    path: Path = REVIEW_DECISIONS_PATH,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Load explicit concept decisions; a missing/invalid file approves nothing."""

    display_path = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    if not path.exists():
        return {}, {
            "status": "review_decisions_missing",
            "path": display_path,
            "schema_version": None,
            "concept_decision_count": 0,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {
            "status": "review_decisions_invalid_json",
            "path": display_path,
            "schema_version": None,
            "concept_decision_count": 0,
        }
    schema_version = data.get("schema_version") if isinstance(data, dict) else None
    if schema_version != "ontology_review_decisions.v1":
        return {}, {
            "status": "review_decisions_schema_mismatch",
            "path": display_path,
            "schema_version": schema_version,
            "concept_decision_count": 0,
        }
    concepts: dict[str, dict[str, Any]] = {}
    for row in data.get("concepts") or []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("disease_concept_id") or row.get("concept_id") or row.get("id") or "").strip()
        if cid:
            concepts[cid] = dict(row)
    return concepts, {
        "status": "loaded",
        "path": display_path,
        "schema_version": schema_version,
        "concept_decision_count": len(concepts),
        "axis_node_decision_count": len(data.get("axis_nodes") or []),
        "axis_relationship_decision_count": len(data.get("axis_relationships") or []),
    }


def _decision_status(row: dict[str, Any] | None) -> str:
    row = row or {}
    return str(row.get("review_status") or row.get("decision") or row.get("status") or "").strip().casefold()


def _valid_iso_datetime(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _concept_approval_failures(row: dict[str, Any] | None) -> list[str]:
    """Validate the complete human medical-approval contract, fail closed."""

    if not isinstance(row, dict):
        return ["concept_review_decision_missing"]
    failures: list[str] = []
    if _decision_status(row) != "approved":
        failures.append("concept_review_status_not_approved")
    if row.get("medical_approval") is not True:
        failures.append("concept_medical_approval_not_true")
    if str(row.get("applicability") or "").strip().casefold() != "applicable":
        failures.append("concept_applicability_not_applicable")
    if str(row.get("claim_entailment") or "").strip().casefold() != "verified":
        failures.append("concept_claim_entailment_not_verified")
    if not str(row.get("reviewer_id") or "").strip():
        failures.append("concept_reviewer_missing")
    if not _valid_iso_datetime(row.get("reviewed_at")):
        failures.append("concept_reviewed_at_invalid")
    review_flags = row.get("review_flags")
    if not isinstance(review_flags, list) or not all(
        isinstance(flag, str) and flag.strip() for flag in review_flags
    ):
        failures.append("concept_review_flags_invalid")
    return failures


def normalized_term(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").casefold())


def load_registry(
    path: Path = REGISTRY_PATH,
    typed_entity_registry_path: Path = TYPED_ENTITY_REGISTRY_PATH,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"status": "registry_missing", "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8"))
    concepts = data.get("concepts") if isinstance(data, dict) else {}
    if isinstance(concepts, list):
        concepts = {
            str(item.get("disease_concept_id")): item
            for item in concepts
            if isinstance(item, dict) and item.get("disease_concept_id")
        }
    if not isinstance(concepts, dict):
        concepts = {}
    source_concept_count = len(concepts)
    typed_entities = load_active_entities(typed_entity_registry_path)
    concepts = {cid: row for cid, row in concepts.items() if cid not in typed_entities}
    return concepts, {
        "status": "loaded",
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "concept_count": len(concepts),
        "source_concept_count": source_concept_count,
        "typed_entities_excluded": len(typed_entities),
        "registry_generated_at": (data.get("_meta") or {}).get("generated_at") if isinstance(data, dict) else None,
    }


def load_axis_registry(path: Path = AXIS_REGISTRY_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"status": "axis_registry_missing", "path": str(path)}
    cache_key = str(path.resolve())
    stamp = path.stat().st_mtime_ns
    cached = _AXIS_CACHE.get(cache_key)
    if cached and cached[0] == stamp:
        return cached[1], dict(cached[2])
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = {
        str(row.get("axis_id")): row
        for row in (data.get("nodes") or [])
        if isinstance(row, dict) and row.get("axis_id")
    }
    review_application = (
        data.get("review_overrides")
        if isinstance(data.get("review_overrides"), dict)
        else data.get("review_decisions")
        if isinstance(data.get("review_decisions"), dict)
        else {}
    )
    meta = {
        "status": "loaded",
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "schema_version": data.get("schema_version"),
        "node_count": len(nodes),
        "relationship_count": len(data.get("relationships") or []),
        "stats": data.get("stats") or {},
        "review_decisions_applied": review_application.get("applied_count"),
        "review_decisions_status": review_application.get("status"),
        "review_decisions_schema_version": review_application.get("schema_version"),
        "review_decisions_path": review_application.get("path"),
        "relationships": data.get("relationships") or [],
    }
    _AXIS_CACHE[cache_key] = (stamp, nodes, meta)
    return nodes, dict(meta)


def build_axis_context(
    cid: str,
    axis_registry_path: Path = AXIS_REGISTRY_PATH,
    *,
    max_chars: int = 12000,
    review_policy: str = DEFAULT_REVIEW_POLICY,
) -> dict[str, Any]:
    policy = normalize_review_policy(review_policy)
    nodes, meta = load_axis_registry(axis_registry_path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    used_chars = 0
    seen: set[tuple[str, str]] = set()
    candidate_relationship_count = 0
    included_relationship_count = 0
    policy_excluded_relationship_count = 0
    excluded_by_reason: dict[str, int] = defaultdict(int)
    verified_refs: dict[str, dict[str, Any]] = {}
    for edge in meta.pop("relationships", []):
        if not isinstance(edge, dict) or edge.get("disease_concept_id") != cid:
            continue
        candidate_relationship_count += 1
        node = nodes.get(str(edge.get("axis_id")))
        if not node:
            excluded_by_reason["axis_node_missing"] += 1
            continue
        if policy == "student_approved":
            policy_reasons = _axis_policy_reasons(node, edge)
            if policy_reasons:
                policy_excluded_relationship_count += 1
                for reason in policy_reasons:
                    excluded_by_reason[reason] += 1
                continue
        axis_type = str(node.get("axis_type") or "axis")
        label = re.sub(r"\s+", " ", str(node.get("label") or "")).strip()
        if not label or (axis_type, label.casefold()) in seen:
            excluded_by_reason["empty_or_duplicate_axis"] += 1
            continue
        if len(grouped[axis_type]) >= AXIS_TYPE_LIMITS.get(axis_type, 8):
            excluded_by_reason["axis_type_limit"] += 1
            continue
        if used_chars + len(label) > max_chars:
            excluded_by_reason["character_budget"] += 1
            continue
        seen.add((axis_type, label.casefold()))
        used_chars += len(label)
        included_relationship_count += 1
        if policy == "student_approved":
            for ref in _verified_evidence_refs(edge):
                ref_key = str(ref.get("ref_id") or json.dumps(ref, ensure_ascii=False, sort_keys=True))
                verified_refs.setdefault(ref_key, ref)
        grouped[axis_type].append(
            {
                "axis_id": node.get("axis_id"),
                "label": label,
                "relation": edge.get("relation"),
                "dimension": node.get("dimension") or "",
                "source": edge.get("source") or ",".join(node.get("sources") or []),
                "axis_review_status": node.get("review_status"),
                "relationship_review_status": edge.get("review_status"),
                "claim_entailment": _claim_entailment_status(edge) or None,
                "needs_review": bool(node.get("needs_review", True)),
            }
        )
    ordered = {
        axis_type: grouped[axis_type]
        for axis_type in (*AXIS_TYPE_ORDER, *sorted(grouped))
        if grouped.get(axis_type)
    }
    excluded_counts = {
        "relationships_total": max(candidate_relationship_count - included_relationship_count, 0),
        "policy_total": policy_excluded_relationship_count,
        "axis_review_not_approved": excluded_by_reason.get("axis_review_not_approved", 0),
        "axis_medical_approval_not_true": excluded_by_reason.get("axis_medical_approval_not_true", 0),
        "axis_applicability_not_applicable": excluded_by_reason.get("axis_applicability_not_applicable", 0),
        "axis_claim_entailment_not_verified": excluded_by_reason.get("axis_claim_entailment_not_verified", 0),
        "axis_reviewer_missing": excluded_by_reason.get("axis_reviewer_missing", 0),
        "axis_reviewed_at_invalid": excluded_by_reason.get("axis_reviewed_at_invalid", 0),
        "relationship_review_not_approved": excluded_by_reason.get("relationship_review_not_approved", 0),
        "relationship_medical_approval_not_true": excluded_by_reason.get("relationship_medical_approval_not_true", 0),
        "relationship_applicability_not_applicable": excluded_by_reason.get("relationship_applicability_not_applicable", 0),
        "claim_entailment_not_verified": excluded_by_reason.get("claim_entailment_not_verified", 0),
        "relationship_reviewer_missing": excluded_by_reason.get("relationship_reviewer_missing", 0),
        "relationship_reviewed_at_invalid": excluded_by_reason.get("relationship_reviewed_at_invalid", 0),
        "axis_node_missing": excluded_by_reason.get("axis_node_missing", 0),
        "empty_or_duplicate_axis": excluded_by_reason.get("empty_or_duplicate_axis", 0),
        "axis_type_limit": excluded_by_reason.get("axis_type_limit", 0),
        "character_budget": excluded_by_reason.get("character_budget", 0),
    }
    if ordered:
        status = "matched"
    elif policy == "student_approved" and candidate_relationship_count:
        status = "no_approved_axis_claims"
    else:
        status = "no_axis_nodes"
    return {
        "status": status,
        "review_policy": policy,
        "policy_requirements": review_policy_requirements(policy),
        "disease_concept_id": cid,
        "types": ordered,
        "type_counts": {key: len(value) for key, value in ordered.items()},
        "node_count": sum(len(value) for value in ordered.values()),
        "candidate_relationship_count": candidate_relationship_count,
        "included_relationship_count": included_relationship_count,
        "excluded_counts": excluded_counts,
        "verified_evidence_refs": list(verified_refs.values()),
        "verified_evidence_ref_count": len(verified_refs),
        "chars": used_chars,
        "registry": meta,
        "needs_review": True,
    }


def concept_terms(cid: str, concept: dict[str, Any]) -> list[str]:
    aliases = concept.get("aliases") if isinstance(concept.get("aliases"), list) else []
    return [cid, cid.replace("_", " "), *[str(alias) for alias in aliases if str(alias).strip()]]


def is_scope_groundable(concept: dict[str, Any]) -> bool:
    return str(concept.get("generation_grounding_status") or "") not in NON_GROUNDABLE_SCOPE_STATUSES


def match_topic_to_concept(
    topic: str,
    concepts: dict[str, Any],
    typed_entities: dict[str, dict[str, Any]] | None = None,
    *,
    semantic_matcher: SemanticMatcher | None = None,
    context_resolver: ContextResolver | None = None,
    semantic_threshold: float = MEDICAL_EMBEDDING_THRESHOLD,
) -> dict[str, Any]:
    """Resolve a generation topic with an exact -> embedding -> context cascade.

    Substring containment is intentionally forbidden.  If a specific disease
    cannot be resolved above the semantic threshold, or an ambiguous shortlist
    cannot be resolved by the supplied context resolver, generation remains
    blocked and ``needs_review`` is carried by the caller.
    """

    query = normalized_term(topic)
    if not query:
        return {"status": "unmatched", "reason": "empty_topic", "disease_concept_id": None}

    typed_entities = load_active_entities() if typed_entities is None else typed_entities
    for cid, entity in typed_entities.items():
        terms = [cid, cid.replace("_", " "), entity.get("label"), *(entity.get("aliases") or [])]
        if any(normalized_term(term) == query for term in terms if str(term or "").strip()):
            return {
                "status": "non_disease_typed_entity",
                "reason": "typed_entity_excluded_from_disease_generation",
                "disease_concept_id": None,
                "typed_entity_id": entity.get("entity_id"),
                "concept_id": cid,
                "entity_type": entity.get("entity_type"),
            }

    for cid, concept in concepts.items():
        if is_scope_groundable(concept):
            continue
        if any(normalized_term(term) == query for term in concept_terms(cid, concept)):
            return {
                "status": "scope_quarantined_concept",
                "reason": "scope_parent_or_classification_node_excluded_from_generation",
                "disease_concept_id": None,
                "concept_id": cid,
                "generation_grounding_status": concept.get("generation_grounding_status"),
            }

    exact_candidates: list[tuple[str, str, str]] = []
    for cid, concept in concepts.items():
        if not is_scope_groundable(concept):
            continue
        for term in concept_terms(cid, concept):
            normalized = normalized_term(term)
            if not normalized:
                continue
            if normalized == query:
                method = "exact_id" if normalized == normalized_term(cid) else "exact_alias"
                exact_candidates.append((cid, method, str(term)))

    exact_ids = sorted({row[0] for row in exact_candidates})
    if len(exact_ids) == 1:
        cid = exact_ids[0]
        if cid in GENERIC_PARENT_CONCEPT_IDS:
            return {
                "status": "generic_parent_rejected",
                "reason": "generic_parent_not_valid_generation_target",
                "disease_concept_id": None,
                "candidate_ids": [cid],
            }
        row = next(row for row in exact_candidates if row[0] == cid)
        return {
            "status": "matched",
            "disease_concept_id": cid,
            "match_method": row[1],
            "matched_term": row[2],
        }

    shortlist: list[dict[str, Any]] = []
    if len(exact_ids) > 1:
        shortlist = [
            {
                "concept_id": cid,
                "label": display_label(cid, concepts[cid]),
                "matched_term": next(row[2] for row in exact_candidates if row[0] == cid),
                "similarity": 1.0,
                "match_stage": "exact_ambiguous",
            }
            for cid in exact_ids
            if cid not in GENERIC_PARENT_CONCEPT_IDS
        ]
    else:
        embedding_candidates = [
            {
                "concept_id": cid,
                "label": display_label(cid, concept),
                "aliases": concept_terms(cid, concept)[:12],
                "embedding_text": " | ".join(concept_terms(cid, concept)[:12]),
            }
            for cid, concept in concepts.items()
            if is_scope_groundable(concept) and cid not in GENERIC_PARENT_CONCEPT_IDS
        ]
        matcher = semantic_matcher or _default_semantic_matcher
        ranked = matcher(str(topic or "").strip(), embedding_candidates)
        shortlist = [
            {**row, "match_stage": "medical_embedding"}
            for row in ranked
            if float(row.get("similarity") or 0.0) >= float(semantic_threshold)
        ][:5]

        if shortlist:
            top = shortlist[0]
            runner_up = float(shortlist[1].get("similarity") or 0.0) if len(shortlist) > 1 else 0.0
            if float(top.get("similarity") or 0.0) - runner_up >= 0.03:
                return {
                    "status": "matched",
                    "disease_concept_id": top["concept_id"],
                    "match_method": "medical_embedding",
                    "matched_term": top.get("label"),
                    "similarity": top.get("similarity"),
                    "embedding_model": top.get("embedding_model"),
                    "semantic_threshold": float(semantic_threshold),
                }

    if shortlist:
        resolver = context_resolver or _default_context_resolver
        selected = resolver(str(topic or "").strip(), [dict(row) for row in shortlist])
        if isinstance(selected, dict):
            selected_id = str(selected.get("concept_id") or selected.get("disease_concept_id") or "")
        else:
            selected_id = str(selected or "")
        allowed_ids = {str(row.get("concept_id") or "") for row in shortlist}
        if selected_id and selected_id in allowed_ids and selected_id not in GENERIC_PARENT_CONCEPT_IDS:
            selected_row = next(row for row in shortlist if row.get("concept_id") == selected_id)
            return {
                "status": "matched",
                "disease_concept_id": selected_id,
                "match_method": "context_resolver",
                "matched_term": selected_row.get("label"),
                "similarity": selected_row.get("similarity"),
                "semantic_threshold": float(semantic_threshold),
                "candidate_ids": sorted(allowed_ids),
            }

    if shortlist:
        return {
            "status": "ambiguous",
            "reason": "context_resolution_required",
            "disease_concept_id": None,
            "candidate_ids": [str(row.get("concept_id")) for row in shortlist],
            "candidate_scores": {
                str(row.get("concept_id")): float(row.get("similarity") or 0.0)
                for row in shortlist
            },
            "semantic_threshold": float(semantic_threshold),
        }
    return {
        "status": "unmatched",
        "reason": "no_exact_or_high_confidence_semantic_match",
        "disease_concept_id": None,
        "semantic_threshold": float(semantic_threshold),
        "substring_fallback": False,
    }


def edge_rows(concept: dict[str, Any], key: str) -> list[dict[str, Any]]:
    edges = concept.get("edges") if isinstance(concept.get("edges"), dict) else {}
    values = edges.get(key) if isinstance(edges.get(key), list) else []
    out: list[dict[str, Any]] = []
    for value in values:
        row = dict(value) if isinstance(value, dict) else {"id": value}
        endpoint = row.get("id")
        endpoint = str(endpoint or "").strip()
        if endpoint:
            row["id"] = endpoint
            out.append(row)
    return out


def edge_ids(concept: dict[str, Any], key: str) -> list[str]:
    out: list[str] = []
    for row in edge_rows(concept, key):
        endpoint = row["id"]
        if endpoint not in out:
            out.append(endpoint)
    return out


def policy_edge_ids(
    concept: dict[str, Any],
    key: str,
    review_policy: str,
) -> tuple[list[str], dict[str, int]]:
    """Filter a concept-registry relationship without inferring approval.

    Legacy scalar endpoints have no review metadata. They remain available to
    ``faculty_draft`` and are excluded from ``student_approved``.
    """

    policy = normalize_review_policy(review_policy)
    rows = edge_rows(concept, key)
    if policy == DEFAULT_REVIEW_POLICY:
        return edge_ids(concept, key), {
            "candidate": len(rows),
            "excluded_total": 0,
            **{reason: 0 for reason in RELATIONSHIP_POLICY_REASON_KEYS},
        }

    out: list[str] = []
    excluded_total = 0
    reasons: dict[str, int] = defaultdict(int)
    for row in rows:
        policy_reasons = _relationship_policy_reasons(row)
        if policy_reasons:
            excluded_total += 1
            for reason in policy_reasons:
                reasons[reason] += 1
            continue
        if row["id"] not in out:
            out.append(row["id"])
    return out, {
        "candidate": len(rows),
        "excluded_total": excluded_total,
        **{reason: reasons.get(reason, 0) for reason in RELATIONSHIP_POLICY_REASON_KEYS},
    }


def _bridge_copresenters(cid: str, path: Path = BRIDGES_PATH) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for bridge in data.get("bridges") or []:
        diseases = bridge.get("co_presenting_diseases") if isinstance(bridge, dict) else []
        if cid not in diseases:
            continue
        for disease in diseases:
            if disease != cid and disease not in out:
                out.append(disease)
    return out


def _sibling_ids(cid: str, concepts: dict[str, Any]) -> list[str]:
    parents_by_concept: dict[str, set[str]] = {}
    members: dict[str, set[str]] = defaultdict(set)
    for concept_id, concept in concepts.items():
        parents = {
            str(value.get("id"))
            for value in (concept.get("is_a") or [])
            if isinstance(value, dict) and value.get("id")
        }
        parents_by_concept[concept_id] = parents
        for parent in parents:
            members[parent].add(concept_id)
    siblings: set[str] = set()
    for parent in parents_by_concept.get(cid, set()):
        siblings.update(members[parent])
    siblings.discard(cid)
    return sorted(siblings)


def display_label(cid: str, concept: dict[str, Any]) -> str:
    for alias in concept.get("aliases") or []:
        if re.search(r"[가-힣]", str(alias)):
            return str(alias)
    return cid


CLINICAL_DOMAIN_PATTERNS: dict[str, tuple[str, ...]] = {
    "hematology": (
        "혈액", "백혈", "림프종", "빈혈", "혈소판", "응고", "골수", "leuk", "lymphoma",
        "anemia", "platelet", "thrombocyt", "coagulation", "marrow", "myelo",
    ),
    "cardiovascular": (
        "심장", "심근", "심방", "심실", "관상", "부정맥", "심부전", "cardiac", "heart",
        "atrial", "ventricular", "coronary", "arrhythm", "myocard",
    ),
    "neurology": (
        "뇌", "신경", "실어", "발작", "stroke", "cerebr", "neuro", "aphasia", "seizure",
    ),
    "gastrointestinal": (
        "장", "위", "간", "담", "췌", "소화", "mesenter", "bowel", "intestin", "hepatic",
        "liver", "biliar", "pancrea", "gastro",
    ),
    "respiratory": ("폐", "호흡", "기관지", "lung", "pulmonary", "bronch", "respirat"),
    "endocrine": ("내분비", "갑상샘", "당뇨", "thyroid", "diabet", "adrenal", "pituitar"),
    "renal": ("신장", "콩팥", "사구체", "renal", "kidney", "glomerul", "neph"),
    "infectious": ("감염", "균", "바이러스", "infect", "bacter", "viral", "sepsis"),
    "musculoskeletal": ("근골격", "관절", "뼈", "arthritis", "bone", "muscul", "joint"),
    "obgyn": ("산부인", "임신", "자궁", "난소", "pregnan", "uter", "ovar", "obstet"),
    "dermatology": ("피부", "발진", "dermat", "skin", "rash"),
}


def _concept_level(concept: dict[str, Any]) -> str:
    raw = str(concept.get("node_type") or "").strip().casefold()
    if raw in {"syndrome", "finding", "disease", "neoplasm", "disorder"}:
        return "disease" if raw in {"neoplasm", "disorder"} else raw
    return raw


def _clinical_domains(cid: str, concept: dict[str, Any]) -> set[str]:
    taxonomy = concept.get("taxonomy") if isinstance(concept.get("taxonomy"), dict) else {}
    text = " ".join(
        [
            cid.replace("_", " "),
            *[str(value) for value in concept.get("aliases") or []],
            str(concept.get("specialty") or ""),
            str(taxonomy.get("primary_category") or ""),
            str(taxonomy.get("top_category") or ""),
        ]
    ).casefold()
    return {
        domain
        for domain, patterns in CLINICAL_DOMAIN_PATTERNS.items()
        if any(pattern.casefold() in text for pattern in patterns)
    }


def _clinically_compatible(
    answer_id: str,
    answer: dict[str, Any],
    candidate_id: str,
    candidate: dict[str, Any],
) -> tuple[bool, str]:
    answer_level = _concept_level(answer)
    candidate_level = _concept_level(candidate)
    if answer_level and candidate_level and answer_level != candidate_level:
        return False, "concept_level_mismatch"
    answer_domains = _clinical_domains(answer_id, answer)
    candidate_domains = _clinical_domains(candidate_id, candidate)
    if answer_domains and candidate_domains and answer_domains.isdisjoint(candidate_domains):
        return False, "cross_domain"
    if answer_domains and not candidate_domains:
        return False, "candidate_domain_unknown"
    return True, "compatible"


def _rank_distractor_rows(
    guidance: str,
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    if not rows:
        return [], "no_candidates"
    model = _local_sentence_transformer(MEDICAL_EMBEDDING_MODEL)
    if model is not None:
        try:
            candidate_texts = [
                " | ".join(
                    [
                        str(row.get("label") or ""),
                        *[str(alias) for alias in row.get("aliases") or []],
                    ]
                )
                for row in rows
            ]
            vectors = model.encode(
                [guidance, *candidate_texts],
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            query_vector = vectors[0]
            ranked = [
                {**row, "guidance_similarity": round(float(query_vector @ vector), 6)}
                for row, vector in zip(rows, vectors[1:])
            ]
            return (
                sorted(
                    ranked,
                    key=lambda row: (
                        -float(row.get("guidance_similarity") or 0.0),
                        str(row.get("id") or ""),
                    ),
                ),
                f"medical_embedding:{MEDICAL_EMBEDDING_MODEL}",
            )
        except Exception:
            pass
    provenance_rank = {"differential_of": 0, "is_a_sibling": 1, "differential_2hop": 2}
    return (
        sorted(rows, key=lambda row: (provenance_rank.get(str(row.get("provenance")), 9), str(row.get("id")))),
        "deterministic_relation_order_embedding_unavailable",
    )


def build_ranked_distractor_pool(
    cid: str,
    concepts: dict[str, Any],
    *,
    topic: str = "",
    review_policy: str = DEFAULT_REVIEW_POLICY,
    limit: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a same-level, same-domain ontology distractor set.

    Expansion order is direct differential -> is-a sibling -> two-hop
    differential.  The correct answer and exact aliases are excluded before a
    question+answer guidance vector ranks the remaining candidates.
    """

    concept = concepts.get(cid)
    if not isinstance(concept, dict):
        return [], {"status": "answer_concept_missing"}
    policy = normalize_review_policy(review_policy)
    answer_terms = {normalized_term(term) for term in concept_terms(cid, concept) if normalized_term(term)}
    candidate_rows: list[dict[str, Any]] = []
    seen: set[str] = {cid}
    excluded: defaultdict[str, int] = defaultdict(int)

    def add_candidates(
        ids: list[str],
        provenance: str,
        edge_types: dict[str, str] | None = None,
    ) -> None:
        for endpoint in ids:
            endpoint = str(endpoint or "").strip()
            if not endpoint or endpoint in seen:
                continue
            if endpoint in GENERIC_PARENT_CONCEPT_IDS:
                excluded["generic_parent"] += 1
                seen.add(endpoint)
                continue
            endpoint_concept = dict(concepts.get(endpoint) or {
                "disease_concept_id": endpoint,
                "aliases": [endpoint.replace("_", " ")],
            })
            # Direct relationship records sometimes carry a more appropriate
            # option-level type than the legacy node (for example TTP is a
            # syndrome node but explicitly a disorder in ITP's differential).
            edge_type = str((edge_types or {}).get(endpoint) or "").strip().casefold()
            if edge_type in {"disorder", "disease", "syndrome", "finding"}:
                endpoint_concept["node_type"] = "disease" if edge_type == "disorder" else edge_type
            endpoint_terms = {
                normalized_term(term)
                for term in concept_terms(endpoint, endpoint_concept)
                if normalized_term(term)
            }
            if answer_terms & endpoint_terms:
                excluded["answer_or_synonym"] += 1
                seen.add(endpoint)
                continue
            compatible, reason = _clinically_compatible(cid, concept, endpoint, endpoint_concept)
            if not compatible:
                excluded[reason] += 1
                seen.add(endpoint)
                continue
            seen.add(endpoint)
            candidate_rows.append(
                {
                    "id": endpoint,
                    "label": display_label(endpoint, endpoint_concept),
                    "aliases": concept_terms(endpoint, endpoint_concept)[:8],
                    "provenance": provenance,
                    "in_registry": endpoint in concepts,
                    "concept_level": _concept_level(endpoint_concept) or None,
                    "clinical_domains": sorted(_clinical_domains(endpoint, endpoint_concept)),
                }
            )

    direct_ids, direct_counts = policy_edge_ids(concept, "differential_of", policy)
    direct_types = {
        str(row.get("id")): str(row.get("type") or "")
        for row in edge_rows(concept, "differential_of")
    }
    add_candidates(direct_ids, "differential_of", direct_types)

    if len(candidate_rows) < limit and policy == DEFAULT_REVIEW_POLICY:
        add_candidates(_sibling_ids(cid, concepts), "is_a_sibling")

    if len(candidate_rows) < limit:
        direct_seed_ids = [str(value) for value in direct_ids if str(value) in concepts]
        for seed_id in direct_seed_ids:
            second_ids, _counts = policy_edge_ids(concepts[seed_id], "differential_of", policy)
            second_types = {
                str(row.get("id")): str(row.get("type") or "")
                for row in edge_rows(concepts[seed_id], "differential_of")
            }
            add_candidates(second_ids, "differential_2hop", second_types)
            if len(candidate_rows) >= max(limit * 3, limit):
                break

    guidance = " | ".join(
        value
        for value in (str(topic or "").strip(), display_label(cid, concept), cid.replace("_", " "))
        if value
    )
    ranked, ranking_method = _rank_distractor_rows(guidance, candidate_rows)
    selected = ranked[: max(1, int(limit))]
    return selected, {
        "status": "ready" if len(selected) >= limit else "insufficient_same_domain_candidates",
        "requested": int(limit),
        "selected": len(selected),
        "direct_candidate_count": direct_counts.get("candidate", 0),
        "excluded_by_policy": direct_counts.get("excluded_total", 0),
        "excluded_by_reason": dict(excluded),
        "ranking_method": ranking_method,
        "expansion_order": ["differential_of", "is_a_sibling", "differential_2hop"],
        "answer_excluded": True,
        "substring_fallback": False,
    }


def _audited_harrison_pointer(cid: str, concept: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    evidence = concept.get("evidence") if isinstance(concept.get("evidence"), dict) else {}
    pointer = dict(evidence.get("harrison")) if isinstance(evidence.get("harrison"), dict) else {}
    correction = HARRISON_LOCATOR_AUDIT_CORRECTIONS.get(cid)
    if correction:
        original = {
            "chapter": pointer.get("chapter"),
            "page": pointer.get("page"),
            "title": pointer.get("title"),
        }
        pointer.update(correction)
        return pointer, {
            "status": "corrected",
            "concept_id": cid,
            "original": original,
            "corrected": {
                "chapter": pointer.get("chapter"),
                "page": pointer.get("page"),
                "title": pointer.get("title"),
            },
            "claim_entailment": "not_inferred_from_locator",
            "needs_registry_rebuild": True,
        }
    return pointer, None


def _retrieval_intents(concept: dict[str, Any], requested: list[str] | None = None) -> list[str]:
    aliases = {
        "pathophysiology": "mechanism",
        "test_selection": "diagnosis",
        "test_interpretation": "diagnosis",
        "treatment_principle": "treatment",
    }
    out: list[str] = []
    for value in [*(requested or []), *(concept.get("assessment_domains") or [])]:
        normalized = aliases.get(str(value or "").strip(), str(value or "").strip())
        if normalized in {"classification", "diagnosis", "treatment", "mechanism"} and normalized not in out:
            out.append(normalized)
    return out or ["diagnosis", "mechanism"]


def retrieve_item_harrison_evidence(
    query: str,
    cid: str,
    concept: dict[str, Any],
    *,
    intents: list[str] | None = None,
    root: Path = ROOT,
    limit: int = 4,
) -> dict[str, Any]:
    """Retrieve private Harrison passages and public page locators for item drafting.

    Retrieval is not labelled as entailment.  A later claim-level validator or
    faculty review must promote ``entailment_status`` to ``verified``.  Internal
    passage text is returned under a private-only key and is stripped from the
    generated item record.
    """

    pointer, audit = _audited_harrison_pointer(cid, concept)
    if not pointer.get("chapter"):
        return {
            "public_sources": [],
            "_private_sources": [],
            "locator_audit": audit,
            "status": "harrison_route_missing",
        }
    retrieval_query = " | ".join(
        dict.fromkeys(
            value
            for value in (
                str(query or "").strip(),
                display_label(cid, concept),
                cid.replace("_", " "),
                *(str(alias or "").strip() for alias in concept.get("aliases") or []),
            )
            if value
        )
    )
    try:
        from src.services.medical_copilot import retrieve_harrison_evidence

        public, internal = retrieve_harrison_evidence(
            retrieval_query,
            [
                {
                    "concept_id": cid,
                    "aliases": concept_terms(cid, concept)[:12],
                    "harrison": pointer,
                    "retrieval_axes": _retrieval_intents(concept, intents),
                }
            ],
            _retrieval_intents(concept, intents),
            limit=limit,
            root=root,
        )
    except Exception as exc:
        return {
            "public_sources": [],
            "_private_sources": [],
            "locator_audit": audit,
            "status": "harrison_retrieval_failed",
            "error_type": type(exc).__name__,
        }

    public_sources = [
        {
            **row,
            "entailment_status": "needs_human_review",
            "claim_scope": "retrieved_page_candidate_not_claim_entailment",
            "quote_exposed": False,
            "needs_review": True,
        }
        for row in public
    ]
    internal_by_source = {str(row.get("source_id")): row for row in internal}
    private_sources = [
        {
            **source,
            "text": str((internal_by_source.get(str(source.get("source_id"))) or {}).get("text") or "")[:2400],
        }
        for source in public_sources
        if str((internal_by_source.get(str(source.get("source_id"))) or {}).get("text") or "").strip()
    ]
    return {
        "public_sources": public_sources,
        "_private_sources": private_sources,
        "locator_audit": audit,
        "status": "retrieved_candidates_needing_claim_entailment" if public_sources else "no_page_candidate",
        "query": retrieval_query,
        "intents": _retrieval_intents(concept, intents),
        "raw_text_exposed_to_client": False,
    }


def build_evidence_pack(
    cid: str,
    concepts: dict[str, Any],
    axis_registry_path: Path = AXIS_REGISTRY_PATH,
    *,
    review_policy: str = DEFAULT_REVIEW_POLICY,
    topic: str = "",
    retrieval_intents: list[str] | None = None,
    harrison_root: Path = ROOT,
) -> dict[str, Any] | None:
    policy = normalize_review_policy(review_policy)
    concept = concepts.get(cid)
    if not isinstance(concept, dict):
        return None

    pool, distractor_strategy = build_ranked_distractor_pool(
        cid,
        concepts,
        topic=topic,
        review_policy=policy,
        limit=4,
    )
    distractor_excluded_total = int(distractor_strategy.get("excluded_by_policy") or 0)
    distractor_excluded_by_reason = defaultdict(
        int,
        {
            str(key): int(value)
            for key, value in (distractor_strategy.get("excluded_by_reason") or {}).items()
        },
    )
    pool_limit_excluded = 0

    evidence = concept.get("evidence") if isinstance(concept.get("evidence"), dict) else {}
    harrison_retrieval = (
        retrieve_item_harrison_evidence(
            topic or display_label(cid, concept),
            cid,
            concept,
            intents=retrieval_intents,
            root=harrison_root,
        )
        if policy == DEFAULT_REVIEW_POLICY
        else {
            "public_sources": [],
            "_private_sources": [],
            "status": "not_run_under_student_approved_without_claim_approval",
            "locator_audit": None,
        }
    )
    audited_pointer, locator_audit = _audited_harrison_pointer(cid, concept)
    raw_inherited_evidence = {
        "harrison": None,
        "harrison_route": audited_pointer or None,
        "harrison_sources": harrison_retrieval.get("public_sources") or [],
        "harrison_retrieval_status": harrison_retrieval.get("status"),
        "harrison_locator_audit": harrison_retrieval.get("locator_audit") or locator_audit,
        "ncbi": evidence.get("ncbi"),
        "ontology_xref": evidence.get("ontology_xref"),
        "source_refs": concept.get("source_refs") or [],
    }
    edge_keys = (
        "presents_with",
        "diagnosed_by",
        "treated_with",
        "indicated_for",
        "contraindicated_for",
        "due_to",
        "predisposes",
        "causative_agent",
    )
    inherited_edges: dict[str, list[str]] = {}
    inherited_relationships_excluded = 0
    inherited_relationship_excluded_by_reason: dict[str, int] = defaultdict(int)
    for key in edge_keys:
        ids, counts = policy_edge_ids(concept, key, policy)
        inherited_edges[key] = ids
        inherited_relationships_excluded += counts["excluded_total"]
        for reason in RELATIONSHIP_POLICY_REASON_KEYS:
            inherited_relationship_excluded_by_reason[reason] += counts[reason]

    axis_context = build_axis_context(cid, axis_registry_path, review_policy=policy)
    raw_evidence_source_count = sum(
        (
            len(raw_inherited_evidence.get("harrison_sources") or []),
            int(bool(raw_inherited_evidence.get("ncbi"))),
            len(raw_inherited_evidence.get("source_refs") or []),
        )
    )
    if policy == "student_approved":
        inherited_evidence = {
            "harrison": None,
            "harrison_route": None,
            "harrison_sources": [],
            "harrison_retrieval_status": "excluded_unverified_under_student_approved",
            "harrison_locator_audit": None,
            "ncbi": None,
            "ontology_xref": None,
            "source_refs": axis_context.get("verified_evidence_refs") or [],
        }
        inherited_evidence_sources_excluded = raw_evidence_source_count
    else:
        inherited_evidence = raw_inherited_evidence
        inherited_evidence_sources_excluded = 0

    evidence_available = bool(
        inherited_evidence.get("harrison_sources")
        or inherited_evidence.get("ncbi")
        or inherited_evidence.get("source_refs")
    )
    excluded_counts = {
        "axis_relationships": (axis_context.get("excluded_counts") or {}).get("relationships_total", 0),
        "axis_relationships_by_policy": (axis_context.get("excluded_counts") or {}).get("policy_total", 0),
        "inherited_relationships_by_policy": inherited_relationships_excluded,
        "distractor_relationships_by_policy": distractor_excluded_total,
        "distractor_pool_limit": pool_limit_excluded,
        "inherited_evidence_sources_by_policy": inherited_evidence_sources_excluded,
    }
    excluded_counts_by_reason = {
        "axis": axis_context.get("excluded_counts") or {},
        "inherited_relationships": dict(inherited_relationship_excluded_by_reason),
        "distractor_relationships": dict(distractor_excluded_by_reason),
    }
    policy_ready = bool(axis_context.get("node_count") and evidence_available and len(pool) >= 4)
    return {
        "review_policy": policy,
        "policy_requirements": review_policy_requirements(policy),
        "disease_concept_id": cid,
        "label": display_label(cid, concept),
        "node_type": concept.get("node_type"),
        "generation_grounding_status": concept.get("generation_grounding_status") or "legacy_needs_review",
        "assessment_domains": concept.get("assessment_domains") or [],
        "cognitive_model": concept.get("cognitive_model") or {},
        "clinical_axes": concept.get("clinical_axes") or {},
        "axis_context": axis_context,
        "inherited_edges": inherited_edges,
        "distractor_pool": pool,
        "distractor_strategy": distractor_strategy,
        "evidence": inherited_evidence,
        "_private_harrison_sources": harrison_retrieval.get("_private_sources") or [],
        "evidence_available": evidence_available,
        "excluded_counts": excluded_counts,
        "excluded_counts_by_reason": excluded_counts_by_reason,
        "policy_ready": policy_ready if policy == "student_approved" else None,
        "needs_review": True,
        "gen_ready": False,
        "draft_generation_ready": bool(
            evidence_available and axis_context.get("node_count")
        ),
    }


def build_generation_grounding(
    topic: str,
    registry_path: Path = REGISTRY_PATH,
    *,
    axis_registry_path: Path = AXIS_REGISTRY_PATH,
    disease_concept_id: str = "",
    review_policy: str = DEFAULT_REVIEW_POLICY,
    review_decisions_path: Path = REVIEW_DECISIONS_PATH,
    semantic_matcher: SemanticMatcher | None = None,
    context_resolver: ContextResolver | None = None,
    semantic_threshold: float = MEDICAL_EMBEDDING_THRESHOLD,
    retrieval_intents: list[str] | None = None,
    harrison_root: Path = ROOT,
) -> dict[str, Any]:
    policy = normalize_review_policy(review_policy)
    concepts, registry = load_registry(registry_path)
    if policy == "student_approved":
        concept_decisions, review_decisions_meta = load_review_decisions(review_decisions_path)
    else:
        concept_decisions, review_decisions_meta = {}, {
            "status": "not_required_for_faculty_draft",
            "path": (
                str(review_decisions_path.relative_to(ROOT))
                if review_decisions_path.is_relative_to(ROOT)
                else str(review_decisions_path)
            ),
            "schema_version": None,
            "concept_decision_count": 0,
        }
    typed_entities = load_active_entities(TYPED_ENTITY_REGISTRY_PATH)
    explicit_id = str(disease_concept_id or "").strip()
    if explicit_id and explicit_id in concepts and not is_scope_groundable(concepts[explicit_id]):
        concept = concepts[explicit_id]
        match = {
            "status": "scope_quarantined_concept",
            "reason": "scope_parent_or_classification_node_excluded_from_generation",
            "disease_concept_id": None,
            "requested_concept_id": explicit_id,
            "concept_id": explicit_id,
            "generation_grounding_status": concept.get("generation_grounding_status"),
        }
    elif explicit_id and explicit_id in GENERIC_PARENT_CONCEPT_IDS:
        match = {
            "status": "generic_parent_rejected",
            "reason": "generic_parent_not_valid_generation_target",
            "disease_concept_id": None,
            "requested_concept_id": explicit_id,
            "candidate_ids": [explicit_id],
        }
    elif explicit_id and explicit_id in concepts:
        match = {
            "status": "matched",
            "disease_concept_id": explicit_id,
            "match_method": "explicit_concept_id",
            "matched_term": explicit_id,
        }
    elif explicit_id in typed_entities:
        entity = typed_entities[explicit_id]
        match = {
            "status": "non_disease_typed_entity",
            "reason": "typed_entity_excluded_from_disease_generation",
            "disease_concept_id": None,
            "requested_concept_id": explicit_id,
            "typed_entity_id": entity.get("entity_id"),
            "concept_id": explicit_id,
            "entity_type": entity.get("entity_type"),
        }
    elif explicit_id:
        match = {
            "status": "unmatched",
            "reason": "explicit_concept_id_not_found",
            "disease_concept_id": None,
            "requested_concept_id": explicit_id,
        }
    else:
        match = match_topic_to_concept(
            topic,
            concepts,
            typed_entities,
            semantic_matcher=semantic_matcher,
            context_resolver=context_resolver,
            semantic_threshold=semantic_threshold,
        )
    matched_cid = str(match.get("disease_concept_id") or "")
    concept_decision = concept_decisions.get(matched_cid) if matched_cid else None
    concept_approval_failures = (
        _concept_approval_failures(concept_decision) if matched_cid else []
    )
    concept_explicitly_approved = bool(
        matched_cid and not concept_approval_failures
    )
    concept_allowed_by_policy = policy == DEFAULT_REVIEW_POLICY or concept_explicitly_approved
    pack = (
        build_evidence_pack(
            match["disease_concept_id"],
            concepts,
            axis_registry_path,
            review_policy=policy,
            topic=topic,
            retrieval_intents=retrieval_intents,
            harrison_root=harrison_root,
        )
        if match.get("disease_concept_id") and concept_allowed_by_policy
        else None
    )
    missing: list[str] = []
    block_reasons: list[str] = []
    concept_policy_blocked = bool(
        policy == "student_approved" and matched_cid and not concept_explicitly_approved
    )
    if concept_policy_blocked:
        missing.append("concept_not_medically_approved")
        block_reasons.append("concept_not_medically_approved")
    elif not pack:
        missing.append(
            "typed_entity_not_disease_generation_target"
            if match.get("status") == "non_disease_typed_entity"
            else "scope_quarantined_not_generation_target"
            if match.get("status") == "scope_quarantined_concept"
            else "concept_registry_match"
        )
        block_reasons.append(
            "student_approved_concept_grounding_missing"
            if policy == "student_approved"
            else "concept_resolution_or_rag_grounding_missing"
        )
    else:
        if policy == "student_approved":
            if not (pack.get("axis_context") or {}).get("node_count"):
                missing.append("approved_axis_claims_missing")
                block_reasons.append("approved_axis_claims_missing")
            if not pack["evidence_available"]:
                missing.append("verified_claim_evidence_missing")
                block_reasons.append("verified_claim_evidence_missing")
            if len(pack["distractor_pool"]) < 4:
                missing.append("approved_distractor_pool_lt_4")
                block_reasons.append("approved_distractor_pool_lt_4")
        else:
            if not pack["evidence_available"]:
                missing.append("inherited_evidence")
            if len(pack["distractor_pool"]) < 4:
                missing.append("distractor_pool_lt_4")
            if not (pack.get("axis_context") or {}).get("node_count"):
                missing.append("axis_context_missing")
    blocked = bool(block_reasons)
    excluded_counts = (pack or {}).get("excluded_counts") or {}
    if concept_policy_blocked:
        excluded_counts = {**excluded_counts, "concepts_by_policy": 1}
    return {
        "topic": str(topic or "").strip(),
        "review_policy": policy,
        "policy_requirements": review_policy_requirements(policy),
        "review_decisions": review_decisions_meta,
        "concept_review": {
            "disease_concept_id": matched_cid or None,
            "review_status": _decision_status(concept_decision) or None,
            "medically_approved": concept_explicitly_approved,
            "approval_required_by_policy": policy == "student_approved",
            "approval_failures": (
                concept_approval_failures if policy == "student_approved" else []
            ),
        },
        "registry": registry,
        "match": match,
        "pack": pack,
        "fallback_general_generation": False,
        "missing": missing,
        "blocked": blocked,
        "block_reasons": block_reasons,
        # A faculty workflow may still use a later QuestionBlueprint to source
        # same-domain treatment/test options.  Keep context preview available,
        # while standalone generators use these reasons as a pre-model stop.
        "draft_generation_block_reasons": [
            reason
            for reason in (
                "harrison_or_approved_evidence_missing" if "inherited_evidence" in missing else "",
                "distractor_pool_lt_4" if "distractor_pool_lt_4" in missing else "",
                "axis_context_missing" if "axis_context_missing" in missing else "",
            )
            if reason
        ],
        "excluded_counts": excluded_counts,
        "needs_review": True,
        "gen_ready": False,
    }


def append_grounding_context(prompt: str, grounding: dict[str, Any]) -> str:
    policy = normalize_review_policy(grounding.get("review_policy") or DEFAULT_REVIEW_POLICY)
    pack = grounding.get("pack")
    if not pack:
        block = {
            "review_policy": policy,
            "policy_requirements": grounding.get("policy_requirements"),
            "concept_review": grounding.get("concept_review"),
            "review_decisions": grounding.get("review_decisions"),
            "match": grounding.get("match"),
            "missing": grounding.get("missing"),
            "blocked": grounding.get("blocked", False),
            "block_reasons": grounding.get("block_reasons") or [],
            "fallback": (
                "blocked_no_general_fallback_under_student_approved"
                if policy == "student_approved"
                else "blocked_no_substring_or_general_generation_fallback"
            ),
        }
    else:
        prompt_pack = {
            key: pack.get(key)
            for key in (
                "disease_concept_id",
                "label",
                "node_type",
                "assessment_domains",
                "inherited_edges",
                "distractor_pool",
                "distractor_strategy",
                "evidence",
                "evidence_available",
                "axis_context",
                "review_policy",
                "policy_requirements",
                "excluded_counts",
                "policy_ready",
                "needs_review",
            )
        }
        block = {
            "review_policy": policy,
            "policy_requirements": grounding.get("policy_requirements"),
            "concept_review": grounding.get("concept_review"),
            "review_decisions": grounding.get("review_decisions"),
            "match": grounding.get("match"),
            "pack": prompt_pack,
            "private_harrison_context": [
                {
                    "source_id": item.get("source_id"),
                    "locator": item.get("locator"),
                    "chapter": item.get("chapter"),
                    "printed_page": item.get("printed_page"),
                    "text": item.get("text"),
                    "entailment_status": item.get("entailment_status"),
                }
                for item in pack.get("_private_harrison_sources") or []
                if isinstance(item, dict)
            ],
            "blocked": grounding.get("blocked", False),
            "block_reasons": grounding.get("block_reasons") or [],
            "contract": {
                "answer_source": (
                    "student_approved-filtered pack.evidence, inherited_edges, and axis_context only"
                    if policy == "student_approved"
                    else "pack.evidence, inherited_edges, and axis_context only"
                ),
                "harrison_source": (
                    "Use only private_harrison_context to draft the explanation; cite its H source_id and locator. "
                    "Never quote segment text. Retrieval membership is not claim entailment, so keep needs_review=true "
                    "unless a separate claim-level validator verifies it."
                ),
                "distractor_source": (
                    "QuestionBlueprint-approved same-domain axis sources when supplied; "
                    "otherwise pack.distractor_pool"
                ),
                "choice_explanations": "set source_id and provenance for every distractor",
                "axis_trace": "use axis_id and relation when an axis claim supports the answer",
                "review": (
                    "facts passed approved+verified claim filters; generated questions still require review and must never be auto-approved"
                    if policy == "student_approved"
                    else "all ontology facts are needs_review drafts; never present as medically approved"
                ),
                "blocked_action": (
                    "do_not_generate_any_item_when blocked=true; resolve concept, four same-domain distractors, and evidence first"
                ),
            },
        }
    return (
        f"{prompt}\n\n[로컬 concept_registry + private Harrison RAG grounding 팩]\n"
        f"{json.dumps(block, ensure_ascii=False, indent=2)}"
    )


def apply_grounding_trace(record: dict[str, Any], grounding: dict[str, Any]) -> dict[str, Any]:
    policy = normalize_review_policy(grounding.get("review_policy") or DEFAULT_REVIEW_POLICY)
    pack = grounding.get("pack") if isinstance(grounding.get("pack"), dict) else None
    reasons = record.get("review_reasons") if isinstance(record.get("review_reasons"), list) else []
    axis_registry_meta = (((pack or {}).get("axis_context") or {}).get("registry") or {})
    blueprint = record.get("question_blueprint") if isinstance(record.get("question_blueprint"), dict) else {}
    blueprint_sources = blueprint.get("distractor_sources") if isinstance(blueprint.get("distractor_sources"), list) else None
    if blueprint_sources is not None:
        allowed_rows = [
            {
                "id": str(item.get("source_id") or "").strip(),
                "label": str(item.get("label") or item.get("source_id") or "").strip(),
                "aliases": [
                    str(alias).strip()
                    for alias in item.get("aliases") or [item.get("label")]
                    if str(alias or "").strip()
                ],
                "provenance": str(item.get("provenance") or "").strip(),
                "concept_level": str(item.get("concept_level") or "").strip() or None,
            }
            for item in blueprint_sources
            if isinstance(item, dict) and str(item.get("source_id") or "").strip()
        ]
        distractor_contract = "question_blueprint"
    else:
        allowed_rows = [
            item for item in (pack.get("distractor_pool") if pack else [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        distractor_contract = "grounding_pack"
    allowed_harrison_source_ids = [
        str(item.get("source_id"))
        for item in (((pack or {}).get("evidence") or {}).get("harrison_sources") or [])
        if isinstance(item, dict) and str(item.get("source_id") or "").strip()
    ]
    citation_blob = json.dumps(
        {
            "explanation": record.get("explanation"),
            "pma_solution": record.get("pma_solution"),
            "evidence_refs": record.get("evidence_refs"),
            "choice_explanations": record.get("choice_explanations"),
        },
        ensure_ascii=False,
    )
    cited_harrison_ids = set(re.findall(r"(?<![A-Z0-9])H([1-9]\d*)(?![A-Z0-9])", citation_blob))
    cited_harrison_ids = {f"H{value}" for value in cited_harrison_ids}
    for ref in record.get("evidence_refs") or []:
        if isinstance(ref, dict) and str(ref.get("source_id") or "").startswith("H"):
            cited_harrison_ids.add(str(ref["source_id"]))
    answer_citations_in_scope = bool(set(allowed_harrison_source_ids) & cited_harrison_ids)

    trace: dict[str, Any] = {
        "review_policy": policy,
        "policy_requirements": grounding.get("policy_requirements") or review_policy_requirements(policy),
        "concept_review": grounding.get("concept_review") or {},
        "review_decisions": grounding.get("review_decisions") or {},
        "policy_blocked": bool(grounding.get("blocked")),
        "block_reasons": grounding.get("block_reasons") or [],
        "excluded_counts": grounding.get("excluded_counts") or ((pack or {}).get("excluded_counts") or {}),
        "match_status": (grounding.get("match") or {}).get("status"),
        "match_method": (grounding.get("match") or {}).get("match_method"),
        "registry_concept_count": (grounding.get("registry") or {}).get("concept_count", 0),
        "disease_concept_id": pack.get("disease_concept_id") if pack else None,
        "answer_concept_level": _concept_level(pack or {}) or None,
        "answer_evidence_available": bool(pack and pack.get("evidence_available")),
        "answer_citations_in_scope": answer_citations_in_scope,
        "answer_evidence_in_scope": bool(pack and pack.get("evidence_available") and answer_citations_in_scope),
        "allowed_harrison_source_ids": allowed_harrison_source_ids,
        "cited_harrison_source_ids": sorted(cited_harrison_ids),
        "allowed_distractor_ids": [item["id"] for item in allowed_rows],
        "distractor_contract": distractor_contract,
        "distractors": [],
        "axis_node_ids": [
            item.get("axis_id")
            for values in ((pack.get("axis_context") or {}).get("types") or {}).values()
            for item in values
            if item.get("axis_id")
        ] if pack else [],
        "axis_type_counts": ((pack.get("axis_context") or {}).get("type_counts") or {}) if pack else {},
        "axis_registry_review": {
            "review_decisions_applied": axis_registry_meta.get("review_decisions_applied"),
            "review_decisions_status": axis_registry_meta.get("review_decisions_status"),
            "review_decisions_schema_version": axis_registry_meta.get("review_decisions_schema_version"),
            "review_decisions_path": axis_registry_meta.get("review_decisions_path"),
        },
    }

    if trace["policy_blocked"]:
        reasons.append("ontology_review_policy_blocked")
        reasons.extend(trace["block_reasons"])

    if not pack:
        record["disease_concept_id"] = None
        if "concept_not_medically_approved" in trace["block_reasons"]:
            record["concept_grounding_status"] = "concept_not_medically_approved"
        else:
            record["concept_grounding_status"] = "unmatched_fallback"
            reasons.append("concept_registry_match_missing")
        trace["all_distractors_in_scope"] = False
    else:
        record["disease_concept_id"] = pack["disease_concept_id"]
        record["concept_grounding_status"] = (
            "matched_policy_blocked" if trace["policy_blocked"] else "matched"
        )
        record["grounding_evidence"] = pack.get("evidence") or {}
        record["harrison_sources"] = list((pack.get("evidence") or {}).get("harrison_sources") or [])
        trace["evidence_sources"] = [
            key for key, value in (pack.get("evidence") or {}).items() if value
        ]
        if not pack.get("evidence_available"):
            reasons.append("grounding_evidence_missing")
        allowed = {item["id"]: item for item in allowed_rows}
        explanations = record.get("choice_explanations") if isinstance(record.get("choice_explanations"), dict) else {}
        answer = str(record.get("answer") or "")
        choices = record.get("options") if isinstance(record.get("options"), list) else []
        choice_map = record.get("choices") if isinstance(record.get("choices"), dict) else {}
        all_in_scope = True
        for index in range(1, 6):
            key = str(index)
            if key == answer:
                continue
            explanation = explanations.get(key) if isinstance(explanations.get(key), dict) else {}
            source_id = str(explanation.get("source_id") or explanation.get("misconception_id") or "").strip()
            choice_text = choices[index - 1] if index <= len(choices) else str(choice_map.get(key) or "")
            if not source_id:
                inferred = [
                    item["id"]
                    for item in allowed.values()
                    if any(normalized_term(term) and normalized_term(term) in normalized_term(choice_text) for term in item.get("aliases") or [])
                ]
                source_id = inferred[0] if len(set(inferred)) == 1 else source_id
            in_scope = source_id in allowed
            all_in_scope = all_in_scope and in_scope
            if in_scope:
                explanation["source_id"] = source_id
                explanation["provenance"] = allowed[source_id]["provenance"]
                explanation["concept_level"] = allowed[source_id].get("concept_level")
            trace["distractors"].append(
                {
                    "choice": key,
                    "source_id": source_id or None,
                    "in_scope": in_scope,
                    "concept_level": (allowed.get(source_id) or {}).get("concept_level"),
                }
            )
        trace["all_distractors_in_scope"] = all_in_scope
        if not all_in_scope:
            reasons.append("distractor_outside_registry_scope")
        if not answer_citations_in_scope:
            reasons.append("explanation_missing_harrison_source")

    record["grounding_trace"] = trace
    record["review_reasons"] = sorted({str(reason) for reason in reasons if str(reason).strip()})
    self_check = record.get("self_check") if isinstance(record.get("self_check"), dict) else {}
    self_check["evidence_within_inherited_only"] = trace["answer_evidence_in_scope"]
    self_check["every_distractor_from_differential_or_misconception"] = trace.get("all_distractors_in_scope", False)
    record["self_check"] = self_check
    return apply_generation_quality_gate(record)
