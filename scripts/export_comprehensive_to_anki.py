#!/usr/bin/env python3
"""임상의학종합평가 4개 교시(280문항) → Anki 덱. 기존 PMA 덱과 동일 디자인.

앞면: 출처칩 + 문항 + 이미지 + 선지카드(정답 강조 없음)
뒷면: 초록 정답박스 + 정답근거·통합해설·선지별 해설·가져갈 개념 패널
교시별 서브덱. 실제 기출 기반 개인 학습용(.apkg는 data_private).
"""

import hashlib
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import genanki

EXTRACTED = Path("data_private/course_exams/extracted")
OUT_DIR = Path("data_private/anki_exports")
SOURCES = [
    ("1교시", "COURSE_4_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_1교시"),
    ("2교시", "COURSE_X_DATE_UNKNOWN_EXAM_2교시"),
    ("3교시", "COURSE_X_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_3교시"),
    ("4교시", "COURSE_X_DATE_UNKNOWN_EXAM_4교시"),
]
MODEL_ID = 1607392600
PARENT = "P:accine::임상의학종합평가 2026"


def sid(v, digits=10):
    return int(hashlib.sha1(str(v).encode()).hexdigest()[:digits], 16)


def txt(v):
    return re.sub(r"\s+", " ", str(v or "").strip())


def ht(v):
    return html.escape(str(v or "")).replace("\n", "<br>")


def tg(v):
    return re.sub(r"[^\w:.-]+", "_", re.sub(r"\s+", "_", str(v or "").strip())).strip("_")


