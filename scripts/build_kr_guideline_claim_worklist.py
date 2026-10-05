#!/usr/bin/env python3
"""Build deterministic per-source/per-axis Korean guideline extraction tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data_private" / "kr_guidelines" / "verified_latest_registry.json"
DEFAULT_ONTOLOGY = ROOT / "data_private" / "kr_guidelines" / "ontology_overlay.json"
DEFAULT_AGENTS = ROOT / "data_private" / "kr_guidelines" / "specialty_agent_registry.json"
DEFAULT_OUTPUT = ROOT / "data_private" / "kr_guidelines" / "claim_extraction_worklist.json"
SCHEMA = ROOT / "schemas" / "kr_guideline_claim_worklist.schema.json"
CURRENT = {"verified_latest_on_official_source", "living_guideline_current"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def file_ref(path: Path) -> dict:
    return {"path": display_path(path), "bytes": path.stat().st_size, "sha256": sha256_path(path)}


def task_id(source_id: str, axis: str) -> str:
    value = hashlib.sha256(f"{source_id}\0{axis}".encode("utf-8")).hexdigest()[:20]
    return f"kr-cpg-task:{value}"


def validate(payload: dict) -> None:
    validator = Draft7Validator(load_json(SCHEMA), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        detail = "\n".join(f"{list(error.path)}: {error.message}" for error in errors[:30])
        raise ValueError(f"worklist schema validation failed ({len(errors)} errors)\n{detail}")


def build(source_path: Path, ontology_path: Path, agent_path: Path) -> dict:
    registry = load_json(source_path)
    ontology = load_json(ontology_path)
    agents = load_json(agent_path)
    link_by_source = {row["source_id"]: row for row in ontology.get("source_links") or []}
    agents_by_source: dict[str, set[str]] = defaultdict(set)
    for agent in agents.get("agents") or []:
        for source_id in agent.get("source_ids") or []:
            agents_by_source[source_id].add(agent["agent_id"])

    tasks = []
    for source in registry.get("sources") or []:
        downloaded = [
            {
                "attachment_id": row["attachment_id"],
                "role": row.get("role") or "main",
                "relative_path": row["relative_path"],
                "bytes": row["bytes"],
                "sha256": row["sha256"],
                "pdf_pages": row.get("pdf_pages"),
            }
            for row in source.get("attachments") or []
            if row.get("download_status") == "downloaded"
            and row.get("relative_path")
            and row.get("sha256")
        ]
        if not downloaded:
            readiness = "source_file_unavailable"
        elif source["latest_status"] not in CURRENT:
            readiness = "currentness_review_required"
        else:
            readiness = "ready_for_candidate_extraction"
        link = link_by_source.get(source["source_id"]) or {}
        concepts = set(link.get("resolved_topic_concept_ids") or [])
        concepts.update(
            row["concept_id"]
            for row in (link.get("title_rule_candidates") or [])
            if row.get("resolved_in_registry")
        )
        for axis in sorted(set(source.get("clinical_axes") or [])):
            tasks.append(
                {
                    "task_id": task_id(source["source_id"], axis),
                    "source_id": source["source_id"],
                    "source_title": source["title"],
                    "priority": source.get("priority") or "P2",
                    "latest_status": source["latest_status"],
                    "clinical_axis": axis,
                    "readiness": readiness,
                    "concept_candidates": sorted(concepts),
                    "specialty_agent_ids": sorted(agents_by_source[source["source_id"]]),
                    "source_files": downloaded,
                    "task_status": "pending_candidate_extraction",
                    "needs_review": True,
                    "medical_approval": False,
                    "student_visible": False,
                    "generation_eligible": False,
                }
            )

    readiness_counts = Counter(row["readiness"] for row in tasks)
    payload = {
        "schema_version": "kr_guideline_claim_worklist.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_registry": file_ref(source_path),
        "ontology_overlay": file_ref(ontology_path),
        "agent_registry": file_ref(agent_path),
        "worklist_role": "candidate_extraction_tasks_not_medical_claims",
        "output_contract": {
            "required_claim_fields": [
                "claim_id",
                "source_id",
                "source_file_sha256",
                "page",
                "verbatim_locator_hash",
                "clinical_axis",
                "subject_concept_id",
                "relation",
                "object_text",
                "polarity",
                "population",
                "recommendation_strength",
                "evidence_grade",
                "effective_version",
                "needs_review",
                "medical_approval"
            ],
            "verbatim_storage_policy": "private_locator_only_by_default",
            "negation_required": True,
            "population_qualifier_required": True,
            "page_pointer_required": True,
            "version_pointer_required": True,
            "claim_extraction_is_not_entailment": True,
        },
        "safety_boundary": {
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "generation_eligible": False,
            "automatic_claim_promotion": False,
        },
        "summary": {
            "tasks": len(tasks),
            "sources": len({row["source_id"] for row in tasks}),
            "axes": dict(sorted(Counter(row["clinical_axis"] for row in tasks).items())),
            "priorities": dict(sorted(Counter(row["priority"] for row in tasks).items())),
            "readiness": dict(sorted(readiness_counts.items())),
            "tasks_with_concept_candidates": sum(bool(row["concept_candidates"]) for row in tasks),
            "tasks_without_concept_candidates": sum(not row["concept_candidates"] for row in tasks),
            "automatic_medical_approvals": 0,
        },
        "tasks": tasks,
    }
    validate(payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--ontology-overlay", type=Path, default=DEFAULT_ONTOLOGY)
    parser.add_argument("--agent-registry", type=Path, default=DEFAULT_AGENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build(args.source_registry, args.ontology_overlay, args.agent_registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
