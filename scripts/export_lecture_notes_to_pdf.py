#!/usr/bin/env python3
"""강의별 노트정리(JSON) → 학습 PDF (개인 학습용).

강의(교시)순. 각 강의: 큰 그림(서사) + 임상 핵심 포인트 + 용어집 + 관련 개념/Harrison.
입력: data_private/lecture_notes/note_*.json (없으면 scratchpad). allowlist(_include_lids.json) 지원.
"""

import html
import json
import re
from pathlib import Path

SRC = Path("data_private/lecture_notes")
Q_DIR = Path("data_private/lecture_questions")  # allowlist 공유
OUT_DIR = Path("data_private/anki_exports")


def esc(v):
    return html.escape(str(v or "")).replace("\n", "<br>")


def lecture_label(lid, source_name):
    m = re.match(r"(\d{4})(\d{2})(\d{2})_([\d_]+교시)_(.+)", str(lid))
    if m:
        _, mo, da, gy, title = m.groups()
        return f"{int(mo)}/{int(da)} {gy.replace('_','·')} · {source_name or title.replace('_',' ')}"
    return source_name or lid


CSS = """
* { box-sizing:border-box; }
body { font-family:"Apple SD Gothic Neo","AppleGothic",sans-serif; color:#172033; font-size:12px; line-height:1.65; margin:0; }
h1.cover { font-size:26px; text-align:center; margin:38vh 0 0; color:#0B1F3A; }
.cover-sub { text-align:center; color:#64748b; font-size:13px; margin-top:10px; }
.cover-note { text-align:center; color:#b45309; font-size:11px; margin-top:16px; }
h2.lec { font-size:16px; color:#fff; background:#0f766e; padding:9px 14px; border-radius:8px; margin:0 0 12px; page-break-before:always; }
.sec { margin:0 0 12px; page-break-inside:avoid; }
.sec h3 { font-size:13px; color:#0f766e; border-left:4px solid #0f766e; padding-left:8px; margin:0 0 6px; }
.big { background:#f1f5f9; border:1px solid #dbe4ef; border-radius:10px; padding:12px 14px; }
.kp { padding-left:6px; } .kp li { margin:4px 0; }
.gloss { width:100%; border-collapse:collapse; }
.gloss td { border-top:1px solid #edf2f7; padding:5px 8px; vertical-align:top; }
.gloss .term { font-weight:800; color:#0B1F3A; width:34%; }
.harr { font-size:11px; color:#475569; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px 9px; margin-top:6px; }
ul { margin:4px 0; padding-left:18px; }
"""


def render_note(d):
    parts = []
    if d.get("big_picture"):
        parts.append(f'<div class="sec"><h3>큰 그림 (이해)</h3><div class="big">{esc(d["big_picture"])}</div></div>')
    kp = d.get("key_points") or []
    if kp:
        parts.append('<div class="sec"><h3>임상 핵심 포인트</h3><ul class="kp">'
                     + "".join(f"<li>{esc(x)}</li>" for x in kp if x) + "</ul></div>")
    gl = d.get("glossary") or []
    if gl:
        rows = "".join(f'<tr><td class="term">{esc(g.get("term"))}</td><td>{esc(g.get("def"))}</td></tr>'
                       for g in gl if g.get("term"))
        parts.append(f'<div class="sec"><h3>용어집</h3><table class="gloss">{rows}</table></div>')
    ha = d.get("harrison") or []
    if ha:
        parts.append('<div class="harr"><b>근거(Harrison)</b> ' + " · ".join(esc(x) for x in ha) + '</div>')
    return "".join(parts)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    allow = None
    ap = Q_DIR / "_include_lids.json"
    if ap.exists():
        try:
            allow = set(json.loads(ap.read_text(encoding="utf-8")))
        except Exception:
            allow = None
    files = sorted(SRC.glob("note_*.json"), key=lambda p: p.name)
    notes = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if allow is not None and d.get("lecture_id") not in allow:
            continue
        notes.append(d)
    notes.sort(key=lambda d: str(d.get("lecture_id")))
    body = ['<h1 class="cover">혈액종양 강의 노트정리</h1>'
            f'<div class="cover-sub">{len(notes)}개 강의 · 큰그림 · 핵심포인트 · 용어집</div>'
            '<div class="cover-note">개인 학습용 · AI 생성(강의+Ontology 근거) · 원본 슬라이드 대조 권장</div>']
    for d in notes:
        body.append(f'<h2 class="lec">{esc(lecture_label(d.get("lecture_id"), d.get("source_name")))}</h2>')
        body.append(render_note(d))
    html_doc = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    html_path = OUT_DIR / "paccine_혈액종양_강의노트정리_20260715.html"
    html_path.write_text(html_doc, encoding="utf-8")
    pdf_path = OUT_DIR / "paccine_혈액종양_강의노트정리_20260715.pdf"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
        pg.pdf(path=str(pdf_path), format="A4", print_background=True,
               margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"})
        b.close()
    print(f"[done] PDF → {pdf_path}  ({len(notes)}개 강의 · {pdf_path.stat().st_size//1024}KB)")


if __name__ == "__main__":
    raise SystemExit(main())