# ── 기존 PMA 덱과 동일 디자인 ──
MODEL = genanki.Model(
    MODEL_ID, "P:accine 임종평 Question",
    fields=[{"name": n} for n in ["Source", "Question", "Stimulus", "Media",
                                  "Choices", "Answer", "Explanation",
                                  "ChoiceExplanations", "LearningPoints"]],
    templates=[{
        "name": "임종평 Question",
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
{{#Explanation}}<section class="panel explanation">{{Explanation}}</section>{{/Explanation}}
{{#ChoiceExplanations}}<section class="panel choice-explanations">{{ChoiceExplanations}}</section>{{/ChoiceExplanations}}
{{#LearningPoints}}<section class="panel learning-points">{{LearningPoints}}</section>{{/LearningPoints}}
""",
    }],
    css="""
.card { font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard", sans-serif;
  font-size: 18px; line-height: 1.55; color: #172033; background: #f8fafc; text-align: left; }
.source { display: inline-block; margin-bottom: 12px; padding: 6px 10px; border: 1px solid #cbd5e1;
  border-radius: 999px; color: #475569; font-size: 13px; font-weight: 700; background: white; }
.question { font-size: 20px; font-weight: 700; line-height: 1.65; margin: 8px 0 14px; }
.stimulus { margin: 12px 0; padding: 12px 14px; border-left: 5px solid #0f766e; border-radius: 12px;
  background: #eefdf8; white-space: pre-wrap; }
.media { margin: 14px 0; }
.media img { display: block; max-width: 100%; max-height: 520px; object-fit: contain; margin: 10px auto;
  border: 1px solid #dbe4ef; border-radius: 14px; background: white; }
.choices { margin-top: 14px; }
.choice { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin: 8px 0;
  border: 1px solid #dbe4ef; border-radius: 12px; background: white; }
.choice-number { min-width: 28px; height: 28px; border: 1px solid #b6c7da; border-radius: 999px;
  color: #003366; font-weight: 800; text-align: center; line-height: 28px; }
.answer { margin: 16px 0; padding: 14px 16px; border-left: 5px solid #0f766e; border-radius: 12px;
  background: #dcfce7; font-size: 19px; font-weight: 800; color: #064e3b; }
.panel { margin: 14px 0; padding: 14px 16px; border: 1px solid #dbe4ef; border-radius: 14px; background: white; }
.panel-title { display: block; margin-bottom: 8px; color: #0f766e; font-size: 14px; font-weight: 900; }
.choice-exp { padding: 10px 0; border-top: 1px solid #edf2f7; }
.choice-exp:first-of-type { border-top: 0; }
.choice-exp.correct { color: #065f46; }
.choice-exp.wrong { color: #991b1b; }
ul { padding-left: 20px; }
""")


def render_choices(q):
    ch = q.get("choices") or {}
    rows = []
    for k in ["1", "2", "3", "4", "5"]:
        if not ch.get(k):
            continue
        rows.append(f'<div class="choice"><span class="choice-number">{k}</span><span>{ht(ch[k])}</span></div>')
    return "\n".join(rows)


def render_answer(q):
    ans = str(q.get("answer"))
    label = (q.get("choices") or {}).get(ans)
    return f"정답: {ans}. {ht(label)}" if label else f"정답: {ans}"


def render_explanation(q):
    parts = []
    if q.get("answer_rationale"):
        parts.append(f'<span class="panel-title">정답근거</span>{ht(q["answer_rationale"])}')
    if q.get("explanation"):
        parts.append(f'<span class="panel-title">통합해설</span>{ht(q["explanation"])}')
    return "<br><br>".join(parts)


def render_choice_explanations(q):
    ce = q.get("choice_explanations") or {}
    if not ce:
        return ""
    ans = str(q.get("answer"))
    out = ['<span class="panel-title">선지별 해설</span>']
    for k in sorted(ce, key=lambda x: int(x) if str(x).isdigit() else 99):
        it = ce.get(k) or {}
        exp = txt(it.get("rationale") or it.get("explanation"))
        if not exp:
            continue
        ctext = txt(it.get("choice_text") or (q.get("choices") or {}).get(str(k)))
        cls = "correct" if (str(k) == ans or it.get("is_correct")) else "wrong"
        out.append(f'<div class="choice-exp {cls}"><b>{k}. {ht(ctext)}</b><br>{ht(exp)}</div>')
    return "\n".join(out) if len(out) > 1 else ""


def render_learning_points(q):
    pts = q.get("key_learning_points") or []
    if not pts:
        return ""
    return ('<span class="panel-title">가져갈 개념</span><ul>'
            + "".join(f"<li>{ht(p)}</li>" for p in pts if txt(p)) + "</ul>")


def stage_media(q, assets_by_id, cache, prefix):
    out, files = [], []
    for i, ref in enumerate((q.get("media") or {}).get("media_refs") or [], 1):
        a = assets_by_id.get(ref.get("media_id"))
        if not a:
            continue
        src = Path(a.get("file_path") or "")
        if not src.exists() or src.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".gif"):
            continue
        name = f"{prefix}_{i}{src.suffix.lower()}"
        dst = cache / name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        files.append(str(dst))
        out.append(f'<img src="{name}">')
    return "\n".join(out), files


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = OUT_DIR / "comprehensive_media_cache"
    cache.mkdir(parents=True, exist_ok=True)
    decks, media_files = [], []
    n = n_img = 0
    for label, stem in SOURCES:
        rec = json.loads((EXTRACTED / f"{stem}.json").read_text(encoding="utf-8"))
        assets_by_id = {a.get("media_id"): a for a in (rec.get("media_assets") or [])}
        deck = genanki.Deck(sid(f"{PARENT}::{label}", 8), f"{PARENT}::{label}")
        for q in rec["questions"]:
            if not q.get("answer") or not q.get("choices"):
                continue
            qn = q.get("question_number")
            labels = q.get("labels") or {}
            sys = (labels.get("concept_tags") or [""])[0]
            source = " · ".join(x for x in ["임상의학종합평가", label, f"Q{qn}", sys.replace('_', ' ')] if x)
            media, mf = stage_media(q, assets_by_id, cache, f"{tg(label)}_{qn}")
            note = genanki.Note(
                model=MODEL,
                fields=[source, ht(q.get("stem")), "", media, render_choices(q),
                        render_answer(q), render_explanation(q),
                        render_choice_explanations(q), render_learning_points(q)],
                tags=["paccine", "임상의학종합평가", tg(label)] + [tg(t) for t in (labels.get("concept_tags") or [])],
                guid=f"{PARENT}::{label}::{q.get('question_id') or qn}")
            deck.add_note(note)
            media_files.extend(mf)
            n += 1
            if mf:
                n_img += 1
        decks.append(deck)
    out = OUT_DIR / "paccine_comprehensive_2026_20260708.apkg"
    genanki.Package(decks, media_files=sorted(set(media_files))).write_to_file(str(out))
    (OUT_DIR / "paccine_comprehensive_2026_20260708.manifest.json").write_text(
        json.dumps({"deck": PARENT, "output": str(out),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "question_count": n, "image_questions": n_img,
                    "media_files": len(set(media_files)), "design": "PMA-parity"},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {out}")
    print(f"  문항 {n} · 이미지 {n_img} · 미디어 {len(set(media_files))} · 서브덱 {len(decks)} · 디자인=PMA동일")


if __name__ == "__main__":
    raise SystemExit(main())
