#!/usr/bin/env python3
"""Materialize authored clinical dimensions as deterministic ontology nodes.

This is a derived consumer layer. It does not invent medical facts: every node
comes from clinical_axes_map.json, p2_nodes.json, or an existing registry edge.
Automatic rows remain draft_unreviewed; only explicit human review decisions can
change a claim's review state.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from scripts.build_typed_entity_registry import load_active_entities
except ModuleNotFoundError:  # direct script execution
    from build_typed_entity_registry import load_active_entities


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
CURRICULUM = DP / "curriculum"
REGISTRY = DP / "concept_registry.json"
CLINICAL_AXES = CURRICULUM / "clinical_axes_map.json"
P2_NODES = CURRICULUM / "p2_nodes.json"
FINDINGS = CURRICULUM / "finding_registry.json"
TYPED_ENTITIES = CURRICULUM / "typed_entity_registry.json"
OUT = CURRICULUM / "axis_registry.json"
REVIEW_DECISIONS = CURRICULUM / "ontology_review_decisions.json"
HARRISON22_CLAIM_OVERLAY = DP / "harrison" / "22e" / "validation" / "claim_support_overlay.json"
# Backward-compatible symbol for callers introduced during the v1.2 transition.
REVIEW_OVERRIDES = REVIEW_DECISIONS
SCHEMA_VERSION = "1.3.0"
REVIEW_DECISION_SCHEMA_VERSION = "ontology_review_decisions.v1"
REVIEW_OVERRIDE_SCHEMA_VERSION = REVIEW_DECISION_SCHEMA_VERSION
REVIEW_STATUSES = {
    "draft_unreviewed",
    "reviewed_not_approved",
    "changes_requested",
    "rejected",
    "approved",
}
ENTAILMENT_STATUSES = {
    "unverified",
    "needs_human_review",
    "verified",
    "not_supported",
    "contradicted",
}
SOURCE_PATHS = {
    "clinical_axes_map": "data_private/curriculum/clinical_axes_map.json",
    "concept_registry": "data_private/concept_registry.json",
    "p2_nodes": "data_private/curriculum/p2_nodes.json",
}


def claim_lineage_id(claim_kind: str, *parts: object) -> str:
    """Stable identity for a clinical assertion across evidence revisions."""

    identity = "|".join(clean_text(part).casefold() for part in parts)
    digest = hashlib.sha256(f"{claim_kind}|{identity}".encode("utf-8")).hexdigest()[:20]
    return f"l:{claim_kind}:{digest}"


def claim_revision_id(lineage_id: str, assertion: object, qualifiers: dict[str, Any]) -> str:
    identity = json.dumps(
        {"lineage_id": lineage_id, "assertion": clean_text(assertion), "qualifiers": qualifiers},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"r:{digest}"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def axis_id(axis_type: str, label: str, canonical_id: str = "") -> str:
    # Identity is label-based across every source so an authored axis string and
    # the same registry endpoint collapse to one shared semantic node.
    identity = clean_text(label).casefold()
    digest = hashlib.sha1(f"{axis_type}|{identity}".encode("utf-8")).hexdigest()[:14]
    return f"a:{axis_type}:{digest}"


def claim_id(claim_kind: str, *parts: object) -> str:
    """Return a deterministic claim identifier independent of row ordering."""

    identity = "|".join(clean_text(part).casefold() for part in parts)
    digest = hashlib.sha1(f"{claim_kind}|{identity}".encode("utf-8")).hexdigest()[:16]
    return f"c:{claim_kind}:{digest}"


def default_qualifiers() -> dict[str, Any]:
    """Explicit empty context for an unqualified authored claim.

    These fields intentionally remain empty until a source-grounded author or a
    human reviewer supplies them. In particular, no dose, population, or stage
    is inferred by this derived builder.
    """

    return {
        "population": [],
        "clinical_context": [],
        "stage_or_grade": [],
        "temporal_context": [],
        "route": [],
        "dose": [],
        "assertion_polarity": "affirmed",
        "certainty": "unspecified",
    }


def default_review_state() -> dict[str, Any]:
    return {
        "status": "draft_unreviewed",
        "medical_approval": False,
        "applicability": "unknown",
        "flags": [],
        "reviewer_id": None,
        "reviewed_at": None,
        "note": "",
        "override_source": None,
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _valid_iso_datetime(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_qualifiers(value: object, *, claim: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"qualifiers must be an object for {claim}")
    allowed_list_fields = {
        "population",
        "clinical_context",
        "stage_or_grade",
        "temporal_context",
        "route",
        "dose",
    }
    allowed_scalar_fields = {"assertion_polarity", "certainty"}
    unknown = set(value) - allowed_list_fields - allowed_scalar_fields
    if unknown:
        raise ValueError(f"unknown qualifier fields for {claim}: {sorted(unknown)}")
    normalized: dict[str, Any] = {}
    for key in allowed_list_fields:
        if key not in value:
            continue
        if not isinstance(value[key], list) or not all(
            isinstance(item, str) and item.strip() for item in value[key]
        ):
            raise ValueError(f"qualifier {key} must be a list of non-empty strings for {claim}")
        normalized[key] = list(dict.fromkeys(item.strip() for item in value[key]))
    if "assertion_polarity" in value:
        if value["assertion_polarity"] not in {"affirmed", "negated"}:
            raise ValueError(f"invalid assertion_polarity for {claim}")
        normalized["assertion_polarity"] = value["assertion_polarity"]
    if "certainty" in value:
        if value["certainty"] not in {"unspecified", "possible", "probable", "confirmed"}:
            raise ValueError(f"invalid certainty for {claim}")
        normalized["certainty"] = value["certainty"]
    return normalized


def _validate_evidence_refs(value: object, *, claim: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"evidence_refs must be an array for {claim}")
    refs: list[dict[str, Any]] = []
    for ref in value:
        if not isinstance(ref, dict) or not str(ref.get("ref_id") or "").strip():
            raise ValueError(f"every evidence ref requires ref_id for {claim}")
        entailment = str(ref.get("entailment_status") or "needs_human_review")
        if entailment not in ENTAILMENT_STATUSES:
            raise ValueError(f"invalid evidence entailment_status for {claim}: {entailment}")
        normalized = dict(ref)
        normalized["ref_id"] = str(ref["ref_id"]).strip()
        normalized["source_type"] = str(ref.get("source_type") or "review_override")
        normalized["scope"] = str(ref.get("scope") or "claim_review")
        normalized["entailment_status"] = entailment
        refs.append(normalized)
    return refs


def _normalize_review_decision(
    raw: object,
    *,
    identifier_field: str,
    source: str,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"review decision rows must be objects: {source}")
    identifier = str(raw.get(identifier_field) or "").strip()
    if not identifier:
        raise ValueError(f"review decision {identifier_field} is required: {source}")
    status = str(raw.get("review_status") or "").strip()
    if status not in REVIEW_STATUSES - {"draft_unreviewed"}:
        raise ValueError(f"invalid review_status for {identifier}: {status}")
    medical_approval = raw.get("medical_approval")
    if not isinstance(medical_approval, bool):
        raise ValueError(f"medical_approval must be boolean for {identifier}")
    reviewer_id = str(raw.get("reviewer_id") or "").strip()
    reviewed_at = str(raw.get("reviewed_at") or "").strip()
    if not reviewer_id or not _valid_iso_datetime(reviewed_at):
        raise ValueError(f"human reviewer_id and ISO reviewed_at are required for {identifier}")
    entailment = str(raw.get("claim_entailment") or "").strip()
    if entailment not in ENTAILMENT_STATUSES:
        raise ValueError(f"invalid claim_entailment for {identifier}: {entailment}")
    applicability = raw.get("applicability") if "applicability" in raw else None
    if applicability not in {None, "applicable", "not_applicable", "unknown"}:
        raise ValueError(f"invalid applicability for {identifier}: {applicability}")
    review_flags = raw.get("review_flags") or []
    if not isinstance(review_flags, list) or not all(
        isinstance(flag, str) and flag.strip() for flag in review_flags
    ):
        raise ValueError(f"review_flags must be a list of non-empty strings for {identifier}")
    review_flags = list(dict.fromkeys(flag.strip() for flag in review_flags))
    if status == "approved":
        if (
            medical_approval is not True
            or entailment != "verified"
            or applicability != "applicable"
        ):
            raise ValueError(
                "approved claim requires medical_approval=true, "
                f"claim_entailment=verified, and applicability=applicable: {identifier}"
            )
    elif medical_approval:
        raise ValueError(f"only review_status=approved may set medical_approval=true: {identifier}")
    return {
        identifier_field: identifier,
        "review_status": status,
        "medical_approval": medical_approval,
        "reviewer_id": reviewer_id,
        "reviewed_at": reviewed_at,
        "note": str(raw.get("note") or "").strip(),
        "claim_entailment": entailment,
        "applicability": applicability,
        "review_flags": review_flags,
        "qualifiers": _validate_qualifiers(raw.get("qualifiers"), claim=identifier),
        "evidence_refs": _validate_evidence_refs(raw.get("evidence_refs"), claim=identifier),
    }


def load_review_decisions(path: Path = REVIEW_DECISIONS) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Load the axis sections of the unified, explicit human-decision file.

    The shared input contract has ``concepts``, ``axis_nodes``, and
    ``axis_relationships`` sections. This builder validates and counts concept
    decisions but only applies the two axis sections. A missing file is a safe
    no-op, so the normal automatic build stays draft_unreviewed.
    """

    source = _display_path(path)
    empty_counts = {"concepts": 0, "axis_nodes": 0, "axis_relationships": 0}
    if not path.exists():
        return {}, {
            "path": source,
            "status": "not_found_no_overrides_applied",
            "schema_version": REVIEW_DECISION_SCHEMA_VERSION,
            "decision_counts": empty_counts,
            "override_count": 0,
            "applied_count": 0,
        }
    payload = load(path)
    if payload.get("schema_version") != REVIEW_DECISION_SCHEMA_VERSION:
        raise ValueError(
            f"review decision schema_version must be {REVIEW_DECISION_SCHEMA_VERSION}: {source}"
        )
    sections = {}
    for name in ("concepts", "axis_nodes", "axis_relationships"):
        rows = payload.get(name)
        if not isinstance(rows, list):
            raise ValueError(f"review decision section {name} must be an array: {source}")
        sections[name] = rows

    concept_ids: set[str] = set()
    for raw in sections["concepts"]:
        normalized = _normalize_review_decision(raw, identifier_field="concept_id", source=source)
        concept_id_value = normalized["concept_id"]
        if concept_id_value in concept_ids:
            raise ValueError(f"duplicate concept review decision: {concept_id_value}")
        concept_ids.add(concept_id_value)

    overrides: dict[str, dict[str, Any]] = {}
    for section_name, prefix in (
        ("axis_nodes", "c:axis_node:"),
        ("axis_relationships", "c:axis_relation:"),
    ):
        for raw in sections[section_name]:
            normalized = _normalize_review_decision(raw, identifier_field="claim_id", source=source)
            cid = normalized["claim_id"]
            if not cid.startswith(prefix):
                raise ValueError(f"{section_name} claim_id must start with {prefix}: {cid}")
            if cid in overrides:
                raise ValueError(f"duplicate axis review decision claim_id: {cid}")
            overrides[cid] = normalized
    counts = {name: len(rows) for name, rows in sections.items()}
    return overrides, {
        "path": source,
        "status": "loaded",
        "schema_version": REVIEW_DECISION_SCHEMA_VERSION,
        "decision_counts": counts,
        "override_count": len(overrides),
        "applied_count": 0,
    }


