#!/usr/bin/env python3
"""혈액종양내과 246문항(3세트) → Anki 덱. 기존 임종평/PMA 덱과 동일 디자인.

앞면: 출처칩(+온톨로지 배지) + 문항 + 이미지 + 선지(정답 강조 없음)
뒷면: 초록 정답박스 + 정답근거·통합해설·선지별 해설·가져갈 개념 + Harrison 근거 패널
이미지는 media_positions(문항별 정확 위치맵)로 배치. 세트별 서브덱. .apkg는 data_private.
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
    ("2023 과정시험", "COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험"),
    ("2026 1차", "COURSE_2_20260306_HEMATOLOGY_ONCOLOGY_1차"),
    ("2026 2차", "COURSE_2_20260317_HEMATOLOGY_ONCOLOGY_2차"),
]
MODEL_ID = 1607392811
PARENT = "P:accine::혈액종양내과 (Ontology 해설)"


def sid(v, digits=10):
    return int(hashlib.sha1(str(v).encode()).hexdigest()[:digits], 16)


def txt(v):
    return re.sub(r"\s+", " ", str(v or "").strip())


def ht(v):
    return html.escape(str(v or "")).replace("\n", "<br>")


def tg(v):
    return re.sub(r"[^\w:.-]+", "_", re.sub(r"\s+", "_", str(v or "").strip())).strip("_")


def clean(v):
    """실제 이미지를 별도 렌더하므로 중복 <그림>/＜그림＞ 플레이스홀더 제거."""
    s = str(v or "")
    if re.search(r"[<＜〈\[]\s*그림\s*[>＞〉\]]", s):
        s = re.sub(r"[<＜〈\[]?\s*그림\s*[>＞〉\]]?", "", s)
    return re.sub(r"\n{2,}", "\n", s).strip()


# ── 기존 PMA/임종평 덱과 동일 디자인 (+ Harrison 패널) ──
MODEL = genanki.Model(
    MODEL_ID, "P:accine 혈액종양 Question",
    fields=[{"name": n} for n in ["Source", "Question", "Stimulus", "Media",
                                  "Substatements", "Choices", "Answer", "Explanation",
                                  "ChoiceExplanations", "LearningPoints", "Harrison"]],
    templates=[{
        "name": "혈액종양 Question",
        "qfmt": """
