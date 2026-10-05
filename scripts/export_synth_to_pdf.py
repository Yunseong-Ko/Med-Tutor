#!/usr/bin/env python3
"""합성 모의고사(세트1·2, 160문항)를 학습용 PDF로 출력.

정답 색표시 없음 + 문항마다 해설 바로 아래 붙임 + Lab 박스 포함.
"""

import html
import json
import re
from pathlib import Path

ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")
EXTRACTED = ROOT / "data_private" / "course_exams" / "extracted"
OUT_DIR = ROOT / "data_private" / "anki_exports"
SOURCES = [("세트1", "SYNTH_2026_MOCK_SET1"), ("세트2", "SYNTH_2026_MOCK_SET2")]


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
.labbox { margin: 8px 0; border: 1px solid #dbe4ef; border-radius: 8px; overflow: hidden; }
.labbox .lt { background: #0f766e; color: #fff; font-weight: 800; padding: 4px 10px; font-size: 10.5px; }
.labbox table { width: 100%; border-collapse: collapse; }
.labbox td { padding: 3px 10px; border-top: 1px solid #edf2f7; font-size: 11px; }
.labbox td.lr { color: #7688a0; text-align: right; font-size: 10px; white-space: nowrap; }
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


def lab_box(lab_values):
    rows = [r for r in (lab_values or []) if r.get("item") or r.get("name")]
    if not rows:
        return ""
    trs = "".join(f'<tr><td>{esc(r.get("item") or r.get("name"))}</td>'
                  f'<td class="lr">{("참고치 " + esc(r["ref"])) if r.get("ref") else ""}</td></tr>' for r in rows)
    return f'<div class="labbox"><div class="lt">검사 결과</div><table>{trs}</table></div>'


def render_q(label, q, assets):
    ans = str(q.get("answer"))
    ch = q.get("choices") or {}
    parts = []
    sysv = (q.get("labels") or {}).get("system") or ((q.get("labels") or {}).get("concept_tags") or [""])[0]
    parts.append(f'<span class="src">합성 모의고사 · {label} · Q{q.get("question_number")} · {esc(sysv)}</span>')
    parts.append(f'<div class="stem">{esc(q.get("stem"))}</div>')
    parts.append(lab_box(q.get("lab_values")))
    for ref in (q.get("media") or {}).get("media_refs") or []:
        a = assets.get(ref.get("media_id"))
        if not a:
            continue
        fp = Path(a.get("file_path") or "")
        if fp.exists() and fp.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".gif"):
            parts.append(f'<img class="qimg" src="file://{fp.resolve()}">')
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
    body = ['<h1 class="cover">합성 임상종합 모의고사 2026</h1>'
            '<div class="cover-sub">세트1·2 · 160문항 · 정답 색표시 없음 · 해설 포함 (AI 생성 초안)</div>']
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
    html_path = OUT_DIR / "paccine_synth_mock_해설붙임_20260708.html"
    html_path.write_text(html_doc, encoding="utf-8")
    pdf_path = OUT_DIR / "paccine_synth_mock_해설붙임_20260708.pdf"
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
