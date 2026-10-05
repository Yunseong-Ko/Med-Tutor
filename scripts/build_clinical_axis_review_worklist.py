#!/usr/bin/env python3
"""Build a deterministic human-review worklist from clinical-axis audit issues.

This adapter does not edit clinical claims and never grants medical approval.
It connects audit warnings to materialized axis relations so reviewers can make
an explicit, claim-scoped decision.  Relationship ``claim_id`` values already
present in ``axis_registry.json`` are authoritative; older registries receive
the same deterministic fallback used by ``build_axis_layer.py``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.build_axis_layer import claim_id as materialized_claim_id
except ModuleNotFoundError:  # direct script execution
    from build_axis_layer import claim_id as materialized_claim_id


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = (
    ROOT
    / "data_private"
    / "curriculum"
    / "clinical_axes_audits"
    / "clinical_axes_map_20260712.audit.json"
)
DEFAULT_AXIS_REGISTRY = ROOT / "data_private" / "curriculum" / "axis_registry.json"
DEFAULT_OUTPUT = (
    ROOT
    / "data_private"
    / "curriculum"
    / "clinical_axis_review_worklist_20260712.json"
)


# Audit path -> materialized axis relation.  The relation is the claim grain;
# an axis node may be shared by many diseases and therefore is not sufficient
# by itself for a review decision.
PATH_RULES: tuple[tuple[re.Pattern[str], str, str, str], ...] = (
    (re.compile(r"^pathophysiology\.summary$"), "pathophysiology", "has_pathophysiology", "summary"),
    (re.compile(r"^pathophysiology\.key_steps\.\d+$"), "pathophysiology", "has_pathophysiology_step", "key_step"),
    (re.compile(r"^risk_factors\.\d+$"), "risk_factor", "has_risk_factor", ""),
    (re.compile(r"^prognosis\.factors\.\d+$"), "prognosis", "has_prognostic_factor", "factor"),
    (re.compile(r"^prognosis\.staging_or_grading$"), "prognosis", "has_stage_or_grade", "stage_or_grade"),
    (re.compile(r"^prognosis\.natural_history$"), "prognosis", "has_natural_history", "natural_history"),
    (re.compile(r"^treatment\.principles$"), "treatment", "has_treatment_principle", "principle"),
    (re.compile(r"^treatment\.indicated_for\.\d+$"), "indication", "has_indication", ""),
    (re.compile(r"^treatment\.contraindicated_for\.\d+$"), "contraindication", "has_contraindication", ""),
    (re.compile(r"^epidemiology\.(age|sex|population|frequency)$"), "epidemiology", "has_epidemiology", "*"),
)


P0_CODES = {
    "batch_needs_review_not_true",
    "ciwa_used_for_active_delirium",
    "dangerous_absolute_expression",
    "diagnostic_procedure_in_treatment_axis",
    "indication_contraindication_exact_overlap",
    "needs_review_not_true",
    "non_contraindication_in_contraindication_axis",
    "non_disease_concept_candidate",
    "non_disease_node_type",
    "symptom_level_concept_candidate",
    "treatment_lacks_specific_intervention",
    "unsafe_thiamine_glucose_sequence",
}
P1_CODES = {
    "generic_treatment_entry",
    "generic_treatment_principle",
    "harrison_ref_mismatch",
    "invalid_alternate_source_refs",
    "not_harrison_grounded",
    "potential_indication_contraindication_overlap",
    "precise_epidemiology_statistic",
    "thin_content",
}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def normalize_text(value: object) -> str:
    text = str(value or "").casefold().replace("…", "")
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def json_pointer(path: str) -> str:
    return "/".join(part.replace("~", "~0").replace("/", "~1") for part in path.split("."))


def priority_for(issue: dict[str, Any]) -> str:
    code = str(issue.get("code") or "")
    if issue.get("blocking") is True or str(issue.get("severity") or "") == "error" or code in P0_CODES:
        return "P0"
    if code in P1_CODES:
        return "P1"
    return "P2"


def path_rule(path: str) -> tuple[str, str, str] | None:
    for pattern, axis_type, relation, dimension in PATH_RULES:
        match = pattern.fullmatch(path)
        if not match:
            continue
        if dimension == "*":
            dimension = match.group(1)
        return axis_type, relation, dimension
    return None


def evidence_parts(issue: dict[str, Any], paths: list[str]) -> list[str]:
    evidence = str(issue.get("evidence") or "").strip()
    if len(paths) == 2 and "|" in evidence:
        left, right = evidence.split("|", 1)
        left = re.sub(r"^\s*INDICATED:\s*", "", left, flags=re.I)
        right = re.sub(r"^\s*CONTRAINDICATED:\s*", "", right, flags=re.I)
        return [left.strip(), right.strip()]
    if issue.get("code") == "over_replicated_phrase" and "| ids=" in evidence:
        evidence = evidence.split("| ids=", 1)[0].strip()
    return [evidence for _ in paths]


def _matches_evidence(label: str, evidence: str) -> bool:
    label_norm = normalize_text(label)
    evidence_norm = normalize_text(evidence)
    if not label_norm or not evidence_norm:
        return False
    return label_norm == evidence_norm or label_norm.startswith(evidence_norm) or evidence_norm.startswith(label_norm)


def _review_id(issue: dict[str, Any], claims: list[dict[str, Any]]) -> str:
    identity = {
        "code": issue.get("code"),
        "concept": issue.get("id"),
        "path": issue.get("path"),
        "evidence": normalize_text(issue.get("evidence")),
        "claims": sorted(str(claim.get("claim_id") or "") for claim in claims),
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:16]
    return f"review:clinical_axis:{digest}"


def _fallback_unmaterialized_claim_id(concept_id: str | None, path: str) -> str:
    # No axis relation exists for empty staging fields, uncertainty notes, or
    # concept-level taxonomy warnings.  Keep these reviewable without implying
    # that an axis node was materialized.
    return materialized_claim_id("unmaterialized_axis", concept_id or "global", path)


def _build_indexes(axis_registry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], list[dict[str, Any]]]]:
    nodes = {
        str(row.get("axis_id")): row
        for row in axis_registry.get("nodes", [])
        if isinstance(row, dict) and row.get("axis_id")
    }
    by_disease_relation: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in axis_registry.get("relationships", []):
        if not isinstance(row, dict):
            continue
        disease_id = str(row.get("disease_concept_id") or "")
        relation = str(row.get("relation") or "")
        axis_id = str(row.get("axis_id") or "")
        if not disease_id or not relation or axis_id not in nodes:
            continue
        enriched = dict(row)
        enriched["node"] = nodes[axis_id]
        by_disease_relation[(disease_id, relation)].append(enriched)
    for rows in by_disease_relation.values():
        rows.sort(key=lambda row: (str(row.get("axis_id")), str(row.get("claim_id") or "")))
    return nodes, by_disease_relation


def _claim_from_relation(
    relation_row: dict[str, Any],
    *,
    concept_id: str,
    claim_path: str,
    source_path: str,
    mapping_status: str,
) -> dict[str, Any]:
    node = relation_row["node"]
    axis_id = str(relation_row["axis_id"])
    relation = str(relation_row["relation"])
    cid = str(relation_row.get("claim_id") or "").strip()
    if not cid:
        cid = materialized_claim_id("axis_relation", concept_id, relation, axis_id)
    return {
        "claim_id": cid,
        "axis_id": axis_id,
        "axis_type": node.get("axis_type"),
        "relation": relation,
        "dimension": node.get("dimension") or "",
        "label": node.get("label") or "",
        "claim_path": claim_path,
        "source_path": source_path,
        "mapping_status": mapping_status,
    }


def map_issue_claims(
    issue: dict[str, Any],
    *,
    axis_source: str,
    nodes: dict[str, dict[str, Any]],
    by_disease_relation: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    del nodes  # reserved for future global-node matching without changing the API
    concept_id = str(issue.get("id") or "").strip() or None
    raw_path = str(issue.get("path") or "").strip()
    paths = [part.strip() for part in raw_path.split("|") if part.strip()] or [raw_path or "concept"]
    evidences = evidence_parts(issue, paths)
    claims: list[dict[str, Any]] = []

    for index, claim_path in enumerate(paths):
        pointer = f"{axis_source}#/axes"
        if concept_id:
            pointer += f"/{concept_id}"
        if claim_path and claim_path != "concept":
            pointer += f"/{json_pointer(claim_path)}"
        rule = path_rule(claim_path)
        evidence = evidences[index] if index < len(evidences) else ""
        candidates: list[dict[str, Any]] = []
        if concept_id and rule:
            axis_type, relation, dimension = rule
            candidates = [
                row
                for row in by_disease_relation.get((concept_id, relation), [])
                if row["node"].get("axis_type") == axis_type
                and (not dimension or row["node"].get("dimension", "") == dimension)
            ]
        exact = [row for row in candidates if normalize_text(row["node"].get("label")) == normalize_text(evidence)]
        prefix = [row for row in candidates if _matches_evidence(str(row["node"].get("label") or ""), evidence)]
        matched = exact or prefix
        if len(matched) == 1:
            claims.append(
                _claim_from_relation(
                    matched[0],
                    concept_id=concept_id or "global",
                    claim_path=claim_path,
                    source_path=pointer,
                    mapping_status="exact_label" if exact else "audit_excerpt_prefix",
                )
            )
            continue
        if not evidence and len(candidates) == 1:
            claims.append(
                _claim_from_relation(
                    candidates[0],
                    concept_id=concept_id or "global",
                    claim_path=claim_path,
                    source_path=pointer,
                    mapping_status="unique_path_candidate",
                )
            )
            continue
        fallback = {
            "claim_id": _fallback_unmaterialized_claim_id(concept_id, claim_path),
            "axis_id": None,
            "axis_type": rule[0] if rule else None,
            "relation": rule[1] if rule else None,
            "dimension": rule[2] if rule else None,
            "label": evidence,
            "claim_path": claim_path,
            "source_path": pointer,
            "mapping_status": "ambiguous_axis_match" if len(matched) > 1 else "not_materialized",
        }
        claims.append(fallback)
    return claims


def build_review_worklist(
    audit: dict[str, Any],
    axis_registry: dict[str, Any],
    *,
    audit_path: str,
    axis_registry_path: str,
) -> dict[str, Any]:
    nodes, relation_index = _build_indexes(axis_registry)
    axis_source = str(audit.get("source") or "data_private/curriculum/clinical_axes_map.json")
    items: list[dict[str, Any]] = []

    for issue in audit.get("issues", []):
        if not isinstance(issue, dict) or not issue.get("code"):
            continue
        claims = map_issue_claims(
            issue,
            axis_source=axis_source,
            nodes=nodes,
            by_disease_relation=relation_index,
        )
        concept_ids = sorted(
            {
                str(issue.get("id"))
                for _ in [0]
                if issue.get("id")
            }
        )
        priority = priority_for(issue)
        item = {
            "review_id": _review_id(issue, claims),
            "priority": priority,
            "warning_code": issue.get("code"),
            "severity": issue.get("severity") or "warning",
            "blocking": bool(issue.get("blocking")),
            "concept_id": issue.get("id"),
            "concept_ids": concept_ids,
            "audit_path": issue.get("path"),
            "source_path": claims[0]["source_path"] if len(claims) == 1 else None,
            "source_paths": [claim["source_path"] for claim in claims],
            "message": issue.get("message") or "",
            "evidence_excerpt": issue.get("evidence") or "",
            "claim_id": claims[0]["claim_id"] if len(claims) == 1 else None,
            "claim_ids": [claim["claim_id"] for claim in claims],
            "axis_id": claims[0]["axis_id"] if len(claims) == 1 else None,
            "axis_ids": sorted({claim["axis_id"] for claim in claims if claim.get("axis_id")}),
            "claims": claims,
            "review_decision": {
                "status": "pending",
                "decision": None,
                "reviewer_id": None,
                "reviewed_at": None,
                "rationale": None,
                "replacement_text": None,
            },
            "medical_approval": False,
        }
        items.append(item)

    items.sort(
        key=lambda row: (
            PRIORITY_ORDER[row["priority"]],
            str(row.get("warning_code") or ""),
            str(row.get("concept_id") or ""),
            str(row.get("audit_path") or ""),
            row["review_id"],
        )
    )
    priority_counts = Counter(row["priority"] for row in items)
    code_counts = Counter(str(row["warning_code"]) for row in items)
    mapped_claims = sum(1 for row in items for claim in row["claims"] if claim.get("axis_id"))
    total_claims = sum(len(row["claims"]) for row in items)
    return {
        "schema_version": "clinical_axis_review_worklist.v1",
        "generated_from": {
            "audit_report": audit_path,
            "axis_registry": axis_registry_path,
            "audit_generated_at": audit.get("generated_at"),
            "axis_registry_schema_version": axis_registry.get("schema_version"),
        },
        "status": "human_review_required",
        "deterministic": True,
        "automatic_medical_approval_performed": False,
        "medical_approval": False,
        "review_required": True,
        "summary": {
            "review_items": len(items),
            "claims": total_claims,
            "claims_mapped_to_axis": mapped_claims,
            "claims_without_materialized_axis": total_claims - mapped_claims,
            "priorities": {key: priority_counts.get(key, 0) for key in ("P0", "P1", "P2")},
            "warning_codes": dict(sorted(code_counts.items())),
            "pending_decisions": len(items),
        },
        "items": items,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--axis-registry", type=Path, default=DEFAULT_AXIS_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(list(argv) if argv is not None else None)

    audit = load_json(args.audit)
    axis_registry = load_json(args.axis_registry)
    payload = build_review_worklist(
        audit,
        axis_registry,
        audit_path=str(args.audit.resolve().relative_to(ROOT)) if args.audit.resolve().is_relative_to(ROOT) else str(args.audit),
        axis_registry_path=(
            str(args.axis_registry.resolve().relative_to(ROOT))
            if args.axis_registry.resolve().is_relative_to(ROOT)
            else str(args.axis_registry)
        ),
    )
    write_json(args.output, payload)
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
