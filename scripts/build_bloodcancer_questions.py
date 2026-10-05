#!/usr/bin/env python3
"""혈액암(백혈병·림프종·골수종·MPN·MDS) 파트 문항만 모아 문제집 → HTML/PDF.

소스: data_private/exam_final/new_questions.json + data_private/lecture_questions/q_*.json
분류: 강의(악성) 기반 + concept 기반(정밀). vignette 'blast/백혈병' 단순매칭은 오탐이라 제외.
출력: data_private/exam_final/혈액암_문제모음.{html,pdf}
전부 needs_review — 개인 학습용.
"""

import html
import json
import glob
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path

BASE = Path("data_private/exam_final")
ORDER = ["급성 백혈병 (AML/ALL)", "소아 백혈병", "만성 백혈병 (CML/CLL)",
         "골수증식성 종양 (MPN)", "골수형성이상증후군 (MDS)",
         "림프종 (호지킨/비호지킨)", "다발골수종·형질세포질환", "혈액암 총론·유전·치료"]

LEC_BUCKET = OrderedDict([
    ("급성백혈병", "급성 백혈병 (AML/ALL)"), ("acute_leukemia", "급성 백혈병 (AML/ALL)"),
    ("소아백혈병", "소아 백혈병"),
    ("만성백혈병", "만성 백혈병 (CML/CLL)"),
    ("골수증식", "골수증식성 종양 (MPN)"),
    ("lymphoma", "림프종 (호지킨/비호지킨)"), ("림프종", "림프종 (호지킨/비호지킨)"),
    ("다발골수종", "다발골수종·형질세포질환"), ("형질세포", "다발골수종·형질세포질환"),
    ("mm_강의", "다발골수종·형질세포질환"), ("_mm_", "다발골수종·형질세포질환"),
    ("혈액암", "혈액암 총론·유전·치료"), ("hematooncology", "혈액암 총론·유전·치료"),
])


def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def h(s):
    return html.escape(str(s or ""))


def lec_bucket(lid):
    low = lid.lower()
    for k, v in LEC_BUCKET.items():
        if k.lower() in low:
            return v
    return None


def concept_bucket(concept, stem):
    c = (concept or "").lower()
    s = (stem or "").lower()
    if any(k in c for k in ["acute_myeloid", "aml", "promyelocyt", "apl", "bone_marrow_blasts_acute", "myeloblast_acute"]):
        return "급성 백혈병 (AML/ALL)"
    if any(k in c for k in ["acute_lymphoblastic", "lymphoblastic_leukemia"]):
        return "급성 백혈병 (AML/ALL)"
    if "cml" in c or "chronic_myeloid" in c:
        return "만성 백혈병 (CML/CLL)"
    if "cll" in c or "chronic_lymphocytic" in c:
        return "만성 백혈병 (CML/CLL)"
    if "lymphoma" in c or "hodgkin" in c:
        return "림프종 (호지킨/비호지킨)"
    if "myeloma" in c or "plasma_cell" in c or "형질세포" in c:
        return "다발골수종·형질세포질환"
    if "myelodysplas" in c or c == "mds" or "sideroblastic" in c:
        return "골수형성이상증후군 (MDS)"
    if "myeloproliferative" in c or "mpn" in c:
        return "골수증식성 종양 (MPN)"
    if "leukemia" in c:  # generic — resolve by stem
        if "cll" in s or "smudge" in s or ("cd5" in s and "cd23" in s):
            return "만성 백혈병 (CML/CLL)"
        if "cml" in s:
            return "만성 백혈병 (CML/CLL)"
        return "급성 백혈병 (AML/ALL)"
    return None


