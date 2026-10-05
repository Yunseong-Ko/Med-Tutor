#!/usr/bin/env python3
"""Build a jurisdiction-aware guideline source map and review-only claim pilot.

The map helps an agent decide *where to look*.  It is not medical evidence.  The
pilot claim registry contains independently written paraphrases from official
public pages, remains unreleased, and is never answer- or generation-eligible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CONCEPTS = ROOT / "data_private" / "concept_registry.json"
KR_REGISTRY = ROOT / "data_private" / "kr_guidelines" / "verified_latest_registry.json"
KR_OVERLAY = ROOT / "data_private" / "kr_guidelines" / "ontology_overlay.json"
US_REGISTRY = ROOT / "data_private" / "us_guidelines" / "verified_latest_registry.json"
JURISDICTION_POLICY = ROOT / "data_private" / "us_guidelines" / "jurisdiction_policy.json"
CLAIM_SEED = ROOT / "data_private" / "guideline_map" / "seeds" / "pilot_claim_candidates.json"
MAP_OUT = ROOT / "data_private" / "guideline_map" / "source_map.json"
CLAIM_OUT = ROOT / "data_private" / "guideline_map" / "atomic_claim_candidates.json"
MAP_SCHEMA = ROOT / "schemas" / "guideline_agent_map.schema.json"
CLAIM_SCHEMA = ROOT / "schemas" / "guideline_atomic_claim_candidate.schema.json"

SPACE_RE = re.compile(r"\s+")
TERM_SPLIT_RE = re.compile(r"[,;/|\n]+")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_ref(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve().relative_to(ROOT.resolve())),
        "bytes": path.stat().st_size,
        "sha256": sha256_path(path),
    }


def clean(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "").replace("\u00a0", " ")).strip()


def unique_strings(values: list[Any], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = clean(value)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if limit is not None and len(result) >= limit:
            break
    return result


def validate(payload: dict[str, Any], schema_path: Path, *, label: str) -> None:
    validator = Draft202012Validator(
        load_json(schema_path), format_checker=FormatChecker()
    )
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        detail = "\n".join(
            f"{list(error.path)}: {error.message}" for error in errors[:30]
        )
        raise ValueError(f"{label} schema validation failed ({len(errors)} errors)\n{detail}")


def generated_at(*registries: dict[str, Any]) -> str:
    checked = sorted(
        clean(registry.get("latest_checked_at"))
        for registry in registries
        if clean(registry.get("latest_checked_at"))
    )
    day = checked[-1] if checked else "2026-07-18"
    return f"{day}T00:00:00+09:00"


def kr_routes_by_source(overlay: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in overlay.get("source_links") or []:
        source_id = clean(link.get("source_id"))
        if not source_id:
            continue
        for concept_id in link.get("resolved_topic_concept_ids") or []:
            result[source_id].append(
                {
                    "concept_id": clean(concept_id),
                    "mapping_method": "kr_overlay_explicit",
                    "resolved_in_registry": True,
                }
            )
        for candidate in link.get("title_rule_candidates") or []:
            if not candidate.get("resolved_in_registry"):
                continue
            result[source_id].append(
                {
                    "concept_id": clean(candidate.get("concept_id")),
                    "mapping_method": "kr_title_rule_review_candidate",
                    "resolved_in_registry": True,
                }
            )
    return result


def source_record(
    source: dict[str, Any],
    *,
    concepts: dict[str, Any],
    kr_routes: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    source_id = clean(source.get("source_id"))
    jurisdiction = clean(source.get("jurisdiction"))
    version = source.get("version") if isinstance(source.get("version"), dict) else {}
    display_version = clean(version.get("display_version")) or str(source.get("publication_year"))
    attachments = [
        item for item in source.get("attachments") or [] if isinstance(item, dict)
    ]
    downloaded = [item for item in attachments if item.get("download_status") == "downloaded"]

    routes: list[dict[str, Any]] = []
    for concept_id in source.get("topic_concept_ids") or []:
        concept_id = clean(concept_id)
        routes.append(
            {
                "concept_id": concept_id,
                "mapping_method": "explicit_source_topic",
                "resolved_in_registry": concept_id in concepts,
            }
        )
    if jurisdiction == "KR":
        routes.extend(kr_routes.get(source_id) or [])

    route_rank = {
        "explicit_source_topic": 0,
        "kr_overlay_explicit": 1,
        "kr_title_rule_review_candidate": 2,
    }
    deduplicated: dict[str, dict[str, Any]] = {}
    for route in sorted(
        routes,
        key=lambda item: (route_rank[item["mapping_method"]], item["concept_id"]),
    ):
        deduplicated.setdefault(route["concept_id"], route)
    routes = [deduplicated[key] for key in sorted(deduplicated)]

    development = source.get("development") if isinstance(source.get("development"), dict) else {}
    keyword_terms = TERM_SPLIT_RE.split(clean(development.get("keywords")))
    themes = source.get("summary_themes") or []
    concept_terms: list[str] = []
    for route in routes:
        concept_id = route["concept_id"]
        concept = concepts.get(concept_id) if isinstance(concepts.get(concept_id), dict) else {}
        concept_terms.extend([concept_id, concept_id.replace("_", " ")])
        concept_terms.extend((concept.get("aliases") or [])[:4])
    search_terms = unique_strings(
        [
            source.get("title"),
            source.get("issuing_body"),
            *keyword_terms,
            *themes,
            *concept_terms,
            *(source.get("specialties") or []),
            *(source.get("clinical_axes") or []),
        ],
        limit=60,
    )

    if jurisdiction == "US":
        rights = source.get("rights") if isinstance(source.get("rights"), dict) else {}
        applicability = (
            source.get("applicability")
            if isinstance(source.get("applicability"), dict)
            else {}
        )
        runtime_ingest = rights.get("runtime_ingest_allowed") is True
        korean_role = clean(applicability.get("kr_role")) or "kr_us_comparison"
        localization_risks = unique_strings(applicability.get("localization_risks") or [])
        review_excerpt_search = False
    else:
        runtime_ingest = False
        korean_role = "primary_review_source"
        localization_risks = []
        review_excerpt_search = bool(downloaded)

    return {
        "source_id": source_id,
        "title": clean(source.get("title")),
        "issuing_body": clean(source.get("issuing_body")),
        "jurisdiction": jurisdiction,
        "document_type": clean(source.get("document_type")),
        "priority": clean(source.get("priority")),
        "publication_year": int(source.get("publication_year") or 0),
        "version": display_version,
        "official_landing_url": clean(source.get("official_landing_url")),
        "latest_status": clean(source.get("latest_status")),
        "latest_checked_at": clean(source.get("latest_checked_at")),
        "specialties": sorted(set(source.get("specialties") or [])),
        "clinical_axes": sorted(set(source.get("clinical_axes") or [])),
        "concept_routes": routes,
        "search_terms": search_terms,
        "access": {
            "attachment_count": len(attachments),
            "downloaded_attachment_count": len(downloaded),
            "metadata_only": not bool(downloaded),
            "runtime_text_ingest_allowed": runtime_ingest,
            "review_excerpt_search_allowed": review_excerpt_search,
        },
        "applicability": {
            "korean_role": korean_role,
            "localization_risks": localization_risks,
        },
        "review_state": {
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "generation_eligible": False,
            "canonical_ontology_mutated": False,
        },
    }


def build_source_map() -> dict[str, Any]:
    concepts_payload = load_json(CONCEPTS)
    concepts = concepts_payload.get("concepts") or {}
    kr_registry = load_json(KR_REGISTRY)
    kr_overlay = load_json(KR_OVERLAY)
    us_registry = load_json(US_REGISTRY)
    policy = load_json(JURISDICTION_POLICY)
    kr_routes = kr_routes_by_source(kr_overlay)

    sources = [
        source_record(source, concepts=concepts, kr_routes=kr_routes)
        for registry in (kr_registry, us_registry)
        for source in registry.get("sources") or []
    ]
    sources.sort(key=lambda item: (item["jurisdiction"], item["source_id"]))

    concept_index: dict[str, list[str]] = defaultdict(list)
    axis_index: dict[str, list[str]] = defaultdict(list)
    jurisdiction_index: dict[str, list[str]] = defaultdict(list)
    for source in sources:
        jurisdiction_index[source["jurisdiction"]].append(source["source_id"])
        for axis in source["clinical_axes"]:
            axis_index[axis].append(source["source_id"])
        for route in source["concept_routes"]:
            concept_index[route["concept_id"]].append(source["source_id"])

    conflict_policy = policy.get("conflict_policy") or {}
    payload = {
        "schema_version": "guideline_agent_map.v1",
        "generated_at": generated_at(kr_registry, us_registry),
        "map_role": "source_navigation_and_retrieval_routing_not_medical_claims",
        "inputs": {
            "concept_registry": file_ref(CONCEPTS),
            "kr_source_registry": file_ref(KR_REGISTRY),
            "kr_ontology_overlay": file_ref(KR_OVERLAY),
            "us_source_registry": file_ref(US_REGISTRY),
            "jurisdiction_policy": file_ref(JURISDICTION_POLICY),
        },
        "routing_modes": {
            "korean_clinical_learning": {
                "primary_jurisdictions": ["KR"],
                "comparison_jurisdictions": ["US"],
                "source_navigation_allowed": True,
                "unreleased_claim_use": "review_queue_only",
                "silent_merge_allowed": False,
            },
            "us_exam": {
                "primary_jurisdictions": ["US"],
                "comparison_jurisdictions": [],
                "source_navigation_allowed": True,
                "unreleased_claim_use": "review_queue_only",
                "silent_merge_allowed": False,
            },
            "research_comparison": {
                "primary_jurisdictions": ["KR", "US"],
                "comparison_jurisdictions": [],
                "source_navigation_allowed": True,
                "unreleased_claim_use": "review_queue_only",
                "silent_merge_allowed": False,
            },
        },
        "safety_boundary": {
            "source_map_is_claim_evidence": False,
            "automatic_cross_jurisdiction_merge": bool(
                conflict_policy.get("silent_merge_allowed", False)
            ),
            "unreleased_claims_answer_eligible": False,
            "student_visible": False,
            "generation_eligible": False,
        },
        "summary": {
            "sources": len(sources),
            "jurisdictions": dict(Counter(item["jurisdiction"] for item in sources)),
            "concept_routes": sum(len(item["concept_routes"]) for item in sources),
            "unique_concepts": len(concept_index),
            "unresolved_concept_routes": sum(
                not route["resolved_in_registry"]
                for item in sources
                for route in item["concept_routes"]
            ),
            "downloaded_source_count": sum(
                item["access"]["downloaded_attachment_count"] > 0 for item in sources
            ),
            "metadata_only_source_count": sum(item["access"]["metadata_only"] for item in sources),
            "runtime_text_ingest_allowed_sources": sum(
                item["access"]["runtime_text_ingest_allowed"] for item in sources
            ),
            "medical_approval": 0,
            "student_visible": 0,
            "generation_eligible": 0,
            "canonical_ontology_mutations": 0,
        },
        "sources": sources,
        "concept_index": {
            key: sorted(set(value)) for key, value in sorted(concept_index.items())
        },
        "axis_index": {
            key: sorted(set(value)) for key, value in sorted(axis_index.items())
        },
        "jurisdiction_index": {
            key: sorted(set(value)) for key, value in sorted(jurisdiction_index.items())
        },
    }
    validate(payload, MAP_SCHEMA, label="guideline source map")
    return payload


REVIEW_STATE = {
    "status": "pending_human_review",
    "needs_review": True,
    "medical_approval": False,
    "student_visible": False,
    "generation_eligible": False,
    "runtime_answer_eligible": False,
}


def deterministic_id(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:24]}"


def build_claim_registry(source_map: dict[str, Any]) -> dict[str, Any]:
    seed = load_json(CLAIM_SEED)
    sources = {item["source_id"]: item for item in source_map["sources"]}
    concepts = (load_json(CONCEPTS).get("concepts") or {})
    candidates: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []

    for authored in seed.get("candidates") or []:
        source_id = clean(authored.get("source_id"))
        source = sources.get(source_id)
        if not source:
            raise ValueError(f"Unknown candidate source_id: {source_id}")
        concept_ids = sorted(set(authored.get("concept_ids") or []))
        unresolved = [concept_id for concept_id in concept_ids if concept_id not in concepts]
        if unresolved:
            raise ValueError(f"Unresolved candidate concept IDs: {unresolved}")
        claim_body = {
            "pilot_id": authored["pilot_id"],
            "source_id": source_id,
            "jurisdiction": source["jurisdiction"],
            "source_version": source["version"],
            "source_checked_at": source["latest_checked_at"],
            "concept_ids": concept_ids,
            "topic_tags": sorted(set(authored.get("topic_tags") or [])),
            "clinical_axis": clean(authored.get("clinical_axis")),
            "population": clean(authored.get("population")),
            "care_setting": clean(authored.get("care_setting")),
            "trigger": clean(authored.get("trigger")),
            "action": clean(authored.get("action")),
            "recommendation_direction": authored["recommendation_direction"],
            "exceptions": unique_strings(authored.get("exceptions") or []),
            "recommendation_strength": authored.get("recommendation_strength"),
            "evidence_certainty": authored.get("evidence_certainty"),
            "locator": {
                "official_url": clean((authored.get("locator") or {}).get("official_url")),
                "section": (authored.get("locator") or {}).get("section"),
                "page": (authored.get("locator") or {}).get("page"),
                "pointer_status": (authored.get("locator") or {}).get("pointer_status"),
            },
            "korean_use_role": authored.get("korean_use_role") or "kr_us_comparison",
            "localization_risks": sorted(set(authored.get("localization_risks") or [])),
            "provenance": {
                "access_type": (authored.get("provenance") or {}).get("access_type"),
                "paraphrase_only": True,
                "source_text_stored": False,
                "extraction_confidence": (authored.get("provenance") or {}).get(
                    "extraction_confidence"
                ),
            },
        }
        candidates.append(
            {
                "candidate_id": deterministic_id("guideline-candidate", claim_body),
                **claim_body,
                "review_state": dict(REVIEW_STATE),
            }
        )

    for authored in seed.get("extraction_tasks") or []:
        source_id = clean(authored.get("source_id"))
        if source_id not in sources:
            raise ValueError(f"Unknown extraction task source_id: {source_id}")
        concept_ids = sorted(set(authored.get("concept_ids") or []))
        unresolved = [concept_id for concept_id in concept_ids if concept_id not in concepts]
        if unresolved:
            raise ValueError(f"Unresolved task concept IDs: {unresolved}")
        task_body = {
            "pilot_id": authored["pilot_id"],
            "source_id": source_id,
            "concept_ids": concept_ids,
            "topic_tags": sorted(set(authored.get("topic_tags") or [])),
            "clinical_axis": clean(authored.get("clinical_axis")),
            "reason": clean(authored.get("reason")),
            "required_review": authored["required_review"],
        }
        tasks.append(
            {
                "task_id": deterministic_id("guideline-extraction-task", task_body),
                **task_body,
                "review_state": dict(REVIEW_STATE),
            }
        )

    candidates.sort(key=lambda item: (item["pilot_id"], item["candidate_id"]))
    tasks.sort(key=lambda item: (item["pilot_id"], item["task_id"]))
    payload = {
        "schema_version": "guideline_atomic_claim_candidates.v1",
        "generated_at": clean(seed.get("authored_at")),
        "registry_role": "review_candidates_not_medical_claims",
        "source_map": file_ref(MAP_OUT),
        "seed": file_ref(CLAIM_SEED),
        "safety_boundary": {
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "generation_eligible": False,
            "runtime_answer_eligible": False,
            "automatic_ontology_merge": False,
        },
        "summary": {
            "candidates": len(candidates),
            "extraction_tasks": len(tasks),
            "candidates_by_pilot": dict(Counter(item["pilot_id"] for item in candidates)),
            "tasks_by_pilot": dict(Counter(item["pilot_id"] for item in tasks)),
            "source_text_stored": 0,
            "medical_approval": 0,
            "student_visible": 0,
            "generation_eligible": 0,
            "runtime_answer_eligible": 0,
            "canonical_ontology_mutations": 0,
        },
        "candidates": candidates,
        "extraction_tasks": tasks,
    }
    validate(payload, CLAIM_SCHEMA, label="guideline atomic claim candidates")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    source_map = build_source_map()
    if args.check:
        if load_json(MAP_OUT) != source_map:
            raise SystemExit("guideline source map mismatch")
        claims = build_claim_registry(source_map)
        if load_json(CLAIM_OUT) != claims:
            raise SystemExit("guideline atomic claim registry mismatch")
    else:
        write_json(MAP_OUT, source_map)
        claims = build_claim_registry(source_map)
        write_json(CLAIM_OUT, claims)

    print(
        "guideline_agent_map_ok "
        f"sources={source_map['summary']['sources']} "
        f"routes={source_map['summary']['concept_routes']} "
        f"claim_candidates={claims['summary']['candidates']} "
        f"tasks={claims['summary']['extraction_tasks']}"
    )


if __name__ == "__main__":
    main()
