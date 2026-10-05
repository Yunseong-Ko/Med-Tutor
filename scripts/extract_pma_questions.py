#!/usr/bin/env python3
"""
PMA PDF -> Question-level JSON extractor
Version: 0.1.0

Usage examples
--------------
# Process all PDFs in default directory, show 5-question sample:
    python scripts/extract_pma_questions.py --sample 5

# Explicit paths:
    python scripts/extract_pma_questions.py \\
        --input_dir  data_private/pma/raw \\
        --output_dir data_private/pma/extracted \\
        --sample 5

# Dry-run (parse only, no file output):
    python scripts/extract_pma_questions.py --dry_run --sample 5

# Override exam/period identifiers (single-PDF re-run):
    python scripts/extract_pma_questions.py \\
        --exam PMA_2023_06_B --period 1 --sample 5

Privacy note
------------
raw_text is written to JSON for debugging but NEVER printed to stdout.
--sample output is truncated to 50 chars of stem text only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PARSER_VERSION = "0.1.0"
MAX_QUESTION_NUMBER = 120  # sanity cap – real exams rarely exceed 100 per session

# Unicode circled digits used as choice markers in Korean exam PDFs
CIRCLE_CHARS = "①②③④⑤"
CIRCLE_TO_STR: Dict[str, str] = {c: str(i + 1) for i, c in enumerate(CIRCLE_CHARS)}

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# Choice line: optional leading whitespace, circled digit, then text
CHOICE_LINE_RE = re.compile(r"^([①②③④⑤])\s*(.*)")

# Question block start: 1-3 digits + literal period + space + Korean/alphanum
# The positive lookahead prevents matching stray "1." in the middle of sentences
QUESTION_START_RE = re.compile(r"(?m)^(\d{1,3})\.\s+(?=[가-힣A-Za-z0-9])")

# Header lines like "2023학년도 3학년 B군 1교시"
HEADER_RE = re.compile(r"^\d{4}학년도[^\n]*교시\s*\n?", re.MULTILINE)

# Page-number lines like  "- 1 -"  or  "– 12 –"
PAGE_NUM_RE = re.compile(r"^\s*[-–]\s*\d+\s*[-–]\s*\n?", re.MULTILINE)

# Trailing answer marker at end of stem, e.g. "치료는? ④"
# We strip this to keep stem clean; answer stays null per PMA-001 spec.
TRAILING_ANSWER_RE = re.compile(r"\s*[①②③④⑤]\s*$")

# Keywords that indicate a question references a visual element (image/graph/scan)
IMAGE_KW_RE = re.compile(
    r"(그림|사진|X선|CT|MRI|초음파|심전도|방사선|조직학|슬라이드|검사\s*사진|단층촬영|혈액도말)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

def parse_filename(stem: str) -> Tuple[str, str]:
    """
    Derive (source_exam, period) from a PDF filename stem.

    Example
    -------
    '2023.06 3학년 PMA (B턴) 문제 - 1교시'
        -> source_exam = 'PMA_2023_06_B'
        -> period      = '1'
    """
    m_date = re.search(r"(\d{4})\.(\d{2})", stem)
    year  = m_date.group(1) if m_date else "UNKN"
    month = m_date.group(2) if m_date else "XX"

    m_group = re.search(r"([AB])턴", stem)
    group = m_group.group(1) if m_group else "X"

    m_session = re.search(r"(\d+)교시", stem)
    session = m_session.group(1) if m_session else "X"

    source_exam = f"PMA_{year}_{month}_{group}"
    period = session  # "1" or "2" – year/month/group already in source_exam
    return source_exam, period


# ---------------------------------------------------------------------------
# PDF extraction helpers
# ---------------------------------------------------------------------------

def extract_pages(pdf_path: Path) -> List[Tuple[int, str, bool]]:
    """
    Open PDF and return a list of (page_num, text, has_images) per page.
    page_num is 1-based.
    has_images is True when PyMuPDF detects at least one raster/vector image
    embedded on that page.
    """
    doc = fitz.open(str(pdf_path))
    pages: List[Tuple[int, str, bool]] = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        has_images = len(page.get_images(full=False)) > 0
        pages.append((i + 1, text, has_images))
    doc.close()
    return pages


def build_full_text(
    pages: List[Tuple[int, str, bool]]
) -> Tuple[str, List[Tuple[int, int, int, bool]]]:
    """
    Concatenate cleaned page texts into a single string.

    Returns
    -------
    full_text   : concatenated, header-stripped text
    boundaries  : [(start_pos, end_pos, page_num, has_images), ...]
                  Character positions are relative to full_text.
    """
    parts: List[str] = []
    boundaries: List[Tuple[int, int, int, bool]] = []
    pos = 0

    for page_num, raw_text, has_images in pages:
        cleaned = HEADER_RE.sub("\n", raw_text)
        cleaned = PAGE_NUM_RE.sub("\n", cleaned)
        end = pos + len(cleaned)
        boundaries.append((pos, end, page_num, has_images))
        parts.append(cleaned)
        pos = end

    return "".join(parts), boundaries


def page_has_images_for_range(
    start: int,
    end: int,
    boundaries: List[Tuple[int, int, int, bool]],
) -> bool:
    """Return True if ANY page overlapping character range [start, end) has images."""
    for b_start, b_end, _, has_images in boundaries:
        if has_images and b_start < end and b_end > start:
            return True
    return False


# ---------------------------------------------------------------------------
# Question parsing
# ---------------------------------------------------------------------------

def parse_question_block(
    q_num: int,
    block_text: str,
    block_start: int,
    boundaries: List[Tuple[int, int, int, bool]],
    source_exam: str,
    period: str,
) -> dict:
    """
    Parse a single raw question block into a structured record.

    Parameters
    ----------
    q_num       : question number parsed from "N. ..."
    block_text  : raw text slice for this question (including "N. " prefix)
    block_start : character offset of block_text in full_text (for image lookup)
    boundaries  : page boundary list from build_full_text()
    source_exam : e.g. "PMA_2023_06_B"
    period      : e.g. "1"
    """
    question_id = f"{source_exam}_{period}_Q{q_num:03d}"
    raw_text = block_text  # kept verbatim for debug; never printed to stdout

    lines = block_text.splitlines()

    # ---- First line: strip "N. " prefix to get first stem fragment
    first_line = re.sub(r"^\d+\.\s*", "", lines[0]).strip() if lines else ""

    stem_parts: List[str] = [first_line] if first_line else []
    choice_raw_lines: List[str] = []
    in_choices = False

    for line in lines[1:]:
        s = line.strip()
        if not s:
            continue
        if CHOICE_LINE_RE.match(s):
            in_choices = True
            choice_raw_lines.append(s)
        elif in_choices:
            # Continuation of previous choice (rare but possible with line wrap)
            choice_raw_lines.append(s)
        else:
            stem_parts.append(s)

    # ---- Build clean stem
    stem = " ".join(p for p in stem_parts if p).strip()
    # Strip trailing answer marker (e.g. "치료는? ④") – answer stays null
    stem = TRAILING_ANSWER_RE.sub("", stem).strip()

    # ---- Parse choices
    choices: Dict[str, str] = {}
    current_key: Optional[str] = None
    current_val_parts: List[str] = []

    for line in choice_raw_lines:
        m = CHOICE_LINE_RE.match(line)
        if m:
            if current_key is not None:
                choices[current_key] = " ".join(current_val_parts).strip()
            current_key = CIRCLE_TO_STR[m.group(1)]
            current_val_parts = [m.group(2).strip()]
        else:
            if current_key is not None:
                current_val_parts.append(line.strip())

    if current_key is not None:
        choices[current_key] = " ".join(current_val_parts).strip()

    # ---- Image detection (two signals combined)
    block_end = block_start + len(block_text)
    page_img = page_has_images_for_range(block_start, block_end, boundaries)
    text_kw  = bool(IMAGE_KW_RE.search(block_text))

    # Conservative rule:
    #  - Text keyword → confident has_image
    #  - Page has images but NO keyword → probable has_image (could be neighbour
    #    question's image on same page), flag for review
    has_image = text_kw or page_img

    # ---- needs_review heuristics
    review_reasons: List[str] = []

    if not stem:
        review_reasons.append("empty_stem")
    if len(choices) == 0:
        review_reasons.append("no_choices")
    elif len(choices) < 5:
        review_reasons.append(f"choice_count={len(choices)}")
    if page_img and not text_kw:
        # Page-level image detected without text description – may be
        # a neighbouring question's image leaking through page-level detection
        review_reasons.append("possible_image_no_text_desc")

    return {
        "question_id": question_id,
        "source_exam": source_exam,
        "period": period,
        "question_number": q_num,
        "stem": stem,
        "choices": choices,
        "answer": None,          # PMA-001: never infer answer
        "has_image": has_image,
        "raw_text": raw_text,    # debug field – never printed to stdout
        "needs_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "parser_version": PARSER_VERSION,
    }


def validate_sequence(records: List[dict]) -> List[dict]:
    """
    Check for non-sequential question numbers and flag the offending record.
    Gaps (e.g. 3 -> 5) or duplicates (e.g. 3 -> 3) both trigger needs_review.
    """
    for i in range(1, len(records)):
        prev = records[i - 1]["question_number"]
        curr = records[i]["question_number"]
        if curr != prev + 1:
            records[i]["needs_review"] = True
            records[i]["review_reasons"].append(
                f"non_sequential(prev={prev},curr={curr})"
            )
    return records


# ---------------------------------------------------------------------------
# PDF processing entry point
# ---------------------------------------------------------------------------

def process_pdf(
    pdf_path: Path,
    source_exam: str,
    period: str,
) -> List[dict]:
    """
    Extract all questions from one PDF file.
    Returns a list of question records sorted by question_number.
    """
    pages = extract_pages(pdf_path)
    full_text, boundaries = build_full_text(pages)
    matches = list(QUESTION_START_RE.finditer(full_text))

    records: List[dict] = []
    for idx, m in enumerate(matches):
        q_num = int(m.group(1))

        if q_num > MAX_QUESTION_NUMBER:
            print(
                f"  SKIP q_num={q_num} (exceeds MAX={MAX_QUESTION_NUMBER})",
                file=sys.stderr,
            )
            continue

        block_start = m.start()
        block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
        block_text = full_text[block_start:block_end].strip()

        record = parse_question_block(
            q_num, block_text, block_start, boundaries, source_exam, period
        )
        records.append(record)

    return validate_sequence(records)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_sample(records: List[dict], n: int) -> None:
    """
    Print truncated summary of the first n records to stdout.
    raw_text is NEVER included in this output (privacy rule).
    stem is truncated to 50 characters.
    """
    count = min(n, len(records))
    print(f"\n{'=' * 62}")
    print(f"  SAMPLE — {count} of {len(records)} questions")
    print(f"{'=' * 62}")
    for rec in records[:count]:
        stem_preview = rec["stem"][:50] + ("…" if len(rec["stem"]) > 50 else "")
        print(f"\n  [{rec['question_id']}]")
        print(f"    stem       : {stem_preview}")
        print(f"    choices    : {list(rec['choices'].keys())}")
        print(f"    has_image  : {rec['has_image']}")
        print(f"    needs_rev  : {rec['needs_review']}")
        if rec["review_reasons"]:
            print(f"    reasons    : {rec['review_reasons']}")
    print(f"\n{'=' * 62}\n")


def check_gitignore() -> None:
    """
    Abort if data_private/ is not listed in .gitignore.
    Protects raw PMA content from accidental git commit.
    """
    gi_path = Path(".gitignore")
    if not gi_path.exists():
        print(
            "WARNING: .gitignore not found – cannot verify data_private/ is ignored.",
            file=sys.stderr,
        )
        return
    if "data_private" not in gi_path.read_text(encoding="utf-8"):
        print(
            "ERROR: 'data_private' not found in .gitignore.\n"
            "  Add it before running this script to prevent raw PMA data leaking into git.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Extract PMA exam questions from PDF → JSON  (v0.1.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--input_dir",
        default="data_private/pma/raw",
        metavar="DIR",
        help="Directory containing input PDF files (default: data_private/pma/raw)",
    )
    ap.add_argument(
        "--output_dir",
        default="data_private/pma/extracted",
        metavar="DIR",
        help="Output directory for JSON files (default: data_private/pma/extracted)",
    )
    ap.add_argument(
        "--sample",
        type=int,
        default=0,
        metavar="N",
        help="Print truncated summary of first N questions to stdout (no raw text)",
    )
    ap.add_argument(
        "--exam",
        default=None,
        metavar="ID",
        help="Override source_exam identifier, e.g. PMA_2023_06_B",
    )
    ap.add_argument(
        "--period",
        default=None,
        metavar="ID",
        help="Override period identifier, e.g. 1  (교시 번호)",
    )
    ap.add_argument(
        "--dry_run",
        action="store_true",
        help="Parse PDFs without writing any output files",
    )
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()

    # Safety gate: ensure raw data cannot leak into git
    check_gitignore()

    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.is_dir():
        print(f"ERROR: input_dir not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No .pdf files found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    all_review_ids: List[str] = []
    last_records:   List[dict] = []

    for pdf_path in pdf_files:
        # Derive identifiers from filename; CLI flags override
        src_exam, period = parse_filename(pdf_path.stem)
        if args.exam:
            src_exam = args.exam
        if args.period:
            period = args.period

        print(f"\n[PDF] {pdf_path.name}", file=sys.stderr)
        print(f"      source_exam={src_exam}  period={period}", file=sys.stderr)

        records = process_pdf(pdf_path, src_exam, period)

        review_ids = [r["question_id"] for r in records if r["needs_review"]]
        all_review_ids.extend(review_ids)

        print(
            f"      extracted={len(records)}  needs_review={len(review_ids)}",
            file=sys.stderr,
        )

        if not args.dry_run:
            out_path = output_dir / f"{src_exam}_{period}.json"
            out_path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"      saved -> {out_path}", file=sys.stderr)

        last_records = records

    # Summary
    print(
        f"\n[DONE] {len(pdf_files)} PDF(s) processed  "
        f"/ total needs_review={len(all_review_ids)}",
        file=sys.stderr,
    )
    if all_review_ids:
        preview = all_review_ids[:10]
        more    = f"  (+{len(all_review_ids)-10} more)" if len(all_review_ids) > 10 else ""
        print(f"[REVIEW IDs] {preview}{more}", file=sys.stderr)

    # Sample output to stdout (no raw_text, truncated stem)
    if args.sample > 0 and last_records:
        print_sample(last_records, args.sample)


if __name__ == "__main__":
    main()
