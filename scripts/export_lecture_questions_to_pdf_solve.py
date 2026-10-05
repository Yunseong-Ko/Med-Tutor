#!/usr/bin/env python3
"""강의별 연습문항(JSON) → 풀이용 PDF (개인 학습용).

앞부분: 문제만(지문 + 5선지 + 사진). 정답/해설 숨김 → 직접 풀기.
뒷부분: 정답 및 해설(정답 번호 + 해설 + 선지별 해설 + 핵심포인트 + 근거).
입력: data_private/lecture_questions/q_*.json
"""

import base64
import html
import json
import mimetypes
import re
from pathlib import Path

SRC = Path("data_private/lecture_questions")
MEDIA = SRC / "media"
OUT_DIR = Path("data_private/anki_exports")


def esc(v):
    return html.escape(str(v or "")).replace("\n", "<br>")


def img_tag(q):
    name = q.get("image")
    if not name:
        return ""
    p = MEDIA / name
    if not p.exists():
        return ""
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f'<div class="qimg"><img src="data:{mime};base64,{b64}" alt="문항 이미지"></div>'


CSS = """
* { box-sizing:border-box; }
body { font-family:"Apple SD Gothic Neo","AppleGothic",sans-serif; color:#172033; font-size:11.5px; line-height:1.55; margin:0; }
h1.cover { font-size:26px; text-align:center; margin:36vh 0 0; color:#0B1F3A; }
.cover-sub { text-align:center; color:#64748b; font-size:13px; margin-top:10px; }
.cover-note { text-align:center; color:#b45309; font-size:11px; margin-top:16px; }
h2.lec { font-size:15.5px; color:#fff; background:#0f766e; padding:8px 14px; border-radius:8px; margin:0 0 12px; page-break-before:always; }
h2.part { font-size:20px; color:#0B1F3A; border-bottom:3px solid #0f766e; padding-bottom:8px; margin:0 0 6px; page-break-before:always; }
.q { border:1px solid #dbe4ef; border-radius:10px; padding:11px 13px; margin:0 0 10px; page-break-inside:avoid; background:#fff; }
.qnum { display:inline-block; min-width:30px; font-weight:800; color:#0f766e; }
.topic { display:inline-block; font-size:10px; font-weight:700; color:#475569; border:1px solid #cbd5e1; border-radius:999px; padding:2px 8px; margin-bottom:6px; }
.stem { font-weight:700; font-size:12.5px; margin:2px 0 8px; }
.qimg { margin:6px 0 10px; text-align:center; page-break-inside:avoid; }
.qimg img { max-width:82%; max-height:360px; border:1px solid #dbe4ef; border-radius:8px; }
.choice { padding:4px 9px; margin:3px 0; border:1px solid #e6edf5; border-radius:6px; }
/* 해설부 */
.a { border-bottom:1px solid #eef2f7; padding:8px 2px; page-break-inside:avoid; }
.a .head { font-weight:800; }
.a .ansnum { color:#065f46; }
.sec { margin-top:4px; }
.sec .t { color:#0f766e; font-weight:800; font-size:10.5px; }
.ce { padding:2px 0; }
.ce.correct { color:#065f46; font-weight:700; } .ce.wrong { color:#7c1d2b; }
ul { margin:3px 0; padding-left:18px; }
.key-tbl { width:100%; border-collapse:collapse; font-size:11px; margin:4px 0 2px; }
.key-tbl td { border:1px solid #dbe4ef; padding:3px 7px; text-align:center; }
.key-tbl td.n { color:#64748b; } .key-tbl td.v { font-weight:800; color:#065f46; }
"""


def lecture_label(lid, source_name):
    m = re.match(r"(\d{4})(\d{2})(\d{2})_([\d_]+교시)_(.+)", str(lid or ""))
    if m:
        _, mo, da, gy, title = m.groups()
        return f"{int(mo)}/{int(da)} {gy.replace('_','·')} · {source_name or title.replace('_',' ')}"
    return source_name or lid


