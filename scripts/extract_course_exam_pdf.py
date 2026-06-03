#!/usr/bin/env python3
"""
Course exam PDF -> question-level JSON extractor

This parser mirrors extract_course_exam_hwp.py so HWP/PDF imports can share the
same review preview, archive, and later database schema.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import fitz

try:
    from .extract_course_exam_hwp import (
        CIRCLE_TO_STR,
        CHOICE_MARK_RE,
        CHOICE_LINE_RE,
        QUESTION_START_RE,
        build_record,
        clean_text,
        parse_filename,
        render_markdown,
        safe_sample,
        slugify,
        split_question_blocks,
    )
except ImportError:
    from extract_course_exam_hwp import (
        CIRCLE_TO_STR,
        CHOICE_MARK_RE,
        CHOICE_LINE_RE,
        QUESTION_START_RE,
        build_record,
        clean_text,
        parse_filename,
        render_markdown,
        safe_sample,
        slugify,
        split_question_blocks,
    )


PARSER_VERSION = "pdf-0.1.0"
MIN_TEXT_CHARS_FOR_TEXT_LAYER = 120
VIEWABLE_IMAGE_EXTS = {".bmp", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
QUESTION_BLOCK_START_RE = re.compile(r"^\s*(\d{1,3})\s*[.)]\s+")


def extract_pdf_pages(path: Path) -> list[dict]:
    pages: list[dict] = []
    with fitz.open(path) as doc:
        for page_index, page in enumerate(doc, start=1):
            text = page.get_text("text", sort=True)
            pages.append(
                {
                    "page_number": page_index,
                    "text": clean_text(text),
                    "width": page.rect.width,
                    "height": page.rect.height,
                }
            )
    return pages


def extract_pdf_text(path: Path) -> tuple[str, list[dict]]:
    pages = extract_pdf_pages(path)
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        result = subprocess.run(
            [pdftotext, "-layout", "-enc", "UTF-8", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            text = clean_text(result.stdout)
            return text, pages
    text = clean_text("\n\n".join(page["text"] for page in pages if page["text"]))
    return text, pages


def detect_sequential_question_starts(text: str, expected_start: int) -> tuple[list[int], int]:
    questions: list[int] = []
    expected = expected_start
    for match in QUESTION_START_RE.finditer(text):
        number = int(match.group(1))
        if number == expected:
            questions.append(number)
            expected += 1
    return questions, expected


def visual_column_for_block(block: tuple, page_width: float) -> int:
    x0 = float(block[0])
    return 0 if x0 < page_width / 2 else 1


def block_is_header_or_footer(block: tuple, page_height: float) -> bool:
    y0 = float(block[1])
    y1 = float(block[3])
    return y1 < 48 or y0 > page_height - 44


def extract_pdf_question_blocks_by_layout(path: Path) -> list[tuple[int, str]]:
    candidates: list[dict] = []
    with fitz.open(path) as doc:
        for page_number, page in enumerate(doc, start=1):
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            raw_blocks = [
                block
                for block in page.get_text("blocks", sort=False)
                if len(block) >= 5
                and isinstance(block[4], str)
                and block[4].strip()
                and not block_is_header_or_footer(block, page_height)
            ]

            starts: list[dict] = []
            for block_index, block in enumerate(raw_blocks):
                text = block[4]
                match = QUESTION_BLOCK_START_RE.match(text)
                if not match:
                    continue
                starts.append(
                    {
                        "question_number": int(match.group(1)),
                        "block_index": block_index,
                        "column": visual_column_for_block(block, page_width),
                        "x0": float(block[0]),
                        "y0": float(block[1]),
                        "y1": float(block[3]),
                    }
                )

            if not starts:
                continue

            starts_by_column = {
                column: sorted(
                    [start for start in starts if start["column"] == column],
                    key=lambda item: item["y0"],
                )
                for column in (0, 1)
            }

            for column, column_starts in starts_by_column.items():
                column_blocks = [
                    block
                    for block in raw_blocks
                    if visual_column_for_block(block, page_width) == column
                ]
                for idx, start in enumerate(column_starts):
                    next_y = (
                        column_starts[idx + 1]["y0"]
                        if idx + 1 < len(column_starts)
                        else page_height - 44
                    )
                    pieces = []
                    for block in column_blocks:
                        y0 = float(block[1])
                        if start["y0"] <= y0 < next_y:
                            pieces.append(block)
                    pieces.sort(key=lambda block: (float(block[1]), float(block[0])))
                    text = clean_text("\n".join(block[4] for block in pieces))
                    if not text:
                        continue
                    choice_count = len(CHOICE_MARK_RE.findall(text))
                    if choice_count < 3 and len(text) < 80:
                        continue
                    candidates.append(
                        {
                            "page_number": page_number,
                            "column": column,
                            "y0": start["y0"],
                            "question_number": start["question_number"],
                            "text": text,
                            "choice_count": choice_count,
                        }
                    )

    candidates.sort(key=lambda item: (item["page_number"], item["column"], item["y0"]))
    selected: list[tuple[int, str]] = []
    expected = 1
    for item in candidates:
        number = item["question_number"]
        if number != expected:
            continue
        selected.append((number, item["text"]))
        expected += 1
    return selected


def block_text(block: dict) -> str:
    parts: list[str] = []
    for line in block.get("lines", []):
        spans = line.get("spans", [])
        line_text = "".join(span.get("text", "") for span in spans)
        if line_text.strip():
            parts.append(line_text)
    return clean_text("\n".join(parts))


def extract_pdf_media(
    path: Path,
    destination: Path,
    *,
    objective_count: int | None = None,
) -> tuple[dict[int, list[str]], list[dict], list[dict]]:
    destination.mkdir(parents=True, exist_ok=True)
    question_media: dict[int, list[str]] = {}
    media_assets: list[dict] = []
    media_positions: list[dict] = []

    expected_question = 1
    current_question: int | None = None
    image_counter = 0
    seen_hashes: set[int] = set()

    with fitz.open(path) as doc:
        for page_index, page in enumerate(doc, start=1):
            page_dict = page.get_text("dict", sort=True)
            blocks = sorted(
                page_dict.get("blocks", []),
                key=lambda item: (item.get("bbox", [0, 0, 0, 0])[1], item.get("bbox", [0, 0, 0, 0])[0]),
            )

            for block_index, block in enumerate(blocks, start=1):
                if block.get("type") == 0:
                    text = block_text(block)
                    starts, next_expected = detect_sequential_question_starts(text, expected_question)
                    if starts:
                        current_question = starts[-1]
                        expected_question = next_expected
                        if objective_count is not None and current_question > objective_count:
                            current_question = None
                    continue

                if block.get("type") != 1:
                    continue

                image_bytes = block.get("image")
                if not image_bytes:
                    continue
                image_hash = hash(image_bytes)
                if image_hash in seen_hashes:
                    continue
                seen_hashes.add(image_hash)

                width = int(block.get("width") or 0)
                height = int(block.get("height") or 0)
                if width < 48 or height < 48:
                    continue

                image_counter += 1
                ext = str(block.get("ext") or "png").lower().lstrip(".")
                storage_id = f"PAGE{page_index:03d}_IMG{image_counter:03d}"
                file_path = destination / f"{storage_id}.{ext}"
                file_path.write_bytes(image_bytes)

                linked_question_numbers: list[int] = []
                match_confidence = 0.35
                if current_question is not None and (
                    objective_count is None or current_question <= objective_count
                ):
                    linked_question_numbers = [current_question]
                    question_media.setdefault(current_question, []).append(storage_id)
                    match_confidence = 0.6

                media_assets.append(
                    {
                        "media_id": storage_id,
                        "source_exam": None,
                        "source_file": path.name,
                        "storage_id": storage_id,
                        "ext": ext,
                        "file_path": str(file_path),
                        "relative_path": str(file_path.relative_to(destination.parent)),
                        "page_number": page_index,
                        "block_index": block_index,
                        "bbox": block.get("bbox"),
                        "width": width,
                        "height": height,
                        "linked_question_numbers": linked_question_numbers,
                        "match_confidence": match_confidence,
                        "modality": None,
                        "caption": None,
                        "deidentified": None,
                        "approved_for_student_use": False,
                        "needs_review": True,
                    }
                )
                media_positions.append(
                    {
                        "question_number": current_question,
                        "page_number": page_index,
                        "block_index": block_index,
                        "storage_id": storage_id,
                        "bbox": block.get("bbox"),
                        "context_hint": "pdf_block_flow",
                    }
                )

    return question_media, media_assets, media_positions


def build_media_refs(meta: dict, media_assets: list[dict], storage_ids: list[str]) -> list[dict]:
    assets_by_storage = {asset["storage_id"]: asset for asset in media_assets}
    refs: list[dict] = []
    for storage_id in storage_ids:
        asset = assets_by_storage.get(storage_id)
        media_id = f"{meta['source_exam']}_{storage_id}"
        refs.append(
            {
                "media_id": media_id,
                "storage_id": storage_id,
                "match_method": "pdf_page_block_flow",
                "match_confidence": asset.get("match_confidence", 0.35) if asset else 0.35,
                "needs_review": True,
            }
        )
    return refs


def extract_file(path: Path, *, media_root: Path | None = None) -> dict:
    meta = parse_filename(path)
    meta["source_format"] = "pdf"
    text, pages = extract_pdf_text(path)
    text_layer_available = len(text) >= MIN_TEXT_CHARS_FOR_TEXT_LAYER

    linear_blocks = split_question_blocks(text) if text_layer_available else []
    layout_blocks = extract_pdf_question_blocks_by_layout(path) if text_layer_available else []
    blocks = layout_blocks if len(layout_blocks) > len(linear_blocks) else linear_blocks
    question_media_map: dict[int, list[str]] = {}
    media_assets: list[dict] = []
    media_positions: list[dict] = []

    if media_root is not None:
        exam_media_dir = media_root / slugify(meta["source_exam"])
        question_media_map, media_assets, media_positions = extract_pdf_media(
            path,
            exam_media_dir,
            objective_count=meta.get("objective_count_from_filename"),
        )
        for asset in media_assets:
            asset["source_exam"] = meta["source_exam"]
            asset["media_id"] = f"{meta['source_exam']}_{asset['storage_id']}"

    questions = []
    for number, block in blocks:
        question = build_record(
            meta,
            number,
            block,
            media_refs=build_media_refs(meta, media_assets, question_media_map.get(number, [])),
        )
        question["parser_version"] = PARSER_VERSION
        if not question["explanation"]:
            question.setdefault("review_reasons", []).append("explanation_not_extracted_or_absent")
            question["needs_review"] = True
        questions.append(question)

    extraction_warnings: list[str] = []
    if not text_layer_available:
        extraction_warnings.append("pdf_text_layer_missing_or_too_short_ocr_required")
    if not questions:
        extraction_warnings.append("no_questions_extracted")

    return {
        "exam": {
            **meta,
            "imported_at": datetime.now().isoformat(timespec="seconds"),
            "parser_version": PARSER_VERSION,
            "extracted_question_count": len(questions),
            "media_asset_count": len(media_assets),
            "media_linked_question_count": len([q for q in questions if q["media"]["media_refs"]]),
            "pdf_page_count": len(pages),
            "pdf_text_layer_available": text_layer_available,
            "extraction_warnings": extraction_warnings,
            "pdf_layout_block_question_count": len(layout_blocks),
            "pdf_linear_question_count": len(linear_blocks),
        },
        "media_assets": media_assets,
        "media_positions": media_positions,
        "questions": questions,
    }


def iter_input_files(values: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        path = Path(value).expanduser()
        if path.is_dir():
            paths.extend(sorted(path.glob("*.pdf")))
        elif path.is_file() and path.suffix.lower() == ".pdf":
            paths.append(path)

    seen = set()
    unique = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract course-exam PDF files into local private JSON.")
    parser.add_argument("inputs", nargs="+", help="PDF file paths or directories")
    parser.add_argument(
        "--output-dir",
        default="data_private/course_exams/extracted",
        help="Output directory. Defaults to data_private/course_exams/extracted",
    )
    parser.add_argument(
        "--markdown-dir",
        default="data_private/course_exams/markdown",
        help="Markdown review output directory. Defaults to data_private/course_exams/markdown",
    )
    parser.add_argument(
        "--media-dir",
        default="data_private/course_exams/media",
        help="Extracted media output directory. Defaults to data_private/course_exams/media",
    )
    parser.add_argument("--json-only", action="store_true", help="Do not write Markdown review files")
    parser.add_argument("--sample", type=int, default=0, help="Print safe structural sample without original text")
    parser.add_argument("--dry-run", action="store_true", help="Parse but do not write JSON/media")
    args = parser.parse_args()

    files = iter_input_files(args.inputs)
    if not files:
        print("No .pdf files found.", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    markdown_dir = Path(args.markdown_dir)
    media_dir = Path(args.media_dir)
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        if not args.json_only:
            markdown_dir.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for path in files:
        record = extract_file(path, media_root=None if args.dry_run else media_dir)
        output_path = output_dir / f"{slugify(record['exam']['source_exam'])}.json"
        if not args.dry_run:
            output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        markdown_path = None
        if not args.dry_run and not args.json_only:
            markdown_path = markdown_dir / f"{slugify(record['exam']['source_exam'])}.md"
            markdown_path.write_text(render_markdown(record), encoding="utf-8")

        summaries.append(
            {
                "source_file": path.name,
                "output": None if args.dry_run else str(output_path),
                "markdown": None if markdown_path is None else str(markdown_path),
                "question_count": len(record["questions"]),
                "expected_objective_count": record["exam"].get("objective_count_from_filename"),
                "needs_review_count": sum(1 for q in record["questions"] if q["needs_review"]),
                "with_answer_count": sum(1 for q in record["questions"] if q["answer"] is not None),
                "with_stimulus_count": sum(1 for q in record["questions"] if q.get("stimulus")),
                "with_explanation_count": sum(1 for q in record["questions"] if q.get("explanation")),
                "media_asset_count": len(record.get("media_assets", [])),
                "media_linked_question_count": sum(
                    1 for q in record["questions"] if q.get("media", {}).get("media_refs")
                ),
                "pdf_text_layer_available": record["exam"]["pdf_text_layer_available"],
                "extraction_warnings": record["exam"]["extraction_warnings"],
            }
        )
        if args.sample:
            print(json.dumps(safe_sample(record, args.sample), ensure_ascii=False, indent=2))

    print(json.dumps({"processed": len(files), "summaries": summaries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