<section class="source">{{Source}}</section>
<section class="question">{{Question}}</section>
{{#Stimulus}}<section class="stimulus">{{Stimulus}}</section>{{/Stimulus}}
{{#Media}}<section class="media">{{Media}}</section>{{/Media}}
{{#Substatements}}<section class="substmt">{{Substatements}}</section>{{/Substatements}}
<section class="choices">{{Choices}}</section>
""",
        "afmt": """
{{FrontSide}}
<hr id="answer">
<section class="answer">{{Answer}}</section>
{{#Explanation}}<section class="panel explanation">{{Explanation}}</section>{{/Explanation}}
{{#ChoiceExplanations}}<section class="panel choice-explanations">{{ChoiceExplanations}}</section>{{/ChoiceExplanations}}
{{#LearningPoints}}<section class="panel learning-points">{{LearningPoints}}</section>{{/LearningPoints}}
{{#Harrison}}<section class="panel harrison">{{Harrison}}</section>{{/Harrison}}
""",
    }],
    css="""
.card { font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard", sans-serif;
  font-size: 18px; line-height: 1.55; color: #172033; background: #f8fafc; text-align: left; }
.source { display: inline-block; margin-bottom: 12px; padding: 6px 10px; border: 1px solid #cbd5e1;
  border-radius: 999px; color: #475569; font-size: 13px; font-weight: 700; background: white; }
.onto { display: inline-block; margin: 0 0 12px 6px; padding: 6px 10px; border: 1px solid #99f6e4;
  border-radius: 999px; color: #0f766e; font-size: 13px; font-weight: 800; background: #ecfdf5; }
.question { font-size: 20px; font-weight: 700; line-height: 1.65; margin: 8px 0 14px; }
.stimulus { margin: 12px 0; padding: 12px 14px; border-left: 5px solid #0f766e; border-radius: 12px;
  background: #eefdf8; white-space: pre-wrap; }
.media { margin: 14px 0; }
.media img { display: block; max-width: 100%; max-height: 520px; object-fit: contain; margin: 10px auto;
  border: 1px solid #dbe4ef; border-radius: 14px; background: white; }
.substmt { margin: 12px 0; padding: 12px 14px; border: 1px solid #dbe4ef; border-radius: 12px; background: white; }
.subst-row { padding: 4px 0; }
.substmt b { color: #0f766e; }
.choices { margin-top: 14px; }
.choice { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin: 8px 0;
  border: 1px solid #dbe4ef; border-radius: 12px; background: white; }
.choice-number { min-width: 28px; height: 28px; border: 1px solid #b6c7da; border-radius: 999px;
  color: #003366; font-weight: 800; text-align: center; line-height: 28px; }
.answer { margin: 16px 0; padding: 14px 16px; border-left: 5px solid #0f766e; border-radius: 12px;
  background: #dcfce7; font-size: 19px; font-weight: 800; color: #064e3b; }
.answer.na { background: #fffbeb; border-left-color: #d97706; color: #92400e; }
.panel { margin: 14px 0; padding: 14px 16px; border: 1px solid #dbe4ef; border-radius: 14px; background: white; }
.panel-title { display: block; margin-bottom: 8px; color: #0f766e; font-size: 14px; font-weight: 900; }
.choice-exp { padding: 10px 0; border-top: 1px solid #edf2f7; }
.choice-exp:first-of-type { border-top: 0; }
.choice-exp.correct { color: #065f46; }
.choice-exp.wrong { color: #991b1b; }
.harrison { background: #f8fafc; }
.harrison a { color: #0369a1; text-decoration: none; }
.review { margin-top: 10px; color: #94a3b8; font-size: 12px; }
ul { padding-left: 20px; }
""")


def render_substatements(q):
    subs = q.get("sub_statements") or {}
    if not subs:
        return ""
    return "".join(f'<div class="subst-row"><b>{ht(k)}.</b> {ht(v)}</div>' for k, v in subs.items())


def render_choices(q):
    ch = q.get("choices") or {}
    rows = []
    for k in sorted(ch, key=lambda x: int(x) if str(x).isdigit() else 99):
        if not ch.get(k):
            continue
        rows.append(f'<div class="choice"><span class="choice-number">{ht(k)}</span><span>{ht(ch[k])}</span></div>')
    return "\n".join(rows)


def render_answer(q):
    ans = q.get("answer")
    if ans in (None, ""):
        return None  # signal missing-answer
    label = (q.get("choices") or {}).get(str(ans))
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
        it = ce.get(k)
        # new format: plain string; legacy: {rationale/explanation}
        exp = txt(it if isinstance(it, str) else (it.get("rationale") or it.get("explanation")) if isinstance(it, dict) else "")
        if not exp:
            continue
        ctext = txt((q.get("choices") or {}).get(str(k)))
        cls = "correct" if str(k) == ans else "wrong"
        head = f'<b>{ht(k)}. {ht(ctext)}</b><br>' if ctext else f'<b>{ht(k)}.</b> '
        out.append(f'<div class="choice-exp {cls}">{head}{ht(exp)}</div>')
    return "\n".join(out) if len(out) > 1 else ""


def render_learning_points(q):
    pts = q.get("key_learning_points") or []
    if not pts:
        return ""
    return ('<span class="panel-title">가져갈 개념</span><ul>'
            + "".join(f"<li>{ht(p)}</li>" for p in pts if txt(p)) + "</ul>")


def render_harrison(q):
    ha = q.get("harrison_anchor")
    if not isinstance(ha, dict) or not ha.get("citation"):
        return ""
    link = f' — <a href="{html.escape(ha.get("url") or "")}">AccessMedicine 열람</a>' if ha.get("url") else ""
    return f'<span class="panel-title">근거 (Harrison)</span>{ht(ha["citation"])}{link}'


def stage_media(q, assets_by_storage, posmap, cache, prefix):
    out, files = [], []
    qn = str(q.get("question_number"))
    seen = set()
    for i, s_id in enumerate(posmap.get(qn, []), 1):
        if s_id in seen:
            continue
        seen.add(s_id)
        a = assets_by_storage.get(s_id)
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
    cache = OUT_DIR / "hemeonc_media_cache"
    cache.mkdir(parents=True, exist_ok=True)
    decks, media_files = [], []
    n = n_img = n_na = 0
    for label, stem in SOURCES:
        rec = json.loads((EXTRACTED / f"{stem}.json").read_text(encoding="utf-8"))
        assets_by_storage = {a.get("storage_id"): a for a in (rec.get("media_assets") or [])}
        posmap = {}
        for m in (rec.get("media_positions") or []):
            posmap.setdefault(str(m.get("question_number")), []).append(m.get("storage_id"))
        deck = genanki.Deck(sid(f"{PARENT}::{label}", 8), f"{PARENT}::{label}")
        for q in rec["questions"]:
            if not q.get("choices"):
                continue
            qn = q.get("question_number")
            labels = q.get("labels") or {}
            g = q.get("ontology_grounding") or {}
            topic = labels.get("subtopic") or labels.get("topic") or (labels.get("concept_tags") or [""])[0]
            source = " · ".join(x for x in ["혈액종양내과", label, f"Q{qn}", str(topic).replace('_', ' ')] if x)
            if g.get("disease_concept_id"):
                source += f'</section><section class="onto">◆ {ht(g.get("label") or g["disease_concept_id"])}'
            media, mf = stage_media(q, assets_by_storage, posmap, cache, f"{tg(label)}_{qn}")
            ans_html = render_answer(q)
            if ans_html is None:
                ans_html = '<span class="na">정답 미기록 · 교수 검수 필요</span>'
                n_na += 1
            note = genanki.Note(
                model=MODEL,
                fields=[source, ht(clean(q.get("stem"))), ht(clean(q.get("stimulus"))), media,
                        render_substatements(q), render_choices(q), ans_html, render_explanation(q),
                        render_choice_explanations(q), render_learning_points(q), render_harrison(q)],
                tags=["paccine", "혈액종양내과", tg(label)]
                     + ([tg(g["disease_concept_id"])] if g.get("disease_concept_id") else [])
                     + [tg(t) for t in (labels.get("concept_tags") or [])][:6],
                guid=f"{PARENT}::{label}::{q.get('question_id') or qn}")
            deck.add_note(note)
            media_files.extend(mf)
            n += 1
            if mf:
                n_img += 1
        decks.append(deck)
    out = OUT_DIR / "paccine_혈액종양내과_Ontology해설_20260712.apkg"
    genanki.Package(decks, media_files=sorted(set(media_files))).write_to_file(str(out))
    (OUT_DIR / "paccine_혈액종양내과_Ontology해설_20260712.manifest.json").write_text(
        json.dumps({"deck": PARENT, "output": str(out),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "question_count": n, "image_questions": n_img, "answer_missing": n_na,
                    "media_files": len(set(media_files)), "design": "PMA/임종평-parity + Harrison"},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {out}")
    print(f"  문항 {n} · 이미지문항 {n_img} · 미디어 {len(set(media_files))} · answer미기록 {n_na} · 서브덱 {len(decks)}")


if __name__ == "__main__":
    raise SystemExit(main())
