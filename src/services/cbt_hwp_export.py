from __future__ import annotations

import base64
import mimetypes
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from src.services.lecture_studio import (
    EXPORT_SET_DIR,
    IMAGE_DIR,
    MEDIA_ASSET_DIR,
    ensure_studio_dirs,
    load_question_set,
    write_json,
)


CIRCLED_NUMBERS = {
    "1": "①",
    "2": "②",
    "3": "③",
    "4": "④",
    "5": "⑤",
    "6": "⑥",
    "7": "⑦",
    "8": "⑧",
    "9": "⑨",
}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def block_text(value: Any) -> str:
    return str(value or "").strip()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣_.-]+", "_", str(value or "").strip())
    return slug.strip("._")[:90] or "question_set"


def choice_label(value: Any, fallback_index: int) -> str:
    raw = str(value or "").strip()
    if raw in CIRCLED_NUMBERS:
        return CIRCLED_NUMBERS[raw]
    if raw and raw[0] in CIRCLED_NUMBERS.values():
        return raw[0]
    return CIRCLED_NUMBERS.get(str(fallback_index), str(fallback_index))


def normalize_choices(question: dict[str, Any]) -> list[tuple[str, str]]:
    options = question.get("options")
    choices = question.get("choices")
    rows: list[tuple[str, str]] = []

    if isinstance(options, list):
        for index, item in enumerate(options, start=1):
            rows.append((choice_label(index, index), clean_text(item)))
        return rows

    if isinstance(choices, list):
        for index, item in enumerate(choices, start=1):
            if isinstance(item, dict):
                label = choice_label(item.get("label") or item.get("number"), index)
                text = clean_text(item.get("text") or item.get("value"))
            else:
                label = choice_label(index, index)
                text = clean_text(item)
            rows.append((label, text))
        return rows

    if isinstance(choices, dict):
        def sort_key(pair: tuple[Any, Any]) -> tuple[int, str]:
            key = str(pair[0])
            return (int(key), key) if key.isdigit() else (999, key)

        for index, (key, value) in enumerate(sorted(choices.items(), key=sort_key), start=1):
            rows.append((choice_label(key, index), clean_text(value)))

    return rows


def answer_label(question: dict[str, Any]) -> str:
    answer = question.get("answer")
    if answer in CIRCLED_NUMBERS.values():
        return str(answer)
    raw = str(answer or "").strip()
    match = re.search(r"[1-9]", raw)
    if match:
        return CIRCLED_NUMBERS.get(match.group(0), raw)
    return raw or "-"


def filename_from_image_ref(image_ref: dict[str, Any]) -> str:
    if image_ref.get("filename"):
        return Path(str(image_ref["filename"])).name
    if image_ref.get("stored_name"):
        return Path(str(image_ref["stored_name"])).name
    url = str(image_ref.get("url") or "")
    if "/api/media/assets/" in url or "/api/studio/images/" in url:
        return Path(unquote(url.rsplit("/", 1)[-1])).name
    return ""


def image_path_from_ref(image_ref: dict[str, Any]) -> Path | None:
    filename = filename_from_image_ref(image_ref)
    if not filename:
        return None
    for root in (MEDIA_ASSET_DIR, IMAGE_DIR):
        candidate = (root / filename).resolve()
        if candidate.exists() and root.resolve() in candidate.parents:
            return candidate
    return None