def collect():
    pool = []
    nq = json.load(open(BASE / "new_questions.json", encoding="utf-8"))
    for u in nq:
        for q in u.get("questions") or []:
            pool.append((nfc(u["unit_id"]), q))
    for f in glob.glob("data_private/lecture_questions/q_*.json"):
        d = json.load(open(f))
        for q in d.get("questions") or []:
            pool.append((nfc(d.get("lecture_id") or ""), q))

    buckets = OrderedDict((b, []) for b in ORDER)
    seen = set()
    dup = 0
    for lid, q in pool:
        b = lec_bucket(lid) or concept_bucket(q.get("concept"), q.get("stem"))
        if not b or b not in buckets:
            continue
        t = (str(q.get("concept", "")) + str(q.get("stem", ""))).lower()
        if "재생불량" in t or "aplastic" in t:
            continue
        key = re.sub(r"\s+", "", str(q.get("stem", "")))[:45].lower()
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        buckets[b].append(q)
    return buckets, dup


CIRC = {"1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤"}


def choices_html(q):
    ch = q.get("choices") or {}
    out = []
    for k in sorted(ch, key=lambda x: int(x) if str(x).isdigit() else 9):
        if ch.get(k):
            out.append(f'<div class="ch">{CIRC.get(str(k), k)} {h(ch[k])}</div>')
    return "".join(out)


def problem_html(n, q):
    return (f'<div class="q"><div class="qs"><span class="qn">{n}</span>{h(q.get("stem"))}</div>'
            f'<div class="chs">{choices_html(q)}</div></div>')


def answer_html(n, q):
    ans = str(q.get("answer"))
    out = [f'<div class="a"><span class="an">{n}</span><b class="ac">정답 {CIRC.get(ans, ans)}</b> {h(q.get("explanation"))}']
    ce = q.get("choice_explanations") or {}
    if ce:
        out.append('<div class="ce">' + "".join(
            f'<div>{CIRC.get(str(k), k)} {h(ce[k])}</div>' for k in sorted(ce) if ce.get(k)) + "</div>")
    kp = [x for x in (q.get("key_point") or []) if x]
    if kp:
        out.append('<div class="kp"><b>핵심</b> ' + " · ".join(h(x) for x in kp) + "</div>")
    out.append("</div>")
    return "".join(out)


