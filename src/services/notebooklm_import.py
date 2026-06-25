from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.generate_lecture_questions import PIPELINE_VERSION, slugify

from src.services.lecture_studio import archive_question_set, load_question_set, timestamp_slug


QUESTION_FIELDS = ("problem", "stem", "question", "question_stem", "vignette", "prompt", "문항", "질문")
STIMULUS_FIELDS = ("stimulus", "case", "scenario", "제시자료", "증례")
OPTION_FIELDS = ("options", "choices", "answer_choices", "선지", "보기")
EXPLANATION_FIELDS = ("explanation", "rationale", "answer_explanation", "해설", "풀이")
REFERENCE_FIELDS = ("reference_notes", "references", "sources", "citations", "source_notes", "출처", "근거")


def _first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_json_from_text(raw_text: str) -> Any:
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("NotebookLM 결과가 비어 있습니다.")
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("NotebookLM 결과는 JSON 형식으로 붙여넣어야 합니다.") from exc


def _extract_question_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("questions", "items", "question_set", "draft_questions"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if any(key in payload for key in QUESTION_FIELDS):
            return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _normalize_options(item: dict[str, Any]) -> list[str]:
    raw_options: Any = None
    for key in OPTION_FIELDS:
        if key in item:
            raw_options = item.get(key)
            break

    if isinstance(raw_options, dict):
        def sort_key(value: str) -> tuple[int, str]:
            label = str(value).strip().lower()
            if label.isdigit():
                return (int(label), label)
            if label in {"a", "b", "c", "d", "e"}:
                return ("abcde".index(label) + 1, label)
            return (99, label)

        options = [str(raw_options[key]).strip() for key in sorted(raw_options, key=sort_key)]
    elif isinstance(raw_options, list):
        options = []
        for option in raw_options:
            if isinstance(option, dict):
                text = option.get("text") or option.get("content") or option.get("label")
                options.append(str(text or "").strip())
            else:
                options.append(str(option or "").strip())
    else:
        options = []

    return [option for option in options if option][:5]


def _normalize_answer(value: Any) -> int | None:
    if isinstance(value, int):
        return value if 1 <= value <= 5 else None
    text = str(value or "").strip()
    if not text:
        return None
    circled = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}
    for marker, number in circled.items():
        if marker in text:
            return number
    letter = text.upper().strip(". ")
    if letter in {"A", "B", "C", "D", "E"}:
        return "ABCDE".index(letter) + 1
    match = re.search(r"[1-5]", text)
    return int(match.group(0)) if match else None


def _normalize_references(item: dict[str, Any], source_name: str) -> list[dict[str, Any]]:
    raw_refs: Any = None
    for key in REFERENCE_FIELDS:
        if key in item:
            raw_refs = item.get(key)
            break

    notes: list[dict[str, Any]] = []
    if isinstance(raw_refs, list):
        for raw_ref in raw_refs:
            if isinstance(raw_ref, dict):
                source = str(raw_ref.get("source") or raw_ref.get("title") or raw_ref.get("name") or source_name).strip()
                basis = str(raw_ref.get("basis") or raw_ref.get("quote") or raw_ref.get("note") or raw_ref.get("summary") or "").strip()
            else:
                source = source_name
                basis = str(raw_ref or "").strip()
            if source or basis:
                notes.append(
                    {
                        "ref_no": len(notes) + 1,
                        "source": source or source_name,
                        "basis": basis or "NotebookLM 출처 요약. 원문 확인 필요",
                        "verification_status": "notebooklm_source_review_needed",
                    }
                )
    elif isinstance(raw_refs, str) and raw_refs.strip():
        notes.append(
            {
                "ref_no": 1,
                "source": source_name,
                "basis": raw_refs.strip(),
                "verification_status": "notebooklm_source_review_needed",
            }
        )

    if not notes:
        notes.append(
            {
                "ref_no": 1,
                "source": source_name,
                "basis": "NotebookLM에 업로드된 자료 기반 초안. 원문 출처 확인 필요",
                "verification_status": "notebooklm_source_review_needed",
            }
        )
    return notes


