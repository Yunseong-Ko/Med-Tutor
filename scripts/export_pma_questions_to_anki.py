#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import genanki


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / "data_private" / "course_exams" / "extracted"
DEFAULT_MEDIA_ROOT = ROOT / "data_private" / "course_exams" / "media"
DEFAULT_OUTPUT_DIR = ROOT / "data_private" / "anki_exports"

MODEL_ID = 3406252025


def stable_int_id(value: str, *, digits: int = 10) -> int:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return int(digest[:digits], 16)


def text_only(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def sanitize_tag(value: Any) -> str:
    tag = re.sub(r"\s+", "_", str(value or "").strip())
    tag = re.sub(r"[^\w:.-]+", "_", tag)
    return tag.strip("_")


def html_text(value: Any) -> str:
    return html.escape(str(value or "")).replace("\n", "<br>")


def parse_answers(question: dict[str, Any]) -> list[str]:
    generated = question.get("generated_answer")
    if isinstance(generated, list) and generated:
        return [str(item).strip() for item in generated if str(item).strip()]

    answer = question.get("answer")
    if isinstance(answer, list):
        return [str(item).strip() for item in answer if str(item).strip()]

    raw = str(answer or "").strip()
    if not raw:
        return []

    circled = "①②③④⑤⑥⑦⑧⑨"
    found = [str(circled.index(ch) + 1) for ch in raw if ch in circled]
    if found:
        return found

    numbers = re.findall(r"\d+", raw)
    return numbers or [raw]


def choice_map(question: dict[str, Any]) -> dict[str, str]:
    choices = question.get("choices")
    if isinstance(choices, dict):
        return {str(key): text_only(value) for key, value in choices.items()}
    if isinstance(choices, list):
        return {str(index): text_only(value) for index, value in enumerate(choices, start=1)}
    return {}


def pma_files(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("PMA_*.json"))


def pma_model() -> genanki.Model:
    return genanki.Model(
        MODEL_ID,
        "P:accine PMA Question",
        fields=[
            {"name": "Source"},
            {"name": "Question"},
            {"name": "Stimulus"},
            {"name": "Media"},
            {"name": "Choices"},
            {"name": "Answer"},
            {"name": "KeyInfo"},
            {"name": "Explanation"},
            {"name": "ChoiceExplanations"},
            {"name": "LearningPoints"},
        ],
        templates=[
            {
                "name": "PMA Question",
                "qfmt": """
<section class="source">{{Source}}</section>
<section class="question">{{Question}}</section>
{{#Stimulus}}<section class="stimulus">{{Stimulus}}</section>{{/Stimulus}}
{{#Media}}<section class="media">{{Media}}</section>{{/Media}}
<section class="choices">{{Choices}}</section>
""",
                "afmt": """
{{FrontSide}}
<hr id="answer">
<section class="answer">{{Answer}}</section>
{{#KeyInfo}}<section class="panel key-info">{{KeyInfo}}</section>{{/KeyInfo}}
{{#Explanation}}<section class="panel explanation">{{Explanation}}</section>{{/Explanation}}
{{#ChoiceExplanations}}<section class="panel choice-explanations">{{ChoiceExplanations}}</section>{{/ChoiceExplanations}}
{{#LearningPoints}}<section class="panel learning-points">{{LearningPoints}}</section>{{/LearningPoints}}
""",
            }
        ],
        css="""
.card {
  font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard", sans-serif;
  font-size: 18px;
  line-height: 1.55;
  color: #172033;
  background: #f8fafc;
  text-align: left;
}
.source {
  display: inline-block;
  margin-bottom: 12px;
  padding: 6px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  color: #475569;
  font-size: 13px;
  font-weight: 700;
  background: white;
}
.question {
  font-size: 20px;
  font-weight: 700;
  line-height: 1.65;
  margin: 8px 0 14px;
}
.stimulus {
  margin: 12px 0;
  padding: 12px 14px;
  border-left: 5px solid #0f766e;
  border-radius: 12px;
  background: #eefdf8;
  white-space: pre-wrap;
}
.media {
  margin: 14px 0;
}
.media img {
  display: block;
  max-width: 100%;
  max-height: 520px;
  object-fit: contain;
  margin: 10px auto;
  border: 1px solid #dbe4ef;
  border-radius: 14px;
  background: white;
}
.choices {
  margin-top: 14px;
}
.choice {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  margin: 8px 0;
  border: 1px solid #dbe4ef;
  border-radius: 12px;
  background: white;
}
.choice-number {
  min-width: 28px;
  height: 28px;
  border: 1px solid #b6c7da;
  border-radius: 999px;
  color: #003366;
  font-weight: 800;
  text-align: center;
  line-height: 28px;
}
.answer {
  margin: 16px 0;
  padding: 14px 16px;
  border-left: 5px solid #0f766e;
  border-radius: 12px;
  background: #dcfce7;
  font-size: 19px;
  font-weight: 800;
  color: #064e3b;
}
.panel {
  margin: 14px 0;
  padding: 14px 16px;
  border: 1px solid #dbe4ef;
  border-radius: 14px;
  background: white;
}
.panel-title {
  display: block;
  margin-bottom: 8px;
  color: #0f766e;
  font-size: 14px;
  font-weight: 900;
}
.choice-exp {
  padding: 10px 0;
  border-top: 1px solid #edf2f7;
}
.choice-exp:first-of-type {
  border-top: 0;
}
.choice-exp.correct {
  color: #065f46;
}
.choice-exp.wrong {
  color: #991b1b;
}
ul {
  padding-left: 20px;
}
""",
    )


def render_source(exam: dict[str, Any], question: dict[str, Any]) -> str:
    parts = [
        text_only(exam.get("source_file") or question.get("source_file")),
        text_only(question.get("period_label") or exam.get("period_label")),
        f"Q{question.get('question_number')}",
    ]
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    category = text_only(labels.get("course_name") or labels.get("major_category") or question.get("course_name"))
    if category:
        parts.append(category)
    return " · ".join(part for part in parts if part)


def render_choices(question: dict[str, Any]) -> str:
    choices = choice_map(question)
    if not choices:
        return ""
    rows: list[str] = []
    for key in sorted(choices, key=lambda item: int(item) if item.isdigit() else item):
        rows.append(
            f'<div class="choice"><span class="choice-number">{html_text(key)}</span>'
            f"<span>{html_text(choices[key])}</span></div>"
        )
    return "\n".join(rows)


def render_answer(question: dict[str, Any]) -> str:
    answers = parse_answers(question)
    choices = choice_map(question)
    if not answers:
        return "정답 정보 없음"
    rendered = []
    for answer in answers:
        label = choices.get(answer)
        rendered.append(f"{answer}. {label}" if label else answer)
    return "정답: " + " / ".join(html_text(item) for item in rendered)


def render_key_info(question: dict[str, Any]) -> str:
    key_info = question.get("key_info") if isinstance(question.get("key_info"), dict) else {}
    chunks: list[str] = []
    clues = key_info.get("important_clues")
    if isinstance(clues, list) and clues:
        chunks.append(
            '<span class="panel-title">핵심 단서</span><ul>'
            + "".join(f"<li>{html_text(clue)}</li>" for clue in clues if text_only(clue))
            + "</ul>"
        )
    summary = text_only(key_info.get("summary"))
    if summary:
        chunks.append(f'<span class="panel-title">상황 요약</span>{html_text(summary)}')
    core = text_only(key_info.get("core_explanation"))
    if core:
        chunks.append(f'<span class="panel-title">핵심 개념</span>{html_text(core)}')
    return "<br>".join(chunks)


def render_choice_explanations(question: dict[str, Any]) -> str:
    explanations = question.get("choice_explanations")
    if not isinstance(explanations, dict):
        return ""
    answers = set(parse_answers(question))
    chunks = ['<span class="panel-title">선지별 해설</span>']
    for key in sorted(explanations, key=lambda item: int(item) if str(item).isdigit() else str(item)):
        item = explanations.get(key)
        if not isinstance(item, dict):
            continue
        choice_text = text_only(item.get("choice_text") or choice_map(question).get(str(key)))
        explanation = text_only(item.get("explanation") or item.get("rationale"))
        if not explanation:
            continue
        cls = "correct" if str(key) in answers or item.get("is_correct") else "wrong"
        chunks.append(
            f'<div class="choice-exp {cls}"><b>{html_text(key)}. {html_text(choice_text)}</b><br>'
            f"{html_text(explanation)}</div>"
        )
    return "\n".join(chunks) if len(chunks) > 1 else ""


def render_learning_points(question: dict[str, Any]) -> str:
    points = question.get("key_learning_points")
    if not isinstance(points, list) or not points:
        return ""
    return (
        '<span class="panel-title">가져갈 개념</span><ul>'
        + "".join(f"<li>{html_text(point)}</li>" for point in points if text_only(point))
        + "</ul>"
    )


def build_media_index(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assets = packet.get("media_assets") if isinstance(packet.get("media_assets"), list) else []
    index: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        for key in (asset.get("media_id"), asset.get("storage_id")):
            if key:
                index[str(key)] = asset
    return index


def source_media_paths(question: dict[str, Any], packet: dict[str, Any], media_root: Path) -> list[Path]:
    index = build_media_index(packet)
    refs = question.get("media", {}).get("media_refs") if isinstance(question.get("media"), dict) else []
    paths: list[Path] = []
    seen: set[Path] = set()

    def add_asset(asset: dict[str, Any] | None) -> None:
        if not asset:
            return
        raw = asset.get("file_path")
        rel = asset.get("relative_path")
        candidates = []
        if raw:
            candidates.append((ROOT / str(raw)).resolve())
            candidates.append(Path(str(raw)).resolve())
        if rel:
            candidates.append((media_root / str(rel)).resolve())
        for candidate in candidates:
            if candidate.exists() and candidate not in seen:
                seen.add(candidate)
                paths.append(candidate)
                return

    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            add_asset(index.get(str(ref.get("media_id") or "")) or index.get(str(ref.get("storage_id") or "")))

    if not paths:
        question_number = question.get("question_number")
        for asset in packet.get("media_assets") or []:
            linked = asset.get("linked_question_numbers") if isinstance(asset, dict) else None
            if isinstance(linked, list) and question_number in linked:
                add_asset(asset)
    return paths


def safe_media_name(source_exam: str, question_number: Any, index: int, source_path: Path) -> str:
    stem = sanitize_tag(source_exam) or "pma"
    q = f"Q{int(question_number):03d}" if str(question_number).isdigit() else f"Q{sanitize_tag(question_number)}"
    return f"{stem}_{q}_IMG{index:02d}{source_path.suffix.lower() or '.png'}"


def stage_question_media(
    question: dict[str, Any],
    packet: dict[str, Any],
    *,
    media_root: Path,
    media_cache_dir: Path,
) -> tuple[str, list[str]]:
    media_html: list[str] = []
    media_files: list[str] = []
    paths = source_media_paths(question, packet, media_root)
    for index, source_path in enumerate(paths, start=1):
        name = safe_media_name(
            str(question.get("source_exam") or packet.get("exam", {}).get("source_exam") or "pma"),
            question.get("question_number") or index,
            index,
            source_path,
        )
        target = media_cache_dir / name
        if not target.exists() or target.stat().st_size != source_path.stat().st_size:
            shutil.copy2(source_path, target)
        media_files.append(str(target))
        media_html.append(f'<img src="{html.escape(name)}" alt="PMA image {index}">')
    return "\n".join(media_html), media_files


def note_tags(exam: dict[str, Any], question: dict[str, Any]) -> list[str]:
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    raw_tags = [
        "paccine",
        "pma",
        exam.get("source_exam"),
        question.get("period_label") or exam.get("period_label"),
        labels.get("course_name") or question.get("course_name"),
        labels.get("major_category"),
        labels.get("topic"),
        labels.get("subtopic"),
        labels.get("assessment_domain"),
        labels.get("question_type") or labels.get("question_type_labeled"),
    ]
    raw_tags.extend(labels.get("concept_tags") or [])
    return [tag for tag in (sanitize_tag(item) for item in raw_tags) if tag]


def build_note(
    model: genanki.Model,
    packet: dict[str, Any],
    question: dict[str, Any],
    *,
    media_root: Path,
    media_cache_dir: Path,
    guid_scope: str,
) -> tuple[genanki.Note, list[str]]:
    exam = packet.get("exam") if isinstance(packet.get("exam"), dict) else {}
    media_html, media_files = stage_question_media(
        question,
        packet,
        media_root=media_root,
        media_cache_dir=media_cache_dir,
    )
    explanation = text_only(question.get("answer_rationale") or question.get("explanation") or "")
    # guid는 (deck scope, 문항ID) 조합으로 만든다. 같은 deck을 재생성(내용 수정)할 때는
    # Anki가 "같은 노트 업데이트"로 처리해야 하므로 scope+question_id 조합을 고정한다.
    # scope를 넣지 않으면 서로 다른 배포본(예: 예전 통합 덱과 새 연도별 덱)의 동일 문항이
    # 같은 guid를 갖게 되어, 나중에 만든 덱을 임포트해도 Anki가 새 카드로 보여주지 않고
    # 기존 노트를 조용히 업데이트만 하는 문제가 생긴다.
    question_id = str(question.get("question_id") or stable_int_id(json.dumps(question, ensure_ascii=False)))
    guid = f"{guid_scope}::{question_id}"
    note = genanki.Note(
        model=model,
        fields=[
            html_text(render_source(exam, question)),
            html_text(question.get("stem")),
            html_text(question.get("stimulus")),
            media_html,
            render_choices(question),
            render_answer(question),
            render_key_info(question),
            html_text(explanation),
            render_choice_explanations(question),
            render_learning_points(question),
        ],
        tags=note_tags(exam, question),
        guid=guid,
    )
    return note, media_files


def build_deck(
    *,
    input_dir: Path,
    media_root: Path,
    output_dir: Path,
    deck_name: str,
    include_pattern: str,
    output_stem: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    media_cache_dir = output_dir / "pma_media_cache"
    media_cache_dir.mkdir(parents=True, exist_ok=True)

    files = [path for path in pma_files(input_dir) if re.search(include_pattern, path.name)]
    if not files:
        raise SystemExit(f"No PMA JSON files matched pattern: {include_pattern}")

    deck = genanki.Deck(stable_int_id(deck_name, digits=8), deck_name)
    model = pma_model()
    media_files: list[str] = []
    question_count = 0
    image_question_count = 0
    source_files: list[str] = []

    for path in files:
        packet = json.loads(path.read_text(encoding="utf-8"))
        source_files.append(path.name)
        questions = packet.get("questions") if isinstance(packet.get("questions"), list) else []
        for question in questions:
            if not isinstance(question, dict):
                continue
            note, note_media = build_note(
                model,
                packet,
                question,
                media_root=media_root,
                media_cache_dir=media_cache_dir,
                guid_scope=deck_name,
            )
            deck.add_note(note)
            media_files.extend(note_media)
            question_count += 1
            if note_media:
                image_question_count += 1

    package = genanki.Package(deck, media_files=sorted(set(media_files)))
    output_path = output_dir / f"{output_stem}.apkg"
    package.write_to_file(str(output_path))

    manifest = {
        "deck_name": deck_name,
        "output_path": str(output_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_files": source_files,
        "question_count": question_count,
        "media_file_count": len(set(media_files)),
        "image_question_count": image_question_count,
    }
    manifest_path = output_dir / f"{output_stem}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export current PMA questions to an Anki .apkg deck.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--media-root", type=Path, default=DEFAULT_MEDIA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--deck-name", default="P:accine::PMA::B턴")
    parser.add_argument(
        "--include-pattern",
        default=r"^PMA_(202206|202306|202511)_G3_B군_[12]교시\.json$",
        help="Regex for PMA JSON filenames to include.",
    )
    parser.add_argument(
        "--output-stem",
        default="paccine_pma_b_turn_questions",
        help="Output filename stem for the APKG and manifest.",
    )
    args = parser.parse_args()
    manifest = build_deck(
        input_dir=args.input_dir,
        media_root=args.media_root,
        output_dir=args.output_dir,
        deck_name=args.deck_name,
        include_pattern=args.include_pattern,
        output_stem=args.output_stem,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
