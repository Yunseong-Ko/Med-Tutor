#!/usr/bin/env python3
"""강의별 시험대비 연습문항(JSON) → 학습 PDF (개인 학습용).

강의(교시) 순으로 그룹. 각 문항: 지문 + 5선지 + 정답 + 해설 + 핵심포인트.
입력: scratchpad/lecture_questions/q_*.json
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
    """문항 이미지가 있으면 base64로 인라인 임베드(자체완결 PDF/HTML)."""
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
h1.cover { font-size:26px; text-align:center; margin:38vh 0 0; color:#0B1F3A; }
.cover-sub { text-align:center; color:#64748b; font-size:13px; margin-top:10px; }
.cover-note { text-align:center; color:#b45309; font-size:11px; margin-top:16px; }
h2.lec { font-size:16px; color:#fff; background:#0f766e; padding:8px 14px; border-radius:8px; margin:0 0 12px; page-break-before:always; }
.q { border:1px solid #dbe4ef; border-radius:10px; padding:11px 13px; margin:0 0 11px; page-break-inside:avoid; background:#fff; }
.topic { display:inline-block; font-size:10px; font-weight:700; color:#475569; border:1px solid #cbd5e1; border-radius:999px; padding:2px 8px; margin-bottom:6px; }
.stem { font-weight:700; font-size:12.5px; margin:2px 0 8px; }
.qimg { margin:6px 0 10px; text-align:center; page-break-inside:avoid; }
.qimg img { max-width:82%; max-height:340px; border:1px solid #dbe4ef; border-radius:8px; }
.choice { padding:3px 8px; margin:3px 0; border:1px solid #e6edf5; border-radius:6px; }
.ans { background:#ecfdf5; border-left:4px solid #0f766e; border-radius:6px; padding:7px 10px; margin:8px 0 4px; font-weight:700; color:#064e3b; }
.sec { margin-top:6px; }
.sec .t { color:#0f766e; font-weight:800; font-size:10.5px; }
.ce { padding:3px 0; }
.ce.correct { color:#065f46; } .ce.wrong { color:#7c1d2b; }
ul { margin:3px 0; padding-left:18px; }
"""


def render_q(idx, q):
    ch = q.get("choices") or {}
    ans = q.get("answer")
    parts = [f'<span class="topic">Q{idx} · {esc(q.get("topic"))}</span>',
             f'<div class="stem">{esc(q.get("stem"))}</div>',
             img_tag(q)]
    for k in sorted(ch, key=lambda x: int(x) if str(x).isdigit() else 99):
        if ch.get(k):
            parts.append(f'<div class="choice">{esc(k)}. {esc(ch[k])}</div>')
    if ans not in (None, ""):
        parts.append(f'<div class="ans">정답 {esc(ans)}. {esc(ch.get(str(ans), ""))}</div>')
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
    return f'<div class="q">{"".join(parts)}</div>'


def lecture_label(lid, source_name):
    # 20260713_3교시_조혈_및_총론 → "7/13 3교시 · 조혈 및 총론"
    m = re.match(r"(\d{4})(\d{2})(\d{2})_([\d_]+교시)_(.+)", lid)
    if m:
        _, mo, da, gy, title = m.groups()
        return f"{int(mo)}/{int(da)} {gy.replace('_','·')} · {source_name or title.replace('_',' ')}"
    return source_name or lid


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # 현재 강의만 포함(있으면). stale/이름변경된 강의 문항 제외.
    allow = None
    allow_path = SRC / "_include_lids.json"
    if allow_path.exists():
        try:
            allow = set(json.loads(allow_path.read_text(encoding="utf-8")))
        except Exception:
            allow = None
    files = sorted(SRC.glob("q_*.json"), key=lambda p: p.name)
    lectures = []
    total = 0
    skipped = 0
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        lid = d.get("lecture_id")
        if allow is not None and lid not in allow:
            skipped += 1
            continue
        qs = d.get("questions") or []
        if qs:
            lectures.append((lid, d.get("source_name"), qs))
            total += len(qs)
    if skipped:
        print(f"  (allowlist 밖 stale 강의 {skipped}개 제외)")
    body = ['<h1 class="cover">혈액종양 강의 연습문항집</h1>'
            f'<div class="cover-sub">{len(lectures)}개 강의 · {total}문항 · 정답·해설 포함</div>'
            '<div class="cover-note">개인 시험대비 학습용 · AI 생성(강의+표준지식 근거) · 원본 슬라이드 대조 권장</div>']
    for lid, sname, qs in lectures:
        body.append(f'<h2 class="lec">{esc(lecture_label(lid, sname))} ({len(qs)}문항)</h2>')
        for i, q in enumerate(qs, 1):
            body.append(render_q(i, q))
    html_doc = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    html_path = OUT_DIR / "paccine_혈액종양_강의연습문항_20260712.html"
    html_path.write_text(html_doc, encoding="utf-8")
    pdf_path = OUT_DIR / "paccine_혈액종양_강의연습문항_20260712.pdf"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
        pg.pdf(path=str(pdf_path), format="A4", print_background=True,
               margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        b.close()
    print(f"[done] PDF → {pdf_path}  ({len(lectures)}강의 · {total}문항 · {pdf_path.stat().st_size//1024}KB)")


if __name__ == "__main__":
    raise SystemExit(main())
