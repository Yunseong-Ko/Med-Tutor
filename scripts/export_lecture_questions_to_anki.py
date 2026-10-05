#!/usr/bin/env python3
"""강의별 시험대비 연습문항(JSON) → Anki 덱 (개인 학습용).

앞면: 출처칩 + 문제 + 5선지(정답 강조 없음)
뒷면: 정답박스 + 이해중심 해설 + 선지별 해설 + 핵심 포인트 + Harrison 근거
강의(교시)별 서브덱. 입력: scratchpad/lecture_questions/q_*.json
"""

import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path

import genanki

SRC = Path("data_private/lecture_questions")
MEDIA = SRC / "media"
OUT_DIR = Path("data_private/anki_exports")
MODEL_ID = 1607393022
PARENT = "P:accine::혈액종양 강의 연습문항"


def sid(v, digits=10):
    return int(hashlib.sha1(str(v).encode()).hexdigest()[:digits], 16)


def ht(v):
    return html.escape(str(v or "")).replace("\n", "<br>")


def tg(v):
    return re.sub(r"[^\w:.-]+", "_", re.sub(r"\s+", "_", str(v or "").strip())).strip("_")


def lecture_label(lid, source_name):
    m = re.match(r"(\d{4})(\d{2})(\d{2})_([\d_]+교시)_(.+)", str(lid))
    if m:
        _, mo, da, gy, title = m.groups()
        return f"{int(mo)}·{int(da)} {gy.replace('_','·')} {source_name or title.replace('_',' ')}"
    return source_name or lid


MODEL = genanki.Model(
    MODEL_ID, "P:accine 강의문항 Question",
    fields=[{"name": n} for n in ["Source", "Question", "Choices", "Answer",
                                  "Explanation", "ChoiceExplanations", "KeyPoints", "Harrison"]],
    templates=[{
        "name": "강의문항 Question",
        "qfmt": """
<section class="source">{{Source}}</section>
<section class="question">{{Question}}</section>
<section class="choices">{{Choices}}</section>
""",
        "afmt": """
{{FrontSide}}
<hr id="answer">
<section class="answer">{{Answer}}</section>
{{#Explanation}}<section class="panel"><span class="panel-title">해설</span>{{Explanation}}</section>{{/Explanation}}
{{#ChoiceExplanations}}<section class="panel">{{ChoiceExplanations}}</section>{{/ChoiceExplanations}}
{{#KeyPoints}}<section class="panel keypoints">{{KeyPoints}}</section>{{/KeyPoints}}
{{#Harrison}}<section class="panel harrison">{{Harrison}}</section>{{/Harrison}}
""",
    }],
    css="""
.card { font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif; font-size:18px; line-height:1.55; color:#172033; background:#f8fafc; text-align:left; }
.source { display:inline-block; margin-bottom:12px; padding:6px 10px; border:1px solid #cbd5e1; border-radius:999px; color:#475569; font-size:13px; font-weight:700; background:#fff; }
.question { font-size:20px; font-weight:700; line-height:1.65; margin:8px 0 14px; }
.qimg { margin:10px 0; text-align:center; }
.qimg img { max-width:100%; max-height:420px; border:1px solid #cbd5e1; border-radius:10px; }
.choices { margin-top:14px; }
.choice { display:flex; gap:10px; padding:10px 12px; margin:8px 0; border:1px solid #dbe4ef; border-radius:12px; background:#fff; }
.choice-number { min-width:28px; height:28px; border:1px solid #b6c7da; border-radius:999px; color:#003366; font-weight:800; text-align:center; line-height:28px; }
.answer { margin:16px 0; padding:14px 16px; border-left:5px solid #0f766e; border-radius:12px; background:#dcfce7; font-size:19px; font-weight:800; color:#064e3b; }
.panel { margin:14px 0; padding:14px 16px; border:1px solid #dbe4ef; border-radius:14px; background:#fff; }
.panel-title { display:block; margin-bottom:8px; color:#0f766e; font-size:14px; font-weight:900; }
.ce { padding:8px 0; border-top:1px solid #edf2f7; } .ce:first-of-type{border-top:0;}
.ce.correct { color:#065f46; } .ce.wrong { color:#991b1b; }
.harrison { background:#f8fafc; } .keypoints ul{padding-left:20px;}
"""
)