def _normalize_labels(item: dict[str, Any]) -> dict[str, Any]:
    labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
    taxonomy = item.get("taxonomy") if isinstance(item.get("taxonomy"), dict) else {}
    merged = {**taxonomy, **labels}
    for key in ("department", "topic", "subtopic", "learning_objective", "assessment_domain", "professor"):
        if key in item and item.get(key):
            merged[key] = item.get(key)
    return merged


def _normalize_notebooklm_question(
    item: dict[str, Any],
    *,
    index: int,
    source_name: str,
    subject: str,
    unit: str,
) -> dict[str, Any]:
    stimulus = _first_text(item, STIMULUS_FIELDS)
    question = _first_text(item, QUESTION_FIELDS)
    problem = "\n\n".join(part for part in (stimulus, question) if part).strip()
    options = _normalize_options(item)
    answer = _normalize_answer(item.get("answer") or item.get("correct_answer") or item.get("정답"))
    explanation = _first_text(item, EXPLANATION_FIELDS)
    labels = _normalize_labels(item)

    review_reasons = ["notebooklm_import_review_needed"]
    if not problem:
        review_reasons.append("missing_problem")
    if len(options) < 2:
        review_reasons.append("missing_options")
    if answer is None:
        review_reasons.append("missing_answer")
    if not explanation:
        review_reasons.append("missing_explanation")

    reference_notes = _normalize_references(item, source_name)
    if explanation and "참고문헌:" not in explanation:
        ref_lines = "\n".join(
            f"{note['ref_no']}. {note['source']}: {note.get('basis') or '근거 요약 검수 필요'}"
            for note in reference_notes
        )
        explanation = f"{explanation}\n\n참고문헌:\n{ref_lines}".strip()

    return {
        "question_id": str(item.get("question_id") or f"NLM_{slugify(Path(source_name).stem)}_Q{index:03d}"),
        "source_name": source_name,
        "source_type": "notebooklm_import",
        "subject": str(item.get("subject") or subject or "미분류").strip() or "미분류",
        "unit": str(item.get("unit") or unit or "미분류").strip() or "미분류",
        "problem": problem or "문항 본문 확인 필요",
        "options": options,
        "answer": answer or 1,
        "explanation": explanation or "해설 확인 필요",
        "evidence_refs": reference_notes,
        "evidence_tier": "notebooklm_source_review",
        "reference_notes": reference_notes,
        "difficulty": str(item.get("difficulty") or "").strip(),
        "question_type": str(item.get("question_type") or item.get("type") or "notebooklm_draft").strip(),
        "cognitive_level": str(item.get("cognitive_level") or "").strip(),
        "labels": labels,
        "review_status": "draft",
        "needs_review": True,
        "review_reasons": sorted(set(review_reasons)),
        "generation_mode": "notebooklm_import",
        "pipeline_version": PIPELINE_VERSION,
    }


def import_notebooklm_question_set(payload: dict[str, Any]) -> dict[str, Any]:
    source_name = str(payload.get("source_name") or payload.get("title") or "NotebookLM import").strip()
    subject = str(payload.get("subject") or "미분류").strip() or "미분류"
    unit = str(payload.get("unit") or "미분류").strip() or "미분류"
    raw_payload = payload.get("questions") or payload.get("items")
    if raw_payload is None:
        raw_payload = _extract_json_from_text(str(payload.get("raw_text") or ""))

    items = _extract_question_items(raw_payload)
    if not items:
        raise ValueError("가져올 문항을 찾지 못했습니다. questions 배열이 있는 JSON으로 붙여넣어 주세요.")

    records = [
        _normalize_notebooklm_question(
            item,
            index=index,
            source_name=source_name,
            subject=subject,
            unit=unit,
        )
        for index, item in enumerate(items[:50], 1)
    ]
    source_slug = f"notebooklm_{timestamp_slug()}_{slugify(source_name)[:40]}"
    archive_question_set(
        source_slug,
        {
            "source_name": source_name,
            "subject": subject,
            "unit": unit,
            "provider": "notebooklm",
            "model": "notebooklm",
            "question_type": "notebooklm_import",
            "reference_policy": "notebooklm_uploaded_sources",
            "generation_mode": "notebooklm_import",
            "notebook_url": str(payload.get("notebook_url") or "").strip(),
            "raw_question_count": len(items),
        },
        records,
    )
    return load_question_set(source_slug)
