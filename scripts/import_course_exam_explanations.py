#!/usr/bin/env python3
"""Import authored learning explanations into extracted course-exam JSON."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_key(value: Any) -> str:
    text = str(value or "").strip()
    circled = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5", "⑥": "6", "⑦": "7", "⑧": "8"}
    if text in circled:
        return circled[text]
    for marker, digit in circled.items():
        if marker in text:
            return digit
    return text


def strip_inline_answer_marker(text: Any) -> str:
    """Remove leaked answer marks appended to HWP stems, e.g. '(두 가지) ④③'."""
    import re

    value = str(text or "").strip()
    return re.sub(r"\s*[①②③④⑤⑥⑦⑧]{1,8}\s*$", "", value).rstrip()


def answer_keys(answer: Any) -> list[str]:
    values = answer if isinstance(answer, list) else [answer]
    return [normalize_key(value) for value in values if str(value or "").strip()]


def normalize_choice_explanations(
    item: dict[str, Any],
    existing_choices: Any,
    batch_file: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    existing_choice_map: dict[str, str] = {}
    if isinstance(existing_choices, list):
        existing_choice_map = {str(index + 1): str(value) for index, value in enumerate(existing_choices)}
    elif isinstance(existing_choices, dict):
        existing_choice_map = {normalize_key(key): str(value) for key, value in existing_choices.items()}

    generated_answers = set(answer_keys(item.get("answer")))
    choice_explanations: dict[str, dict[str, Any]] = {}
    choice_texts: dict[str, str] = {}
    raw_choices = item.get("choice_explanations") or {}
    for key, value in raw_choices.items():
        normalized = normalize_key(key)
        if isinstance(value, dict):
            choice_text = str(value.get("choice_text") or existing_choice_map.get(normalized) or "").strip()
            rationale = str(
                value.get("rationale")
                or value.get("explanation")
                or value.get("text")
                or ""
            ).strip()
            learning_points = value.get("learning_points") or value.get("learningPoints") or []
        else:
            choice_text = existing_choice_map.get(normalized, "")
            rationale = str(value or "").strip()
            learning_points = []

        if choice_text:
            choice_texts[normalized] = choice_text
        choice_explanations[normalized] = {
            "choice_text": choice_text,
            "rationale": rationale,
            "explanation": rationale,
            "is_correct": normalized in generated_answers,
            "needs_review": bool(item.get("needs_review")),
            "learning_points": learning_points if isinstance(learning_points, list) else [],
            "source": "claude_batch_import",
            "batch_file": batch_file,
        }
    return choice_explanations, choice_texts


def merge_item(question: dict[str, Any], item: dict[str, Any], batch_path: Path, imported_at: str) -> None:
    if question.get("stem"):
        question["stem"] = strip_inline_answer_marker(question.get("stem"))

    if "original_explanation" not in question and question.get("explanation"):
        question["original_explanation"] = question.get("explanation")

    choice_explanations, choice_texts = normalize_choice_explanations(
        item,
        question.get("choices"),
        batch_path.name,
    )
    existing_choice_count = len(question.get("choices") or {})
    if choice_texts and len(choice_texts) >= existing_choice_count:
        question["choices"] = dict(sorted(choice_texts.items(), key=lambda pair: int(pair[0]) if pair[0].isdigit() else pair[0]))

    key_info = item.get("key_info") if isinstance(item.get("key_info"), dict) else {}
    answer_rationale = str(item.get("answer_rationale") or "").strip()
    explanation_parts = [
        str(key_info.get("core_explanation") or "").strip(),
        answer_rationale,
    ]
    authored_explanation = "\n\n".join(part for part in explanation_parts if part)
    if authored_explanation:
        question["explanation"] = authored_explanation

    item_labels = item.get("labels")
    if isinstance(item_labels, dict):
        existing_labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
        question["labels"] = {**existing_labels, **item_labels}

    if isinstance(item.get("media_refs"), list):
        question["authored_media_refs"] = item["media_refs"]

    if key_info:
        question["key_info"] = key_info
    if answer_rationale:
        question["answer_rationale"] = answer_rationale
    if choice_explanations:
        question["choice_explanations"] = choice_explanations
    if isinstance(item.get("key_learning_points"), list):
        question["key_learning_points"] = item["key_learning_points"]
    if isinstance(item.get("anki_cards"), list):
        question["anki_cards"] = item["anki_cards"]

    generated = answer_keys(item.get("answer"))
    if generated:
        question["generated_answer"] = generated
        if not str(question.get("answer") or "").strip() and len(generated) == 1:
            question["answer"] = generated[0]

    for field in ("question_format", "sub_format"):
        if item.get(field):
            question[field] = item[field]

    question["explanation_import"] = {
        "source": "claude_batch_import",
        "batch_file": batch_path.name,
        "imported_at": imported_at,
        "needs_review": bool(item.get("needs_review")),
        "review_reason": str(item.get("review_reason") or "").strip(),
    }


def import_batches(target: Path, batches: list[Path], no_backup: bool = False) -> dict[str, Any]:
    data = load_json(target)
    questions = data.get("questions") or []
    question_by_number = {str(question.get("question_number")): question for question in questions}
    imported_at = datetime.now().isoformat(timespec="seconds")

    if not no_backup:
        backup = target.with_name(f"{target.name}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(target, backup)
    else:
        backup = None

    imported: list[str] = []
    missing: list[dict[str, str]] = []
    duplicate_inputs: dict[str, list[str]] = {}
    seen: dict[str, str] = {}

    for batch in batches:
        payload = load_json(batch)
        for item in payload.get("items") or []:
            number = str(item.get("question_number") or "").strip()
            if not number:
                continue
            if number in seen:
                duplicate_inputs.setdefault(number, [seen[number]]).append(batch.name)
            seen[number] = batch.name
            question = question_by_number.get(number)
            if not question:
                missing.append({"question_number": number, "batch_file": batch.name})
                continue
            merge_item(question, item, batch, imported_at)
            imported.append(number)

    data["explanation_import_summary"] = {
        "source": "claude_batch_import",
        "imported_at": imported_at,
        "imported_count": len(imported),
        "imported_question_numbers": imported,
        "batch_files": [path.name for path in batches],
        "missing": missing,
        "duplicate_inputs": duplicate_inputs,
        "backup_file": str(backup) if backup else None,
    }
    dump_json(target, data)
    return data["explanation_import_summary"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--batch", action="append", required=True, type=Path)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    summary = import_batches(args.target, args.batch, no_backup=args.no_backup)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
