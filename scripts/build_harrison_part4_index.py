#!/usr/bin/env python3
"""Build a local RAG index for Harrison's Part 4 (Oncology and Hematology).

Mirrors build_heme_onc_rag_index.py but enriches each chunk with chapter/section
metadata so Evidence Jump can produce precise location citations.

Output: data_private/rag/harrison_part4/rag_index.json  (gitignored)
Source: data_private/textbook_grounding/harrison/11_PART 4 Oncology and Hematology.pdf

Usage:
    python3 scripts/build_harrison_part4_index.py
    python3 scripts/build_harrison_part4_index.py --source /path/to/part4.pdf
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.rag_library import (
    PARSER_VERSION,
    clean_text,
    expand_query_terms,
    search_rag_evidence,
    tokenize,
)

COURSE_ID = "harrison_part4"  # compatibility identifier used by Evidence Jump
SOURCE_ID = "harrison_22e_part4"
HARRISON_EDITION = "22e"
DEFAULT_SOURCE = (
    ROOT
    / "data_private"
    / "textbook_grounding"
    / "harrison"
    / "11_PART 4 Oncology and Hematology.pdf"
)
OUTPUT_PATH = ROOT / "data_private" / "rag" / "harrison_part4" / "rag_index.json"

CHUNK_SIZE = 1800
OVERLAP = 180

# Chapter number range for Harrison Part 4 (Oncology & Hematology)
CHAP_NUM_MIN = 73
CHAP_NUM_MAX = 130

HARRISON_PAGE_RE = re.compile(r"^\d{3,4}$")  # printed book page numbers (e.g. 498)
CHAPTER_HEADER_RE = re.compile(r"^CHAPTER\s+(\d+)$")


def stable_id(*parts: str, length: int = 16) -> str:
    digest = hashlib.sha1("::".join(str(p) for p in parts).encode()).hexdigest()
    return digest[:length]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _extract_printed_page(lines: list[str]) -> int | None:
    """Extract the printed book page number from the first few lines of a PDF page."""
    for line in lines[:4]:
        if HARRISON_PAGE_RE.match(line):
            num = int(line)
            if 490 <= num <= 1000:  # Part 4 spans ~p.496-940
                return num
    return None


def _detect_chapter_starts(doc: "fitz.Document") -> list[dict]:
    """Scan the PDF and return a list of chapter-start records.

    Detects chapter boundaries by finding 'CHAPTER NN' in page headers and
    reading the chapter title from the preceding line(s).

    Returns sorted list of dicts: pdf_page (1-based), chapter_num, chapter_title.
    """
    chapter_map: dict[int, dict] = {}

    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text("text")
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

        for idx, line in enumerate(lines[:8]):
            m = CHAPTER_HEADER_RE.match(line)
            if not m:
                continue
            chap_num = int(m.group(1))
            if not (CHAP_NUM_MIN <= chap_num <= CHAP_NUM_MAX):
                continue

            # Collect title from lines BEFORE 'CHAPTER NN', skipping page numbers
            title_candidates: list[str] = []
            for prev_line in reversed(lines[:idx]):
                if HARRISON_PAGE_RE.match(prev_line):
                    continue
                if len(prev_line) < 3:
                    continue
                title_candidates.append(prev_line)
                if len(title_candidates) >= 2:
                    break
            title = " ".join(reversed(title_candidates)).strip()

            # Record only the first (lowest pdf_page) occurrence per chapter
            if chap_num not in chapter_map:
                chapter_map[chap_num] = {
                    "pdf_page": i + 1,
                    "chapter_num": chap_num,
                    "chapter_title": title[:120],
                }
            break  # only one CHAPTER header per page

    return sorted(chapter_map.values(), key=lambda x: x["pdf_page"])


def _assign_chapter(pdf_page: int, chapter_starts: list[dict]) -> dict:
    """Return the chapter metadata for a given PDF page (1-based)."""
    current: dict = {"chapter_num": None, "chapter_title": "Part 4 Oncology and Hematology"}
    for cs in chapter_starts:
        if cs["pdf_page"] <= pdf_page:
            current = cs
        else:
            break
    return current


def extract_harrison_pages(pdf_path: Path) -> list[dict]:
    """Extract pages from Harrison Part 4 PDF, adding printed page and chapter info."""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) must be installed.") from exc

    pages: list[dict] = []
    with fitz.open(str(pdf_path)) as doc:
        chapter_starts = _detect_chapter_starts(doc)

        for i, page in enumerate(doc, start=1):
            text = clean_text(page.get_text("text"))
            if not text:
                continue
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            printed_page = _extract_printed_page(lines)
            chapter_meta = _assign_chapter(i, chapter_starts)
            pages.append(
                {
                    "pdf_page": i,
                    "printed_page": printed_page,
                    "chapter_num": chapter_meta.get("chapter_num"),
                    "chapter_title": chapter_meta.get("chapter_title", ""),
                    "text": text,
                }
            )
    return pages


def chunk_harrison_pages(
    pages: list[dict],
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = OVERLAP,
) -> list[dict]:
    """Chunk pages, preserving chapter/page metadata on each chunk."""
    chunks: list[dict] = []
    for page in pages:
        pdf_page = page["pdf_page"]
        printed_page = page.get("printed_page")
        chapter_num = page.get("chapter_num")
        chapter_title = page.get("chapter_title", "")
        paragraphs = [clean_text(p) for p in re.split(r"\n\s*\n", page["text"]) if clean_text(p)]
        buffer = ""
        for paragraph in paragraphs:
            if not buffer:
                buffer = paragraph
                continue
            if len(buffer) + len(paragraph) + 2 <= chunk_size:
                buffer = f"{buffer}\n\n{paragraph}"
            else:
                chunks.append(
                    {
                        "pdf_page_start": pdf_page,
                        "pdf_page_end": pdf_page,
                        "printed_page": printed_page,
                        "chapter_num": chapter_num,
                        "chapter_title": chapter_title,
                        "text": buffer,
                    }
                )
                tail = buffer[-overlap:] if overlap and len(buffer) > overlap else ""
                buffer = clean_text(f"{tail}\n\n{paragraph}")
        if buffer:
            chunks.append(
                {
                    "pdf_page_start": pdf_page,
                    "pdf_page_end": pdf_page,
                    "printed_page": printed_page,
                    "chapter_num": chapter_num,
                    "chapter_title": chapter_title,
                    "text": buffer,
                }
            )
    return chunks


def build_harrison_index(
    source_path: Path,
    *,
    output_path: Path = OUTPUT_PATH,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = OVERLAP,
) -> dict:
    source_path = source_path.expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source_path}")

    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    doc_id = stable_id(COURSE_ID, source_sha256, length=12)
    pages = extract_harrison_pages(source_path)
    raw_chunks = chunk_harrison_pages(pages, chunk_size=chunk_size, overlap=overlap)

    document_frequency: dict[str, int] = defaultdict(int)
    index_chunks: list[dict] = []

    for chunk_index, chunk in enumerate(raw_chunks, start=1):
        text = chunk["text"]
        terms = sorted(set(tokenize(text)))
        for term in terms:
            document_frequency[term] += 1

        chapter_num = chunk.get("chapter_num")
        chapter_title = chunk.get("chapter_title", "")
        printed_page = chunk.get("printed_page")

        # Build human-readable location string
        if chapter_num and chapter_title:
            location = f"Harrison's Part 4, Chapter {chapter_num}: {chapter_title}"
        else:
            location = "Harrison's Part 4, Oncology and Hematology"
        if printed_page:
            location += f", ~p.{printed_page}"

        chunk_id = stable_id(doc_id, str(chunk_index), text[:80], length=16)
        index_chunks.append(
            {
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "course_id": COURSE_ID,
                "title": f"Harrison's Part 4 Ch.{chapter_num or '?'}: {chapter_title or 'Oncology and Hematology'}",
                "source_type": "textbook",
                "source_name": source_path.name,
                "source_edition": HARRISON_EDITION,
                "source_sha256": source_sha256,
                # Location fields for Evidence Jump output contract
                "chapter_num": chapter_num,
                "chapter_title": chapter_title,
                "printed_page": printed_page,
                "pdf_page_start": chunk["pdf_page_start"],
                "pdf_page_end": chunk["pdf_page_end"],
                "location": location,
                # Aliases for rag_library compatibility
                "page_start": chunk["pdf_page_start"],
                "page_end": chunk["pdf_page_end"],
                "text": text,
                "terms": terms,
                "char_count": len(text),
            }
        )

    document_record = {
        "document_id": doc_id,
        "course_id": COURSE_ID,
        "source_id": SOURCE_ID,
        "title": "Harrison's Principles of Internal Medicine — Part 4: Oncology and Hematology",
        "source_type": "textbook",
        "source_edition": HARRISON_EDITION,
        "source_sha256": source_sha256,
        "source_path": source_path.name,
        "source_name": source_path.name,
        "page_count": len(pages),
        "chunk_count": len(index_chunks),
    }

    index = {
        "schema_version": PARSER_VERSION,
        "course_id": COURSE_ID,
        "source_id": SOURCE_ID,
        "source_edition": HARRISON_EDITION,
        "source_sha256": source_sha256,
        "created_at": utc_now(),
        "documents": [document_record],
        "chunks": index_chunks,
        "stats": {
            "document_count": 1,
            "chunk_count": len(index_chunks),
            "term_count": len(document_frequency),
        },
        "document_frequency": dict(sorted(document_frequency.items())),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(index, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(output_path.parent), delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(output_path)

    return index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Harrison Part 4 RAG index with chapter/section/page metadata."
    )
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help="Path to Harrison Part 4 PDF.",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
        help="Output path for the RAG index JSON.",
    )
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=OVERLAP)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output)

    print(f"[BUILD] Indexing: {source.name}")
    print(f"[BUILD] Output:   {output}")

    index = build_harrison_index(source, output_path=output, chunk_size=args.chunk_size, overlap=args.overlap)

    print(f"[DONE]  index: {output}")
    print(
        "[STATS]",
        f"chunks={index['stats']['chunk_count']}",
        f"terms={index['stats']['term_count']}",
    )

    # Validation: test a couple of queries
    from src.services.rag_library import search_rag_evidence, _load_rag_index_from_path
    _load_rag_index_from_path.cache_clear()

    sample_queries = [
        "iron deficiency anemia ferritin TIBC",
        "AML acute myeloid leukemia Auer rods blast",
        "febrile neutropenia antibiotic",
        "multiple myeloma CRAB criteria",
    ]
    for q in sample_queries:
        try:
            result = search_rag_evidence(q, course_id=COURSE_ID, limit=2, index_path=output)
            for item in result["results"]:
                loc = item.get("location", f"p.{item['page_start']}")
                print(f"[SAMPLE] '{q}' -> {loc} (score={item['score']})")
        except Exception as exc:
            print(f"[SAMPLE] '{q}' failed: {exc}")


if __name__ == "__main__":
    main()