def image_data_uri(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def render_source_notes(question: dict[str, Any]) -> str:
    refs = question.get("reference_notes") if isinstance(question.get("reference_notes"), list) else []
    if not refs:
        return ""
    items = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        source = clean_text(ref.get("source"))
        basis = clean_text(ref.get("basis"))
        status = clean_text(ref.get("verification_status"))
        if source:
            detail = f"{escape(source)}"
            if basis:
                detail += f" — {escape(basis)}"
            if status:
                detail += f" <span class=\"muted\">({escape(status)})</span>"
            items.append(f"<li>{detail}</li>")
    if not items:
        return ""
    return f"<div class=\"references\"><strong>근거자료</strong><ol>{''.join(items)}</ol></div>"


def render_data_table(question: dict[str, Any]) -> str:
    table = question.get("data_table") if isinstance(question.get("data_table"), dict) else {}
    columns = table.get("columns") if isinstance(table.get("columns"), list) else []
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    if not columns or not rows:
        return ""
    header = "".join(f"<th>{escape(clean_text(column))}</th>" for column in columns)
    body = []
    for row in rows:
        if not isinstance(row, list):
            continue
        body.append("<tr>" + "".join(f"<td>{escape(clean_text(cell))}</td>" for cell in row) + "</tr>")
    if not body:
        return ""
    title = clean_text(table.get("title"))
    caption = f"<caption>{escape(title)}</caption>" if title else ""
    return f"<table>{caption}<thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_images(question: dict[str, Any]) -> str:
    image_refs = question.get("image_refs") if isinstance(question.get("image_refs"), list) else []
    image_blocks = []
    for index, image_ref in enumerate(image_refs, start=1):
        if not isinstance(image_ref, dict):
            continue
        path = image_path_from_ref(image_ref)
        label = clean_text(image_ref.get("locator_label") or image_ref.get("source_name") or f"제시자료 {index}")
        caption = clean_text(image_ref.get("text_preview") or image_ref.get("caption"))
        if path:
            image_blocks.append(
                f"""
                <figure>
                  <img src="{image_data_uri(path)}" alt="{escape(label)}">
                  <figcaption>{escape(label)}{f" · {escape(caption)}" if caption else ""}</figcaption>
                </figure>
                """
            )
        elif label or caption:
            image_blocks.append(
                f"<div class=\"missing-media\">제시자료 확인 필요: {escape(label or caption)}</div>"
            )
    if not image_blocks:
        return ""
    return f"<div class=\"media-block\">{''.join(image_blocks)}</div>"


def render_question(
    question: dict[str, Any],
    display_number: int,
    *,
    include_answers: bool,
    include_explanations: bool,
    include_references: bool,
) -> str:
    stem = block_text(question.get("problem") or question.get("stem") or question.get("question"))
    choices = normalize_choices(question)
    choice_rows = "\n".join(
        f"<li><span class=\"choice-label\">{escape(label)}</span> {escape(text)}</li>"
        for label, text in choices
    )
    explanation = block_text(question.get("explanation"))
    review_badge = clean_text(question.get("review_status") or "draft")
    table_html = render_data_table(question)
    images_html = render_images(question)
    answer_html = (
        f"<div class=\"answer-line\"><strong>정답</strong> {escape(answer_label(question))}</div>"
        if include_answers
        else ""
    )
    explanation_html = (
        f"<div class=\"explanation\"><strong>해설</strong><p>{escape(explanation).replace(chr(10), '<br>')}</p></div>"
        if include_explanations and explanation
        else ""
    )
    refs_html = render_source_notes(question) if include_references else ""

    return f"""
    <section class="question-card">
      <div class="question-meta">
        <span>문항 {display_number}</span>
        <span>{escape(review_badge)}</span>
        <span>{escape(clean_text(question.get("question_type") or ""))}</span>
      </div>
      <p class="stem"><strong>{display_number}.</strong> {escape(stem).replace(chr(10), '<br>')}</p>
      {images_html}
      {table_html}
      <ol class="choices">{choice_rows}</ol>
      {answer_html}
      {explanation_html}
      {refs_html}
    </section>
    """


def render_html(
    packet: dict[str, Any],
    questions: list[dict[str, Any]],
    *,
    include_answers: bool,
    include_explanations: bool,
    include_references: bool,
) -> str:
    metadata = packet.get("metadata") if isinstance(packet.get("metadata"), dict) else {}
    title = clean_text(metadata.get("subject") or metadata.get("source_name") or packet.get("set_id") or "문항 세트")
    unit = clean_text(metadata.get("unit"))
    source_name = clean_text(metadata.get("source_name"))
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    question_html = "\n".join(
        render_question(
            question,
            index,
            include_answers=include_answers,
            include_explanations=include_explanations,
            include_references=include_references,
        )
        for index, question in enumerate(questions, start=1)
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{escape(title)} CBT HWP 양식</title>
  <style>
    @page {{ size: A4; margin: 18mm 16mm; }}
    body {{
      font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
      color: #111827;
      font-size: 11pt;
      line-height: 1.65;
      background: #ffffff;
    }}
    h1 {{ font-size: 18pt; margin: 0 0 8px; }}
    .subtitle {{ margin: 0 0 18px; color: #475569; }}
    .cover {{
      border-bottom: 2px solid #111827;
      padding-bottom: 12px;
      margin-bottom: 18px;
    }}
    .notice {{
      border: 1px solid #cbd5e1;
      background: #f8fafc;
      padding: 10px 12px;
      margin: 14px 0 20px;
      color: #334155;
    }}
    .question-card {{
      page-break-inside: avoid;
      border-top: 1px solid #cbd5e1;
      padding-top: 14px;
      margin-top: 18px;
    }}
    .question-meta {{
      display: flex;
      gap: 8px;
      color: #64748b;
      font-size: 9pt;
      margin-bottom: 8px;
    }}
    .question-meta span {{
      border: 1px solid #cbd5e1;
      border-radius: 999px;
      padding: 2px 8px;
    }}
    .stem {{ font-size: 11.5pt; margin: 0 0 10px; }}
    .choices {{ list-style: none; padding: 0; margin: 10px 0; }}
    .choices li {{ margin: 4px 0; }}
    .choice-label {{ display: inline-block; min-width: 20px; font-weight: 700; }}
    .answer-line {{
      margin-top: 10px;
      padding: 7px 10px;
      border-left: 4px solid #003366;
      background: #f1f5f9;
    }}
    .explanation {{
      margin-top: 10px;
      color: #1f2937;
    }}
    .explanation p {{ margin: 4px 0 0; }}
    .media-block {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin: 12px 0;
    }}
    figure {{
      margin: 0;
      border: 1px solid #cbd5e1;
      padding: 8px;
      page-break-inside: avoid;
    }}
    img {{ max-width: 100%; height: auto; display: block; margin: 0 auto; }}
    figcaption {{ color: #475569; font-size: 9pt; margin-top: 6px; }}
    .missing-media {{
      border: 1px dashed #f59e0b;
      color: #92400e;
      padding: 10px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0;
      font-size: 10pt;
    }}
    caption {{ text-align: left; font-weight: 700; margin-bottom: 4px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 5px 7px; }}
    th {{ background: #f1f5f9; }}
    .references {{
      margin-top: 10px;
      color: #475569;
      font-size: 9pt;
    }}
    .references ol {{ margin: 4px 0 0 18px; padding: 0; }}
    .muted {{ color: #94a3b8; }}
  </style>
</head>
<body>
  <header class="cover">
    <h1>{escape(title)}</h1>
    <p class="subtitle">
      {escape(unit or "단원 미지정")} · {len(questions)}문항 · 생성 문항 검토본 · {escape(created_at)}
      {f"<br>원자료: {escape(source_name)}" if source_name else ""}
    </p>
  </header>
  <div class="notice">
    이 파일은 한글에서 열어 편집한 뒤 <strong>.hwp</strong>로 저장하는 CBT 업로드 준비용 양식입니다.
    생성 문항은 담당 교원의 문항 검토 후 사용합니다.
  </div>
  {question_html}
</body>
</html>
"""


def build_cbt_hwp_export(
    set_id: str,
    *,
    include_unapproved: bool = False,
    include_answers: bool = True,
    include_explanations: bool = True,
    include_references: bool = True,
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
        raise ValueError("승인된 문항이 없습니다. 문항 검토 큐에서 승인 후 CBT HWP 양식을 생성하세요.")

    export_slug = f"{safe_slug(set_id)}_cbt_hwp_template"
    html_path = EXPORT_SET_DIR / f"{export_slug}.html"
    manifest_path = EXPORT_SET_DIR / f"{export_slug}.manifest.json"
    html_path.write_text(
        render_html(
            packet,
            selected_questions,
            include_answers=include_answers,
            include_explanations=include_explanations,
            include_references=include_references,
        ),
        encoding="utf-8",
    )

    now = datetime.now(timezone.utc).isoformat()
    artifact = {
        "export_id": export_slug,
        "export_type": "cbt_hwp_template_html",
        "set_id": set_id,
        "subject": metadata.get("subject"),
        "unit": metadata.get("unit"),
        "question_count": len(selected_questions),
        "include_unapproved": include_unapproved,
        "include_answers": include_answers,
        "include_explanations": include_explanations,
        "include_references": include_references,
        "file_path": str(html_path),
        "download_url": f"/api/exports/{html_path.name}",
        "hwp_workflow": "한글에서 HTML 파일 열기 → 필요 시 편집 → 다른 이름으로 저장(.hwp)",
        "created_at": now,
    }
    write_json(manifest_path, artifact)
    return artifact
