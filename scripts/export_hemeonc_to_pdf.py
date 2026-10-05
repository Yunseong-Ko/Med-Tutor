#!/usr/bin/env python3
"""혈액종양내과 246문항(3세트)을 Ontology 근거 해설 학습 PDF로 출력.

각 문항: 지문 + (가변)선지 + 정답 + Ontology 근거 해설(통합/정답근거/선지별/핵심포인트)
+ Harrison 근거 앵커(AccessMedicine 링크). answer 미기록은 '검수 필요'로 표기.
playwright HTML→PDF, 이미지 축소 캐시.
"""

import html
import json
import re
from pathlib import Path
from PIL import Image

ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")
EXTRACTED = ROOT / "data_private" / "course_exams" / "extracted"
OUT_DIR = ROOT / "data_private" / "anki_exports"
THUMB_DIR = OUT_DIR / "_hemeonc_thumb_cache"
SOURCES = [
    ("2023 과정시험", "COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험"),
    ("2026 1차", "COURSE_2_20260306_HEMATOLOGY_ONCOLOGY_1차"),
    ("2026 2차", "COURSE_2_20260317_HEMATOLOGY_ONCOLOGY_2차"),
]


def thumb(src_path):
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


def clean_stem(v):
    """실제 이미지를 별도로 렌더하므로, 중복되는 <그림>/＜그림＞ 플레이스홀더 마커를 제거."""
    s = str(v or "")
    s = re.sub(r"[<＜〈\[]?\s*그림\s*[>＞〉\]]?", "", s) if re.search(r"[<＜〈\[]\s*그림\s*[>＞〉\]]", s) else s
    return re.sub(r"\n{2,}", "\n", s).strip()


CSS = """
* { box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo","AppleGothic",sans-serif; color:#172033; font-size:11.5px; line-height:1.5; margin:0; }
h1.cover { font-size:26px; text-align:center; margin:38vh 0 0; color:#0B1F3A; }
.cover-sub { text-align:center; color:#64748b; font-size:13px; margin-top:10px; }
.cover-note { text-align:center; color:#b45309; font-size:11px; margin-top:16px; }
h2.period { font-size:18px; color:#fff; background:#0f766e; padding:8px 14px; border-radius:8px; margin:0 0 14px; page-break-before:always; }
.q { border:1px solid #dbe4ef; border-radius:10px; padding:12px 14px; margin:0 0 12px; page-break-inside:avoid; background:#fff; }
.src { display:inline-block; font-size:10px; font-weight:700; color:#475569; border:1px solid #cbd5e1; border-radius:999px; padding:2px 8px; margin:0 4px 6px 0; }
.onto { display:inline-block; font-size:10px; font-weight:700; color:#0f766e; background:#ecfdf5; border:1px solid #99f6e4; border-radius:999px; padding:2px 8px; margin-bottom:6px; }
.stem { font-weight:700; font-size:12.5px; margin:4px 0 8px; }
.qimg { display:block; max-width:60%; max-height:280px; object-fit:contain; margin:8px auto; border:1px solid #dbe4ef; border-radius:8px; }
.qcap { text-align:center; color:#94a3b8; font-size:9.5px; margin:-4px 0 6px; }
.substmt { margin:8px 0; padding:8px 12px; background:#f8fafc; border:1px solid #dbe4ef; border-radius:8px; }
.subst-row { padding:2px 0; }
.substmt b { color:#0f766e; }
.choice { padding:3px 8px; margin:3px 0; border:1px solid #e6edf5; border-radius:6px; }
.ans { background:#ecfdf5; border-left:4px solid #0f766e; border-radius:6px; padding:7px 10px; margin:8px 0 4px; font-weight:700; color:#064e3b; }
.ans.na { background:#fffbeb; border-left-color:#d97706; color:#92400e; }
.sec { margin-top:6px; }
.sec .t { color:#0f766e; font-weight:800; font-size:10.5px; }
.ce { padding:3px 0; }
.ce.correct { color:#065f46; } .ce.wrong { color:#7c1d2b; }
.harrison { margin-top:6px; font-size:10.5px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px 9px; }
.harrison a { color:#0369a1; text-decoration:none; word-break:break-all; }
.review { margin-top:6px; font-size:9.5px; color:#94a3b8; }
ul { margin:3px 0; padding-left:18px; }
"""


