#!/usr/bin/env python3
"""
Render extracted course-exam JSON into a local HTML review preview.

The generated HTML stays under data_private by default and may contain original
exam content, so do not commit or publish it.
"""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path


VIEWABLE_EXTS = {".bmp", ".png", ".jpg", ".jpeg", ".gif", ".webp"}


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def rel_url(target: Path, base: Path) -> str:
    relative = os.path.relpath(Path(target).resolve(), base.resolve().parent)
    return html.escape(Path(relative).as_posix())


def render_media(ref: dict, media_by_id: dict[str, dict], output_path: Path) -> str:
    asset = media_by_id.get(ref.get("media_id"), {})
    file_path = asset.get("file_path")
    ext = Path(file_path).suffix.lower() if file_path else ""
    title = esc(ref.get("media_id") or asset.get("media_id") or "media")
    confidence = esc(ref.get("match_confidence", ""))

    if file_path and ext in VIEWABLE_EXTS and Path(file_path).exists():
        src = rel_url(Path(file_path), output_path)
        return f"""
        <figure class="media-card">
          <img src="{src}" alt="{title}" loading="lazy" />
          <figcaption>{title} · match {confidence} · 검수 필요</figcaption>
        </figure>
        """

    if file_path:
        src = rel_url(Path(file_path), output_path)
        return f"""
        <div class="media-card media-file">
          <strong>{title}</strong>
          <span>미리보기 어려운 형식입니다.</span>
          <a href="{src}">파일 열기</a>
        </div>
        """

    return f"""
    <div class="media-card media-file">
      <strong>{title}</strong>
      <span>추출 파일 경로가 없습니다. 원본 HWP 검수가 필요합니다.</span>
    </div>
    """


def render_question(question: dict, media_by_id: dict[str, dict], output_path: Path) -> str:
    status = "검수 필요" if question.get("needs_review") else "구조화 완료"
    status_class = "needs-review" if question.get("needs_review") else "ok"
    choices = question.get("choices") or {}
    choice_html = "\n".join(
        f"<li><span>{key}</span><p>{esc(choices[key])}</p></li>"
        for key in ["1", "2", "3", "4", "5"]
        if key in choices
    )
    media_refs = question.get("media", {}).get("media_refs") or []
    media_html = "\n".join(render_media(ref, media_by_id, output_path) for ref in media_refs)

    stimulus = ""
    if question.get("stimulus"):
        stimulus = f"""
        <section class="stimulus">
          <h4>텍스트 제시자료</h4>
          <p>{esc(question.get("stimulus")).replace(chr(10), "<br />")}</p>
        </section>
        """

    media_section = ""
    if media_html:
        media_section = f"""
        <section class="media-section">
          <h4>이미지/자료 제시자료</h4>
          <div class="media-grid">{media_html}</div>
        </section>
        """

    explanation = ""
    if question.get("explanation"):
        explanation = f"""
        <section class="explanation">
          <h4>해설</h4>
          <p>{esc(question.get("explanation")).replace(chr(10), "<br />")}</p>
        </section>
        """

    review_reasons = ""
    if question.get("review_reasons"):
        review_reasons = "<p class=\"review-reasons\">검수 사유: " + esc(", ".join(question["review_reasons"])) + "</p>"

    return f"""
    <article class="question-card">
      <header>
        <div>
          <span class="eyebrow">Q{question.get("question_number")}</span>
          <h3>{esc(question.get("stem") or "문항 지문 미추출")}</h3>
        </div>
        <div class="answer-box">
          <span>정답</span>
          <strong>{esc(question.get("answer") or "미확인")}</strong>
        </div>
      </header>
      <div class="meta-row">
        <span class="{status_class}">{status}</span>
        <span>{esc(question.get("labels", {}).get("question_type"))}</span>
        <span>{esc(question.get("labels", {}).get("cognitive_level"))}</span>
        <span>media {len(media_refs)}</span>
      </div>
      {review_reasons}
      {stimulus}
      {media_section}
      <section>
        <h4>선지</h4>
        <ol class="choices">{choice_html}</ol>
      </section>
      {explanation}
    </article>
    """