def main():
    buckets, dup = collect()
    tot = sum(len(v) for v in buckets.values())
    ngrp = sum(1 for b in ORDER if buckets[b])

    problems, answers, key = [], [], []
    n = 0
    for b in ORDER:
        qs = buckets[b]
        if not qs:
            continue
        problems.append(f'<h2 class="grp">{h(b)} <small>{len(qs)}문항</small></h2>')
        answers.append(f'<h3 class="agrp">{h(b)}</h3>')
        for q in qs:
            n += 1
            problems.append(problem_html(n, q))
            answers.append(answer_html(n, q))
            key.append((n, str(q.get("answer"))))

    keygrid = '<div class="keygrid">' + "".join(
        f'<span class="kc"><b>{i}</b>{CIRC.get(a, a)}</span>' for i, a in key) + "</div>"

    cover = ('<section class="cover"><div class="cbrand">2026 여름 계절학기 · 혈종대비</div>'
             '<h1 class="ctitle">혈액암 파이널</h1>'
             '<div class="csub">백혈병 · 림프종 · 골수종 · MPN · MDS</div>'
             f'<div class="cmeta"><span><b>{tot}</b><small>문항</small></span>'
             f'<span><b>{ngrp}</b><small>질환군</small></span></div>'
             '<div class="cnote">앞: 문제(정답 미표기, 필기용) · 뒤: 정답 일람표 + 해설<br>학생 노트 + 강의 기반 · 전부 needs_review</div></section>')

    problem_sec = '<section class="psec"><h1 class="ph">문제</h1>' + "".join(problems) + "</section>"
    answer_sec = ('<section class="asec"><h1 class="ph">정답 일람표</h1>' + keygrid
                  + '<h1 class="ph" style="margin-top:26px">해설</h1>' + "".join(answers) + "</section>")

    css = """
@page{margin:14mm;}
body{font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;background:#fff;color:#111827;line-height:1.65;max-width:820px;margin:0 auto;padding:24px;font-size:15px;}
.cover{page-break-after:always;min-height:86vh;display:flex;flex-direction:column;justify-content:center;text-align:center;background:linear-gradient(160deg,#7a1f3d,#0b5450);color:#fff;border-radius:18px;padding:40px;}
.cbrand{letter-spacing:3px;font-weight:800;font-size:14px;opacity:.85;} .ctitle{color:#fff;font-size:42px;margin:16px 0 8px;} .csub{font-size:18px;opacity:.92;font-weight:600;}
.cmeta{display:flex;justify-content:center;gap:34px;margin:30px 0;} .cmeta b{font-size:34px;} .cmeta small{opacity:.85;font-size:13px;display:block;} .cnote{font-size:13px;opacity:.85;line-height:1.7;}
.psec{page-break-after:always;} .asec{page-break-before:always;}
.ph{color:#0e7c7b;font-size:28px;border-bottom:3px solid #0e7c7b;padding-bottom:6px;}
h2.grp{color:#0e7c7b;font-size:18px;border-left:6px solid #0e7c7b;padding:2px 0 2px 10px;margin:26px 0 10px;} h2.grp small{color:#94a3b8;font-size:13px;font-weight:600;}
.q{padding:10px 2px 14px;margin:0;border-bottom:1px solid #eef1f5;page-break-inside:avoid;}
.qs{font-weight:600;margin-bottom:10px;} .qn{display:inline-block;min-width:26px;height:26px;line-height:26px;text-align:center;background:#0e7c7b;color:#fff;border-radius:50%;font-weight:800;font-size:13px;margin-right:8px;}
.chs{padding-left:34px;} .ch{padding:5px 0;border-bottom:1px dotted #f0f0f0;} .ch:last-child{border:0;}
.keygrid{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0;} .kc{display:inline-flex;align-items:center;gap:3px;border:1px solid #d7dde5;border-radius:7px;padding:3px 8px;font-size:14px;background:#f8fafc;} .kc b{color:#0e7c7b;font-size:12px;}
h3.agrp{color:#0b5450;font-size:16px;margin:20px 0 6px;border-bottom:2px solid #cfe6e4;padding-bottom:3px;}
.a{padding:9px 2px;border-bottom:1px solid #f0f2f5;font-size:14px;page-break-inside:avoid;} .an{display:inline-block;min-width:24px;height:24px;line-height:24px;text-align:center;background:#e6f3f2;color:#0b5450;border-radius:50%;font-weight:800;font-size:12px;margin-right:7px;} .ac{color:#0b5450;} .ce{margin:5px 0 0 31px;color:#555;font-size:13px;} .ce div{padding:1px 0;} .kp{margin:5px 0 0 31px;font-size:13px;color:#6d28d9;}
"""
    doc = (f"<!doctype html><html lang=ko><head><meta charset=utf-8>"
           f"<title>2026 여름 계절학기 혈종대비: 혈액암 파이널</title>"
           f"<style>{css}</style></head><body>{cover}{problem_sec}{answer_sec}</body></html>")
    (BASE / "혈액암_파이널.html").write_text(doc, encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
        p = (BASE / "혈액암_파이널.html").resolve()
        foot = ('<div style="font-size:9px;width:100%;text-align:center;color:#9aa4b0;padding-top:2px;">'
                '2026 여름 계절학기 혈종대비 · 혈액암 파이널 · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        with sync_playwright() as pw:
            b = pw.chromium.launch(); pg = b.new_page(); pg.goto(f"file://{p}")
            pg.pdf(path=str(BASE / "혈액암_파이널.pdf"), format="A4", print_background=True,
                   display_header_footer=True, header_template="<div></div>", footer_template=foot,
                   margin={"top": "12mm", "bottom": "16mm", "left": "12mm", "right": "12mm"})
            b.close()
        print("[pdf]", BASE / "혈액암_파이널.pdf")
    except Exception as e:
        print("PDF skip:", e)
    print(f"혈액암 파이널 {tot}문항 (중복 {dup} 제거)")
    for b in ORDER:
        if buckets[b]:
            print(f"  {len(buckets[b]):3d}  {b}")


if __name__ == "__main__":
    main()