def render_q(label, q, assets_by_storage, posmap):
    ch = q.get("choices") or {}
    ans = q.get("answer")
    g = q.get("ontology_grounding") or {}
    lab = q.get("labels") or {}
    parts = []
    topic = lab.get("subtopic") or lab.get("topic") or ""
    parts.append(f'<div><span class="src">혈액종양내과 · {esc(label)} · Q{esc(q.get("question_number"))} · {esc(topic)}</span>')
    if g.get("disease_concept_id"):
        parts.append(f'<span class="onto">◆ {esc(g.get("label") or g["disease_concept_id"])}</span>')
    parts.append('</div>')
    stim = clean_stem(q.get("stimulus"))
    if stim:
        parts.append(f'<div class="stem" style="font-weight:500">{esc(stim)}</div>')
    parts.append(f'<div class="stem">{esc(clean_stem(q.get("stem")))}</div>')
    # images — use media_positions (accurate per-question map), not the scrambled media_refs
    qn = str(q.get("question_number"))
    seen = set()
    for sid in posmap.get(qn, []):
        if sid in seen:
            continue
        seen.add(sid)
        a = assets_by_storage.get(sid)
        if not a:
            continue
        fp = Path(a.get("file_path") or "")
        if fp.exists() and fp.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".gif"):
            parts.append(f'<img class="qimg" src="file://{thumb(fp).resolve()}">')
            cap = a.get("caption")
            if cap:
                parts.append(f'<div class="qcap">{esc(cap)}</div>')
    # R형 보기(가/나/다/라) — HWP에서 복구, 선지 앞에 표시
    subs = q.get("sub_statements") or {}
    if subs:
        rows = "".join(f'<div class="subst-row"><b>{esc(k)}.</b> {esc(v)}</div>' for k, v in subs.items())
        parts.append(f'<div class="substmt">{rows}</div>')
    # choices (variable count)
    for k in sorted(ch, key=lambda x: int(x) if str(x).isdigit() else 99):
        if ch.get(k):
            parts.append(f'<div class="choice">{esc(k)}. {esc(ch[k])}</div>')
    # answer
    if ans in (None, ""):
        parts.append('<div class="ans na">정답 미기록 · 교수 검수에서 확정 필요</div>')
    else:
        parts.append(f'<div class="ans">정답 {esc(ans)}. {esc(ch.get(str(ans), ""))}</div>')
    if q.get("answer_rationale"):
        parts.append(f'<div class="sec"><span class="t">정답근거</span> {esc(q["answer_rationale"])}</div>')
    if q.get("explanation"):
        parts.append(f'<div class="sec"><span class="t">통합해설</span> {esc(q["explanation"])}</div>')
    # choice explanations (new format: dict of strings; legacy: {rationale})
    ce = q.get("choice_explanations") or {}
    rows = []
    for k in sorted(ce, key=lambda x: int(x) if str(x).isdigit() else 99):
        it = ce.get(k)
        e = txt(it if isinstance(it, str) else (it.get("rationale") or it.get("explanation")) if isinstance(it, dict) else "")
        if not e:
            continue
        cls = "correct" if str(k) == str(ans) else "wrong"
        rows.append(f'<div class="ce {cls}">{esc(k)}. {esc(e)}</div>')
    if rows:
        parts.append(f'<div class="sec"><span class="t">선지별 해설</span>{"".join(rows)}</div>')
    klp = q.get("key_learning_points") or []
    if klp:
        parts.append('<div class="sec"><span class="t">핵심 학습 포인트</span><ul>'
                     + "".join(f"<li>{esc(x)}</li>" for x in klp) + "</ul></div>")
    ha = q.get("harrison_anchor")
    if isinstance(ha, dict) and ha.get("citation"):
        link = f' — <a href="{esc(ha.get("url"))}">AccessMedicine 열람</a>' if ha.get("url") else ""
        parts.append(f'<div class="harrison"><b>근거</b> {esc(ha["citation"])}{link}</div>')
    parts.append('<div class="review">※ Ontology 근거 초안 · 교수 의학검토 전(needs_review)</div>')
    return f'<div class="q">{"".join(parts)}</div>'


def build_html():
    body = ['<h1 class="cover">혈액종양내과 · Ontology 근거 해설집</h1>'
            '<div class="cover-sub">2023 과정시험 · 2026 1차 · 2026 2차 · 246문항 · 해설 포함</div>'
            '<div class="cover-note">교수 의학검토 전 초안(needs_review) · 학생 배포 전 검수 필요</div>']
    total = 0
    for label, stem in SOURCES:
        d = json.loads((EXTRACTED / f"{stem}.json").read_text(encoding="utf-8"))
        assets_by_storage = {a.get("storage_id"): a for a in (d.get("media_assets") or [])}
        posmap = {}
        for m in (d.get("media_positions") or []):
            posmap.setdefault(str(m.get("question_number")), []).append(m.get("storage_id"))
        qs = [q for q in d["questions"] if q.get("choices")]
        body.append(f'<h2 class="period">{label} ({len(qs)}문항)</h2>')
        for q in qs:
            body.append(render_q(label, q, assets_by_storage, posmap))
            total += 1
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(body)}</body></html>", total


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_doc, total = build_html()
    html_path = OUT_DIR / "paccine_혈액종양내과_Ontology해설_20260712.html"
    html_path.write_text(html_doc, encoding="utf-8")
    pdf_path = OUT_DIR / "paccine_혈액종양내과_Ontology해설_20260712.pdf"
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
