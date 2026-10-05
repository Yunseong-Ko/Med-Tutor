#!/usr/bin/env python3
"""Audit clinical-axis expansion drafts without granting medical approval.

The auditor accepts either a batch document (``axes`` plus
``harrison_refs``) or the merged ``clinical_axes_map.json``.  It is
deliberately read-only with respect to ontology inputs: the only optional
write is the requested JSON report.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data_private" / "curriculum" / "clinical_axes_map.json"
DEFAULT_WORKLIST = ROOT / "data_private" / "curriculum" / "clinical_axes_worklist.json"

REQUIRED_AXES = (
    "pathophysiology",
    "risk_factors",
    "prognosis",
    "treatment",
    "epidemiology",
)
HARRISON_FIELDS = ("chapter", "title", "page", "part")
ALTERNATE_SOURCE_REQUIRED_FIELDS = (
    "ref_id",
    "source_type",
    "authority",
    "title",
    "url",
    "verified_on",
    "scope",
    "entailment_status",
)
APPROVED_ALTERNATE_SOURCE_TYPES = {
    "government_clinical_guideline",
    "government_clinical_reference",
    "government_evidence_review",
    "government_patient_guidance",
    "international_authoritative_classification",
    "peer_reviewed_systematic_review",
    "professional_society_clinical_report",
    "professional_society_educational_review",
    "professional_society_guideline",
    "professional_society_patient_guidance",
}
DISEASE_LIKE_NODE_TYPES = {"disease", "neoplasm", "syndrome"}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

PLACEHOLDER_EXACT = {
    "-",
    "?",
    "n/a",
    "na",
    "none",
    "null",
    "tbd",
    "todo",
    "unknown",
    "unspecified",
    "not specified",
    "not available",
    "insufficient data",
    "needs review",
    "review needed",
    "varies",
    "variable",
    "depends",
    "multiple factors",
    "기타",
    "미상",
    "모름",
    "확인 필요",
    "검토 필요",
}

GENERIC_TREATMENT_PATTERNS = (
    re.compile(r"^(?:general\s+)?supportive care(?: only)?$", re.I),
    re.compile(r"^symptomatic (?:care|management|treatment)$", re.I),
    re.compile(r"^(?:treat|treatment of) (?:the )?underlying (?:cause|condition|disease)$", re.I),
    re.compile(r"^(?:conservative|medical|surgical|individuali[sz]ed) (?:care|management|treatment)$", re.I),
    re.compile(r"^(?:standard|usual) (?:care|therapy|treatment|management)$", re.I),
    re.compile(r"^(?:close )?observation$", re.I),
    re.compile(r"^follow (?:local |current )?guidelines$", re.I),
    re.compile(r"^multidisciplinary care$", re.I),
    re.compile(r"^lifestyle modifications?$", re.I),
    re.compile(r"^(?:보존적|대증적|지지적) (?:치료|관리)$"),
    re.compile(r"^원인 질환 치료$"),
)

PRECISE_EPIDEMIOLOGY_PATTERNS = (
    re.compile(r"(?:~|≈|about\s+|roughly\s+)?\d+(?:\.\d+)?\s*%", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?\b"),
    re.compile(r"\b\d+(?:\.\d+)?\s+(?:per|in)\s+\d[\d,]*\b", re.I),
    re.compile(r"\bper\s+\d[\d,]*\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s*/\s*\d[\d,]*\b"),
)

DANGEROUS_ABSOLUTE = re.compile(
    r"(?<!nearly )(?<!almost )\balways\b|"
    r"\bnever\b(?![-\s]?smok)|"
    r"\b(?:all|every)\s+patients?\b|"
    r"\bmust\s+(?:always|never|not)\b|"
    r"\b(?:guarantees?|guaranteed|zero risk|no risk|completely safe|cannot fail)\b|"
    r"\b(?:only|sole)\s+(?:effective\s+)?(?:treatment|therapy|option)\b|"
    r"\babsolutely contraindicated\b|"
    r"항상|절대|모든 환자|반드시|결코|위험(?:이 )?없음|유일한 치료|완치 보장",
    re.I,
)

UNSAFE_THIAMINE_GLUCOSE_SEQUENCE = re.compile(
    r"thiamine.{0,80}\b(?:before|prior\s+to)\b.{0,40}\b(?:glucose|dextrose)\b",
    re.I,
)
DIAGNOSTIC_PROCEDURE_IN_TREATMENT = re.compile(
    r"\b(?:diagnostic|diagnosis|imaging|scan|scintigraphy|locali[sz]ation|biopsy)\b",
    re.I,
)
NON_CONTRAINDICATION_LANGUAGE = re.compile(
    r"\b(?:not adequate|inadequate as|insufficient as|not recommended|avoid routine|"
    r"monotherapy|sole therapy)\b",
    re.I,
)

STRONG_NON_DISEASE_ID = re.compile(
    r"(?:^|_)(?:screening|testing|test|prevention|prophylaxis|vaccination|"
    r"counseling|procedure|therapy|treatment|postmenopausal)$"
)
WEAK_NON_DISEASE_ID = re.compile(r"(?:^|_)(?:symptom|symptoms|sign|finding|pain)$")

OVERLAP_STOPWORDS = {
    "a", "an", "and", "as", "at", "before", "during", "for", "if", "in",
    "of", "on", "or", "the", "to", "use", "when", "with", "without",
    "avoid", "avoiding", "routine", "routinely", "administration", "therapy",
    "treatment", "management", "patients", "patient",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: object) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def excerpt(value: object, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load_json_with_duplicate_keys(path: Path) -> tuple[Any, list[str]]:
    duplicates: list[str] = []

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                duplicates.append(key)
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook), duplicates


def is_populated(value: object) -> bool:
    return value not in (None, "", [], {})


def is_placeholder(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = normalize_text(value)
    if not normalized:
        return True
    return normalized in {normalize_text(item) for item in PLACEHOLDER_EXACT}


def harrison_ref(value: object) -> dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    return {key: row.get(key) for key in HARRISON_FIELDS}


def valid_alternate_source_refs(value: object) -> bool:
    """Accept explicit authority-scoped references without implying approval."""
    if not isinstance(value, list) or not value:
        return False
    for ref in value:
        if not isinstance(ref, dict):
            return False
        if any(not isinstance(ref.get(key), str) or not ref[key].strip() for key in ALTERNATE_SOURCE_REQUIRED_FIELDS):
            return False
        if ref["source_type"] not in APPROVED_ALTERNATE_SOURCE_TYPES:
            return False
        if not ref["url"].startswith("https://"):
            return False
        if ref["entailment_status"] not in {"unverified", "needs_human_review"}:
            return False
    return True


def iter_strings(value: object, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield from iter_strings(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_strings(item, f"{path}.{index}")
    elif isinstance(value, str):
        yield path, value


def treatment_core(value: object) -> tuple[str, set[str]]:
    text = str(value or "").casefold()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(
        r"^(?:avoid(?:ing)?|do not use|not recommended|contraindicated|routine(?:ly)?|"
        r"use of|administration of)\s+",
        "",
        text,
    )
    head = re.split(r"\b(?:for|in|when|if|during|with|without|after|before)\b", text, maxsplit=1)[0]
    normalized = normalize_text(head)
    tokens = {token for token in normalized.split() if token not in OVERLAP_STOPWORDS and len(token) > 1}
    return normalized, tokens


def is_generic_treatment(value: object) -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return any(pattern.fullmatch(text) for pattern in GENERIC_TREATMENT_PATTERNS)


def issue(
    issues: list[dict[str, Any]],
    code: str,
    severity: str,
    message: str,
    *,
    entity_id: str | None = None,
    path: str | None = None,
    evidence: object | None = None,
    blocking: bool | None = None,
) -> None:
    row: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "blocking": severity == "error" if blocking is None else bool(blocking),
        "message": message,
    }
    if entity_id is not None:
        row["id"] = entity_id
    if path is not None:
        row["path"] = path
    if evidence is not None:
        row["evidence"] = excerpt(evidence)
    issues.append(row)


def validate_string(
    issues: list[dict[str, Any]],
    cid: str,
    path: str,
    value: object,
    *,
    minimum: int = 1,
    allow_no_staging: bool = False,
) -> bool:
    if not isinstance(value, str) or not value.strip():
        issue(issues, "missing_required_content", "error", "Required text is absent.", entity_id=cid, path=path)
        return False
    text = value.strip()
    if allow_no_staging and re.match(r"^no\s+(?:formal|standard(?:ized)?|widely used).{0,40}stag", text, re.I):
        return True
    if is_placeholder(text):
        issue(issues, "placeholder_content", "error", "Placeholder text is not clinical-axis content.", entity_id=cid, path=path, evidence=text)
        return False
    if len(text) < minimum:
        issue(
            issues,
            "thin_content",
            "warning",
            f"Text is unusually short ({len(text)} characters; expected at least {minimum}).",
            entity_id=cid,
            path=path,
            evidence=text,
        )
    return True


def validate_list(
    issues: list[dict[str, Any]],
    cid: str,
    path: str,
    value: object,
    *,
    minimum_items: int,
    minimum_text: int = 8,
) -> list[str]:
    if not isinstance(value, list):
        issue(issues, "invalid_axis_schema", "error", "Expected a list.", entity_id=cid, path=path)
        return []
    if len(value) < minimum_items:
        issue(
            issues,
            "thin_axis_list",
            "error",
            f"Expected at least {minimum_items} populated entries; found {len(value)}.",
            entity_id=cid,
            path=path,
        )
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}.{index}"
        if not isinstance(item, str) or not item.strip():
            issue(issues, "missing_required_content", "error", "List entry must be populated text.", entity_id=cid, path=item_path)
            continue
        text = item.strip()
        result.append(text)
        if is_placeholder(text):
            issue(issues, "placeholder_content", "error", "Placeholder list entry detected.", entity_id=cid, path=item_path, evidence=text)
        elif len(text) < minimum_text:
            issue(issues, "thin_content", "warning", "List entry is too terse to be independently reviewable.", entity_id=cid, path=item_path, evidence=text)
        normalized = normalize_text(text)
        if normalized in seen:
            issue(issues, "duplicate_within_axis", "warning", "Duplicate text appears within the same axis list.", entity_id=cid, path=item_path, evidence=text)
        seen.add(normalized)
    return result


def validate_axis_schema(cid: str, axis: object, issues: list[dict[str, Any]]) -> None:
    if not isinstance(axis, dict):
        issue(issues, "invalid_axis_record", "error", "Axis record must be an object.", entity_id=cid)
        return
    if axis.get("id") != cid:
        issue(issues, "id_mismatch", "error", "Axis id field does not match its map key.", entity_id=cid, path="id", evidence=axis.get("id"))
    if axis.get("needs_review") is not True:
        issue(
            issues,
            "needs_review_not_true",
            "error",
            "Automated clinical-axis content must remain needs_review=true.",
            entity_id=cid,
            path="needs_review",
            evidence=axis.get("needs_review"),
        )
    for name in REQUIRED_AXES:
        if not is_populated(axis.get(name)):
            issue(issues, "missing_required_axis", "error", f"Required axis {name!r} is absent or empty.", entity_id=cid, path=name)

    pathophysiology = axis.get("pathophysiology")
    if not isinstance(pathophysiology, dict):
        issue(issues, "invalid_axis_schema", "error", "pathophysiology must be an object.", entity_id=cid, path="pathophysiology")
    else:
        validate_string(issues, cid, "pathophysiology.summary", pathophysiology.get("summary"), minimum=60)
        validate_list(issues, cid, "pathophysiology.key_steps", pathophysiology.get("key_steps"), minimum_items=2, minimum_text=12)

    # Some rare disorders have one defensible antecedent risk factor and should
    # not be padded with mechanisms, demographics, or findings merely to meet a
    # numeric quota.
    validate_list(issues, cid, "risk_factors", axis.get("risk_factors"), minimum_items=1, minimum_text=6)

    prognosis = axis.get("prognosis")
    if not isinstance(prognosis, dict):
        issue(issues, "invalid_axis_schema", "error", "prognosis must be an object.", entity_id=cid, path="prognosis")
    else:
        # One well-grounded prognostic factor is preferable to padding a rare or
        # benign condition with weakly supported entries merely to satisfy a
        # numeric quota.
        validate_list(issues, cid, "prognosis.factors", prognosis.get("factors"), minimum_items=1, minimum_text=8)
        staging = prognosis.get("staging_or_grading")
        if isinstance(staging, str) and staging.strip():
            validate_string(
                issues,
                cid,
                "prognosis.staging_or_grading",
                staging,
                minimum=12,
                allow_no_staging=True,
            )
        else:
            issue(
                issues,
                "staging_or_grading_unresolved",
                "warning",
                "No staging or grading statement is authored; this may be non-applicable or may require source review.",
                entity_id=cid,
                path="prognosis.staging_or_grading",
                blocking=False,
            )
        validate_string(issues, cid, "prognosis.natural_history", prognosis.get("natural_history"), minimum=35)

    treatment = axis.get("treatment")
    if not isinstance(treatment, dict):
        issue(issues, "invalid_axis_schema", "error", "treatment must be an object.", entity_id=cid, path="treatment")
    else:
        principles = treatment.get("principles")
        validate_string(issues, cid, "treatment.principles", principles, minimum=35)
        indicated = validate_list(issues, cid, "treatment.indicated_for", treatment.get("indicated_for"), minimum_items=1)
        contraindicated = validate_list(
            issues,
            cid,
            "treatment.contraindicated_for",
            treatment.get("contraindicated_for"),
            minimum_items=0,
        )
        if isinstance(principles, str) and (is_generic_treatment(principles) or (len(principles.split()) <= 6 and len(principles) < 45)):
            issue(
                issues,
                "generic_treatment_principle",
                "warning",
                "Treatment principle is too generic to ground a disease-specific decision.",
                entity_id=cid,
                path="treatment.principles",
                evidence=principles,
            )
        generic_indicated = []
        for index, value in enumerate(indicated):
            if is_generic_treatment(value):
                generic_indicated.append(value)
                issue(
                    issues,
                    "generic_treatment_entry",
                    "warning",
                    "Treatment entry lacks a disease-specific intervention or condition.",
                    entity_id=cid,
                    path=f"treatment.indicated_for.{index}",
                    evidence=value,
                )
        if indicated and len(generic_indicated) == len(indicated):
            issue(
                issues,
                "treatment_lacks_specific_intervention",
                "error",
                "All indicated treatments are generic placeholders.",
                entity_id=cid,
                path="treatment.indicated_for",
            )
        detect_treatment_overlap(cid, indicated, contraindicated, issues)

    epidemiology = axis.get("epidemiology")
    if not isinstance(epidemiology, dict):
        issue(issues, "invalid_axis_schema", "error", "epidemiology must be an object.", entity_id=cid, path="epidemiology")
    else:
        for name in ("age", "sex", "population", "frequency"):
            value = epidemiology.get(name)
            validate_string(issues, cid, f"epidemiology.{name}", value, minimum=3)
            if isinstance(value, str) and any(pattern.search(value) for pattern in PRECISE_EPIDEMIOLOGY_PATTERNS):
                issue(
                    issues,
                    "precise_epidemiology_statistic",
                    "error",
                    "Precise epidemiology rate, percentage, or ratio is prohibited in an auto-authored draft.",
                    entity_id=cid,
                    path=f"epidemiology.{name}",
                    evidence=value,
                )

    if not isinstance(axis.get("uncertainty_notes", []), list):
        issue(issues, "invalid_uncertainty_notes", "error", "uncertainty_notes must be a list.", entity_id=cid, path="uncertainty_notes")


def detect_treatment_overlap(
    cid: str,
    indicated: list[str],
    contraindicated: list[str],
    issues: list[dict[str, Any]],
) -> None:
    for indicated_index, indicated_value in enumerate(indicated):
        indicated_normalized = normalize_text(indicated_value)
        indicated_head, indicated_tokens = treatment_core(indicated_value)
        for contraindicated_index, contraindicated_value in enumerate(contraindicated):
            contraindicated_normalized = normalize_text(contraindicated_value)
            contraindicated_head, contraindicated_tokens = treatment_core(contraindicated_value)
            if indicated_normalized and indicated_normalized == contraindicated_normalized:
                issue(
                    issues,
                    "indication_contraindication_exact_overlap",
                    "error",
                    "The same treatment text appears as both indicated and contraindicated.",
                    entity_id=cid,
                    path=f"treatment.indicated_for.{indicated_index}|treatment.contraindicated_for.{contraindicated_index}",
                    evidence=indicated_value,
                )
                continue
            union = indicated_tokens | contraindicated_tokens
            intersection = indicated_tokens & contraindicated_tokens
            jaccard = len(intersection) / len(union) if union else 0.0
            same_head = bool(indicated_head and indicated_head == contraindicated_head and len(indicated_tokens) >= 2)
            if same_head or (len(intersection) >= 2 and jaccard >= 0.72):
                issue(
                    issues,
                    "potential_indication_contraindication_overlap",
                    "warning",
                    "Indication and contraindication may name the same intervention; conditions require human review.",
                    entity_id=cid,
                    path=f"treatment.indicated_for.{indicated_index}|treatment.contraindicated_for.{contraindicated_index}",
                    evidence=f"INDICATED: {indicated_value} | CONTRAINDICATED: {contraindicated_value}",
                )


def detect_non_disease_candidate(cid: str, item: dict[str, Any] | None, issues: list[dict[str, Any]]) -> None:
    node_type = str((item or {}).get("node_type") or "").strip().casefold()
    if node_type and node_type not in DISEASE_LIKE_NODE_TYPES:
        issue(
            issues,
            "non_disease_node_type",
            "error",
            f"Worklist node_type {node_type!r} is not disease-like.",
            entity_id=cid,
            path="worklist.node_type",
            evidence=node_type,
        )
        return
    if STRONG_NON_DISEASE_ID.search(cid):
        issue(
            issues,
            "non_disease_concept_candidate",
            "error",
            "Concept id appears to describe a state, preventive service, test, or intervention rather than a disease entity.",
            entity_id=cid,
            path="id",
            evidence=cid,
        )
    elif node_type == "disease" and WEAK_NON_DISEASE_ID.search(cid):
        issue(
            issues,
            "symptom_level_concept_candidate",
            "warning",
            "Disease-typed concept id appears symptom- or finding-level and needs taxonomy review.",
            entity_id=cid,
            path="id",
            evidence=cid,
        )


def audit_document(
    data: object,
    *,
    source: str,
    worklist_data: object,
    duplicate_keys: list[str] | None = None,
    max_identical_phrase_uses: int = 4,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    duplicate_keys = duplicate_keys or []
    if not isinstance(data, dict):
        issue(issues, "invalid_document", "error", "Input JSON must be an object.")
        axes: dict[str, Any] = {}
        source_kind = "invalid"
        refs: dict[str, Any] | None = None
    else:
        axes_value = data.get("axes")
        axes = axes_value if isinstance(axes_value, dict) else {}
        refs_value = data.get("harrison_refs")
        refs = refs_value if isinstance(refs_value, dict) else None
        alternate_refs_value = data.get("source_refs")
        alternate_refs = alternate_refs_value if isinstance(alternate_refs_value, dict) else None
        if "source_refs" in data and "harrison_refs" not in data:
            source_kind = "alternate_batch"
        elif "harrison_refs" in data or "_meta" in data:
            source_kind = "batch"
        else:
            source_kind = "merged_map"
        if not isinstance(axes_value, dict):
            issue(issues, "invalid_axes_map", "error", "Input must contain an axes object.", path="axes")
        if source_kind == "merged_map" and "total" in data and data.get("total") != len(axes):
            issue(issues, "total_mismatch", "error", "Merged-map total does not equal axes size.", path="total", evidence=data.get("total"))
        if source_kind in {"batch", "alternate_batch"}:
            meta = data.get("_meta")
            if isinstance(meta, dict) and meta.get("needs_review") is not True:
                issue(issues, "batch_needs_review_not_true", "error", "Batch metadata must remain needs_review=true.", path="_meta.needs_review", evidence=meta.get("needs_review"))
            if source_kind == "batch" and refs is None:
                issue(issues, "missing_harrison_refs", "error", "Batch input must contain a harrison_refs object.", path="harrison_refs")
            if source_kind == "alternate_batch" and alternate_refs is None:
                issue(issues, "missing_source_refs", "error", "Alternate-source batch must contain a source_refs object.", path="source_refs")

    if not isinstance(data, dict):
        alternate_refs = None

    work_items = worklist_data.get("items", []) if isinstance(worklist_data, dict) else []
    if not isinstance(work_items, list):
        work_items = []
        issue(issues, "invalid_worklist", "error", "Worklist must contain an items list.")
    work: dict[str, dict[str, Any]] = {}
    for item in work_items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        cid = item["id"]
        if cid in work:
            issue(issues, "duplicate_worklist_id", "error", "Duplicate id appears in worklist.", entity_id=cid)
        work[cid] = item

    for key in sorted(set(duplicate_keys)):
        issue(issues, "duplicate_json_key", "error", "Duplicate key appeared within a JSON object; a value may have been overwritten while parsing.", evidence=key)

    normalized_ids: dict[str, list[str]] = defaultdict(list)
    harrison_checked = 0
    harrison_exact = 0
    alternate_checked = 0
    alternate_exact = 0
    for cid, axis in axes.items():
        normalized_ids[normalize_text(cid).replace(" ", "_")].append(cid)
        if not ID_PATTERN.fullmatch(cid):
            issue(issues, "invalid_concept_id", "error", "Concept id must be lowercase snake_case.", entity_id=cid, path="id", evidence=cid)
        item = work.get(cid)
        if item is None:
            issue(issues, "id_absent_from_worklist", "error", "Concept id is absent from the clinical-axis worklist.", entity_id=cid)
        detect_non_disease_candidate(cid, item, issues)
        validate_axis_schema(cid, axis, issues)

        expected = harrison_ref((item or {}).get("harrison"))
        if not item or expected.get("chapter") is None:
            inline_alternate = axis.get("evidence_refs") if isinstance(axis, dict) else None
            batch_alternate = (alternate_refs or {}).get(cid) if source_kind == "alternate_batch" else inline_alternate
            if source_kind == "alternate_batch":
                alternate_checked += 1
                if batch_alternate != inline_alternate:
                    issue(
                        issues,
                        "alternate_source_ref_mismatch",
                        "error",
                        "Batch source_refs must exactly match the axis evidence_refs.",
                        entity_id=cid,
                        path=f"source_refs.{cid}",
                    )
                elif valid_alternate_source_refs(batch_alternate):
                    alternate_exact += 1
                else:
                    issue(
                        issues,
                        "invalid_alternate_source_refs",
                        "error",
                        "Alternate-source grounding is missing required authority, scope, or review metadata.",
                        entity_id=cid,
                        path=f"source_refs.{cid}",
                    )
            elif valid_alternate_source_refs(inline_alternate):
                alternate_checked += 1
                alternate_exact += 1
            else:
                issue(
                    issues,
                    "not_harrison_grounded",
                    "error",
                    "Concept has neither a grounded Harrison reference nor approved alternate-source provenance.",
                    entity_id=cid,
                    path="worklist.harrison|axes.evidence_refs",
                )
        elif source_kind == "batch":
            harrison_checked += 1
            actual = harrison_ref((refs or {}).get(cid))
            if actual != expected:
                issue(
                    issues,
                    "harrison_ref_mismatch",
                    "error",
                    "Batch Harrison reference does not exactly match the worklist.",
                    entity_id=cid,
                    path=f"harrison_refs.{cid}",
                    evidence=f"actual={actual!r}; expected={expected!r}",
                )
            else:
                harrison_exact += 1
        else:
            harrison_checked += 1
            harrison_exact += 1

    for normalized_id, ids in normalized_ids.items():
        if len(ids) > 1:
            issue(issues, "normalized_id_collision", "error", "Concept ids collide after normalization.", evidence=", ".join(sorted(ids)))

    if source_kind == "batch" and refs is not None:
        for cid in sorted(set(refs) - set(axes)):
            issue(issues, "orphan_harrison_ref", "warning", "Harrison reference has no matching axis record in this batch.", entity_id=cid, path=f"harrison_refs.{cid}")
    if source_kind == "alternate_batch" and alternate_refs is not None:
        for cid in sorted(set(alternate_refs) - set(axes)):
            issue(issues, "orphan_source_ref", "warning", "Alternate source reference has no matching axis record in this batch.", entity_id=cid, path=f"source_refs.{cid}")

    phrase_uses: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for cid, axis in axes.items():
        if not isinstance(axis, dict):
            continue
        for path, value in iter_strings(axis):
            if path == "id":
                continue
            if UNSAFE_THIAMINE_GLUCOSE_SEQUENCE.search(value):
                issue(
                    issues,
                    "unsafe_thiamine_glucose_sequence",
                    "error",
                    "Wording may delay urgently indicated glucose; thiamine must not be used as a prerequisite for dextrose.",
                    entity_id=cid,
                    path=path,
                    evidence=value,
                )
            if (
                cid == "delirium_tremens"
                and path == "prognosis.staging_or_grading"
                and re.search(r"\bCIWA(?:-Ar)?\b", value, re.I)
                and not re.search(r"(?:should\s+not|not\s+be\s+used|unreliable|inappropriate)", value, re.I)
            ):
                issue(
                    issues,
                    "ciwa_used_for_active_delirium",
                    "error",
                    "CIWA-Ar relies on patient report and must not be presented as the monitoring scale for active alcohol-withdrawal delirium.",
                    entity_id=cid,
                    path=path,
                    evidence=value,
                )
            if path.startswith("treatment.indicated_for") and DIAGNOSTIC_PROCEDURE_IN_TREATMENT.search(value):
                issue(
                    issues,
                    "diagnostic_procedure_in_treatment_axis",
                    "warning",
                    "A diagnostic or localization procedure appears in the treatment axis and may need relocation.",
                    entity_id=cid,
                    path=path,
                    evidence=value,
                )
            if path.startswith("treatment.contraindicated_for") and NON_CONTRAINDICATION_LANGUAGE.search(value):
                issue(
                    issues,
                    "non_contraindication_in_contraindication_axis",
                    "warning",
                    "This wording describes weak evidence, insufficient monotherapy, or non-routine use rather than a true contraindication.",
                    entity_id=cid,
                    path=path,
                    evidence=value,
                )
            if DANGEROUS_ABSOLUTE.search(value):
                issue(
                    issues,
                    "dangerous_absolute_expression",
                    "warning",
                    "Potentially unsafe absolute wording requires human medical review.",
                    entity_id=cid,
                    path=path,
                    evidence=value,
                )
            normalized = normalize_text(value)
            if len(normalized) >= 25 and len(normalized.split()) >= 4:
                phrase_uses[normalized].append((cid, path, value))

    for uses in phrase_uses.values():
        distinct_ids = sorted({cid for cid, _, _ in uses})
        if len(distinct_ids) <= max_identical_phrase_uses:
            continue
        first = uses[0]
        issue(
            issues,
            "over_replicated_phrase",
            "warning",
            f"Identical wording is reused across {len(distinct_ids)} concepts (limit {max_identical_phrase_uses}).",
            path=first[1],
            evidence=f"{first[2]} | ids={', '.join(distinct_ids[:12])}",
        )

    issues.sort(key=lambda row: (not row["blocking"], row.get("id", ""), row.get("path", ""), row["code"]))
    code_counts = Counter(row["code"] for row in issues)
    severity_counts = Counter(row["severity"] for row in issues)
    blocking_count = sum(bool(row["blocking"]) for row in issues)
    quality_gate_passed = blocking_count == 0
    if quality_gate_passed and issues:
        status = "draft_quality_gate_passed_with_review_warnings"
    elif quality_gate_passed:
        status = "draft_quality_gate_passed_not_medically_approved"
    else:
        status = "draft_quality_gate_failed"

    return {
        "schema_version": "clinical_axes_expansion_audit.v1",
        "generated_at": _now(),
        "source": source,
        "source_kind": source_kind,
        "status": status,
        "quality_gate_passed": quality_gate_passed,
        "medical_approval": False,
        "automatic_medical_approval_performed": False,
        "review_required": True,
        "disposition": "Automated checks only. Every axis remains a needs_review draft until explicit human medical sign-off.",
        "summary": {
            "axes_audited": len(axes),
            "issues": len(issues),
            "blocking_issues": blocking_count,
            "warnings": severity_counts.get("warning", 0),
            "issue_codes": dict(sorted(code_counts.items())),
            "harrison_refs_checked": harrison_checked,
            "harrison_refs_exact_or_worklist_grounded": harrison_exact,
            "alternate_source_refs_checked": alternate_checked,
            "alternate_source_refs_exact_or_embedded": alternate_exact,
            "max_identical_phrase_uses": max_identical_phrase_uses,
        },
        "checks": {
            "required_axes": list(REQUIRED_AXES),
            "needs_review_must_be_true": True,
            "grounding_comparison": (
                "alternate_ref_exact_match"
                if source_kind == "alternate_batch"
                else "inline_harrison_ref_exact_match"
                if source_kind == "batch"
                else "worklist_or_embedded_alternate_grounding"
            ),
            "precise_epidemiology_prohibited": True,
            "medical_approval_is_out_of_scope": True,
        },
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT, help="batch JSON or merged clinical_axes_map.json")
    parser.add_argument("--worklist", type=Path, default=DEFAULT_WORKLIST, help="clinical_axes_worklist.json path")
    parser.add_argument("--output", type=Path, help="optional JSON report path; stdout is always emitted")
    parser.add_argument("--strict", action="store_true", help="exit 1 when a blocking draft-quality issue is found")
    parser.add_argument(
        "--max-identical-phrase-uses",
        type=int,
        default=4,
        help="warn when identical substantive wording appears across more than this many concepts",
    )
    args = parser.parse_args()
    if args.max_identical_phrase_uses < 1:
        parser.error("--max-identical-phrase-uses must be at least 1")

    data, duplicate_keys = load_json_with_duplicate_keys(args.input)
    worklist, worklist_duplicates = load_json_with_duplicate_keys(args.worklist)
    report = audit_document(
        data,
        source=str(args.input),
        worklist_data=worklist,
        duplicate_keys=duplicate_keys + worklist_duplicates,
        max_identical_phrase_uses=args.max_identical_phrase_uses,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if args.strict and not report["quality_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
