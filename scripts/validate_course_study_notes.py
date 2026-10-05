#!/usr/bin/env python3
"""Validate completeness and local links for generated course study notes."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


REQUIRED_SECTION_ALTERNATIVES = (
    ("## 30초 핵심 요약", "## 30초 요약"),
    ("## 핵심 흐름",),
    ("## 시험에 잘 나오는 부분", "## 시험 포인트"),
    ("## 사진자료", "## 강의 슬라이드 이미지"),
    ("## 연관 문항", "## 새 5지선다 문항"),
    ("## Ontology 검증 기록", "## 온톨로지 교차검증 기록"),
    ("## 출처",),
)

IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
QUESTION_RE = re.compile(r"(?m)^###\s+(?:새\s+)?문항\s+\d+")
QUESTION_BLOCK_RE = re.compile(
    r"(?ms)^###\s+(?:새\s+)?문항\s+\d+\s*\n(.*?)(?=^###\s+(?:새\s+)?문항\s+\d+|^##\s+|\Z)"
)
CHOICE_RE = re.compile(r"(?m)^(?:[1-5][.)]|[①②③④⑤])\s+")
ANSWER_RE = re.compile(r"<details>\s*<summary>\s*정답(?:\s+및\s+해설)?\s*</summary>")
VISIBLE_ANSWER_RE = re.compile(r"(?m)^\*\*정답(?::\*\*|\*\*:|:)\s*")


def validate(inventory_path: Path, report_path: Path) -> dict[str, Any]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    note_rows: list[dict[str, Any]] = []

    for group in inventory["groups"]:
        note_path = Path(group["note_path"])
        if not note_path.exists():
            errors.append(f"{group['group_id']}: missing note {note_path}")
            continue
        text = note_path.read_text(encoding="utf-8")
        normalized_text = unicodedata.normalize("NFKC", text)
        if f"group_id: {group['group_id']}" not in text:
            errors.append(f"{group['group_id']}: frontmatter group_id missing or wrong")
        if f"source_count: {len(group['sources'])}" not in text:
            errors.append(f"{group['group_id']}: source_count missing or wrong")
        for source in group["sources"]:
            source_name = unicodedata.normalize("NFKC", source["source_name"])
            sha12 = source["source_sha256"][:12]
            if source_name not in normalized_text:
                errors.append(
                    f"{group['group_id']}: source name missing from note: {source['source_name']}"
                )
            if sha12 not in text:
                errors.append(f"{group['group_id']}: source SHA prefix missing: {sha12}")
        for alternatives in REQUIRED_SECTION_ALTERNATIVES:
            if not any(section in text for section in alternatives):
                errors.append(
                    f"{group['group_id']}: missing section alternatives {alternatives}"
                )

        question_count = len(QUESTION_RE.findall(text))
        hidden_answer_count = len(ANSWER_RE.findall(text))
        visible_answer_count = len(VISIBLE_ANSWER_RE.findall(text))
        answer_count = max(hidden_answer_count, visible_answer_count)
        expected_questions = int(group["expected_question_count"])
        if question_count != expected_questions:
            errors.append(
                f"{group['group_id']}: question_count={question_count} expected={expected_questions}"
            )
        if answer_count != expected_questions:
            errors.append(
                f"{group['group_id']}: answer_count={answer_count} expected={expected_questions}"
            )
        question_blocks = QUESTION_BLOCK_RE.findall(text)
        malformed_choice_counts = [
            len(CHOICE_RE.findall(block))
            for block in question_blocks
            if len(CHOICE_RE.findall(block)) != 5
        ]
        if malformed_choice_counts:
            errors.append(
                f"{group['group_id']}: non-5-choice question blocks {malformed_choice_counts}"
            )

        image_links = IMAGE_RE.findall(text)
        if not image_links and "적절한 대표 이미지 없음" not in text:
            errors.append(f"{group['group_id']}: no image and no explicit no-image rationale")
        if len(image_links) > 4:
            warnings.append(f"{group['group_id']}: image_count={len(image_links)} exceeds 4")
        broken_images: list[str] = []
        for link in image_links:
            if re.match(r"^[a-z]+://", link):
                continue
            image_path = (note_path.parent / link).resolve()
            if not image_path.exists():
                broken_images.append(link)
        if broken_images:
            errors.append(f"{group['group_id']}: broken images {broken_images}")

        minimum_chars = 2600 if len(group["periods"]) >= 2 else 1700
        if len(text) < minimum_chars:
            warnings.append(
                f"{group['group_id']}: note_chars={len(text)} below suggested {minimum_chars}"
            )
        frontmatter = text.split("---", 2)[1].lower() if text.startswith("---") else ""
        if "ontology_check:" not in frontmatter or "consistency" not in frontmatter:
            errors.append(f"{group['group_id']}: Ontology boundary missing from frontmatter")
        if "의학 승인" not in text and "의학적 승인" not in text and "approval" not in text:
            warnings.append(f"{group['group_id']}: medical-approval boundary not explicit")

        note_rows.append(
            {
                "group_id": group["group_id"],
                "note_path": str(note_path),
                "chars": len(text),
                "questions": question_count,
                "images": len(image_links),
                "broken_images": broken_images,
            }
        )

    payload = {
        "schema_version": "1.0.0",
        "source_files": inventory["source_file_count"],
        "expected_notes": inventory["lecture_group_count"],
        "completed_notes": len(note_rows),
        "total_questions": sum(row["questions"] for row in note_rows),
        "total_embedded_images": sum(row["images"] for row in note_rows),
        "errors": errors,
        "warnings": warnings,
        "notes": note_rows,
        "status": "ok" if not errors else "failed",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = validate(args.inventory.resolve(), args.report.resolve())
    print(
        "course_study_notes_validation "
        f"status={payload['status']} notes={payload['completed_notes']}/{payload['expected_notes']} "
        f"questions={payload['total_questions']} images={payload['total_embedded_images']} "
        f"errors={len(payload['errors'])} warnings={len(payload['warnings'])}"
    )
    if payload["errors"]:
        for error in payload["errors"]:
            print(f"ERROR {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