def load_review_overrides(path: Path = REVIEW_DECISIONS) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Compatibility alias for the unified review-decision loader."""

    return load_review_decisions(path)


def _merge_evidence_refs(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {str(ref.get("ref_id")): dict(ref) for ref in existing if ref.get("ref_id")}
    for ref in additions:
        merged[str(ref["ref_id"])] = dict(ref)
    return [merged[key] for key in sorted(merged)]


def load_harrison22_claim_overlay(
    path: Path = HARRISON22_CLAIM_OVERLAY,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    source = _display_path(path)
    if not path.exists():
        return {}, {
            "path": source,
            "status": "not_found_no_candidates_applied",
            "snapshot_id": None,
            "candidate_claims": 0,
            "applied_claims": 0,
        }
    payload = load(path)
    if payload.get("schema_version") != "harrison22_claim_revalidation.v1":
        raise ValueError(f"unsupported Harrison 22e claim overlay schema: {source}")
    claims = payload.get("claims")
    if not isinstance(claims, dict):
        raise ValueError(f"Harrison 22e claim overlay requires a claims object: {source}")
    return claims, {
        "path": source,
        "status": "loaded",
        "snapshot_id": payload.get("snapshot_id"),
        "candidate_claims": sum(bool(row.get("candidates")) for row in claims.values()),
        "applied_claims": 0,
    }


def apply_harrison22_candidates(
    node_rows: list[dict[str, Any]],
    edge_rows: list[dict[str, Any]],
    overlay: dict[str, dict[str, Any]],
) -> int:
    """Attach retrieval locators without converting them to verified evidence."""

    targets = {row["claim_id"]: row for row in [*node_rows, *edge_rows]}
    applied = 0
    for cid, candidate_row in overlay.items():
        row = targets.get(cid)
        if not row:
            continue
        refs: list[dict[str, Any]] = []
        for candidate in (candidate_row.get("candidates") or [])[:3]:
            if not candidate.get("ref_id"):
                continue
            refs.append(
                {
                    key: deepcopy(value)
                    for key, value in candidate.items()
                    if key
                    not in {
                        "review_excerpt",
                        "matched_terms",
                        "query_sha256",
                        "disease_concept_id",
                    }
                }
            )
            refs[-1]["disease_concept_id"] = candidate.get("disease_concept_id")
        if not refs:
            continue
        provenance = row["provenance"]
        provenance["status"] = "retrieval_candidate"
        provenance["claim_entailment"] = "needs_human_review"
        provenance["evidence_refs"] = _merge_evidence_refs(
            provenance.get("evidence_refs") or [], refs
        )
        if "evidence_refs" in row:
            row["evidence_refs"] = deepcopy(provenance["evidence_refs"])
        if "provenance_status" in row:
            row["provenance_status"] = provenance["status"]
        applied += 1
    return applied


def attach_claim_lineage(
    node_rows: list[dict[str, Any]], edge_rows: list[dict[str, Any]]
) -> None:
    nodes_by_axis = {row["axis_id"]: row for row in node_rows}
    for row in node_rows:
        endpoint_key = row.get("canonical_id") or f"legacy:{row['claim_id']}"
        lineage = claim_lineage_id("axis_node", row["axis_type"], endpoint_key)
        row["claim_lineage_id"] = lineage
        row["claim_revision_id"] = claim_revision_id(lineage, row["label"], row["qualifiers"])
        row["legacy_claim_ids"] = [row["claim_id"]]
        row["supersedes"] = None
    for row in edge_rows:
        node = nodes_by_axis[row["axis_id"]]
        endpoint_lineage = node["claim_lineage_id"]
        lineage = claim_lineage_id(
            "axis_relation",
            row["disease_concept_id"],
            row["relation"],
            endpoint_lineage,
        )
        row["claim_lineage_id"] = lineage
        row["claim_revision_id"] = claim_revision_id(
            lineage,
            f"{row['disease_concept_id']}|{row['relation']}|{node['label']}",
            row["qualifiers"],
        )
        row["legacy_claim_ids"] = [row["claim_id"]]
        row["supersedes"] = None


def apply_review_overrides(
    node_rows: list[dict[str, Any]],
    edge_rows: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]],
    *,
    source_path: str,
) -> int:
    targets = {
        row["claim_id"]: row
        for row in [*node_rows, *edge_rows]
    }
    unknown = sorted(set(overrides) - set(targets))
    if unknown:
        raise ValueError(f"review override references unknown claim_id(s): {unknown}")
    for cid, override in overrides.items():
        row = targets[cid]
        row["qualifiers"].update(deepcopy(override["qualifiers"]))
        provenance = row["provenance"]
        provenance["status"] = "human_review_override"
        provenance["claim_entailment"] = override["claim_entailment"]
        provenance["evidence_refs"] = _merge_evidence_refs(
            provenance.get("evidence_refs") or [], override["evidence_refs"]
        )
        if "evidence_refs" in row:
            row["evidence_refs"] = deepcopy(provenance["evidence_refs"])
        if "provenance_status" in row:
            row["provenance_status"] = provenance["status"]
        review = {
            "status": override["review_status"],
            "medical_approval": override["medical_approval"],
            "applicability": override["applicability"] or row["applicability"],
            "flags": deepcopy(override["review_flags"]),
            "reviewer_id": override["reviewer_id"],
            "reviewed_at": override["reviewed_at"],
            "note": override["note"],
            "override_source": source_path,
        }
        row["review"] = review
        row["review_status"] = review["status"]
        row["medical_approval"] = review["medical_approval"]
        row["applicability"] = review["applicability"]
        row["needs_review"] = review["status"] != "approved"
    return len(overrides)


def build(
    *,
    review_decisions_path: Path = REVIEW_DECISIONS,
    review_overrides_path: Path | None = None,
    harrison22_claim_overlay_path: Path = HARRISON22_CLAIM_OVERLAY,
) -> dict:
    if review_overrides_path is not None:
        # Compatibility for callers from the short-lived axis-only override API.
        review_decisions_path = review_overrides_path
    registry = load(REGISTRY)
    concepts = registry["concepts"]
    authored = load(CLINICAL_AXES).get("axes", {})
    p2_rows = load(P2_NODES).get("nodes", []) if P2_NODES.exists() else []
    typed_entities = load_active_entities(TYPED_ENTITIES)
    excluded_disease_ids = set(typed_entities)
    finding_ids = {
        row.get("finding_id")
        for row in (load(FINDINGS).get("findings", []) if FINDINGS.exists() else [])
        if isinstance(row, dict) and row.get("finding_id")
    }

    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}

    def provenance_for(disease_id: str, source: str) -> dict:
        concept = concepts.get(disease_id) or {}
        harrison = ((concept.get("evidence") or {}).get("harrison") or {})
        refs = [
            {
                "ref_id": f"local:{source}:{disease_id}",
                "source_type": "local_structured_record",
                "source_path": SOURCE_PATHS.get(source, source),
                "scope": "source_record",
                "entailment_status": "unverified",
            }
        ]
        if harrison.get("chapter") is not None and harrison.get("page") is not None:
            edition = harrison.get("edition") or "legacy_unverified_edition"
            source_id = harrison.get("source_id") or "legacy_pointer"
            refs.append(
                {
                    "ref_id": (
                        f"harrison:{edition}:{source_id}:"
                        f"ch{harrison.get('chapter')}:p{harrison.get('page')}"
                    ),
                    "source_type": "textbook_pointer",
                    "source_path": (
                        "data_private/harrison/22e/concept_harrison_overlay.json"
                        if edition == "22e"
                        else "data_private/harrison/concept_to_harrison.json"
                    ),
                    "edition": edition,
                    "source_id": source_id,
                    "title": harrison.get("title") or "",
                    "chapter": harrison.get("chapter"),
                    "page": harrison.get("page"),
                    "scope": "inherited_disease_reference",
                    "entailment_status": "unverified",
                }
            )
        axis_record = authored.get(disease_id) or {}
        for external in axis_record.get("evidence_refs") or []:
            if not isinstance(external, dict) or not external.get("ref_id"):
                continue
            refs.append(dict(external))
        return {
            "status": "source_pointer_only",
            "claim_entailment": "unverified",
            "evidence_refs": refs,
        }

    def add(
        disease_id: str,
        axis_type: str,
        label: object,
        relation: str,
        source: str,
        *,
        dimension: str = "",
        canonical_id: str = "",
    ) -> None:
        text = clean_text(label)
        if disease_id not in concepts or disease_id in excluded_disease_ids or not text:
            return
        aid = axis_id(axis_type, text, canonical_id)
        row = nodes.setdefault(
            aid,
            {
                "axis_id": aid,
                "claim_id": claim_id("axis_node", aid),
                "axis_type": axis_type,
                "label": text,
                "dimension": dimension,
                "canonical_id": canonical_id,
                "sources": [],
                "disease_ids": [],
                "qualifiers": default_qualifiers(),
                "applicability": "unknown",
                "needs_review": True,
                "review_status": "draft_unreviewed",
                "medical_approval": False,
                "review": default_review_state(),
                "provenance_status": "source_pointer_only",
                "evidence_refs": [],
                "provenance": {
                    "status": "source_pointer_only",
                    "claim_entailment": "unverified",
                    "evidence_refs": [],
                },
            },
        )
        if canonical_id and not row["canonical_id"]:
            row["canonical_id"] = canonical_id
        if source not in row["sources"]:
            row["sources"].append(source)
        if disease_id not in row["disease_ids"]:
            row["disease_ids"].append(disease_id)
        provenance = provenance_for(disease_id, source)
        existing_ref_ids = {ref["ref_id"] for ref in row["evidence_refs"]}
        for ref in provenance["evidence_refs"]:
            if ref["ref_id"] not in existing_ref_ids:
                row["evidence_refs"].append(ref)
                existing_ref_ids.add(ref["ref_id"])
        key = (disease_id, aid, relation)
        edges[key] = {
            "claim_id": claim_id("axis_relation", disease_id, relation, aid),
            "disease_concept_id": disease_id,
            "axis_id": aid,
            "relation": relation,
            "source": source,
            "qualifiers": default_qualifiers(),
            "applicability": "unknown",
            "needs_review": True,
            "review_status": "draft_unreviewed",
            "medical_approval": False,
            "review": default_review_state(),
            "provenance": provenance,
        }

    for disease_id, axes in sorted(authored.items()):
        path = axes.get("pathophysiology") or {}
        add(disease_id, "pathophysiology", path.get("summary"), "has_pathophysiology", "clinical_axes_map", dimension="summary")
        for value in path.get("key_steps") or []:
            add(disease_id, "pathophysiology", value, "has_pathophysiology_step", "clinical_axes_map", dimension="key_step")

        for value in axes.get("risk_factors") or []:
            add(disease_id, "risk_factor", value, "has_risk_factor", "clinical_axes_map")

        prognosis = axes.get("prognosis") or {}
        for value in prognosis.get("factors") or []:
            add(disease_id, "prognosis", value, "has_prognostic_factor", "clinical_axes_map", dimension="factor")
        add(disease_id, "prognosis", prognosis.get("staging_or_grading"), "has_stage_or_grade", "clinical_axes_map", dimension="stage_or_grade")
        add(disease_id, "prognosis", prognosis.get("natural_history"), "has_natural_history", "clinical_axes_map", dimension="natural_history")

        treatment = axes.get("treatment") or {}
        add(disease_id, "treatment", treatment.get("principles"), "has_treatment_principle", "clinical_axes_map", dimension="principle")
        for value in treatment.get("indicated_for") or []:
            add(disease_id, "indication", value, "has_indication", "clinical_axes_map")
        for value in treatment.get("contraindicated_for") or []:
            add(disease_id, "contraindication", value, "has_contraindication", "clinical_axes_map")

        epidemiology = axes.get("epidemiology") or {}
        for dimension in ("age", "sex", "population", "frequency"):
            add(disease_id, "epidemiology", epidemiology.get(dimension), "has_epidemiology", "clinical_axes_map", dimension=dimension)

    # Promote already-authored but unresolved diagnostic/treatment endpoints.
    edge_axis = {
        "presents_with": ("symptom", "presents_with"),
        "predisposes": ("risk_factor", "has_risk_factor"),
        "due_to": ("etiology", "has_etiology"),
        "causative_agent": ("etiology", "has_causative_agent"),
        "diagnosed_by": ("diagnosis", "diagnosed_by"),
        "treated_with": ("treatment", "treated_with"),
        "indicated_for": ("indication", "has_indication"),
        "contraindicated_for": ("contraindication", "has_contraindication"),
    }
    for disease_id, concept in sorted(concepts.items()):
        for edge_name, (kind, relation) in edge_axis.items():
            for value in (concept.get("edges") or {}).get(edge_name, []) or []:
                target = value.get("id") if isinstance(value, dict) else value
                target = clean_text(target)
                if not target or target in concepts or target in finding_ids:
                    continue
                add(
                    disease_id,
                    kind,
                    target.replace("_", " "),
                    relation,
                    "concept_registry",
                    canonical_id=target,
                )

    # P2 contributes symptoms and diagnostic features already curated for items.
    for row in p2_rows:
        disease_id = row.get("node_id")
        model = row.get("cognitive_model") or {}
        for value in model.get("chief_complaint") or []:
            add(disease_id, "symptom", value, "presents_with", "p2_nodes", dimension="chief_complaint")
        for value in model.get("key_cues") or []:
            add(disease_id, "diagnosis", value, "has_diagnostic_feature", "p2_nodes", dimension="key_cue")
        for value in model.get("presented_data") or []:
            add(disease_id, "diagnosis", value, "has_diagnostic_evidence", "p2_nodes", dimension="presented_data")

    for row in nodes.values():
        row["sources"].sort()
        row["disease_ids"].sort()
        row["evidence_refs"].sort(key=lambda ref: ref["ref_id"])
        row["provenance"]["evidence_refs"] = deepcopy(row["evidence_refs"])

    node_rows = [nodes[key] for key in sorted(nodes)]
    edge_rows = [edges[key] for key in sorted(edges)]
    attach_claim_lineage(node_rows, edge_rows)
    harrison22_overlay, harrison22_meta = load_harrison22_claim_overlay(
        harrison22_claim_overlay_path
    )
    harrison22_meta["applied_claims"] = apply_harrison22_candidates(
        node_rows, edge_rows, harrison22_overlay
    )
    overrides, override_meta = load_review_decisions(review_decisions_path)
    override_meta["applied_count"] = apply_review_overrides(
        node_rows,
        edge_rows,
        overrides,
        source_path=override_meta["path"],
    )
    type_counts = Counter(row["axis_type"] for row in node_rows)
    relation_counts = Counter(row["relation"] for row in edge_rows)
    review_counts = Counter(row["review_status"] for row in [*node_rows, *edge_rows])
    entailment_counts = Counter(
        (row.get("provenance") or {}).get("claim_entailment")
        for row in [*node_rows, *edge_rows]
    )
    stats = {
        "nodes": len(node_rows),
        "relationships": len(edge_rows),
        "diseases_covered": len({row["disease_concept_id"] for row in edge_rows}),
        "typed_entities_excluded_from_disease_axes": len(excluded_disease_ids),
        "types": dict(sorted(type_counts.items())),
        "relations": dict(sorted(relation_counts.items())),
        "review_statuses": dict(sorted(review_counts.items())),
        "claim_entailment_statuses": dict(sorted(entailment_counts.items())),
        "medical_approval_claims": sum(
            bool(row.get("medical_approval")) for row in [*node_rows, *edge_rows]
        ),
        "review_decisions_applied": override_meta["applied_count"],
        "harrison22_candidate_claims": harrison22_meta["applied_claims"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_from": [
            "data_private/curriculum/clinical_axes_map.json",
            "data_private/curriculum/p2_nodes.json",
            "data_private/concept_registry.json",
            "data_private/curriculum/typed_entity_registry.json",
            harrison22_meta["path"],
            override_meta["path"],
        ],
        "needs_review": any(row.get("needs_review") for row in [*node_rows, *edge_rows]),
        "harrison22_validation": harrison22_meta,
        "review_decisions": override_meta,
        "stats": stats,
        "nodes": node_rows,
        "relationships": edge_rows,
    }


def main() -> None:
    payload = build()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
