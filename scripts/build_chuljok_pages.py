#!/usr/bin/env python3
"""출족 2020·2021·2022·2023·2026 → 원본 페이지 이미지(무손실) + 재작성 해설.

텍스트 파싱은 2단 레이아웃에서 답·해설·그림을 유실하므로, 대상 연도 문항이 있는
원본 페이지를 그대로 이미지로 가져와(문제·선지·정답·해설·그림 온전) 연도별로 재조립.
각 페이지 아래에 AI 재작성 해설(있으면)을 얹는다. 전부 needs_review.
출력: data_private/exam_final/출족_연도별_원본이미지_2020_2026.pdf
"""
import base64
import html
import io
import json
import re
from collections import defaultdict
from pathlib import Path

import fitz
from PIL import Image

BASE = Path("data_private/exam_final")
SRC = "/Users/goyunseong/Downloads/[출족]혈액 및 종양학 출족(2).pdf"
TARGET = ["2020", "2021", "2022", "2023", "2026"]
DPI = 175


def h(s):
    return html.escape(str(s or ""))


def skey(s):
    return re.sub(r"\s+", "", str(s or ""))[:50].lower()


def page_jpeg_uri(doc, pageno):
    pix = doc[pageno - 1].get_pixmap(matrix=fitz.Matrix(DPI / 72, DPI / 72))
    im = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def main():
    qs = json.load(open("data_private/chuljok/parsed.json", encoding="utf-8"))
    newx = {}
    nx = Path("data_private/chuljok/new_explanations.json")
    if nx.exists():
        for r in json.loads(nx.read_text(encoding="utf-8")):
            if r.get("new_explanation"):
                newx[r["stem_key"]] = r

    tgt = [q for q in qs if q["year"] in TARGET and q["stem"]]
    # page -> questions; primary year = max target year on page
    bypage = defaultdict(list)
    for q in tgt:
        bypage[q["page"]].append(q)
    page_year = {}
    for pg, ql in bypage.items():
        page_year[pg] = max(q["year"] for q in ql if q["year"] in TARGET)
    year_pages = defaultdict(list)
    for pg, y in page_year.items():
        year_pages[y].append(pg)

    doc = fitz.open(SRC)
    toc, body = [], []
    n_pages = 0
    for y in TARGET:
        pages = sorted(year_pages.get(y, []))
        if not pages:
            continue
        toc.append(f'<div class="titem"><a href="#y{y}">{y}년</a><span class="tq">{len(pages)}쪽</span></div>')
        body.append(f'<h1 class="ysec" id="y{y}">{y}년 <small>{len(pages)}쪽</small></h1>')
        for pg in pages:
            uri = page_jpeg_uri(doc, pg)
            n_pages += 1
            # 재작성 해설 (이 페이지의 대상 문항들)
            rw = ""
            for q in bypage[pg]:
                if q["year"] not in TARGET:
                    continue
                rec = newx.get(skey(q["stem"]))
                if not rec:
                    continue
                ca = rec.get("answer_confirm")
                warn = ' <span class="warn">⚠️ 원본정답과 상이 — 재검토</span>' if rec.get("conflict") else ""
                rw += (f'<div class="rw"><div class="rwq">✍️ {h(q["stem"][:60])}…</div>'
                       f'<div class="rwa">재작성 판단 정답 {h(str(ca))}{warn}</div>'
                       f'<div class="rwe">{h(rec["new_explanation"])}</div></div>')
            body.append(f'<div class="pg"><div class="pgcap">원본 p.{pg} · {y}년</div>'
                        f'<img class="pgimg" src="{uri}">' + (f'<div class="rwbox">{rw}</div>' if rw else "") + '</div>')

    cover = ('<section class="cover"><div class="cbrand">본2-1 · 혈액 및 종양학</div>'
             '<h1 class="ctitle">출족 연도별 (원본 이미지)</h1><div class="csub">2020 · 2021 · 2022 · 2023 · 2026</div>'
             f'<div class="cmeta"><span><b>{len(tgt)}</b><small>문항</small></span>'
             f'<span><b>{n_pages}</b><small>원본 쪽</small></span></div>'
             '<div class="cnote">원본 페이지를 그대로 가져와 문제·선지·정답·해설·그림이 온전합니다<br>각 쪽 아래 ✍️ 재작성 해설(있으면) · 전부 needs_review</div></section>')
    toc_html = '<section class="toc"><h2 class="pgh">연도별 목차</h2>' + "".join(toc) + "</section>"

    css = """
@page{margin:10mm;}
body{font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;background:#fff;color:#111827;line-height:1.55;margin:0 auto;padding:0;font-size:14px;}
.cover{page-break-after:always;min-height:88vh;display:flex;flex-direction:column;justify-content:center;text-align:center;background:linear-gradient(160deg,#334155,#0e7c7b);color:#fff;padding:50px;}
.cbrand{letter-spacing:3px;font-weight:800;font-size:13px;opacity:.85;} .ctitle{color:#fff;font-size:40px;margin:14px 0 6px;} .csub{font-size:17px;opacity:.92;font-weight:600;letter-spacing:2px;}
.cmeta{display:flex;justify-content:center;gap:32px;margin:26px 0;} .cmeta b{font-size:32px;} .cmeta small{opacity:.85;font-size:12px;display:block;} .cnote{font-size:12px;opacity:.85;line-height:1.7;}
.toc{page-break-after:always;padding:24px;} .pgh{color:#0e7c7b;font-size:24px;border-bottom:3px solid #0e7c7b;padding-bottom:6px;}
.titem{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dotted #ddd3bf;font-size:16px;} .toc a{color:#0b5450;text-decoration:none;font-weight:800;} .tq{background:#e6f3f2;color:#0b5450;font-weight:800;font-size:12px;padding:2px 9px;border-radius:999px;}
h1.ysec{page-break-before:always;color:#fff;background:#0e7c7b;font-size:26px;padding:8px 14px;margin:0;}
.pg{page-break-before:always;padding:6px 10px 14px;} .pgcap{font-size:11px;color:#94a3b8;font-weight:700;margin:4px 0;} .pgimg{width:100%;max-width:820px;display:block;margin:0 auto;border:1px solid #e5e7eb;}
.rwbox{max-width:820px;margin:10px auto 0;} .rw{border-left:4px solid #0e7c7b;background:#f0fdfa;border-radius:0 8px 8px 0;padding:9px 12px;margin:8px 0;} .rwq{font-size:12px;color:#64748b;font-weight:700;} .rwa{font-weight:800;color:#0b5450;margin:3px 0;} .rwe{font-size:13px;color:#374151;} .warn{font-size:11px;font-weight:800;color:#b91c1c;background:#fde8e8;padding:1px 6px;border-radius:5px;}
"""
    doc_html = (f"<!doctype html><html lang=ko><head><meta charset=utf-8><title>출족 연도별 원본이미지</title>"
                f"<style>{css}</style></head><body>{cover}{toc_html}" + "".join(body) + "</body></html>")
    out_html = BASE / "출족_연도별_원본이미지_2020_2026.html"
    out_html.write_text(doc_html, encoding="utf-8")
    from playwright.sync_api import sync_playwright
    p = out_html.resolve()
    foot = ('<div style="font-size:9px;width:100%;text-align:center;color:#9aa4b0;">'
            '출족 연도별 원본이미지 2020~2026 · <span class="pageNumber"></span></div>')
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(); pg.goto(f"file://{p}")
        pg.pdf(path=str(BASE / "출족_연도별_원본이미지_2020_2026.pdf"), format="A4", print_background=True,
               display_header_footer=True, header_template="<div></div>", footer_template=foot,
               margin={"top": "8mm", "bottom": "12mm", "left": "8mm", "right": "8mm"})
        b.close()
    print(f"[done] 원본 쪽 {n_pages} · 대상 문항 {len(tgt)}")
    for y in TARGET:
        print(f"  {y}: {len(year_pages.get(y, []))}쪽")


if __name__ == "__main__":
    main()
