#!/usr/bin/env python3
"""Audit Claude handoffs against the current private data sources.

The report intentionally contains aggregate counts only. It does not copy stems,
choices, source filenames, or medical images out of data_private/.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HANDOFF_DOCUMENTS = (
    "docs/Codex_Handoff_Study_Content_20260712.md",
    "docs/Explanation_Reasoning_Standard_20260712.md",
    "docs/Explanation_Quality_Standard_v1.md",
    "docs/Study_Content_Pipelines_Kickoff.md",
    "docs/ontology/CLAUDE_SESSION_HANDOFF_20260711.md",
    "docs/ontology/STATUS.md",
    "docs/ontology/FILE_INDEX.md",
    "docs/Codex_Handoff_Feedback_Stratification_20260713.md",
    "docs/P0_Feedback_Stratification_Tickets_20260713.md",
    "docs/design/set-builder-spec-v6-research-delta.md",
    "docs/Codex_Handoff_Lecture_Question_Bank_20260714.md",
    "docs/Claude_Design_UIUX_Coverage_Gap_Prompt_20260715.md",
    "docs/Paccine_Current_Behavior_Inventory_20260715.md",
)

DOCUMENTED_LECTURE_SNAPSHOTS = (
    {
        "document": "docs/Codex_Handoff_Study_Content_20260712.md",
        "documented_questions": 336,
        "meaning": "historical snapshot",
    },
    {
        "document": "docs/Codex_Handoff_Lecture_Question_Bank_20260714.md",
        "documented_questions": 432,
        "documented_image_links": 12,
        "meaning": "intended/generated state described by the handoff",
    },
)

QUESTION_REQUIRED_FIELDS = (
    "stem",
    "choices",
    "answer",
    "explanation",
    "choice_explanations",
    "key_point",
)

IMAGE_FIELDS = ("image", "images", "image_refs", "media", "media_refs")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_image_refs(question: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for field in IMAGE_FIELDS:
        value = question.get(field)
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
        elif isinstance(value, list):
            refs.extend(item.strip() for item in value if isinstance(item, str) and item.strip())
        elif isinstance(value, dict):
            for key in ("path", "src", "file", "filename"):
                item = value.get(key)
                if isinstance(item, str) and item.strip():
                    refs.append(item.strip())
    return refs


def audit_lecture_bank(root: Path) -> dict[str, Any]:
    bank_dir = root / "data_private" / "lecture_questions"
    media_dir = bank_dir / "media"
    question_files = sorted(bank_dir.glob("q_*.json"))

    per_file_counts: Counter[int] = Counter()
    answer_distribution: Counter[int] = Counter()
    issue_categories: Counter[str] = Counter()
    image_refs: list[str] = []
    question_count = 0

    for path in question_files:
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError):
            issue_categories["unreadable_json_file"] += 1
            continue

        questions = payload.get("questions") if isinstance(payload, dict) else payload
        if not isinstance(questions, list):
            issue_categories["missing_questions_array"] += 1
            continue

        per_file_counts[len(questions)] += 1
        question_count += len(questions)

        for question in questions:
            if not isinstance(question, dict):
                issue_categories["question_not_object"] += 1
                continue

            for field in QUESTION_REQUIRED_FIELDS:
                value = question.get(field)
                if value is None or value == "" or value == [] or value == {}:
                    issue_categories[f"missing_{field}"] += 1

            choices = question.get("choices")
            if isinstance(choices, (list, dict)) and len(choices) >= 2:
                choice_count = len(choices)
            else:
                issue_categories["invalid_choices"] += 1
                choice_count = 0

            answer = question.get("answer")
            if isinstance(answer, int) and 1 <= answer <= choice_count:
                answer_distribution[answer] += 1
            else:
                issue_categories["invalid_answer"] += 1

            choice_explanations = question.get("choice_explanations")
            if isinstance(choice_explanations, list):
                explanation_count = len(choice_explanations)
            elif isinstance(choice_explanations, dict):
                explanation_count = len(choice_explanations)
            else:
                explanation_count = 0
            if choice_count and explanation_count < choice_count:
                issue_categories["incomplete_choice_explanations"] += 1

            image_refs.extend(normalize_image_refs(question))

    media_files = sorted(path for path in media_dir.glob("*") if path.is_file())
    media_names = {path.name for path in media_files}
    referenced_names = {Path(ref).name for ref in image_refs}
    missing_media = sorted(referenced_names - media_names)
    unlinked_media = sorted(media_names - referenced_names)

    total_answers = sum(answer_distribution.values())
    max_share = (
        max(answer_distribution.values()) / total_answers if total_answers and answer_distribution else 0.0
    )

    return {
        "question_files": len(question_files),
        "questions": question_count,
        "per_file_question_count_distribution": {
            str(count): files for count, files in sorted(per_file_counts.items())
        },
        "answer_distribution": {
            str(answer): count for answer, count in sorted(answer_distribution.items())
        },
        "largest_answer_position_share": round(max_share, 4),
        "answer_position_bias_warning": max_share > 0.35,
        "schema_issue_counts": dict(sorted(issue_categories.items())),
        "schema_issue_total": sum(issue_categories.values()),
        "media_files_present": len(media_files),
        "question_image_links": len(image_refs),
        "unique_linked_media": len(referenced_names),
        "missing_linked_media_count": len(missing_media),
        "unlinked_media_count": len(unlinked_media),
        "privacy_note": "Only aggregate counts are reported; source filenames and question text are omitted.",
    }


def audit_ontology(root: Path) -> dict[str, Any]:
    concept_path = root / "data_private" / "concept_registry.json"
    axis_path = root / "data_private" / "curriculum" / "axis_registry.json"
    decisions_path = root / "data_private" / "curriculum" / "ontology_review_decisions.json"

    concept_payload = load_json(concept_path) if concept_path.exists() else {}
    axis_payload = load_json(axis_path) if axis_path.exists() else {}
    decisions_payload = load_json(decisions_path) if decisions_path.exists() else {}

    meta = concept_payload.get("_meta", {}) if isinstance(concept_payload, dict) else {}
    concepts = concept_payload.get("concepts", []) if isinstance(concept_payload, dict) else []
    stats = axis_payload.get("stats", {}) if isinstance(axis_payload, dict) else {}

    decision_count = 0
    if isinstance(decisions_payload, dict):
        for field in ("concepts", "axis_nodes", "axis_relationships"):
            value = decisions_payload.get(field, [])
            if isinstance(value, list):
                decision_count += len(value)

    return {
        "concepts": len(concepts) if isinstance(concepts, list) else meta.get("count"),
        "all_concepts_need_review": bool(meta.get("all_needs_review")),
        "axis_nodes": stats.get("nodes"),
        "axis_relationships": stats.get("relationships"),
        "axis_claims": (stats.get("nodes") or 0) + (stats.get("relationships") or 0),
        "draft_unreviewed_claims": stats.get("review_statuses", {}).get("draft_unreviewed", 0),
        "verified_entailment_claims": stats.get("claim_entailment_statuses", {}).get("verified", 0),
        "medical_approval_claims": stats.get("medical_approval_claims", 0),
        "review_decisions_applied": stats.get("review_decisions_applied", decision_count),
        "student_ready": bool(stats.get("medical_approval_claims", 0)) and not bool(meta.get("all_needs_review")),
    }


def build_report(root: Path) -> dict[str, Any]:
    documents = {path: (root / path).exists() for path in HANDOFF_DOCUMENTS}
    lecture = audit_lecture_bank(root)
    ontology = audit_ontology(root)

    conflicts: list[dict[str, Any]] = []
    for snapshot in DOCUMENTED_LECTURE_SNAPSHOTS:
        if lecture["questions"] != snapshot["documented_questions"]:
            conflicts.append(
                {
                    "document": snapshot["document"],
                    "field": "lecture_question_count",
                    "documented": snapshot["documented_questions"],
                    "actual": lecture["questions"],
                    "interpretation": snapshot["meaning"],
                }
            )
        documented_images = snapshot.get("documented_image_links")
        if documented_images is not None and lecture["question_image_links"] != documented_images:
            conflicts.append(
                {
                    "document": snapshot["document"],
                    "field": "question_image_links",
                    "documented": documented_images,
                    "actual": lecture["question_image_links"],
                    "interpretation": "media files exist, but current questions do not reference them",
                }
            )

    warnings: list[str] = []
    if not all(documents.values()):
        warnings.append("One or more handoff documents are missing.")
    if lecture["answer_position_bias_warning"]:
        warnings.append("Answer positions are substantially imbalanced; rebalance before student use.")
    if lecture["unlinked_media_count"]:
        warnings.append("Prepared media files are not linked from the current question JSON.")
    if ontology["medical_approval_claims"] == 0:
        warnings.append("Ontology construction is not equivalent to medical approval; student exposure remains fail-closed.")
    if conflicts:
        warnings.append("Historical handoff counts conflict with the current private data source.")

    return {
        "audit_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(root),
        "source_precedence": [
            "current executable data and script audit",
            "docs/ontology/STATUS.md",
            "newest dated handoff",
            "older historical handoffs",
        ],
        "handoff_documents": documents,
        "lecture_question_bank": lecture,
        "ontology": ontology,
        "document_conflicts": conflicts,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--fail-on-schema",
        action="store_true",
        help="Exit non-zero only when the current lecture question schema is invalid.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    report = build_report(root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"

    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")

    if args.fail_on_schema and report["lecture_question_bank"]["schema_issue_total"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
