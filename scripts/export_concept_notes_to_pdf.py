#!/usr/bin/env python3
"""질환 노트(JSON) → AMBOSS식 학습 모노그래프 PDF.

섹션 헤딩·본문(출처태그 [O]/[보강] 강조)·고위험 검증박스·감별 구분점·Harrison 근거·
provenance 푸터·needs_review 배너. playwright HTML→PDF.
입력: scratchpad/concept_notes/note_*.json (+ hemophilia_note_sample.json)
"""

import html
import json
import re
from pathlib import Path

SRC = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad/concept_notes")
EXTRA = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad/hemophilia_note_sample.json")
OUT_DIR = Path("data_private/anki_exports")

SECTION_ORDER = ["요약", "역학", "병인·유전", "병인/유전", "병태생리", "임상양상", "진단",
                 "치료", "합병증·예후", "합병증/예후", "감별진단", "근거"]


def esc(v):
    return html.escape(str(v or ""))


def tagify(text):
    """[O]/[보강] 출처태그를 배지로."""
    s = esc(text).replace("\n", "<br>")
    s = s.replace("[O]", '<span class="tag o">O</span>')
    s = s.replace("[보강]", '<span class="tag aug">보강</span>')
    s = re.sub(r"verify\s*[:：]\s*true", '<span class="verify">⚠검증</span>', s, flags=re.I)
    return s


CSS = """
* { box-sizing: border-box; }
body { font-family:"Apple SD Gothic Neo","AppleGothic",sans-serif; color:#172033; font-size:11.5px; line-height:1.6; margin:0; }
h1.cover { font-size:26px; text-align:center; margin:38vh 0 0; color:#0B1F3A; }
.cover-sub { text-align:center; color:#64748b; font-size:13px; margin-top:10px; }
.cover-note { text-align:center; color:#b45309; font-size:11px; margin-top:16px; }
.note { page-break-before:always; padding:4px 2px; }
.note-title { font-size:20px; font-weight:800; color:#0B1F3A; margin:0 0 2px; }
.note-cid { font-size:10px; color:#94a3b8; margin-bottom:8px; }
.review-banner { background:#fffbeb; border:1px solid #fde68a; color:#92400e; border-radius:8px; padding:6px 10px; font-size:10.5px; font-weight:700; margin-bottom:10px; }
.sec { margin:0 0 10px; page-break-inside:avoid; }
.sec h2 { font-size:13px; color:#0f766e; border-left:4px solid #0f766e; padding-left:8px; margin:0 0 5px; }
.sec .body { padding-left:10px; }
.tag { display:inline-block; font-size:8.5px; font-weight:800; border-radius:4px; padding:0 4px; margin:0 1px; vertical-align:middle; }
.tag.o { background:#ecfdf5; color:#065f46; border:1px solid #99f6e4; }
.tag.aug { background:#eff6ff; color:#1e40af; border:1px solid #bfdbfe; }
.verify { display:inline-block; font-size:8.5px; font-weight:800; color:#b42318; background:#fef2f2; border:1px solid #fecaca; border-radius:4px; padding:0 4px; }
.hs { background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:8px 10px; margin:8px 0; }
.hs .t { color:#b42318; font-weight:800; font-size:11px; }
.hs li { margin:2px 0; }
.diff { padding-left:10px; }
.diff li { margin:3px 0; }
.harrison { margin-top:8px; font-size:10.5px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px 9px; }
.harrison a { color:#0369a1; text-decoration:none; word-break:break-all; }
.prov { margin-top:6px; font-size:9.5px; color:#94a3b8; }
ul { margin:3px 0; padding-left:18px; }
"""


def render_note(d):
    parts = [f'<div class="note-title">{esc(d.get("title") or d.get("disease_concept_id"))}</div>',
             f'<div class="note-cid">{esc(d.get("disease_concept_id"))} · Ontology 근거 초안</div>',
             '<div class="review-banner">⚠ 교수 의학검토 전 초안(needs_review) · 고위험 수치(용량·목표치·역치)는 검증 전 학습참고만 · 근거: Ontology + Harrison</div>']
    secs = d.get("sections") or {}
    seen = set()
    for name in SECTION_ORDER + list(secs.keys()):
        if name in seen or name not in secs:
            continue
        seen.add(name)
        s = secs[name]
        body = s.get("body") if isinstance(s, dict) else s
        if not body:
            continue
        parts.append(f'<div class="sec"><h2>{esc(name)}</h2><div class="body">{tagify(body)}</div></div>')
    # 고위험 검증박스
    hs = d.get("high_stakes") or []
    if hs:
        rows = "".join(f'<li><b>{esc(h.get("item"))}</b>: {esc(h.get("value"))} <span class="verify">⚠검증</span></li>' for h in hs)
        parts.append(f'<div class="hs"><span class="t">⚠ 교수 검증 필요 — 고위험 수치 {len(hs)}건</span><ul>{rows}</ul></div>')
    # 감별(구조화)
    diffs = d.get("differentials") or []
    if diffs:
        rows = "".join(f'<li><b>{esc(x.get("id"))}</b> — {esc(x.get("구분점"))}</li>' for x in diffs if x.get("구분점"))
        if rows:
            parts.append(f'<div class="sec"><h2>감별 요약(구분점)</h2><ul class="diff">{rows}</ul></div>')
    ha = d.get("harrison_anchor") or {}
    if ha.get("citation"):
        link = f' — <a href="{esc(ha.get("url"))}">AccessMedicine</a>' if ha.get("url") else ""
        parts.append(f'<div class="harrison"><b>근거</b> {esc(ha["citation"])}{link}</div>')
    pv = d.get("provenance") or {}
    if pv:
        parts.append(f'<div class="prov">provenance: 온톨로지발 {pv.get("ontology_facts","?")} · 표준지식 보강 {pv.get("augmented_facts","?")} · source={esc(d.get("source"))}</div>')
    return f'<div class="note">{"".join(parts)}</div>'


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(SRC.glob("note_*.json"))
    notes = []
    for f in files:
        try:
            notes.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    if EXTRA.exists():
        try:
            notes.append(json.loads(EXTRA.read_text(encoding="utf-8")))
        except Exception:
            pass
    notes.sort(key=lambda d: d.get("title") or d.get("disease_concept_id") or "")
    body = ['<h1 class="cover">혈액종양 질환 노트집 — Ontology × Harrison</h1>'
            f'<div class="cover-sub">{len(notes)}개 질환 · AMBOSS식 구조 · 출처태그(O/보강) · 고위험 검증표시</div>'
            '<div class="cover-note">교수 의학검토 전 초안 · 학생 배포 전 검수 필요</div>']
    for d in notes:
        body.append(render_note(d))
    html_doc = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    html_path = OUT_DIR / "paccine_혈액종양_질환노트집_20260712.html"
    html_path.write_text(html_doc, encoding="utf-8")
    pdf_path = OUT_DIR / "paccine_혈액종양_질환노트집_20260712.pdf"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
        pg.pdf(path=str(pdf_path), format="A4", print_background=True,
               margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"})
        b.close()
    print(f"[done] PDF → {pdf_path}  ({len(notes)}개 노트, {pdf_path.stat().st_size//1024}KB)")


if __name__ == "__main__":
    raise SystemExit(main())