def render_problem(idx, q):
    ch = q.get("choices") or {}
    parts = [f'<span class="topic">Q{idx} · {esc(q.get("topic"))}</span>',
             f'<div class="stem"><span class="qnum">{idx}.</span> {esc(q.get("stem"))}</div>',
             img_tag(q)]
    for k in sorted(ch, key=lambda x: int(x) if str(x).isdigit() else 99):
        if ch.get(k):
            parts.append(f'<div class="choice">{esc(k)}. {esc(ch[k])}</div>')
    return f'<div class="q">{"".join(parts)}</div>'


def render_answer(idx, q):
    ch = q.get("choices") or {}
    ans = q.get("answer")
    parts = [f'<div class="head">{idx}. <span class="ansnum">정답 {esc(ans)}</span> '
             f'— {esc(ch.get(str(ans), ""))}</div>']
    if q.get("explanation"):
        parts.append(f'<div class="sec"><span class="t">해설</span> {esc(q["explanation"])}</div>')
    ce = q.get("choice_explanations") or {}
    rows = []
    for k in sorted(ce, key=lambda x: int(x) if str(x).isdigit() else 99):
        e = ce.get(k)
        if not e:
            continue
        cls = "correct" if str(k) == str(ans) else "wrong"
        rows.append(f'<div class="ce {cls}">{esc(k)}. {esc(e)}</div>')
    if rows:
        parts.append(f'<div class="sec"><span class="t">선지별 해설</span>{"".join(rows)}</div>')
    kp = q.get("key_point") or []
    if kp:
        parts.append('<div class="sec"><span class="t">핵심 포인트</span><ul>'
                     + "".join(f"<li>{esc(x)}</li>" for x in kp) + "</ul></div>")
    ha = q.get("harrison")
    if ha and isinstance(ha, str):
        parts.append(f'<div class="sec"><span class="t">근거</span> {esc(ha)}</div>')
    return f'<div class="a">{"".join(parts)}</div>'


def key_table(qs):
    cells = "".join(
        f'<td class="n">{i}</td>' for i in range(1, len(qs) + 1)
    )
    vals = "".join(f'<td class="v">{esc(q.get("answer"))}</td>' for q in qs)
    return f'<table class="key-tbl"><tr>{cells}</tr><tr>{vals}</tr></table>'


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(SRC.glob("q_*.json"), key=lambda p: p.name)
    lectures = []
    total = 0
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        qs = d.get("questions") or []
        if qs:
            lectures.append((d.get("lecture_id"), d.get("source_name"), qs))
            total += len(qs)

    body = ['<h1 class="cover">혈액종양 강의 연습문항 · 풀이용</h1>'
            f'<div class="cover-sub">{len(lectures)}개 강의 · {total}문항 · 앞=문제 / 뒤=정답·해설</div>'
            '<div class="cover-note">개인 시험대비 학습용 · AI 생성(강의+표준지식 근거) · 원본 슬라이드 대조 권장</div>']

    # 문제부
    for lid, sname, qs in lectures:
        body.append(f'<h2 class="lec">{esc(lecture_label(lid, sname))} ({len(qs)}문항)</h2>')
        for i, q in enumerate(qs, 1):
            body.append(render_problem(i, q))

    # 정답·해설부
    body.append('<h2 class="part">정답 및 해설</h2>')
    for lid, sname, qs in lectures:
        body.append(f'<h2 class="lec">{esc(lecture_label(lid, sname))} — 정답·해설</h2>')
        body.append(key_table(qs))
        for i, q in enumerate(qs, 1):
            body.append(render_answer(i, q))

    html_doc = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    html_path = OUT_DIR / "paccine_혈액종양_강의연습문항_풀이용.html"
    html_path.write_text(html_doc, encoding="utf-8")
    pdf_path = OUT_DIR / "paccine_혈액종양_강의연습문항_풀이용.pdf"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
        pg.pdf(path=str(pdf_path), format="A4", print_background=True,
               margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        b.close()
    print(f"[done] 풀이용 PDF → {pdf_path}  ({len(lectures)}강의 · {total}문항 · {pdf_path.stat().st_size//1024}KB)")


if __name__ == "__main__":
    raise SystemExit(main())
