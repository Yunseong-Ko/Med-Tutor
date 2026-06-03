from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import genanki

from src.services.lecture_studio import (
    EXPORT_SET_DIR,
    IMAGE_DIR,
    MEDIA_ASSET_DIR,
    ensure_studio_dirs,
    load_question_set,
    write_json,
)


BASIC_MODEL_ID = 2764851021
CLOZE_MODEL_ID = 2764851022


def stable_int_id(value: str, *, digits: int = 10) -> int:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return int(digest[:digits], 16)


def sanitize_tag(value: str) -> str:
    tag = re.sub(r"\s+", "_", str(value or "").strip())
    tag = re.sub(r"[^\w:.-]+", "_", tag)
    return tag.strip("_")


def text_only(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def sentence_split(value: str) -> list[str]:
    text = text_only(value)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+|(?<=요\.)\s+", text)
    return [part.strip() for part in parts if part.strip()]


def question_answer_text(question: dict[str, Any]) -> str:
    answer = question.get("answer")
    options = question.get("options") if isinstance(question.get("options"), list) else []
    try:
        index = int(answer) - 1
    except (TypeError, ValueError):
        index = -1
    if 0 <= index < len(options):
        return text_only(options[index])
    return ""


def question_tags(packet: dict[str, Any], question: dict[str, Any]) -> list[str]:
    metadata = packet.get("metadata") if isinstance(packet.get("metadata"), dict) else {}
    raw_tags = [
        "paccine",
        "review::approved" if question.get("review_status") == "approved" else "review::draft",
        f"question::{question.get('question_id')}",
        f"subject::{question.get('subject') or metadata.get('subject')}",
        f"unit::{question.get('unit') or metadata.get('unit')}",
        f"type::{question.get('question_type') or metadata.get('question_type')}",
    ]
    if question.get("image_refs"):
        raw_tags.append("media::image")
    return [tag for tag in (sanitize_tag(item) for item in raw_tags) if tag]


def source_line(question: dict[str, Any]) -> str:
    refs = question.get("reference_notes") if isinstance(question.get("reference_notes"), list) else []
    sources = [text_only(ref.get("source")) for ref in refs[:3] if isinstance(ref, dict) and ref.get("source")]
    source = " / ".join(sources) if sources else text_only(question.get("source_name"))
    return f"Source question: {question.get('question_id') or '-'}<br>References: {source or '-'}"


def media_filename_from_ref(image_ref: dict[str, Any]) -> str:
    if image_ref.get("filename"):
        return Path(str(image_ref["filename"])).name
    url = str(image_ref.get("url") or "")
    if "/api/media/assets/" in url:
        return Path(unquote(url.rsplit("/", 1)[-1])).name
    if "/api/studio/images/" in url:
        return Path(unquote(url.rsplit("/", 1)[-1])).name
    return ""


def media_file_path(filename: str) -> Path | None:
    if not filename:
        return None
    candidate = (MEDIA_ASSET_DIR / Path(filename).name).resolve()
    if candidate.exists() and MEDIA_ASSET_DIR.resolve() in candidate.parents:
        return candidate
    studio_candidate = (IMAGE_DIR / Path(filename).name).resolve()
    if studio_candidate.exists() and IMAGE_DIR.resolve() in studio_candidate.parents:
        return studio_candidate
    return None


def build_flashcards_for_question(packet: dict[str, Any], question: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    qid = str(question.get("question_id") or stable_int_id(json.dumps(question, ensure_ascii=False)))
    pma = question.get("pma_solution") if isinstance(question.get("pma_solution"), dict) else {}
    high_yield = text_only(pma.get("high_yield_point") or "")
    correct_reason = text_only(pma.get("correct_reason") or "")
    trap = text_only(pma.get("trap") or "")
    answer_text = question_answer_text(question)
    tags = question_tags(packet, question)
    source = source_line(question)

    if answer_text:
        cards.append(
            {
                "card_id": f"{qid}_answer_cloze",
                "card_type": "cloze",
                "cloze_text": f"이 문항의 핵심 판단에서 가장 적절한 선택지는 {{{{c1::{answer_text}}}}}이다.",
                "extra": f"{correct_reason or high_yield}<br><br>{source}",
                "tags": tags + ["card::answer"],
                "media_filenames": [],
            }
        )

    for idx, sentence in enumerate(sentence_split(high_yield)[:2], start=1):
        if answer_text and answer_text in sentence:
            cloze_text = sentence.replace(answer_text, f"{{{{c1::{answer_text}}}}}", 1)
        else:
            cloze_text = f"High-yield point: {{{{c1::{sentence}}}}}"
        cards.append(
            {
                "card_id": f"{qid}_hy_{idx}",
                "card_type": "cloze",
                "cloze_text": cloze_text,
                "extra": f"{correct_reason or text_only(question.get('explanation'))}<br><br>{source}",
                "tags": tags + ["card::high_yield"],
                "media_filenames": [],
            }
        )

    if trap:
        cards.append(
            {
                "card_id": f"{qid}_trap",
                "card_type": "basic",
                "front": "이 문항에서 흔한 함정은?",
                "back": trap,
                "extra": source,
                "tags": tags + ["card::trap"],
                "media_filenames": [],
            }
        )

    image_refs = question.get("image_refs") if isinstance(question.get("image_refs"), list) else []
    for idx, image_ref in enumerate(image_refs[:2], start=1):
        if not isinstance(image_ref, dict):
            continue
        finding = text_only(image_ref.get("text_preview") or pma.get("reasoning_summary") or high_yield)
        filename = media_filename_from_ref(image_ref)
        image_html = f'<img src="{filename}"><br>' if filename else ""
        cards.append(
            {
                "card_id": f"{qid}_image_{idx}",
                "card_type": "basic",
                "front": f"{image_html}이 제시자료에서 확인해야 할 핵심 소견은?",
                "back": finding,
                "extra": source,
                "tags": tags + ["card::image_finding"],
                "media_filenames": [filename] if filename else [],
            }
        )

    return cards


def basic_model() -> genanki.Model:
    return genanki.Model(
        BASIC_MODEL_ID,
        "P:accine Basic",
        fields=[
            {"name": "Front"},
            {"name": "Back"},
            {"name": "Extra"},
        ],
        templates=[
            {
                "name": "Card 1",
                "qfmt": '<div class="front">{{Front}}</div>',
                "afmt": '{{FrontSide}}<hr id="answer"><div class="back">{{Back}}</div><div class="extra">{{Extra}}</div>',
            }
        ],
        css="""
.card { font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif; font-size: 20px; line-height: 1.45; color: #111827; }
img { max-width: 100%; border-radius: 12px; }
.front { font-weight: 700; }
.back { margin-top: 12px; }
.extra { margin-top: 18px; color: #64748b; font-size: 15px; }
""",
    )


def cloze_model() -> genanki.Model:
    return genanki.Model(
        CLOZE_MODEL_ID,
        "P:accine Cloze",
        fields=[
            {"name": "Text"},
            {"name": "Extra"},
        ],
        templates=[
            {
                "name": "Cloze",
                "qfmt": "{{cloze:Text}}",
                "afmt": '{{cloze:Text}}<hr id="answer"><div class="extra">{{Extra}}</div>',
            }
        ],
        css="""
.card { font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif; font-size: 20px; line-height: 1.45; color: #111827; }
.cloze { color: #0f766e; font-weight: 800; }
.extra { margin-top: 18px; color: #64748b; font-size: 15px; }
""",
        model_type=genanki.Model.CLOZE,
    )


def build_anki_export(
    set_id: str,
    *,
    deck_name: str | None = None,
    include_unapproved: bool = False,
) -> dict[str, Any]:
    ensure_studio_dirs()
    packet = load_question_set(set_id, include_summary=True)
    metadata = packet.get("metadata") if isinstance(packet.get("metadata"), dict) else {}
    questions = packet.get("questions") if isinstance(packet.get("questions"), list) else []
    selected_questions = [
        question
        for question in questions
        if include_unapproved or question.get("review_status") == "approved"
    ]
    if not selected_questions:
        raise ValueError("승인된 문항이 없습니다. 문항 확인 큐에서 승인 후 Anki export를 생성하세요.")

    subject = sanitize_tag(metadata.get("subject") or "General").replace("_", " ")
    unit = sanitize_tag(metadata.get("unit") or "Uncategorized").replace("_", " ")
    final_deck_name = deck_name or f"P:accine::PNU Medicine::PMA::{subject}::{unit}"
    deck = genanki.Deck(stable_int_id(final_deck_name, digits=8), final_deck_name)
    basic = basic_model()
    cloze = cloze_model()

    card_payloads: list[dict[str, Any]] = []
    media_files: list[str] = []
    for question in selected_questions:
        for card in build_flashcards_for_question(packet, question):
            card_payloads.append(card)
            tags = [sanitize_tag(tag) for tag in card.get("tags", []) if sanitize_tag(tag)]
            if card["card_type"] == "cloze":
                note = genanki.Note(
                    model=cloze,
                    fields=[card.get("cloze_text", ""), card.get("extra", "")],
                    tags=tags,
                    guid=card["card_id"],
                )
            else:
                note = genanki.Note(
                    model=basic,
                    fields=[card.get("front", ""), card.get("back", ""), card.get("extra", "")],
                    tags=tags,
                    guid=card["card_id"],
                )
            deck.add_note(note)
            for filename in card.get("media_filenames", []):
                path = media_file_path(str(filename))
                if path:
                    media_files.append(str(path))

    export_slug = f"{set_id}_anki"
    apkg_path = EXPORT_SET_DIR / f"{export_slug}.apkg"
    json_path = EXPORT_SET_DIR / f"{export_slug}.flashcards.json"
    package = genanki.Package(deck, media_files=sorted(set(media_files)))
    package.write_to_file(str(apkg_path))

    now = datetime.now(timezone.utc).isoformat()
    artifact = {
        "export_id": export_slug,
        "set_id": set_id,
        "deck_name": final_deck_name,
        "card_count": len(card_payloads),
        "question_count": len(selected_questions),
        "include_unapproved": include_unapproved,
        "file_path": str(apkg_path),
        "download_url": f"/api/exports/{apkg_path.name}",
        "flashcard_json_path": str(json_path),
        "created_at": now,
        "cards": card_payloads,
    }
    write_json(json_path, artifact)
    return {key: value for key, value in artifact.items() if key != "cards"}
