#!/usr/bin/env python3
"""
Add choice-level explanations to an extracted course-exam JSON file.

This is the safer production path for student-facing review:
1. Extract HWP/PDF exam questions into JSON.
2. Run this enrichment step once.
3. Review/edit choice_explanations in the stored JSON.
4. Serve the reviewed JSON to the student practice UI.

The script does not print original question text to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

# Ensure the project root is on sys.path so the script can be run directly:
#   python scripts/enrich_course_exam_choice_explanations.py <args>
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.services.choice_explanations import (
    build_choice_explanation_draft,
    is_negative_question,
    normalize_answer_key,
    normalize_choice_entries,
)


AUTHORING_HARNESS_DOC = "docs/Choice_Explanation_Authoring_Harness_20260620.md"
AUTHORING_HARNESS_RULES = (
    "선지별 해설은 답 번호 비교가 아니라 개념 학습 단위로 작성한다. "
    "negative 문항에서는 statement_status만 true_statement/false_statement로 표시하고, "
    "해설 본문에는 판정 문장 없이 개념 설명만 작성한다. "
    "Anki 카드는 자연스러운 개념 문장에서 핵심 단어만 cloze 처리한다."
)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as temp_file:
        json.dump(payload, temp_file, ensure_ascii=False, indent=2)
        temp_name = temp_file.name
    Path(temp_name).replace(path)


def enrich_record(
    record: dict[str, Any],
    *,
    course_id: str | None,
    use_rag: bool,
    only_missing: bool,
    include_anki: bool,
) -> dict[str, Any]:
    questions = record.get("questions") if isinstance(record.get("questions"), list) else []
    enriched_count = 0
    needs_review_count = 0
    anki_count = 0

    for question in questions:
        if not isinstance(question, dict):
            continue
        if only_missing and question.get("choice_explanations"):
            continue
        if not question.get("choices") or not question.get("answer"):
            continue

        if not only_missing:
            question.pop("choice_explanations", None)
            if include_anki:
                question.pop("anki_cards", None)

        draft = build_choice_explanation_draft(question, course_id=course_id, use_rag=use_rag)
        rows = draft.get("choice_explanations", {})
        if draft.get("question_understanding"):
            question["question_understanding"] = draft["question_understanding"]
        question["choice_explanations"] = rows
        if include_anki and (not only_missing or not question.get("anki_cards")):
            cards = build_question_anki_cards(question, rows, course_id=course_id, use_rag=use_rag)
            if cards:
                question["anki_cards"] = cards
                anki_count += len(cards)
        question.setdefault("enrichment", {})
        question["enrichment"]["choice_explanations"] = {
            "status": "draft",
            "rag_course_id": draft.get("rag_course_id"),
            "needs_review_count": draft.get("needs_review_count", 0),
            "policy": draft.get("draft_policy"),
        }
        if include_anki:
            question["enrichment"]["anki_cards"] = {
                "status": "draft",
                "count": len(question.get("anki_cards") or []),
                "policy": "정답 근거와 RAG 근거에서 자연스러운 개념 문장 기반 cloze 후보를 생성합니다. 학생 배포 전 검수 필요.",
            }
        enriched_count += 1
        needs_review_count += int(draft.get("needs_review_count", 0))

    record.setdefault("exam", {})
    record["exam"]["choice_explanation_enrichment"] = {
        "status": "drafted",
        "question_count": enriched_count,
        "needs_review_count": needs_review_count,
        "anki_card_count": anki_count,
        "course_id": course_id,
        "use_rag": use_rag,
        "authoring_harness": AUTHORING_HARNESS_DOC,
        "authoring_rules": AUTHORING_HARNESS_RULES,
        "workflow": "question_understanding -> choice_explanations -> anki_cards",
    }
    return record


def build_question_anki_query(question: dict[str, Any], choice_rows: dict[str, Any]) -> str:
    answer = normalize_answer_key(question.get("answer"))
    choices = normalize_choice_entries(question)
    correct_choice = choices.get(answer, "")
    correct_row = choice_rows.get(answer) if isinstance(choice_rows, dict) else {}
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    concept_tags = labels.get("concept_tags") if isinstance(labels.get("concept_tags"), list) else []
    values = [
        labels.get("topic"),
        labels.get("subtopic"),
        labels.get("question_type"),
        *concept_tags,
        question.get("stem"),
        question.get("stimulus"),
        correct_choice,
        correct_row.get("rationale") if isinstance(correct_row, dict) else "",
        question.get("explanation"),
    ]
    return " ".join(str(value or "") for value in values).replace("\n", " ").strip()[:520]


ANKI_BAD_PHRASES = (
    "정답은",
    "이 문항은",
    "지문에서",
    "근거 DB",
    "저장된",
    "검토",
    "부족",
    "교수",
    "학습부원",
    "출출",
    "出",
    "曰",
    "PNU internal source",
)


ANKI_STOP_TERMS = {
    "해설",
    "정답",
    "선지",
    "문항",
    "환자",
    "설명",
    "다음",
    "가장",
    "대한",
    "것은",
    "있는",
    "없는",
    "관련",
    "개념",
    "확인",
    "근거",
    "기준",
    "보기",
    "정상",
    "정상적",
    "정상적인",
    "반드시",
    "지문",
    "직접",
    "핵심",
    "단서",
    "연결",
    "가장",
    "많은",
    "형태",
    "시작된다",
}


def clean_anki_sentence(text: str) -> str:
    sentence = str(text or "").replace("\n", " ")
    sentence = sentence.replace("해설:", "").replace("해설：", "")
    sentence = " ".join(sentence.split()).strip(" -:;,.")
    return sentence


def is_good_anki_sentence(sentence: str) -> bool:
    text = clean_anki_sentence(sentence)
    if len(text) < 18 or len(text) > 260:
        return False
    if any(phrase in text for phrase in ANKI_BAD_PHRASES):
        return False
    if text.count("(") != text.count(")"):
        return False
    if text.startswith("고준경 교수님"):
        return False
    return True


def split_anki_sentences(text: str) -> list[str]:
    import re as _re
    cleaned = clean_anki_sentence(text)
    if not cleaned:
        return []
    return [
        clean_anki_sentence(part)
        for part in _re.split(r"(?<=[.!?。！？다])\s+|[.;]\s+", cleaned)
        if is_good_anki_sentence(part)
    ]


def anki_cloze_terms(sentence: str, *, question: dict[str, Any], correct_choice: str) -> list[str]:
    import re as _re
    terms: list[str] = []
    for value in (correct_choice,):
        value = str(value or "").strip()
        if 3 <= len(value) <= 60 and value in sentence:
            terms.append(value)
    for match in _re.finditer(r"\d+\s*(?:세|개월|년|일|주|시간)\s*(?:초반|전후|이내|이상|이하)?|[A-Za-z][A-Za-z0-9+\-/]{3,}(?:\s+[A-Za-z][A-Za-z0-9+\-/]{3,}){0,2}|[가-힣]{2,}", sentence):
        term = match.group(0).strip("()[]{}.,;:")
        term = _re.sub(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과)$", "", term)
        if len(term) < 3:
            continue
        if term.lower() in ANKI_STOP_TERMS or term in ANKI_STOP_TERMS:
            continue
        if len(term) <= 3 and not _re.search(r"\d", term):
            continue
        terms.append(term)
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    concept_tags = labels.get("concept_tags") if isinstance(labels.get("concept_tags"), list) else []
    for tag in concept_tags:
        tag = str(tag or "").strip()
        if 3 <= len(tag) <= 40 and tag in sentence:
            terms.insert(0, tag)
    return list(dict.fromkeys(terms))[:2]


def make_anki_text(sentence: str, terms: list[str]) -> str:
    import re as _re
    output = clean_anki_sentence(sentence)
    cloze_index = 1
    for term in terms:
        if cloze_index > 2:
            break
        pattern = _re.compile(_re.escape(term), flags=_re.IGNORECASE)
        if not pattern.search(output):
            continue
        output = pattern.sub(lambda match: f"{{{{c{cloze_index}::{match.group(0)}}}}}", output, count=1)
        cloze_index += 1
    return output


def fallback_anki_cards(question: dict[str, Any], choice_rows: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    answer = normalize_answer_key(question.get("answer"))
    choices = normalize_choice_entries(question)
    correct_choice = choices.get(answer, "정답 선지")
    correct_row = choice_rows.get(answer) if isinstance(choice_rows, dict) else {}
    rationale = ""
    evidence_sentences: list[str] = []
    if isinstance(correct_row, dict):
        rationale = str(correct_row.get("rationale") or "").strip()
        for evidence in correct_row.get("evidence") or []:
            if isinstance(evidence, dict):
                evidence_sentences.extend(split_anki_sentences(evidence.get("snippet") or ""))
    explanation = str(question.get("explanation") or "").strip()
    negative = is_negative_question(question)
    candidate_sentences: list[tuple[str, str]] = []
    for sentence in split_anki_sentences(explanation):
        candidate_sentences.append((sentence, "원문 해설"))
    if not negative:
        for sentence in split_anki_sentences(rationale):
            candidate_sentences.append((sentence, "정답 선지 해설"))
    for sentence in evidence_sentences:
        candidate_sentences.append((sentence, "근거 DB"))

    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sentence, source in candidate_sentences:
        if len(cards) >= limit:
            break
        plain = clean_anki_sentence(sentence)
        if not is_good_anki_sentence(plain) or plain in seen:
            continue
        terms = anki_cloze_terms(plain, question=question, correct_choice=correct_choice if not negative else "")
        anki_text = make_anki_text(plain, terms)
        if "{{c" not in anki_text:
            continue
        seen.add(plain)
        cards.append(
            {
                "card_id": f"{question.get('question_id', 'q')}_anki_{len(cards) + 1}",
                "plain_text": plain,
                "anki_text": anki_text,
                "source": source,
                "tags": [str(question.get("source_exam") or "course_exam"), "choice_explanation", "cloze_draft"],
                "needs_review": True,
            }
        )
    return cards


def build_question_anki_cards(
    question: dict[str, Any],
    choice_rows: dict[str, Any],
    *,
    course_id: str | None,
    use_rag: bool,
    limit: int = 4,
) -> list[dict[str, Any]]:
    return fallback_anki_cards(question, choice_rows, limit=limit)


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich extracted course-exam JSON with choice-level explanations.")
    parser.add_argument("json_path", type=Path, help="Path to extracted course-exam JSON.")
    parser.add_argument("--output", type=Path, help="Output JSON path. Defaults to overwriting the input.")
    parser.add_argument("--course-id", default=None, help="RAG course id, e.g. hematology_oncology.")
    parser.add_argument("--no-rag", action="store_true", help="Disable local RAG evidence lookup.")
    parser.add_argument("--no-anki", action="store_true", help="Do not create anki_cards candidates.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing choice_explanations.")
    args = parser.parse_args()

    source_path = args.json_path.expanduser().resolve()
    record = json.loads(source_path.read_text(encoding="utf-8"))
    output_path = (args.output.expanduser().resolve() if args.output else source_path)

    enriched = enrich_record(
        record,
        course_id=args.course_id,
        use_rag=not args.no_rag,
        only_missing=not args.overwrite,
        include_anki=not args.no_anki,
    )
    write_json_atomic(output_path, enriched)

    summary = enriched.get("exam", {}).get("choice_explanation_enrichment", {})
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output_path),
                "question_count": summary.get("question_count", 0),
                "needs_review_count": summary.get("needs_review_count", 0),
                "anki_card_count": summary.get("anki_card_count", 0),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
