#!/usr/bin/env python3
"""Import a final-reviewed mixed objective/subjective explanation bundle."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from import_course_exam_explanations import merge_item, strip_inline_answer_marker


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_objective_item(item: dict[str, Any]) -> bool:
    number = str(item.get("question_number") or "").strip()
    question_format = str(item.get("question_format") or "").lower()
    return number.isdigit() and "subjective" not in question_format and "short" not in question_format


def subjective_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    number = str(item.get("question_number") or "").strip()
    match = re.search(r"(\d+)", number)
    if match:
        return (int(match.group(1)), number)
    return (9999, number)


def normalize_subjective_item(item: dict[str, Any], source_file: str, imported_at: str) -> dict[str, Any]:
    number = str(item.get("question_number") or "").strip()
    numeric = re.search(r"(\d+)", number)
    suffix = f"{int(numeric.group(1)):02d}" if numeric else re.sub(r"\W+", "_", number)
    question_id = str(item.get("question_id") or f"SUBJ{suffix}").strip()
    stem = item.get("question_text") or item.get("stem") or item.get("prompt") or ""
    labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}

    return {
        "question_id": question_id,
        "question_number": number,
        "source_exam": item.get("source_exam") or "",
        "question_format": item.get("question_format") or "subjective",
        "sub_format": item.get("sub_format") or "short_answer",
        "labels": labels,
        "stem": strip_inline_answer_marker(stem),
        "stimulus": item.get("stimulus") or "",
        "media_refs": item.get("media_refs") if isinstance(item.get("media_refs"), list) else [],
        "model_answer": item.get("model_answer") or item.get("answer") or "",
        "grading_points": item.get("grading_points") if isinstance(item.get("grading_points"), list) else [],
        "explanation": item.get("explanation") or "",
        "key_learning_points": item.get("key_learning_points") if isinstance(item.get("key_learning_points"), list) else [],
        "anki_cards": item.get("anki_cards") if isinstance(item.get("anki_cards"), list) else [],
        "needs_review": bool(item.get("needs_review")),
        "review_reason": str(item.get("review_reason") or "").strip(),
        "explanation_import": {
            "source": "claude_final_review_import",
            "batch_file": source_file,
            "imported_at": imported_at,
            "needs_review": bool(item.get("needs_review")),
            "review_reason": str(item.get("review_reason") or "").strip(),
        },
    }


def import_final_review(target: Path, master: Path, index: Path | None, no_backup: bool = False) -> dict[str, Any]:
    data = load_json(target)
    payload = load_json(master)
    index_payload = load_json(index) if index else None
    items = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        raise ValueError(f"master file has no item list: {master}")

    questions = data.get("questions") or []
    question_by_number = {str(question.get("question_number")): question for question in questions}
    imported_at = datetime.now().isoformat(timespec="seconds")

    if not no_backup:
        backup = target.with_name(f"{target.name}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(target, backup)
    else:
        backup = None

    objective_imported: list[str] = []
    subjective_imported: list[str] = []
    missing: list[dict[str, str]] = []

    for question in questions:
        if question.get("stem"):
            question["stem"] = strip_inline_answer_marker(question.get("stem"))

    for item in items:
        if not isinstance(item, dict):
            continue

        if is_objective_item(item):
            number = str(item.get("question_number") or "").strip()
            question = question_by_number.get(number)
            if not question:
                missing.append({"question_number": number, "batch_file": master.name})
                continue
            merge_item(question, item, master, imported_at)
            objective_imported.append(number)
            continue

        number = str(item.get("question_number") or "").strip()
        if not number:
            continue
        normalized = normalize_subjective_item(item, master.name, imported_at)
        subjective_questions = data.setdefault("subjective_questions", [])
        if not isinstance(subjective_questions, list):
            subjective_questions = []
            data["subjective_questions"] = subjective_questions
        existing_index = next(
            (idx for idx, existing in enumerate(subjective_questions) if str(existing.get("question_number")) == number),
            None,
        )
        if existing_index is None:
            subjective_questions.append(normalized)
        else:
            subjective_questions[existing_index] = {**subjective_questions[existing_index], **normalized}
        subjective_imported.append(number)

    if isinstance(index_payload, list):
        data["question_index"] = index_payload

    if data.get("subjective_questions"):
        data["subjective_questions"] = sorted(data["subjective_questions"], key=subjective_sort_key)

    summary = {
        "source": "claude_final_review_import",
        "imported_at": imported_at,
        "master_file": master.name,
        "index_file": index.name if index else None,
        "objective_imported_count": len(objective_imported),
        "objective_imported_question_numbers": objective_imported,
        "subjective_imported_count": len(subjective_imported),
        "subjective_imported_question_numbers": subjective_imported,
        "index_count": len(index_payload) if isinstance(index_payload, list) else 0,
        "missing": missing,
        "backup_file": str(backup) if backup else None,
    }
    data["final_review_summary"] = summary
    data["explanation_import_summary"] = {
        "source": "claude_final_review_import",
        "imported_at": imported_at,
        "imported_count": len(objective_imported),
        "imported_question_numbers": objective_imported,
        "batch_files": [master.name],
        "missing": missing,
        "duplicate_inputs": {},
        "backup_file": str(backup) if backup else None,
    }
    dump_json(target, data)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--master", required=True, type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    summary = import_final_review(args.target, args.master, args.index, no_backup=args.no_backup)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
