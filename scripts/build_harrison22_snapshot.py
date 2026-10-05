#!/usr/bin/env python3
"""Build a private, reproducible Harrison 22e source snapshot.

The source PDFs are licensed local material.  This program records checksums,
chapter/page locators, and private extracted text for local retrieval; it does
not copy textbook text into public documentation.  Chapter boundaries are
located inside the extracted text because adjacent chapters can share a PDF
page (for example chapters 45 and 46).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import fitz


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path.home() / "Downloads" / "Harrison_22e_분할"
DEFAULT_OUTPUT = ROOT / "data_private" / "harrison" / "22e"
LEGACY_TOC = ROOT / "data_private" / "curriculum" / "harrison_toc_index.json"
SCHEMA_VERSION = "harrison_source_snapshot.v1"
EXTRACTION_VERSION = "pymupdf_text_v1"
CHAPTER_FILE_RE = re.compile(r"^(?P<chapter>\d{3})_(?P<title>.+)\.pdf$")
NUMBER_LINE_RE_TEMPLATE = r"(?m)^\s*{chapter}\s*$"
TOC_PARSER_GAP_FIXES = {
    354: {
        "title": "Metabolic Dysfunction–Associated Steatotic Liver Disease and Steatohepatitis",
        "page": 2700,
        "part": 10,
    },
    373: {"title": "Sjögren’s Disease", "page": 2876, "part": 11},
    376: {"title": "Behçet Syndrome", "page": 2908, "part": 11},
    412: {
        "title": (
            "Lesbian, Gay, Bisexual, Transgender, Queer or Questioning, Intersex, "
            "Asexual, and More (LGBTQIA+) Health"
        ),
        "page": 3178,
        "part": 12,
    },
    458: {
        "title": "Guillain-Barré Syndrome and Other Immune-Mediated Neuropathies",
        "page": 3617,
        "part": 13,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_content(value: str) -> str:
    value = value.casefold().replace("\u00ad", "")
    value = re.sub(r"-\s*\n\s*(?=[a-z])", "", value)
    return re.sub(r"\s+", " ", value).strip()


def title_tokens(value: str) -> set[str]:
    value = value.replace("/", " ").replace("–", " ").replace("—", " ")
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    stop = {"a", "an", "and", "as", "in", "of", "or", "the", "to", "with"}
    return {token for token in tokens if token not in stop and len(token) > 1}


def heading_offset(text: str, chapter: int, title: str) -> tuple[int | None, float]:
    """Return the body offset immediately after the chapter number heading."""

    wanted = title_tokens(title)
    matches = list(re.finditer(NUMBER_LINE_RE_TEMPLATE.format(chapter=chapter), text))
    best: tuple[float, int] | None = None
    for match in matches:
        before = text[max(0, match.start() - 700) : match.start()]
        seen = title_tokens(before)
        overlap = len(wanted & seen) / max(1, len(wanted))
        # A short title can appear in body text.  Prefer a heading-like match
        # close to the title and author block, but keep deterministic fallback.
        distance_bonus = 0.05 if any(
            token in title_tokens(before[-250:]) for token in wanted
        ) else 0.0
        score = overlap + distance_bonus
        candidate = (score, match.end())
        if best is None or candidate > best:
            best = candidate
    if best is not None:
        score, offset = best
        if score >= 0.45:
            return offset, round(score, 4)

    # A small number of chapters use a compact ``440 Title`` heading instead
    # of placing the chapter number below the authors.  Detect that layout
    # separately and start at the heading so preceding-chapter carry-over is
    # still excluded.
    compact = re.compile(rf"(?m)^\s*{chapter}\s+[^\n]+")
    for match in compact.finditer(text):
        vicinity = text[match.start() : min(len(text), match.end() + 250)]
        seen = title_tokens(vicinity)
        overlap = len(wanted & seen) / max(1, len(wanted))
        if overlap >= 0.45:
            return match.start(), round(overlap, 4)
    return None, round(best[0], 4) if best is not None else 0.0


def printed_page(page: fitz.Page) -> int | None:
    """Read the running printed page number from the outside page margin."""

    candidates: list[tuple[float, int]] = []
    width, height = page.rect.width, page.rect.height
    for word in page.get_text("words"):
        x0, y0, x1, y1, token = word[:5]
        if not re.fullmatch(r"\d{1,4}", token):
            continue
        number = int(token)
        if not 1 <= number <= 4500:
            continue
        top_or_bottom = y0 < 55 or y1 > height - 55
        outer_margin = x0 < 35 or x1 > width - 35
        if not (top_or_bottom and outer_margin):
            continue
        score = (0 if y0 < 55 else 10) + min(x0, width - x1)
        candidates.append((score, number))
    return min(candidates)[1] if candidates else None


def page_offsets(page_texts: list[str]) -> list[int]:
    offsets, cursor = [], 0
    for index, text in enumerate(page_texts):
        offsets.append(cursor)
        cursor += len(text)
        if index + 1 < len(page_texts):
            cursor += 3  # len("\n\f\n")
    return offsets


def trim_to_range(
    text: str,
    *,
    page_start: int,
    start: int,
    end: int,
) -> tuple[str, int, int]:
    local_start = max(0, start - page_start)
    local_end = min(len(text), end - page_start)
    if local_end <= local_start:
        return "", local_start, local_end
    return text[local_start:local_end], local_start, local_end


def json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def canonical_toc() -> dict[int, dict[str, Any]]:
    """Load the same-edition TOC and repair its five known parser omissions."""

    rows: dict[int, dict[str, Any]] = {}
    if LEGACY_TOC.exists():
        payload = json.loads(LEGACY_TOC.read_text(encoding="utf-8"))
        for row in payload.get("chapters", []):
            if isinstance(row, dict) and row.get("ch"):
                rows[int(row["ch"])] = {
                    "title": str(row.get("title") or ""),
                    "page": row.get("page"),
                    "part": row.get("part"),
                }
    rows.update(TOC_PARSER_GAP_FIXES)
    return rows


def build_snapshot(source: Path, output: Path) -> dict[str, Any]:
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Harrison split-PDF directory not found: {source}")

    pdf_paths = sorted(source.glob("*.pdf"), key=lambda path: path.name.casefold())
    if not pdf_paths:
        raise ValueError(f"no PDFs found: {source}")

    numbered: dict[int, tuple[Path, str]] = {}
    for path in pdf_paths:
        match = CHAPTER_FILE_RE.match(path.name)
        if match:
            numbered[int(match.group("chapter"))] = (path, match.group("title"))
    expected = set(range(0, 506))
    missing = sorted(expected - set(numbered))
    extra = sorted(set(numbered) - expected)
    if missing or extra:
        raise ValueError(f"numbered PDF integrity error: missing={missing}, extra={extra}")

    toc = canonical_toc()
    chapter_titles = {
        chapter: (toc.get(chapter) or {}).get("title") or row[1]
        for chapter, row in numbered.items()
        if chapter > 0
    }
    file_rows: list[dict[str, Any]] = []
    chapter_rows: list[dict[str, Any]] = []
    page_rows: list[dict[str, Any]] = []
    normalized_page_locations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    zero_text_pages: list[str] = []
    low_text_pages: list[str] = []
    extraction_errors: list[dict[str, str]] = []

    for path in pdf_paths:
        match = CHAPTER_FILE_RE.match(path.name)
        chapter = int(match.group("chapter")) if match else None
        filename_title = match.group("title") if match else None
        title = (
            ((toc.get(chapter) or {}).get("title") if chapter else None)
            or filename_title
            or ("Index" if path.name == "Index.pdf" else path.stem)
        )
        file_sha = sha256_file(path)
        try:
            document = fitz.open(path)
        except Exception as exc:  # pragma: no cover - fail-fast path
            extraction_errors.append({"file": path.name, "error": str(exc)})
            continue

        texts: list[str] = []
        printed: list[int | None] = []
        page_hashes: list[str] = []
        for pdf_page_index, page in enumerate(document):
            # Preserve the PDF content-stream reading order.  ``sort=True``
            # interleaves the two textbook columns and destroys chapter-title
            # / author / standalone-number heading sequences used below.
            text = page.get_text("text")
            texts.append(text)
            printed.append(printed_page(page))
            norm_hash = stable_hash(normalize_content(text))
            page_hashes.append(norm_hash)
            locator = f"{path.name}#pdf_page={pdf_page_index + 1}"
            normalized_page_locations[norm_hash].append(
                {"file": path.name, "pdf_page": pdf_page_index + 1}
            )
            chars = len(normalize_content(text))
            if chars == 0:
                zero_text_pages.append(locator)
            elif chars < 100:
                low_text_pages.append(locator)

        file_row = {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": file_sha,
            "pdf_pages": len(document),
            "pdf_version": document.metadata.get("format") or "",
            "encrypted": bool(document.needs_pass),
            "text_chars": sum(len(normalize_content(value)) for value in texts),
            "text_extractable": any(normalize_content(value) for value in texts),
            "normalized_page_hashes": page_hashes,
        }
        if chapter is not None:
            file_row["chapter_number"] = chapter
            file_row["filename_title"] = filename_title
            file_row["canonical_title"] = title
        file_rows.append(file_row)

        if not chapter or chapter > 505:
            document.close()
            continue

        joined = "\n\f\n".join(texts)
        start, start_score = heading_offset(joined, chapter, title)
        next_start: int | None = None
        next_score = 0.0
        if chapter < 505:
            next_title = chapter_titles[chapter + 1]
            next_start, next_score = heading_offset(joined, chapter + 1, next_title)
        if start is None:
            start = 0
        end = next_start if next_start is not None and next_start > start else len(joined)
        offsets = page_offsets(texts)
        chapter_page_count = 0
        segmented_chars = 0
        first_segmented_pdf_page: int | None = None
        last_segmented_pdf_page: int | None = None
        for pdf_page_index, (page_text, page_start) in enumerate(zip(texts, offsets), start=1):
            segment, local_start, local_end = trim_to_range(
                page_text,
                page_start=page_start,
                start=start,
                end=end,
            )
            normalized_segment = normalize_content(segment)
            if normalized_segment:
                chapter_page_count += 1
                segmented_chars += len(normalized_segment)
                first_segmented_pdf_page = first_segmented_pdf_page or pdf_page_index
                last_segmented_pdf_page = pdf_page_index
            page_rows.append(
                {
                    "chapter": chapter,
                    "source_file": path.name,
                    "source_file_sha256": file_sha,
                    "pdf_page": pdf_page_index,
                    "printed_page": printed[pdf_page_index - 1],
                    "page_text_sha256": stable_hash(page_text),
                    "normalized_page_sha256": page_hashes[pdf_page_index - 1],
                    "segment_start_char": local_start,
                    "segment_end_char": local_end,
                    "segment_text_sha256": stable_hash(segment),
                    "segment_text": segment,
                    "segment_chars": len(normalized_segment),
                    "inside_chapter_boundary": bool(normalized_segment),
                }
            )

        printed_values = [value for value in printed if value is not None]
        chapter_rows.append(
            {
                "chapter": chapter,
                "title": title,
                "filename_title": filename_title,
                "part": (toc.get(chapter) or {}).get("part"),
                "toc_printed_page": (toc.get(chapter) or {}).get("page"),
                "source_file": path.name,
                "source_file_sha256": file_sha,
                "pdf_pages": len(texts),
                "printed_page_first": min(printed_values) if printed_values else None,
                "printed_page_last": max(printed_values) if printed_values else None,
                "chapter_start_offset": start,
                "chapter_end_offset": end,
                "chapter_start_found": start_score >= 0.45,
                "chapter_start_match_score": start_score,
                "next_chapter_boundary_found": next_start is not None and next_start > start,
                "next_chapter_match_score": next_score,
                "first_segmented_pdf_page": first_segmented_pdf_page,
                "last_segmented_pdf_page": last_segmented_pdf_page,
                "segmented_pages": chapter_page_count,
                "segmented_text_chars": segmented_chars,
                "needs_review": start_score < 0.45,
            }
        )
        document.close()

    duplicate_pages = [
        {"normalized_page_sha256": digest, "locations": locations}
        for digest, locations in sorted(normalized_page_locations.items())
        if len(locations) > 1 and digest != stable_hash("")
    ]
    file_rows.sort(key=lambda row: row["path"].casefold())
    chapter_rows.sort(key=lambda row: row["chapter"])
    page_rows.sort(key=lambda row: (row["chapter"], row["pdf_page"]))

    file_digest = stable_hash(
        "\n".join(f"{row['path']}\t{row['sha256']}" for row in file_rows)
    )
    snapshot_id = f"harrison22e:{file_digest[:20]}"
    pages_path = output / "pages.jsonl"
    output.mkdir(parents=True, exist_ok=True)
    pages_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in page_rows
        ),
        encoding="utf-8",
    )
    pages_sha = sha256_file(pages_path)

    summary = {
        "pdf_files": len(file_rows),
        "numbered_files": len(numbered),
        "clinical_chapters": len(chapter_rows),
        "pdf_pages": sum(row["pdf_pages"] for row in file_rows),
        "chapter_segment_pages": sum(row["segmented_pages"] for row in chapter_rows),
        "text_chars": sum(row["text_chars"] for row in file_rows),
        "zero_text_pages": len(zero_text_pages),
        "low_text_pages": len(low_text_pages),
        "duplicate_page_groups": len(duplicate_pages),
        "chapter_boundaries_unresolved": sum(row["needs_review"] for row in chapter_rows),
        "extraction_errors": len(extraction_errors),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "source": {
            "work": "Harrison's Principles of Internal Medicine",
            "edition": "22e",
            "copyright_year": 2025,
            "source_directory_name": source.name,
            "access_scope": "private licensed local source; do not redistribute extracted text",
            "redistribution_allowed": False,
        },
        "extractor": {
            "name": EXTRACTION_VERSION,
            "pymupdf_version": fitz.VersionBind,
            "boundary_rule": "current chapter heading through next chapter heading within split PDF",
        },
        "artifacts": {
            "chapter_index": "chapter_index.json",
            "private_pages": "pages.jsonl",
            "private_pages_sha256": pages_sha,
        },
        "summary": summary,
        "integrity": {
            "expected_numbered_files": "000-505",
            "missing_numbered_files": missing,
            "extra_numbered_files": extra,
            "zero_text_pages": zero_text_pages,
            "low_text_pages": low_text_pages,
            "duplicate_pages": duplicate_pages,
            "extraction_errors": extraction_errors,
        },
        "files": file_rows,
    }
    chapter_index = {
        "schema_version": "harrison_chapter_index.v2",
        "snapshot_id": snapshot_id,
        "edition": "22e",
        "source_manifest": "snapshot_manifest.json",
        "chapters": chapter_rows,
    }
    json_dump(output / "snapshot_manifest.json", manifest)
    json_dump(output / "chapter_index.json", chapter_index)
    return manifest


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_snapshot(args.source, args.output)
    print(json.dumps({"snapshot_id": manifest["snapshot_id"], **manifest["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