def render_choices(ch):
    rows = []
    for k in sorted(ch, key=lambda x: int(x) if str(x).isdigit() else 99):
        if ch.get(k):
            rows.append(f'<div class="choice"><span class="choice-number">{ht(k)}</span><span>{ht(ch[k])}</span></div>')
    return "\n".join(rows)


def render_choice_exps(q):
    ce = q.get("choice_explanations") or {}
    if not ce:
        return ""
    ans = str(q.get("answer"))
    out = ['<span class="panel-title">선지별 해설</span>']
    for k in sorted(ce, key=lambda x: int(x) if str(x).isdigit() else 99):
        if not ce.get(k):
            continue
        cls = "correct" if str(k) == ans else "wrong"
        out.append(f'<div class="ce {cls}"><b>{ht(k)}.</b> {ht(ce[k])}</div>')
    return "\n".join(out) if len(out) > 1 else ""


def render_keypoints(q):
    kp = q.get("key_point") or []
    if not kp:
        return ""
    return '<span class="panel-title">핵심 포인트</span><ul>' + "".join(f"<li>{ht(x)}</li>" for x in kp if x) + "</ul>"


def render_harrison(q):
    h = q.get("harrison")
    return f'<span class="panel-title">근거</span>{ht(h)}' if h and isinstance(h, str) else ""


def question_html(q):
    """이미지가 있으면 <img>를 지문 위에 붙임(Anki는 basename으로 media 참조)."""
    name = q.get("image")
    img = ""
    if name and (MEDIA / name).exists():
        img = f'<div class="qimg"><img src="{ht(name)}"></div>'
    return img + ht(q.get("stem"))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    allow = None
    allow_path = SRC / "_include_lids.json"
    if allow_path.exists():
        try:
            allow = set(json.loads(allow_path.read_text(encoding="utf-8")))
        except Exception:
            allow = None
    decks = []
    media_files = []
    n = 0
    for f in sorted(SRC.glob("q_*.json"), key=lambda p: p.name):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        qs = d.get("questions") or []
        if not qs:
            continue
        lid = d.get("lecture_id")
        if allow is not None and lid not in allow:
            continue
        label = lecture_label(lid, d.get("source_name"))
        deck = genanki.Deck(sid(f"{PARENT}::{label}", 9), f"{PARENT}::{label}")
        for i, q in enumerate(qs, 1):
            ch = q.get("choices") or {}
            ans = q.get("answer")
            ans_html = f"정답 {ht(ans)}. {ht(ch.get(str(ans), ''))}" if ans not in (None, "") else "정답 미표기"
            note = genanki.Note(
                model=MODEL,
                fields=[f"{label} · Q{i} · {ht(q.get('topic'))}", question_html(q), render_choices(ch),
                        ans_html, ht(q.get("explanation")), render_choice_exps(q),
                        render_keypoints(q), render_harrison(q)],
                tags=["paccine", "혈액종양강의", tg(lid)] + ([tg(q.get("concept"))] if q.get("concept") else []),
                guid=f"{PARENT}::{lid}::{i}")
            deck.add_note(note)
            name = q.get("image")
            if name and (MEDIA / name).exists():
                media_files.append(str(MEDIA / name))
            n += 1
        decks.append(deck)
    out = OUT_DIR / "paccine_혈액종양_강의연습문항_20260712.apkg"
    pkg = genanki.Package(decks)
    pkg.media_files = sorted(set(media_files))
    pkg.write_to_file(str(out))
    (OUT_DIR / "paccine_혈액종양_강의연습문항_20260712.manifest.json").write_text(
        json.dumps({"deck": PARENT, "output": str(out), "question_count": n, "subdecks": len(decks),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "design": "PMA-parity · 개인학습용"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {out}")
    print(f"  문항 {n} · 서브덱(강의) {len(decks)}")


if __name__ == "__main__":
    raise SystemExit(main())
