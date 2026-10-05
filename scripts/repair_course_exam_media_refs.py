#!/usr/bin/env python3
"""Repair question-level media_refs from media_assets.linked_question_numbers.

Some extracted exam JSON files already contain media assets with
`linked_question_numbers`, but individual question records may have an empty
`media.media_refs` list. The web practice renderer uses question-level refs, so
this script fills only missing refs without overwriting existing mappings.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTRACTED_DIR = ROOT / "data_private" / "course_exams" / "extracted"


def question_number_key(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def build_ref(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "media_id": asset.get("media_id"),
        "storage_id": asset.get("storage_id"),
        "file_path": asset.get("file_path"),
        "relative_path": asset.get("relative_path"),
        "match_method": asset.get("match_method") or "linked_question_numbers_repair",
        "match_confidence": asset.get("match_confidence", 0.6),
        "needs_review": asset.get("needs_review", True),
    }


def repair_file(path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assets = data.get("media_assets") if isinstance(data.get("media_assets"), list) else []
    questions = data.get("questions") if isinstance(data.get("questions"), list) else []

    assets_by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        for linked_number in asset.get("linked_question_numbers") or []:
            key = question_number_key(linked_number)
            if key:
                assets_by_question[key].append(asset)

    changed_questions: list[str] = []
    added_refs = 0
    for question in questions:
        if not isinstance(question, dict):
            continue
        key = question_number_key(question.get("question_number"))
        linked_assets = assets_by_question.get(key) or []
        if not linked_assets:
            continue

        media = question.get("media")
        if not isinstance(media, dict):
            media = {}
            question["media"] = media

        existing_refs = media.get("media_refs")
        if isinstance(existing_refs, list) and existing_refs:
            continue

        media["has_image_or_data_reference"] = True
        media["asset_policy"] = media.get("asset_policy") or "link_extracted_or_uploaded_media_after_review"
        media["media_refs"] = [build_ref(asset) for asset in linked_assets]
        changed_questions.append(key)
        added_refs += len(linked_assets)

    if changed_questions and not dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "file": str(path),
        "asset_count": len(assets),
        "question_count": len(questions),
        "changed_question_count": len(changed_questions),
        "changed_questions": changed_questions,
        "added_ref_count": added_refs,
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair course exam question media refs.")
    parser.add_argument("targets", nargs="*", type=Path, help="Specific extracted JSON files to repair.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    targets = args.targets or sorted(DEFAULT_EXTRACTED_DIR.glob("*.json"))
    summaries = [repair_file(path, dry_run=args.dry_run) for path in targets]
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
