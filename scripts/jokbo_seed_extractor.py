#!/usr/bin/env python3
"""Extract lesson/concept/question seeds from P:accine jokbo source materials.

This script intentionally starts with deterministic structure extraction:
- 정리족 PDFs with a table of contents become lesson note seeds.
- 정리족 materials become concept seed candidates.
- 출족 materials become question seed candidates.

Generated seed drafts stay under data_private/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_lecture_questions import clean_text, extract_text, slugify

try:
    import fitz
except Exception:  # pragma: no cover
    fitz = None


DEFAULT_OUTPUT_DIR = Path("data_private/curriculum_seeds")


def _load_materials(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("materials file must contain a JSON list")
    return data


def _compact_korean_name(value: str) -> str:
    value = re.sub(r"\s+", "", value or "")
    return value.strip("- ")


def _extract_pdf_pages(path: Path) -> list[str]:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not available")
    doc = fitz.open(str(path))
    pages = [clean_text(page.get_text("text")) for page in doc]
    doc.close()
    return pages


def _parse_toc_from_pages(pages: list[str], *, max_pages: int = 8) -> list[dict[str, Any]]:
    toc: list[dict[str, Any]] = []
    recent_line = ""
    recent_professor = ""
    toc_text = "\n".join(pages[:max_pages])
    lines = [line.strip() for line in toc_text.splitlines() if line.strip()]

    for line in lines:
        if line.startswith("<") or line in {"-", "–"}:
            continue
        if re.fullmatch(r"-?\s*\d+\s*-?", line):
            continue
        if "정리족" in line or "차례" in line:
            continue

        match = re.search(r"(.+?)\s*[·.]{3,}\s*p\.?\s*([0-9,\-\s]+)", line)
        if match:
            title = clean_text(match.group(1)).strip(" -")
            page_refs = [int(x) for x in re.findall(r"\d+", match.group(2))]
            if title and page_refs:
                professor = _compact_korean_name(recent_professor or recent_line)
                toc.append({
                    "professor": professor,
                    "title": title,
                    "start_page": page_refs[0],
                    "page_refs": page_refs,
                })
            recent_line = line
            continue

        if line == "-":
            recent_professor = recent_line
            continue
        if re.fullmatch(r"[가-힣A-Za-z\s]{2,12}", line):
            recent_professor = line
        recent_line = line

    for idx, item in enumerate(toc):
        next_start = toc[idx + 1]["start_page"] if idx + 1 < len(toc) else None
        item["end_page"] = next_start - 1 if next_start else None
    return toc


def _slice_pages(pages: list[str], start_page: int, end_page: int | None) -> str:
    start_idx = max(0, start_page - 1)
    end_idx = min(len(pages), end_page if end_page else len(pages))
    selected = []
    for idx, text in enumerate(pages[start_idx:end_idx], start=start_page):
        selected.append(f"=== page {idx} ===\n{text}")
    return clean_text("\n\n".join(selected))


def _summary_seed_id(material_id: str, title: str, start_page: int | str = "") -> str:
    suffix = slugify(f"{title}_{start_page}")[:80]
    return f"seed_{material_id}_{suffix}"


def _extract_heading_candidates(text: str, *, limit: int = 40) -> list[str]:
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line = clean_text(raw_line)
        if not line or len(line) > 80:
            continue
        if re.fullmatch(r"[-=·.\s\d]+", line):
            continue
        if line.startswith("==="):
            continue
        if re.match(r"^(\d+[\).]|[IVX]+\.|[가-힣]\.)\s*", line) or len(line) <= 28:
            candidates.append(line)
        if len(candidates) >= limit:
            break
    return candidates


def _make_lesson_seed(
    material: dict[str, Any],
    toc_item: dict[str, Any],
    text: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    seed_id = _summary_seed_id(material["material_id"], toc_item["title"], toc_item["start_page"])
    return {
        "seed_id": seed_id,
        "seed_type": "lesson_note",
        "source_material_id": material["material_id"],
        "source_name": material["original_name"],
        "course": material.get("course", ""),
        "unit": toc_item["title"],
        "professor": toc_item.get("professor") or material.get("teacher", ""),
        "start_page": toc_item["start_page"],
        "end_page": toc_item.get("end_page"),
        "page_refs": toc_item.get("page_refs", []),
        "text_preview": text[:1200],
        "heading_candidates": _extract_heading_candidates(text),
        "review_status": "needs_review",
        "created_at": now,
        "updated_at": now,
    }


def _make_whole_material_seed(material: dict[str, Any], text: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    seed_type = "question_seed" if material.get("material_type") == "jokbo_recall" else "concept_seed"
    return {
        "seed_id": _summary_seed_id(material["material_id"], material["original_name"]),
        "seed_type": seed_type,
        "source_material_id": material["material_id"],
        "source_name": material["original_name"],
        "course": material.get("course", ""),
        "unit": material.get("unit", ""),
        "professor": material.get("teacher", ""),
        "jokbo_type": material.get("jokbo_type", ""),
        "jokbo_label": material.get("jokbo_label", ""),
        "text_preview": text[:1600],
        "heading_candidates": _extract_heading_candidates(text),
        "review_status": "needs_review",
        "created_at": now,
        "updated_at": now,
    }


def extract_seeds(materials: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    lesson_note_seeds: list[dict[str, Any]] = []
    concept_seeds: list[dict[str, Any]] = []
    question_seeds: list[dict[str, Any]] = []
    extraction_errors: list[dict[str, Any]] = []

    for material in materials:
        material_type = material.get("material_type")
        if material_type not in {"lesson_note", "jokbo_summary", "jokbo_recall"}:
            continue

        path = Path(material.get("source_root", "")) / material.get("relative_path", "")
        if not path.exists():
            extraction_errors.append({
                "source_material_id": material.get("material_id"),
                "source_name": material.get("original_name"),
                "error": f"file not found: {path}",
            })
            continue

        try:
            if path.suffix.lower() == ".pdf":
                pages = _extract_pdf_pages(path)
                toc = _parse_toc_from_pages(pages)
                if material_type in {"lesson_note", "jokbo_summary"} and toc:
                    for item in toc:
                        section_text = _slice_pages(pages, item["start_page"], item.get("end_page"))
                        lesson_seed = _make_lesson_seed(material, item, section_text)
                        lesson_note_seeds.append(lesson_seed)
                        if material_type == "jokbo_summary":
                            concept_seeds.append({**lesson_seed, "seed_type": "concept_seed"})
                    continue
                text = clean_text("\n\n".join(pages))
            else:
                text = extract_text(path)
        except Exception as exc:
            extraction_errors.append({
                "source_material_id": material.get("material_id"),
                "source_name": material.get("original_name"),
                "error": str(exc),
            })
            continue

        seed = _make_whole_material_seed(material, text)
        if material_type == "jokbo_recall":
            question_seeds.append(seed)
        elif material_type == "lesson_note":
            lesson_note_seeds.append({**seed, "seed_type": "lesson_note"})
        else:
            concept_seeds.append(seed)

    return {
        "lesson_note_seeds": lesson_note_seeds,
        "concept_seeds": concept_seeds,
        "question_seeds": question_seeds,
        "extraction_errors": extraction_errors,
    }


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract curriculum seeds from jokbo materials.")
    parser.add_argument("--materials", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--batch-slug", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    materials = _load_materials(args.materials)
    seeds = extract_seeds(materials)
    batch_slug = args.batch_slug or args.materials.parent.name
    target_dir = args.output_dir / batch_slug
    summary = {
        "materials": str(args.materials),
        "output_dir": str(target_dir),
        "written": not args.dry_run,
        "lesson_note_seed_count": len(seeds["lesson_note_seeds"]),
        "concept_seed_count": len(seeds["concept_seeds"]),
        "question_seed_count": len(seeds["question_seeds"]),
        "extraction_error_count": len(seeds["extraction_errors"]),
    }

    if not args.dry_run:
        _write_json(target_dir / "lesson_note_seeds.draft.json", seeds["lesson_note_seeds"])
        _write_json(target_dir / "concept_seeds.draft.json", seeds["concept_seeds"])
        _write_json(target_dir / "question_seeds.draft.json", seeds["question_seeds"])
        _write_json(target_dir / "extraction_errors.json", seeds["extraction_errors"])
        _write_json(target_dir / "summary.json", summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if seeds["lesson_note_seeds"][:3]:
        print("\npreview:")
        for seed in seeds["lesson_note_seeds"][:3]:
            print(json.dumps({
                "seed_type": seed["seed_type"],
                "course": seed.get("course"),
                "unit": seed.get("unit"),
                "professor": seed.get("professor"),
                "start_page": seed.get("start_page"),
                "end_page": seed.get("end_page"),
            }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"jokbo_seed_extractor error: {exc}", file=sys.stderr)
        raise SystemExit(1)
