#!/usr/bin/env python3
"""
Course exam HWP -> question-level JSON extractor
Version: 0.1.0

This script is intended for locally available medical school course-exam
materials such as "정답 및 해설.hwp" files. It writes extracted records under
data_private by default. Stdout never prints original question text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


PARSER_VERSION = "0.4.0"
CIRCLE_CHARS = "①②③④⑤"
CIRCLE_TO_STR = {char: str(idx + 1) for idx, char in enumerate(CIRCLE_CHARS)}

QUESTION_START_RE = re.compile(r"(?m)^\s*(\d{1,3})\s*[.)]\s+(?=\S)")
CHOICE_MARK_RE = re.compile(r"([①②③④⑤])")
CHOICE_LINE_RE = re.compile(r"(?m)^\s*([①②③④⑤])\s*")
ANSWER_RES = [
    re.compile(r"(?:정답|답)\s*[:：]?\s*([①②③④⑤1-5])"),
    re.compile(r"([①②③④⑤1-5])\s*(?:정답|답)\b"),
]
IMAGE_KW_RE = re.compile(
    r"(그림|사진|영상|X선|X-ray|CXR|CT|MRI|초음파|US|심전도|ECG|EEG|뇌파|"
    r"병리|조직|슬라이드|검체|혈액도말|도표|그래프|표)",
    re.IGNORECASE,
)
IMAGE_EXTS = {".bmp", ".png", ".jpg", ".jpeg", ".gif", ".wmf"}


COURSE_ALIASES = [
    ("신경 및 특수감각기학", "neuro_special_senses"),
    ("인간.사회.의료", "human_society_medicine"),
    ("인간사회의료", "human_society_medicine"),
    ("정신의학", "psychiatry"),
]

QUESTION_TYPE_RULES = [
    ("image_interpretation", IMAGE_KW_RE),
    ("ethics_policy", re.compile(r"(의료윤리|법|제도|정책|보험|인권|동의|설명|사회|역학|보건)", re.I)),
    ("clinical_reasoning", re.compile(r"(환자|증례|내원|주소|검사|진단|치료|처치|약물|증상)", re.I)),
    ("basic_concept", re.compile(r"(정의|기전|원리|특징|분류|기준|개념)", re.I)),
]


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", value)
    value = value.strip("_")
    return value[:120] or "course_exam"


def extract_hwp_text(path: Path) -> str:
    hwp5txt = shutil.which("hwp5txt")
    if not hwp5txt:
        raise RuntimeError("hwp5txt not found. Install pyhwp first.")
    result = subprocess.run(
        [hwp5txt, str(path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "hwp5txt failed")
    if not result.stdout.strip():
        raise RuntimeError("hwp5txt returned empty text")
    return clean_text(result.stdout)


def run_hwp5_xml(path: Path) -> str:
    result = subprocess.run(
        ["hwp5proc", "xml", str(path)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "hwp5proc xml failed")
    return result.stdout


def unpack_hwp_media(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        result = subprocess.run(
            ["hwp5proc", "unpack", str(path), str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "hwp5proc unpack failed")
        bin_dir = tmp_path / "BinData"
        if not bin_dir.exists():
            return
        for source in sorted(bin_dir.iterdir()):
            if source.is_file() and source.suffix.lower() in IMAGE_EXTS:
                shutil.copy2(source, destination / source.name)


def picture_id_to_storage_id(bindata_id: str | int) -> str:
    try:
        return f"BIN{int(bindata_id):04X}"
    except Exception:
        return str(bindata_id)


def parse_hwp_xml_flow(path: Path) -> tuple[dict[str, dict], list[dict]]:
    xml_text = run_hwp5_xml(path)
    root = ET.fromstring(xml_text)

    bindata_map: dict[str, dict] = {}
    for idx, node in enumerate(root.findall(".//BinData"), start=1):
        embedding = node.find("BinDataEmbedding")
        if embedding is None:
            continue
        storage_id = embedding.attrib.get("storage-id") or picture_id_to_storage_id(idx)
        bindata_map[str(idx)] = {
            "bindata_id": str(idx),
            "storage_id": storage_id,
            "ext": embedding.attrib.get("ext"),
            "compression": node.attrib.get("compression"),
        }

    paragraphs: list[dict] = []
    for para_idx, paragraph in enumerate(root.findall(".//BodyText//Paragraph"), start=1):
        texts = []
        for text_node in paragraph.findall(".//Text"):
            if text_node.text:
                texts.append(text_node.text)
        picture_ids = [
            node.attrib.get("bindata-id")
            for node in paragraph.findall(".//PictureInfo")
            if node.attrib.get("bindata-id")
        ]
        paragraphs.append(
            {
                "paragraph_index": para_idx,
                "text": clean_text("".join(texts)),
                "picture_bindata_ids": picture_ids,
            }
        )
    return bindata_map, paragraphs


def build_question_media_map(
    path: Path,
    *,
    objective_count: int | None = None,
) -> tuple[dict[int, list[str]], dict[str, dict], list[dict]]:
    try:
        bindata_map, paragraphs = parse_hwp_xml_flow(path)
    except Exception:
        return {}, {}, []

    current_question: int | None = None
    expected_question = 1
    objective_section_active = True
    question_media: dict[int, list[str]] = {}
    media_positions: list[dict] = []

    for paragraph in paragraphs:
        text = paragraph["text"]
        if "주관식" in text:
            current_question = None
            if objective_count is not None and expected_question > objective_count:
                objective_section_active = False

        start_match = re.match(r"^\s*(\d{1,3})\s*[.)]\s+", text)
        if start_match:
            number = int(start_match.group(1))
            if objective_section_active and number == expected_question:
                current_question = number
                expected_question += 1
                if objective_count is not None and expected_question > objective_count + 1:
                    objective_section_active = False
            elif objective_count is not None and expected_question > objective_count:
                objective_section_active = False
                current_question = None

        for bindata_id in paragraph["picture_bindata_ids"]:
            storage_id = bindata_map.get(str(bindata_id), {}).get(
                "storage_id",
                picture_id_to_storage_id(bindata_id),
            )
            if current_question is not None and (
                objective_count is None or current_question <= objective_count
            ):
                question_media.setdefault(current_question, []).append(storage_id)
            media_positions.append(
                {
                    "question_number": current_question,
                    "paragraph_index": paragraph["paragraph_index"],
                    "bindata_id": str(bindata_id),
                    "storage_id": storage_id,
                    "context_hint": text[:80],
                }
            )
    return question_media, bindata_map, media_positions


def parse_filename(path: Path) -> dict:
    name = unicodedata.normalize("NFC", path.name)
    grade = None
    m_grade = re.search(r"\((\d+)학년\)", name)
    if m_grade:
        grade = int(m_grade.group(1))

    exam_date = None
    m_date = re.search(r"\((20\d{2})-(\d{1,2})-(\d{1,2})\)", name)
    if m_date:
        year, month, day = m_date.groups()
        exam_date = f"{year}-{int(month):02d}-{int(day):02d}"

    course_name = "unknown"
    course_id = "unknown"
    for alias, cid in COURSE_ALIASES:
        if alias in name:
            course_name = alias
            course_id = cid
            break
    if course_id == "unknown" and (("임상" in name and "종합평가" in name) or "임종평" in name):
        course_name = "임상의학종합평가"
        course_id = "clinical_comprehensive_exam"

    round_label = None
    m_round = re.search(r"(\d+)차\s*과정시험", name)
    if m_round:
        round_label = f"{m_round.group(1)}차"
    elif "종합평가" in name:
        m_round = re.search(r"(\d+)차", name)
        if m_round:
            round_label = f"{m_round.group(1)}차"
    elif "과정시험" in name:
        round_label = "과정시험"

    period_label = None
    m_period = re.search(r"(\d+)\s*교시", name)
    if m_period:
        period_label = f"{m_period.group(1)}교시"

    objective_count = None
    subjective_count = None
    m_counts = re.search(r"객\s*(\d+)(?:[_ ,]+주\s*(\d+))?", name)
    if m_counts:
        objective_count = int(m_counts.group(1))
        if m_counts.group(2):
            subjective_count = int(m_counts.group(2))

    source_exam = "_".join(
        part
        for part in [
            "COURSE",
            str(grade) if grade else "X",
            exam_date.replace("-", "") if exam_date else "DATE",
            course_id.upper(),
            round_label or "EXAM",
            period_label,
        ]
        if part
    )

    return {
        "source_exam": source_exam,
        "source_file": name,
        "grade": grade,
        "exam_date": exam_date,
        "course_name": course_name,
        "course_id": course_id,
        "round_label": round_label,
        "period_label": period_label,
        "objective_count_from_filename": objective_count,
        "subjective_count_from_filename": subjective_count,
    }


def candidate_has_choices(text: str, start: int, window: int = 5000) -> bool:
    excerpt = text[start : start + window]
    return len(CHOICE_MARK_RE.findall(excerpt)) >= 3


def select_question_starts(text: str) -> list[re.Match[str]]:
    matches = list(QUESTION_START_RE.finditer(text))
    selected: list[re.Match[str]] = []
    expected = 1
    for match in matches:
        number = int(match.group(1))
        if number != expected:
            continue
        if not candidate_has_choices(text, match.end()):
            continue
        selected.append(match)
        expected += 1
    return selected


def split_question_blocks(text: str) -> list[tuple[int, str]]:
    starts = select_question_starts(text)
    blocks: list[tuple[int, str]] = []
    for idx, match in enumerate(starts):
        start = match.start()
        end = starts[idx + 1].start() if idx + 1 < len(starts) else len(text)
        blocks.append((int(match.group(1)), text[start:end].strip()))
    return blocks


def detect_question_type(text: str) -> str:
    for label, pattern in QUESTION_TYPE_RULES:
        if pattern.search(text):
            return label
    return "knowledge_recall"


def infer_cognitive_level(question_type: str) -> str:
    if question_type in {"clinical_reasoning", "image_interpretation"}:
        return "application"
    if question_type == "ethics_policy":
        return "interpretation"
    return "knowledge"


def extract_trailing_answer_marker(text: str) -> tuple[str, str | None]:
    text = clean_text(text)
    for pattern in ANSWER_RES:
        match = pattern.search(text)
        if match:
            value = match.group(1)
            answer = CIRCLE_TO_STR.get(value, value)
            return clean_text(pattern.sub("", text)), answer

    match = re.search(r"([①②③④⑤])\s*$", text)
    if match:
        answer = CIRCLE_TO_STR[match.group(1)]
        return clean_text(text[: match.start()]), answer
    return text, None


def strip_answer_markers(text: str) -> str:
    cleaned = text
    for pattern in ANSWER_RES:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"[①②③④⑤]\s*$", "", cleaned)
    return clean_text(cleaned)


def split_stem_and_stimulus(text_before_choices: str) -> tuple[str, str | None, str | None]:
    original_lines = [line.strip() for line in text_before_choices.splitlines() if line.strip()]

    # Common HWP layout:
    #   85. question stem? ④
    #   boxed stimulus/case text
    #   ① choice...
    # In text extraction, the box is usually just the next line before choices.
    for idx, line in enumerate(original_lines):
        stripped_line, line_answer = extract_trailing_answer_marker(line)
        if line_answer and idx + 1 < len(original_lines):
            stem = "\n".join(original_lines[:idx] + [stripped_line])
            stimulus = "\n".join(original_lines[idx + 1 :])
            return clean_text(stem), clean_text(stimulus), line_answer

    text_before_choices, answer_from_stem = extract_trailing_answer_marker(text_before_choices)
    if "제시 자료" not in text_before_choices:
        if len(original_lines) >= 2:
            first_line = original_lines[0]
            remaining = "\n".join(original_lines[1:])
            # Conservative fallback: only split when the first line already
            # reads like a complete question and the following line is long
            # enough to be a case/stimulus rather than a wrapped stem.
            if re.search(r"[?？]\s*$", first_line) and len(remaining) >= 20:
                return clean_text(first_line), clean_text(remaining), answer_from_stem
        return clean_text(text_before_choices), None, answer_from_stem

    marker_index = text_before_choices.find("제시 자료")
    before_marker = text_before_choices[:marker_index].strip()
    after_marker = text_before_choices[marker_index + len("제시 자료") :].strip()

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", before_marker) if p.strip()]
    if len(paragraphs) >= 2:
        lead_in = paragraphs[0]
        stimulus = "\n\n".join(paragraphs[1:])
    else:
        lines = [line.strip() for line in before_marker.splitlines() if line.strip()]
        if len(lines) >= 2:
            lead_in = lines[0]
            stimulus = "\n".join(lines[1:])
        else:
            lead_in = before_marker
            stimulus = None

    if after_marker:
        stimulus = f"{stimulus or ''}\n{after_marker}".strip()
    return clean_text(lead_in), clean_text(stimulus) if stimulus else None, answer_from_stem


def looks_like_choice_continuation(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    if re.match(r"^[,.;:)\]}>〉」』]", line):
        return True
    if re.match(r"^(및|또는|그리고|이나|거나|으로|에서|의|가|를|을)\b", line):
        return True
    return False


def parse_choice_lines(lines: list[str]) -> tuple[dict[str, str], str | None, list[str]]:
    choices: dict[str, str] = {}
    explanation_lines: list[str] = []
    review_reasons: list[str] = []
    current_key: str | None = None
    current_parts: list[str] = []
    explanation_started = False

    def flush_current() -> None:
        nonlocal current_key, current_parts
        if current_key is not None:
            value = clean_text(" ".join(part for part in current_parts if part.strip()))
            value = re.sub(r"^(해설|풀이|정답|답)\s*[:：]?\s*", "", value).strip()
            choices[current_key] = value
        current_key = None
        current_parts = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        match = CHOICE_LINE_RE.match(line)
        if match and not explanation_started:
            flush_current()
            current_key = CIRCLE_TO_STR[match.group(1)]
            current_parts = [line[match.end() :].strip()]
            continue

        if explanation_started:
            explanation_lines.append(line)
            continue

        if current_key == "5" and current_parts:
            if looks_like_choice_continuation(line):
                current_parts.append(line)
            else:
                flush_current()
                explanation_started = True
                explanation_lines.append(line)
            continue

        if current_key is not None:
            current_parts.append(line)
        else:
            explanation_started = True
            explanation_lines.append(line)

    flush_current()
    explanation = clean_text("\n".join(explanation_lines)) if explanation_lines else None
    if explanation:
        review_reasons.append("explanation_inferred_after_choices")
    return choices, explanation, review_reasons


def strip_standalone_answer_line(lines: list[str]) -> tuple[list[str], str | None]:
    filtered: list[str] = []
    answer: str | None = None
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        match = re.fullmatch(r"([①②③④⑤1-5])\s*(?:정답|답)?", line)
        if match and answer is None:
            next_line = ""
            for candidate in lines[idx + 1 :]:
                if candidate.strip():
                    next_line = candidate.strip()
                    break
            # PDF exports sometimes put the answer marker on its own line
            # between the stem and the first choice.
            if CHOICE_LINE_RE.match(next_line):
                value = match.group(1)
                answer = CIRCLE_TO_STR.get(value, value)
                continue
        filtered.append(raw_line)
    return filtered, answer


def parse_question_parts(block: str) -> tuple[str, str | None, dict[str, str], str | None, str | None, list[str]]:
    block = re.sub(r"^\s*\d{1,3}\s*[.)]\s+", "", block).strip()
    lines, standalone_answer = strip_standalone_answer_line(block.splitlines())
    first_choice_idx = None
    for idx, line in enumerate(lines):
        if CHOICE_LINE_RE.match(line.strip()):
            first_choice_idx = idx
            break

    if first_choice_idx is None:
        stem, stimulus, answer_from_stem = split_stem_and_stimulus(block)
        return stem, stimulus, {}, standalone_answer or answer_from_stem, None, []

    before_choices = "\n".join(lines[:first_choice_idx])
    choice_and_after_lines = lines[first_choice_idx:]
    stem, stimulus, answer_from_stem = split_stem_and_stimulus(before_choices)
    choices, explanation, review_reasons = parse_choice_lines(choice_and_after_lines)
    answer = standalone_answer or answer_from_stem or parse_answer(block)
    return stem, stimulus, choices, answer, explanation, review_reasons


def parse_answer(block: str) -> str | None:
    for pattern in ANSWER_RES:
        match = pattern.search(block)
        if match:
            value = match.group(1)
            return CIRCLE_TO_STR.get(value, value)
    return None


def build_record(
    meta: dict,
    question_number: int,
    block: str,
    media_refs: list[dict] | None = None,
) -> dict:
    stem, stimulus, choices, answer, explanation, part_review_reasons = parse_question_parts(block)
    question_type = detect_question_type(block)
    media_refs = media_refs or []
    has_image = bool(IMAGE_KW_RE.search(block)) or bool(media_refs)
    extraction_notes: list[str] = list(part_review_reasons)
    review_reasons: list[str] = []

    if len(choices) < 4:
        review_reasons.append("choices_under_4")
    if not stem:
        review_reasons.append("empty_stem")
    if answer is None:
        review_reasons.append("answer_not_extracted")
    if has_image:
        review_reasons.append("image_or_data_reference_needs_asset_link")

    question_id = f"{meta['source_exam']}_Q{question_number:03d}"
    return {
        "question_id": question_id,
        "source_exam": meta["source_exam"],
        "source_file": meta["source_file"],
        "exam_date": meta["exam_date"],
        "grade": meta["grade"],
        "course_id": meta["course_id"],
        "course_name": meta["course_name"],
        "round_label": meta["round_label"],
        "period_label": meta.get("period_label"),
        "question_number": question_number,
        "stem": stem,
        "stimulus": stimulus,
        "choices": choices,
        "answer": answer,
        "explanation": explanation,
        "raw_text": block,
        "labels": {
            "unit_id": None,
            "learning_objective": None,
            "concept_tags": [],
            "question_type": question_type,
            "cognitive_level": infer_cognitive_level(question_type),
            "difficulty": None,
            "style_family": None,
        },
        "performance": {
            "item_accuracy": None,
            "cohort_accuracy": None,
            "discrimination_index": None,
            "objection_count": None,
        },
        "media": {
            "has_image_or_data_reference": has_image,
            "media_refs": media_refs,
            "asset_policy": "link_extracted_or_uploaded_media_after_review",
        },
        "extraction_notes": extraction_notes,
        "review_status": "imported",
        "needs_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "parser_version": PARSER_VERSION,
    }


def extract_file(path: Path, *, media_root: Path | None = None) -> dict:
    meta = parse_filename(path)
    text = extract_hwp_text(path)
    blocks = split_question_blocks(text)
    question_media_map, bindata_map, media_positions = build_question_media_map(
        path,
        objective_count=meta.get("objective_count_from_filename"),
    )

    media_assets: list[dict] = []
    if media_root is not None:
        exam_media_dir = media_root / slugify(meta["source_exam"])
        try:
            unpack_hwp_media(path, exam_media_dir)
        except Exception:
            exam_media_dir.mkdir(parents=True, exist_ok=True)

        for bindata_id, info in sorted(bindata_map.items(), key=lambda item: int(item[0])):
            storage_id = info["storage_id"]
            matches = sorted(exam_media_dir.glob(f"{storage_id}.*"))
            file_path = matches[0] if matches else None
            media_assets.append(
                {
                    "media_id": f"{meta['source_exam']}_{storage_id}",
                    "source_exam": meta["source_exam"],
                    "source_file": meta["source_file"],
                    "bindata_id": bindata_id,
                    "storage_id": storage_id,
                    "ext": info.get("ext"),
                    "compression": info.get("compression"),
                    "file_path": str(file_path) if file_path else None,
                    "relative_path": str(file_path.relative_to(media_root)) if file_path else None,
                    "linked_question_numbers": [
                        qn for qn, refs in question_media_map.items() if storage_id in refs
                    ],
                    "modality": None,
                    "caption": None,
                    "deidentified": None,
                    "approved_for_student_use": False,
                    "needs_review": True,
                }
            )

    media_asset_by_storage = {asset["storage_id"]: asset for asset in media_assets}
    questions = []
    for number, block in blocks:
        media_refs = []
        for storage_id in question_media_map.get(number, []):
            asset = media_asset_by_storage.get(storage_id)
            media_refs.append(
                {
                    "media_id": asset["media_id"] if asset else f"{meta['source_exam']}_{storage_id}",
                    "storage_id": storage_id,
                    "match_method": "hwp_xml_paragraph_flow",
                    "match_confidence": 0.75,
                    "needs_review": True,
                }
            )
        questions.append(build_record(meta, number, block, media_refs=media_refs))

    return {
        "exam": {
            **meta,
            "imported_at": datetime.now().isoformat(timespec="seconds"),
            "parser_version": PARSER_VERSION,
            "extracted_question_count": len(questions),
            "media_asset_count": len(media_assets),
            "media_linked_question_count": len([q for q in questions if q["media"]["media_refs"]]),
        },
        "media_assets": media_assets,
        "media_positions": media_positions,
        "questions": questions,
    }


def safe_sample(record: dict, sample_size: int) -> dict:
    questions = []
    for question in record["questions"][:sample_size]:
        questions.append(
            {
                "question_id": question["question_id"],
                "question_number": question["question_number"],
                "course_id": question["course_id"],
                "choices_count": len(question["choices"]),
                "has_answer": question["answer"] is not None,
                "has_stimulus": bool(question.get("stimulus")),
                "has_explanation": bool(question.get("explanation")),
                "media_refs_count": len(question.get("media", {}).get("media_refs", [])),
                "question_type": question["labels"]["question_type"],
                "cognitive_level": question["labels"]["cognitive_level"],
                "needs_review": question["needs_review"],
                "review_reasons": question["review_reasons"],
            }
        )
    return {"exam": record["exam"], "sample_questions": questions}


def render_question_markdown(question: dict) -> str:
    lines: list[str] = []
    qn = question["question_number"]
    status = "검수 필요" if question.get("needs_review") else "구조화 완료"
    lines.append(f"## {qn}. {status}")
    lines.append("")
    lines.append(f"- question_id: `{question['question_id']}`")
    lines.append(f"- answer: `{question.get('answer') or '미확인'}`")
    lines.append(f"- question_type: `{question['labels']['question_type']}`")
    lines.append(f"- cognitive_level: `{question['labels']['cognitive_level']}`")
    lines.append(f"- has_stimulus: `{bool(question.get('stimulus'))}`")
    lines.append(f"- has_explanation: `{bool(question.get('explanation'))}`")
    lines.append(f"- has_image_or_data_reference: `{question['media']['has_image_or_data_reference']}`")
    if question.get("media", {}).get("media_refs"):
        lines.append("- media_refs:")
        for ref in question["media"]["media_refs"]:
            lines.append(f"  - `{ref['media_id']}` / confidence `{ref['match_confidence']}`")
    if question.get("review_reasons"):
        lines.append(f"- review_reasons: `{', '.join(question['review_reasons'])}`")
    if question.get("extraction_notes"):
        lines.append(f"- extraction_notes: `{', '.join(question['extraction_notes'])}`")
    lines.append("")
    lines.append("### 문항 지문")
    lines.append("")
    lines.append(question.get("stem") or "_미추출_")
    lines.append("")
    if question.get("stimulus"):
        lines.append("### 제시 자료")
        lines.append("")
        lines.append("> " + str(question["stimulus"]).replace("\n", "\n> "))
        lines.append("")
    if question.get("media", {}).get("media_refs"):
        lines.append("### 이미지/자료 파일")
        lines.append("")
        for ref in question["media"]["media_refs"]:
            lines.append(f"- `{ref['media_id']}`: HWP 본문 흐름 기준 문항 연결 후보입니다. 검수가 필요합니다.")
        lines.append("")
    lines.append("### 문항 선지")
    lines.append("")
    choices = question.get("choices") or {}
    for key in ["1", "2", "3", "4", "5"]:
        if key in choices:
            lines.append(f"{key}. {choices[key]}")
    if not choices:
        lines.append("_미추출_")
    lines.append("")
    if question.get("explanation"):
        lines.append("### 해설")
        lines.append("")
        lines.append(str(question["explanation"]))
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def render_markdown(record: dict) -> str:
    exam = record["exam"]
    questions = record["questions"]
    summary = {
        "question_count": len(questions),
        "expected_objective_count": exam.get("objective_count_from_filename"),
        "with_answer_count": sum(1 for q in questions if q.get("answer")),
        "with_stimulus_count": sum(1 for q in questions if q.get("stimulus")),
        "with_explanation_count": sum(1 for q in questions if q.get("explanation")),
        "needs_review_count": sum(1 for q in questions if q.get("needs_review")),
        "media_asset_count": len(record.get("media_assets", [])),
        "media_linked_question_count": sum(1 for q in questions if q.get("media", {}).get("media_refs")),
    }

    lines = [
        f"# {exam.get('course_name')} {exam.get('round_label') or ''} 문항 구조화 검수본".strip(),
        "",
        "## 시험 정보",
        "",
        f"- source_exam: `{exam['source_exam']}`",
        f"- source_file: `{exam['source_file']}`",
        f"- exam_date: `{exam.get('exam_date') or 'unknown'}`",
        f"- grade: `{exam.get('grade') or 'unknown'}`",
        f"- parser_version: `{exam['parser_version']}`",
        "",
        "## 추출 요약",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## 미디어 처리 원칙",
            "",
            "- HWP/PDF 안의 이미지, 표, 영상 캡처는 문항 본문에 직접 섞지 않고 `media_refs`로 연결합니다.",
            "- 1차 파서는 이미지 여부를 키워드/문맥으로 표시하고, 실제 이미지 파일은 별도 `media/` 폴더와 manifest로 관리합니다.",
            "- 학생 공개 전에는 교수/조교가 이미지 저작권, 개인정보, 공개 가능 여부를 검수합니다.",
            "",
            "## 문항",
            "",
        ]
    )
    for question in questions:
        lines.append(render_question_markdown(question))
    return "\n".join(lines)


def iter_input_files(values: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        path = Path(value).expanduser()
        if path.is_dir():
            paths.extend(sorted(path.glob("*.hwp")))
        elif path.is_file() and path.suffix.lower() == ".hwp":
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
    parser = argparse.ArgumentParser(description="Extract course-exam HWP files into local private JSON.")
    parser.add_argument("inputs", nargs="+", help="HWP file paths or directories")
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
    parser.add_argument("--dry-run", action="store_true", help="Parse but do not write JSON")
    args = parser.parse_args()

    files = iter_input_files(args.inputs)
    if not files:
        print("No .hwp files found.", file=sys.stderr)
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
        output_name = f"{slugify(record['exam']['source_exam'])}.json"
        output_path = output_dir / output_name
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
            }
        )
        if args.sample:
            print(json.dumps(safe_sample(record, args.sample), ensure_ascii=False, indent=2))

    print(json.dumps({"processed": len(files), "summaries": summaries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
