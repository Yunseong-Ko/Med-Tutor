#!/usr/bin/env python3
"""2026 1차 임상의학종합평가 4개 교시(320문항)를 학습용 PDF로 출력.

정답 색표시 없음 + 문항마다 해설 바로 아래 붙임. playwright HTML→PDF.
"""

import html
import json
import re
from pathlib import Path

ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")
EXTRACTED = ROOT / "data_private" / "course_exams" / "extracted"
OUT_DIR = ROOT / "data_private" / "anki_exports"
SOURCES = [
    ("1교시", "COMPREHENSIVE_2026_1CHA_1교시"),
    ("2교시", "COMPREHENSIVE_2026_1CHA_2교시"),
    ("3교시", "COMPREHENSIVE_2026_1CHA_3교시"),
    ("4교시", "COMPREHENSIVE_2026_1CHA_4교시"),
]


from PIL import Image

THUMB_DIR = OUT_DIR / "_1cha_thumb_cache"


def thumb(src_path):
    """고해상도 이미지를 최대 1000px·JPEG로 축소해 PDF 용량을 줄인다."""
    src = Path(src_path)
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    dst = THUMB_DIR / (src.stem + ".jpg")
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    try:
        im = Image.open(src)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((1000, 1000))
        im.save(dst, "JPEG", quality=82)
        return dst
    except Exception:
        return src


def esc(v):
    return html.escape(str(v or "")).replace("\n", "<br>")


def txt(v):
    return re.sub(r"\s+", " ", str(v or "").strip())


CSS = """
* { box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", "AppleGothic", sans-serif; color: #172033;
  font-size: 11.5px; line-height: 1.5; margin: 0; }
h1.cover { font-size: 26px; text-align: center; margin: 40vh 0 0; color: #0B1F3A; }
.cover-sub { text-align: center; color: #64748b; font-size: 13px; margin-top: 10px; }
h2.period { font-size: 18px; color: #fff; background: #0B1F3A; padding: 8px 14px; border-radius: 8px;
  margin: 0 0 14px; page-break-before: always; }
.q { border: 1px solid #dbe4ef; border-radius: 10px; padding: 12px 14px; margin: 0 0 12px;
  page-break-inside: avoid; background: #fff; }
.src { display: inline-block; font-size: 10px; font-weight: 700; color: #475569;
  border: 1px solid #cbd5e1; border-radius: 999px; padding: 2px 8px; margin-bottom: 6px; }
.stem { font-weight: 700; font-size: 12.5px; margin: 4px 0 8px; }
.qimg { display: block; max-width: 62%; max-height: 300px; object-fit: contain; margin: 8px auto;
  border: 1px solid #dbe4ef; border-radius: 8px; }
.qcap { text-align: center; color: #94a3b8; font-size: 9.5px; margin: -4px 0 6px; }
.choice { padding: 3px 8px; margin: 3px 0; border: 1px solid #e6edf5; border-radius: 6px; }
.ans { background: #ecfdf5; border-left: 4px solid #0f766e; border-radius: 6px; padding: 7px 10px;
  margin: 8px 0 4px; font-weight: 700; color: #064e3b; }
.sec { margin-top: 6px; }
.sec .t { color: #0f766e; font-weight: 800; font-size: 10.5px; }
.ce { padding: 3px 0; }
.ce.correct { color: #065f46; } .ce.wrong { color: #7c1d2b; }
ul { margin: 3px 0; padding-left: 18px; }
"""


def render_q(label, q, assets):
    ans = str(q.get("answer"))
    ch = q.get("choices") or {}
    parts = []
    sysv = (q.get("labels") or {}).get("concept_tags") or [""]
    parts.append(f'<span class="src">임상의학종합평가 2026 1차 · {label} · Q{q.get("question_number")} · {esc(sysv[0].replace("_"," "))}</span>')
    parts.append(f'<div class="stem">{esc(q.get("stem"))}</div>')
    for ref in (q.get("media") or {}).get("media_refs") or []:
        a = assets.get(ref.get("media_id"))
        if not a:
            continue
        fp = Path(a.get("file_path") or "")
        if fp.exists() and fp.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".gif"):
            parts.append(f'<img class="qimg" src="file://{thumb(fp).resolve()}">')
            cap = a.get("caption") or ref.get("caption")
            if cap:
                parts.append(f'<div class="qcap">{esc(cap)}</div>')
    for k in ["1", "2", "3", "4", "5"]:
        if ch.get(k):
            parts.append(f'<div class="choice">{k}. {esc(ch[k])}</div>')
    parts.append(f'<div class="ans">정답 {ans}. {esc(ch.get(ans,""))}</div>')
    if q.get("answer_rationale"):
        parts.append(f'<div class="sec"><span class="t">정답근거</span> {esc(q["answer_rationale"])}</div>')
    if q.get("explanation"):
        parts.append(f'<div class="sec"><span class="t">통합해설</span> {esc(q["explanation"])}</div>')
    ce = q.get("choice_explanations") or {}
    if ce:
        rows = []
        for k in sorted(ce, key=lambda x: int(x) if str(x).isdigit() else 99):
            it = ce.get(k) or {}
            e = txt(it.get("rationale") or it.get("explanation"))
            if not e:
                continue
            cls = "correct" if (str(k) == ans or it.get("is_correct")) else "wrong"
            rows.append(f'<div class="ce {cls}">{k}. {esc(e)}</div>')
        if rows:
            parts.append(f'<div class="sec"><span class="t">선지별 해설</span>{"".join(rows)}</div>')
    klp = q.get("key_learning_points") or []
    if klp:
        parts.append('<div class="sec"><span class="t">핵심 학습 포인트</span><ul>'
                     + "".join(f"<li>{esc(x)}</li>" for x in klp) + "</ul></div>")
    return f'<div class="q">{"".join(parts)}</div>'


def build_html():
    body = ['<h1 class="cover">임상의학종합평가 2026 · 1차</h1>'
            '<div class="cover-sub">1~4교시 · 320문항 · 정답 색표시 없음 · 해설 포함</div>']
    total = 0
    for label, stem in SOURCES:
        d = json.loads((EXTRACTED / f"{stem}.json").read_text(encoding="utf-8"))
        assets = {a.get("media_id"): a for a in (d.get("media_assets") or [])}
        qs = [q for q in d["questions"] if q.get("choices")]
        body.append(f'<h2 class="period">{label} ({len(qs)}문항)</h2>')
        for q in qs:
            body.append(render_q(label, q, assets))
            total += 1
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(body)}</body></html>", total


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_doc, total = build_html()
    html_path = OUT_DIR / "paccine_1cha_2026_해설붙임_20260708.html"
    html_path.write_text(html_doc, encoding="utf-8")
    pdf_path = OUT_DIR / "paccine_1cha_2026_해설붙임_20260708.pdf"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto(f"file://{html_path}", wait_until="networkidle")
        page.pdf(path=str(pdf_path), format="A4", print_background=True,
                 margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        b.close()
    print(f"[done] PDF → {pdf_path}  ({total}문항, {pdf_path.stat().st_size//1024}KB)")


if __name__ == "__main__":
    raise SystemExit(main())
