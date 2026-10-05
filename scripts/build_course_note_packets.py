#!/usr/bin/env python3
"""Build deterministic study-note source packets from mixed PDF/PPT/PPTX lectures.

The script never edits the source lectures. It groups original and annotated
variants, converts presentation copies to PDF for extraction, renders a small
set of candidate visual pages, and records provenance for downstream note
authoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


SUPPORTED_SUFFIXES = {".pdf", ".ppt", ".pptx"}
ANNOTATION_SUFFIX_RE = re.compile(r"(?:[_\- ]?필기)$", re.IGNORECASE)
PERIOD_RANGE_RE = re.compile(r"(?P<a>\d+)\s*(?P<sep>[,\-])\s*(?P<b>\d+)\s*교시")
PERIOD_SINGLE_RE = re.compile(r"(?P<a>\d+)\s*교시")
DATE_RE = re.compile(r"^(?P<date>20\d{6})")

VISUAL_KEYWORDS = (
    "smear",
    "morphology",
    "pathology",
    "histology",
    "microscopy",
    "peripheral blood",
    "bone marrow",
    "pbs",
    "bma",
    "bmb",
    "flow cytometry",
    "karyotype",
    "fish",
    "algorithm",
    "staging",
    "classification",
    "ct ",
    "pet",
    "mri",
    "image",
    "figure",
    "도말",
    "골수",
    "조직",
    "현미경",
    "병리",
    "사진",
    "그림",
    "분류",
    "알고리즘",
    "진단",
    "감별",
)

LOW_VALUE_KEYWORDS = (
    "references",
    "bibliography",
    "thank you",
    "감사합니다",
    "목차",
    "contents",
)


@dataclass(frozen=True)
class LectureGroup:
    key: str
    files: tuple[Path, ...]
    date: str
    periods: tuple[int, ...]
    title: str


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_group_key(path: Path) -> str:
    return ANNOTATION_SUFFIX_RE.sub("", nfc(path.stem)).strip()


def parse_periods(stem: str) -> tuple[int, ...]:
    match = PERIOD_RANGE_RE.search(stem)
    if match:
        a = int(match.group("a"))
        b = int(match.group("b"))
        if match.group("sep") == "-" and a <= b and b - a <= 4:
            return tuple(range(a, b + 1))
        return tuple(dict.fromkeys((a, b)))
    match = PERIOD_SINGLE_RE.search(stem)
    return (int(match.group("a")),) if match else tuple()


def parse_title(stem: str) -> str:
    title = re.sub(r"^20\d{6}_", "", stem)
    title = re.sub(r"^\d+\s*(?:[,\-]\s*\d+)?\s*교시[_\- ]*", "", title)
    return title.strip(" _-")


def discover_groups(source_root: Path) -> list[LectureGroup]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if path.name.startswith("~$"):
            continue
        grouped[clean_group_key(path)].append(path)

    groups: list[LectureGroup] = []
    for key, paths in sorted(grouped.items()):
        date_match = DATE_RE.match(key)
        groups.append(
            LectureGroup(
                key=key,
                files=tuple(sorted(paths, key=lambda p: nfc(p.name))),
                date=date_match.group("date") if date_match else "undated",
                periods=parse_periods(key),
                title=parse_title(key),
            )
        )
    return groups


def run_soffice_conversion(source: Path, destination_pdf: Path, scratch_dir: Path) -> None:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    copied = scratch_dir / f"{destination_pdf.stem}{source.suffix.lower()}"
    shutil.copy2(source, copied)
    result = subprocess.run(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(scratch_dir),
            str(copied),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    produced = copied.with_suffix(".pdf")
    if result.returncode != 0 or not produced.exists():
        raise RuntimeError(
            f"presentation conversion failed for {source}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    destination_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(produced), destination_pdf)
    copied.unlink(missing_ok=True)


def page_visual_metrics(page: fitz.Page, text: str) -> dict[str, Any]:
    page_area = max(page.rect.width * page.rect.height, 1.0)
    image_area = 0.0
    try:
        for block in page.get_text("dict", flags=fitz.TEXT_PRESERVE_IMAGES).get("blocks", []):
            if block.get("type") != 1:
                continue
            bbox = fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
            image_area += max(0.0, bbox.width) * max(0.0, bbox.height)
    except Exception:
        image_area = 0.0
    image_ratio = min(1.0, image_area / page_area)
    lowered = text.lower()
    keyword_hits = sum(1 for keyword in VISUAL_KEYWORDS if keyword in lowered)
    low_value_hits = sum(1 for keyword in LOW_VALUE_KEYWORDS if keyword in lowered)
    char_count = len(text.strip())
    readable_bonus = 0.7 if 20 <= char_count <= 1800 else 0.2 if char_count else -0.5
    score = image_ratio * 6.0 + keyword_hits * 0.55 + readable_bonus - low_value_hits * 2.5
    return {
        "image_area_ratio": round(image_ratio, 4),
        "visual_keyword_hits": keyword_hits,
        "low_value_hits": low_value_hits,
        "text_chars": char_count,
        "score": round(score, 4),
    }


def extract_pdf(pdf_path: Path) -> tuple[list[dict[str, Any]], str]:
    pages: list[dict[str, Any]] = []
    sections: list[str] = []
    with fitz.open(pdf_path) as document:
        for index, page in enumerate(document):
            text = page.get_text("text", sort=True).strip()
            metrics = page_visual_metrics(page, text)
            text_hash = hashlib.sha256(re.sub(r"\s+", " ", text).encode("utf-8")).hexdigest()
            pages.append(
                {
                    "page_number": index + 1,
                    "text": text,
                    "text_sha256": text_hash,
                    **metrics,
                }
            )
            sections.append(f"\n===== PAGE {index + 1} =====\n{text}\n")
    return pages, "".join(sections)


def iter_shape_text(shape: Any) -> list[str]:
    texts: list[str] = []
    if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.GROUP:
        for child in shape.shapes:
            texts.extend(iter_shape_text(child))
        return texts
    if getattr(shape, "has_text_frame", False):
        value = shape.text_frame.text.strip()
        if value:
            texts.append(value)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            values = [cell.text.strip() for cell in row.cells]
            if any(values):
                texts.append(" | ".join(values))
    return texts


def extract_pptx(pptx_path: Path) -> tuple[list[dict[str, Any]], str]:
    presentation = Presentation(pptx_path)
    slide_area = max(float(presentation.slide_width * presentation.slide_height), 1.0)
    pages: list[dict[str, Any]] = []
    sections: list[str] = []
    for index, slide in enumerate(presentation.slides):
        text_parts: list[str] = []
        image_area = 0.0
        for shape in slide.shapes:
            text_parts.extend(iter_shape_text(shape))
            if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE:
                image_area += float(shape.width * shape.height)
        try:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                text_parts.append(f"[발표자 노트]\n{notes}")
        except Exception:
            pass
        text = "\n".join(dict.fromkeys(part for part in text_parts if part)).strip()
        lowered = text.lower()
        keyword_hits = sum(1 for keyword in VISUAL_KEYWORDS if keyword in lowered)
        low_value_hits = sum(1 for keyword in LOW_VALUE_KEYWORDS if keyword in lowered)
        image_ratio = min(1.0, image_area / slide_area)
        char_count = len(text)
        readable_bonus = 0.7 if 20 <= char_count <= 1800 else 0.2 if char_count else -0.5
        score = image_ratio * 6.0 + keyword_hits * 0.55 + readable_bonus - low_value_hits * 2.5
        text_hash = hashlib.sha256(re.sub(r"\s+", " ", text).encode("utf-8")).hexdigest()
        pages.append(
            {
                "page_number": index + 1,
                "text": text,
                "text_sha256": text_hash,
                "image_area_ratio": round(image_ratio, 4),
                "visual_keyword_hits": keyword_hits,
                "low_value_hits": low_value_hits,
                "text_chars": char_count,
                "score": round(score, 4),
            }
        )
        sections.append(f"\n===== SLIDE {index + 1} =====\n{text}\n")
    return pages, "".join(sections)


def choose_visual_candidates(
    source_records: list[dict[str, Any]],
    max_candidates: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source_index, record in enumerate(source_records):
        if not record.get("visual_eligible", False):
            continue
        annotation_bonus = 0.35 if record["is_annotated"] else 0.0
        pdf_bonus = 0.15 if record["source_suffix"] == ".pdf" else 0.0
        for page in record["pages"]:
            if page["page_number"] == 1 and len(record["pages"]) > 2:
                first_page_penalty = 1.5
            else:
                first_page_penalty = 0.0
            candidates.append(
                {
                    "source_index": source_index,
                    "source_name": record["source_name"],
                    "render_pdf": record["render_pdf"],
                    "page_number": page["page_number"],
                    "text_sha256": page["text_sha256"],
                    "text_preview": re.sub(r"\s+", " ", page["text"])[:220],
                    "score": round(page["score"] + annotation_bonus + pdf_bonus - first_page_penalty, 4),
                    "image_area_ratio": page["image_area_ratio"],
                    "visual_keyword_hits": page["visual_keyword_hits"],
                }
            )

    candidates.sort(key=lambda row: (-row["score"], row["source_index"], row["page_number"]))
    selected: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for candidate in candidates:
        text_hash = candidate["text_sha256"]
        if text_hash in seen_hashes and text_hash != hashlib.sha256(b"").hexdigest():
            continue
        selected.append(candidate)
        seen_hashes.add(text_hash)
        if len(selected) >= max_candidates:
            break
    return selected


def render_visual(candidate: dict[str, Any], destination: Path) -> None:
    with fitz.open(candidate["render_pdf"]) as document:
        page = document[candidate["page_number"] - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.55, 1.55), alpha=False)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(destination, jpg_quality=88)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_packets(source_root: Path, output_root: Path, build_root: Path) -> dict[str, Any]:
    groups = discover_groups(source_root)
    output_root.mkdir(parents=True, exist_ok=True)
    assets_root = output_root / "assets"
    notes_root = output_root / "notes"
    packets_root = build_root / "groups"
    converted_root = build_root / "converted"
    packets_root.mkdir(parents=True, exist_ok=True)
    notes_root.mkdir(parents=True, exist_ok=True)

    inventory_groups: list[dict[str, Any]] = []
    for group_number, group in enumerate(groups, start=1):
        period_label = "-".join(str(period) for period in group.periods) or "NA"
        group_id = f"L{group_number:02d}_{group.date}_P{period_label}"
        group_packet_dir = packets_root / group_id
        group_packet_dir.mkdir(parents=True, exist_ok=True)
        source_records: list[dict[str, Any]] = []
        packet_sections = [
            f"# SOURCE PACKET: {group_id}",
            "",
            f"- 강의: {group.title}",
            f"- 날짜: {group.date}",
            f"- 교시: {', '.join(map(str, group.periods)) or '미상'}",
            f"- 합친 원본: {len(group.files)}개",
            "",
        ]

        for source_index, source in enumerate(group.files, start=1):
            is_annotated = bool(ANNOTATION_SUFFIX_RE.search(nfc(source.stem)))
            if source.suffix.lower() == ".pdf":
                render_pdf = source
                pages, extracted_text = extract_pdf(render_pdf)
                visual_eligible = True
                extraction_note = "PDF text and page visuals extracted"
            elif source.suffix.lower() == ".pptx":
                render_pdf = None
                pages, extracted_text = extract_pptx(source)
                visual_eligible = False
                extraction_note = "PPTX text, tables, and speaker notes extracted; paired PDF used for visuals"
            else:
                paired_pdfs = [path for path in group.files if path.suffix.lower() == ".pdf"]
                if paired_pdfs:
                    render_pdf = None
                    pages = []
                    extracted_text = "[구형 PPT는 동일 강의 PDF를 기준으로 읽었습니다.]"
                    visual_eligible = False
                    extraction_note = "legacy PPT paired with PDF; PDF used for content and visuals"
                else:
                    render_pdf = converted_root / f"{group_id}_S{source_index:02d}.pdf"
                    if not render_pdf.exists():
                        run_soffice_conversion(
                            source,
                            render_pdf,
                            converted_root / "soffice_tmp" / f"{group_id}_S{source_index:02d}",
                        )
                    pages, extracted_text = extract_pdf(render_pdf)
                    visual_eligible = True
                    extraction_note = "legacy PPT converted to PDF for extraction"
            source_record = {
                "source_name": nfc(source.name),
                "source_path": str(source),
                "source_relative_path": str(source.relative_to(source_root)),
                "source_suffix": source.suffix.lower(),
                "source_size": source.stat().st_size,
                "source_sha256": sha256_file(source),
                "is_annotated": is_annotated,
                "render_pdf": str(render_pdf) if render_pdf else None,
                "visual_eligible": visual_eligible,
                "extraction_note": extraction_note,
                "page_count": len(pages),
                "text_chars": sum(page["text_chars"] for page in pages),
                "pages": pages,
            }
            source_records.append(source_record)
            packet_sections.extend(
                [
                    f"## SOURCE {source_index}: {nfc(source.name)}",
                    "",
                    f"- pages/slides: {len(pages)}",
                    f"- annotated: {str(is_annotated).lower()}",
                    f"- sha256: `{source_record['source_sha256']}`",
                    "",
                    extracted_text,
                    "",
                ]
            )

        visual_count = 8 if len(group.periods) >= 2 or any(
            keyword in group.title.lower()
            for keyword in ("조직", "pathol", "pbs", "bm", "lymphoma", "종양")
        ) else 6
        selected_visuals = choose_visual_candidates(source_records, visual_count)
        visual_records: list[dict[str, Any]] = []
        asset_dir = assets_root / group_id
        for visual_index, candidate in enumerate(selected_visuals, start=1):
            destination = asset_dir / f"visual_{visual_index:02d}_p{candidate['page_number']:03d}.jpg"
            render_visual(candidate, destination)
            visual_records.append(
                {
                    **{key: value for key, value in candidate.items() if key != "render_pdf"},
                    "asset_path": str(destination),
                    "asset_relative_to_output": str(destination.relative_to(output_root)),
                }
            )

        packet_path = group_packet_dir / "source_packet.md"
        packet_path.write_text("\n".join(packet_sections), encoding="utf-8")
        context_payload = {
            "group_id": group_id,
            "group_key": group.key,
            "date": group.date,
            "periods": list(group.periods),
            "expected_question_count": max(1, len(group.periods)),
            "title": group.title,
            "source_packet_path": str(packet_path),
            "sources": [
                {key: value for key, value in record.items() if key not in {"pages", "render_pdf"}}
                for record in source_records
            ],
            "visual_candidates": visual_records,
        }
        write_json(group_packet_dir / "context.json", context_payload)
        write_json(group_packet_dir / "visual_candidates.json", visual_records)

        note_filename = f"{group_id}_{group.title}.md".replace("/", "-")
        context_payload["note_path"] = str(notes_root / note_filename)
        inventory_groups.append(context_payload)

    inventory = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(source_root),
        "output_root": str(output_root),
        "build_root": str(build_root),
        "source_file_count": sum(len(group.files) for group in groups),
        "lecture_group_count": len(groups),
        "groups": inventory_groups,
    }
    write_json(build_root / "inventory.json", inventory)
    write_json(output_root / "source_manifest.json", inventory)
    return inventory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory = build_packets(
        args.source_root.expanduser().resolve(),
        args.output_root.expanduser().resolve(),
        args.build_root.expanduser().resolve(),
    )
    print(
        "course_note_packets_built "
        f"files={inventory['source_file_count']} groups={inventory['lecture_group_count']} "
        f"output={inventory['output_root']}"
    )


if __name__ == "__main__":
    main()
