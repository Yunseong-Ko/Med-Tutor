#!/usr/bin/env python3
"""출족 파싱 결과 → 2020·2021·2022·2023·2026 연도별 정리 PDF.

해설: data_private/chuljok/new_explanations.json 있으면 재작성 해설 사용, 없으면 원본.
이미지 의존 문항은 '원본 PDF p.N 참조'로 표시.
출력: data_private/exam_final/출족_연도별정리_2020_2026.{html,pdf}
"""
import base64
import html
import json
import re
from pathlib import Path

BASE = Path("data_private/exam_final")
TARGET = ["2020", "2021", "2022", "2023", "2026"]
CIRC = {"1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤", "6": "⑥", "7": "⑦", "8": "⑧", "9": "⑨"}
IMG = re.compile(r"다음과 같|소견은|방사선 소견|사진|그림|아래 (사진|그림|소견)|figure|도판|조직 소견|말초혈액|골수 소견|영상")
STRONG_IMG = re.compile(r"방사선 소견|사진|그림|그래프|도판|조직 소견|골수 소견|말초혈액|영상|X-?ray|소견은 (다음|아래)|다음과 같은 (소견|그림|사진)")


def h(s):
    return html.escape(str(s or ""))


def img_datauri(p):
    try:
        return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()
    except Exception:
        return None