def render_record(record: dict, output_path: Path) -> str:
    exam = record["exam"]
    questions = record["questions"]
    media_assets = record.get("media_assets", [])
    media_by_id = {asset["media_id"]: asset for asset in media_assets}

    summary_cards = [
        ("문항", len(questions)),
        ("정답 추출", sum(1 for q in questions if q.get("answer"))),
        ("텍스트 제시자료", sum(1 for q in questions if q.get("stimulus"))),
        ("해설", sum(1 for q in questions if q.get("explanation"))),
        ("이미지 asset", len(media_assets)),
        ("이미지 연결 문항", sum(1 for q in questions if q.get("media", {}).get("media_refs"))),
    ]
    summary_html = "\n".join(
        f"<div class=\"stat\"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>"
        for label, value in summary_cards
    )
    question_html = "\n".join(render_question(q, media_by_id, output_path) for q in questions)

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(exam.get("course_name"))} {esc(exam.get("round_label"))} 검수 미리보기</title>
  <style>
    :root {{
      --ink: #172033;
      --muted: #667085;
      --line: #d9e1ec;
      --bg: #f5f7fb;
      --card: #ffffff;
      --navy: #0f4274;
      --green: #07846f;
      --red: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
      line-height: 1.58;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 40px 24px 80px; }}
    .hero {{
      background: linear-gradient(135deg, #0f4274, #0e7568);
      color: white;
      border-radius: 28px;
      padding: 34px;
      box-shadow: 0 24px 70px rgba(15, 66, 116, 0.22);
    }}
    .hero h1 {{ margin: 8px 0 10px; font-size: 34px; letter-spacing: -0.04em; }}
    .hero p {{ margin: 0; color: rgba(255,255,255,.82); }}
    .stats {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin: 18px 0 28px; }}
    .stat {{ background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 16px; }}
    .stat span {{ display: block; color: var(--muted); font-size: 13px; font-weight: 700; }}
    .stat strong {{ font-size: 28px; color: var(--navy); }}
    .question-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 24px;
      margin: 18px 0;
      box-shadow: 0 18px 45px rgba(23, 32, 51, .06);
    }}
    .question-card header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }}
    .eyebrow {{ color: var(--green); font-weight: 900; letter-spacing: .08em; }}
    h3 {{ margin: 4px 0 0; font-size: 21px; letter-spacing: -0.025em; }}
    h4 {{ margin: 22px 0 8px; font-size: 15px; color: var(--navy); }}
    .answer-box {{ min-width: 92px; text-align: center; background: #e8f2ff; border-radius: 16px; padding: 10px 14px; }}
    .answer-box span {{ display: block; color: var(--muted); font-size: 12px; font-weight: 800; }}
    .answer-box strong {{ font-size: 24px; color: var(--navy); }}
    .meta-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
    .meta-row span {{ border: 1px solid var(--line); border-radius: 999px; padding: 5px 10px; color: var(--muted); font-size: 12px; font-weight: 800; }}
    .meta-row .ok {{ color: var(--green); border-color: #b9e7dc; background: #effaf7; }}
    .meta-row .needs-review {{ color: var(--red); border-color: #ffd0c8; background: #fff3f1; }}
    .review-reasons {{ color: var(--red); font-weight: 700; }}
    .stimulus, .explanation {{ background: #f8fbff; border: 1px dashed #b9cce5; border-radius: 18px; padding: 14px 16px; margin-top: 14px; }}
    .stimulus p, .explanation p {{ margin: 0; }}
    .choices {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }}
    .choices li {{ display: grid; grid-template-columns: 34px 1fr; gap: 10px; align-items: start; background: #f7f9fc; border-radius: 14px; padding: 10px 12px; }}
    .choices span {{ width: 28px; height: 28px; border-radius: 50%; background: white; border: 1px solid var(--line); display: grid; place-items: center; font-weight: 900; color: var(--navy); }}
    .choices p {{ margin: 0; }}
    .media-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }}
    .media-card {{ margin: 0; border: 1px solid var(--line); background: #fff; border-radius: 18px; padding: 12px; }}
    .media-card img {{ width: 100%; max-height: 360px; object-fit: contain; border-radius: 12px; background: #101828; }}
    .media-card figcaption, .media-file span {{ display: block; margin-top: 8px; color: var(--muted); font-size: 12px; }}
    a {{ color: var(--navy); font-weight: 800; }}
    @media (max-width: 900px) {{
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
      .question-card header {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <span class="eyebrow">P:ACCINE EXAM PREVIEW</span>
      <h1>{esc(exam.get("course_name"))} {esc(exam.get("round_label"))} 구조화 검수본</h1>
      <p>{esc(exam.get("source_file"))}</p>
    </section>
    <section class="stats">{summary_html}</section>
    {question_html}
  </main>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render extracted course exam JSON as local HTML preview.")
    parser.add_argument("inputs", nargs="+", help="Extracted JSON files")
    parser.add_argument(
        "--output-dir",
        default="data_private/course_exams/previews",
        help="Output preview directory. Defaults to data_private/course_exams/previews",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for value in args.inputs:
        path = Path(value)
        record = json.loads(path.read_text(encoding="utf-8"))
        output_path = output_dir / f"{path.stem}.html"
        output_path.write_text(render_record(record, output_path), encoding="utf-8")
        outputs.append(str(output_path))

    print(json.dumps({"outputs": outputs}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