def main():
    qs = json.load(open("data_private/chuljok/parsed.json", encoding="utf-8"))
    def skey(s):
        return re.sub(r"\s+", "", str(s or ""))[:50].lower()
    pimg = {}
    pip = Path("data_private/chuljok/page_images.json")
    if pip.exists():
        pimg = json.loads(pip.read_text(encoding="utf-8"))
    newx = {}
    nx = Path("data_private/chuljok/new_explanations.json")
    if nx.exists():
        for r in json.loads(nx.read_text(encoding="utf-8")):
            if r.get("new_explanation"):
                newx[r["stem_key"]] = r

    tgt = [q for q in qs if q["year"] in TARGET and q["stem"] and len(q["choices"]) >= 2]
    by_year = {y: [] for y in TARGET}
    for q in tgt:
        by_year[q["year"]].append(q)
    for y in TARGET:
        by_year[y].sort(key=lambda q: (q["topic"], q["page"], q["qnum"]))

    toc, body = [], []
    n_new = 0
    for y in TARGET:
        ql = by_year[y]
        if not ql:
            continue
        toc.append(f'<div class="titem"><a href="#y{y}">{y}년</a><span class="tq">{len(ql)}문항</span></div>')
        body.append(f'<h1 class="ysec" id="y{y}">{y}년 <small>{len(ql)}문항</small></h1>')
        cur_topic = None
        for i, q in enumerate(ql, 1):
            if q["topic"] != cur_topic:
                cur_topic = q["topic"]
                body.append(f'<h2 class="tp">{h(cur_topic)}</h2>')
            ch = "".join(f'<div class="ch">{CIRC.get(k, k)} {h(v)}</div>'
                         for k, v in sorted(q["choices"].items(), key=lambda x: int(x[0]) if x[0].isdigit() else 9) if v)
            img = ""
            if IMG.search(q["stem"]):
                strong = bool(STRONG_IMG.search(q["stem"]))
                figs = ""
                fullpage = False
                for im in pimg.get(str(q["page"]), []):
                    # 실사 도판은 항상, 페이지 렌더 폴백은 강한 이미지 키워드일 때만
                    if im.get("fullpage") and not strong:
                        continue
                    uri = img_datauri(im["path"])
                    if uri:
                        cls = "figfull" if im.get("fullpage") else "fig"
                        figs += f'<img class="{cls}" src="{uri}">'
                        fullpage = fullpage or im.get("fullpage", False)
                if figs:
                    cap = (f"📄 원본 페이지 전체 (p.{q['page']}) — 그래프/도판 포함"
                           if fullpage else f"📷 원본 도판 (p.{q['page']})")
                    img = f'<div class="figbox"><div class="figcap">{cap}</div>{figs}</div>'
                elif strong:
                    img = f'<div class="imgtag">🖼 도판은 원본 PDF p.{q["page"]} 참조</div>'
            others = [yy for yy in q.get("years", []) if yy in TARGET and yy != y]
            yrs = f'<span class="oyr">also {"·".join(others)}</span>' if others else ""
            rec = newx.get(skey(q["stem"]))
            ans = q.get("answer")
            if ans:
                ans_disp = f'정답 {CIRC.get(str(ans), ans)}'
                if rec and rec.get("conflict"):
                    ca = rec.get("answer_confirm")
                    ans_disp += f' <span class="warn">⚠️ 재작성은 {CIRC.get(str(ca), ca)}로 판단 — 정답 재검토</span>'
            elif rec and rec.get("answer_confirm"):
                ca = rec["answer_confirm"]
                ans_disp = f'정답 {CIRC.get(str(ca), ca)} <span class="softwarn">(재작성 판단 · 원본 미표기)</span>'
            else:
                ans_disp = '정답 미표기(원본 확인)'
            tag = '<span class="ntag">재작성</span>' if rec else '<span class="otag">원본</span>'
            if rec:
                n_new += 1
            expl = (rec["new_explanation"] if rec else q.get("orig_explanation")) or "(해설 없음)"
            body.append(
                f'<div class="q"><div class="qs"><span class="qn">{i}</span>{h(q["stem"])}{yrs}</div>'
                f'{img}<div class="chs">{ch}</div>'
                f'<div class="ans">{tag}<b>{ans_disp}</b></div>'
                f'<div class="ex">{h(expl)}</div></div>')

    cover = ('<section class="cover"><div class="cbrand">본2-1 · 혈액 및 종양학</div>'
             '<h1 class="ctitle">출족 연도별 정리</h1><div class="csub">2020 · 2021 · 2022 · 2023 · 2026</div>'
             f'<div class="cmeta"><span><b>{len(tgt)}</b><small>문항</small></span>'
             f'<span><b>{len(TARGET)}</b><small>개 연도</small></span></div>'
             '<div class="cnote">원본 [출족] 파싱 · 연도 태그 필터 · 해설 AI 재작성(재작성 태그) · 원본 도판 삽입<br>정답충돌은 ⚠️로, 정답은 원본 출족 기준 · 전부 needs_review</div></section>')
    toc_html = '<section class="toc"><h2 class="pgh">연도별 목차</h2>' + "".join(toc) + "</section>"

    css = """
@page{margin:14mm;}
body{font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;background:#fff;color:#111827;line-height:1.6;max-width:840px;margin:0 auto;padding:24px;font-size:14.5px;}
.cover{page-break-after:always;min-height:84vh;display:flex;flex-direction:column;justify-content:center;text-align:center;background:linear-gradient(160deg,#334155,#0e7c7b);color:#fff;border-radius:18px;padding:40px;}
.cbrand{letter-spacing:3px;font-weight:800;font-size:13px;opacity:.85;} .ctitle{color:#fff;font-size:42px;margin:14px 0 6px;} .csub{font-size:17px;opacity:.92;font-weight:600;letter-spacing:2px;}
.cmeta{display:flex;justify-content:center;gap:32px;margin:26px 0;} .cmeta b{font-size:32px;} .cmeta small{opacity:.85;font-size:12px;display:block;} .cnote{font-size:12px;opacity:.82;line-height:1.7;}
.toc{page-break-after:always;} .pgh{color:#0e7c7b;font-size:24px;border-bottom:3px solid #0e7c7b;padding-bottom:6px;}
.titem{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dotted #ddd3bf;font-size:16px;} .toc a{color:#0b5450;text-decoration:none;font-weight:800;} .tq{background:#e6f3f2;color:#0b5450;font-weight:800;font-size:12px;padding:2px 9px;border-radius:999px;}
h1.ysec{page-break-before:always;color:#fff;background:#0e7c7b;font-size:26px;padding:8px 14px;border-radius:8px;margin-top:20px;} h1.ysec small{opacity:.85;font-size:14px;}
h2.tp{color:#0e7c7b;font-size:15px;border-left:5px solid #0e7c7b;padding-left:9px;margin:20px 0 8px;}
.q{padding:11px 2px 13px;border-bottom:1px solid #eef1f5;page-break-inside:avoid;} .qs{font-weight:600;margin-bottom:8px;} .qn{display:inline-block;min-width:24px;height:24px;line-height:24px;text-align:center;background:#334155;color:#fff;border-radius:50%;font-weight:800;font-size:12px;margin-right:7px;} .oyr{margin-left:6px;font-size:11px;color:#94a3b8;font-weight:700;}
.imgtag{margin:2px 0 6px 31px;font-size:12px;color:#b45309;background:#fff7ea;border-radius:6px;padding:3px 8px;display:inline-block;}
.figbox{margin:6px 0 8px 31px;padding:8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;} .figcap{font-size:11px;color:#64748b;font-weight:700;margin-bottom:5px;} .figfull{max-width:100%;max-height:560px;border:1px solid #cbd5e1;border-radius:6px;} .fig{max-width:70%;max-height:320px;border:1px solid #cbd5e1;border-radius:6px;margin:3px 6px 3px 0;vertical-align:top;}
.chs{padding-left:31px;} .ch{padding:2px 0;}
.ans{margin:8px 0 0 31px;} .ans b{color:#0b5450;} .otag,.ntag{font-size:10px;font-weight:800;padding:1px 6px;border-radius:5px;margin-right:6px;} .otag{background:#eef2f7;color:#64748b;} .ntag{background:#dcfce7;color:#15803d;}
.warn{font-size:11px;font-weight:800;color:#b91c1c;background:#fde8e8;padding:1px 7px;border-radius:5px;margin-left:6px;} .softwarn{font-size:11px;color:#b45309;font-weight:700;margin-left:4px;}
.ex{margin:6px 0 0 31px;padding:9px 11px;background:#f8fafc;border-left:3px solid #cbd5e1;border-radius:6px;font-size:13.5px;color:#374151;white-space:pre-wrap;}
"""
    doc = (f"<!doctype html><html lang=ko><head><meta charset=utf-8><title>출족 연도별 정리</title>"
           f"<style>{css}</style></head><body>{cover}{toc_html}<div class='content'>" + "".join(body) + "</div></body></html>")
    (BASE / "출족_연도별정리_2020_2026.html").write_text(doc, encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
        p = (BASE / "출족_연도별정리_2020_2026.html").resolve()
        foot = ('<div style="font-size:9px;width:100%;text-align:center;color:#9aa4b0;">'
                '출족 연도별 정리 2020~2026 · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        with sync_playwright() as pw:
            b = pw.chromium.launch(); pg = b.new_page(); pg.goto(f"file://{p}")
            pg.pdf(path=str(BASE / "출족_연도별정리_2020_2026.pdf"), format="A4", print_background=True,
                   display_header_footer=True, header_template="<div></div>", footer_template=foot,
                   margin={"top": "12mm", "bottom": "15mm", "left": "12mm", "right": "12mm"})
            b.close()
        print("[pdf]", BASE / "출족_연도별정리_2020_2026.pdf")
    except Exception as e:
        print("PDF skip:", e)
    print(f"대상 문항 {len(tgt)} · 재작성 해설 {n_new} · 원본 해설 {len(tgt) - n_new}")
    for y in TARGET:
        print(f"  {y}: {len(by_year[y])}")


if __name__ == "__main__":
    main()
