#!/usr/bin/env python3
"""병기·예후인자 집중 정리 + 문항 → PDF, + Anki cloze 카드 emit.

입력: data_private/exam_final/prognosis_focus.json (병기표·좋은/나쁜 예후)
      data_private/exam_final/prognosis_questions.json (집중 문항)
출력: data_private/exam_final/병기예후_집중정리.pdf (+ .html)
      data_private/exam_cards/cards_예후병기집중.json (cloze 카드 → 덱에 포함)
전부 needs_review — 수치·분류는 최신 지침으로 재확인.
"""

import html
import json
import re
from pathlib import Path

BASE = Path("data_private/exam_final")


def h(s):
    return html.escape(str(s or ""))


def render_pdf():
    foc = json.load(open(BASE / "prognosis_focus.json", encoding="utf-8"))
    qs = json.load(open(BASE / "prognosis_questions.json", encoding="utf-8"))
    by_dis = {}
    for q in qs:
        by_dis.setdefault(q["disease"], []).append(q)

    parts = []
    for d in foc["diseases"]:
        parts.append(f'<section class="dis"><h2>{h(d["name"])}</h2>')
        st = d["staging"]
        rows = "".join(f"<tr><td class=k>{h(a)}</td><td>{h(b)}</td></tr>" for a, b in st["rows"])
        parts.append(f'<div class="stg"><span class="lb">📊 {h(st["title"])}</span>'
                     f'<table class="tt">{rows}</table></div>')
        good = "".join(f"<li>{h(x)}</li>" for x in d["good"])
        bad = "".join(f"<li>{h(x)}</li>" for x in d["bad"])
        parts.append(f'<div class="gb"><div class="good"><span class="lb">🟢 좋은 예후</span><ul>{good}</ul></div>'
                     f'<div class="bad"><span class="lb">🔴 나쁜 예후</span><ul>{bad}</ul></div></div>')
        # questions
        dqs = by_dis.get(d["name"], [])
        if dqs:
            parts.append(f'<div class="qs"><span class="lb">📝 집중 문항 {len(dqs)}</span>')
            for i, q in enumerate(dqs, 1):
                ch = q["choices"]
                chr_ = "".join(f'<div class="ch"><b>{k}</b> {h(ch[k])}</div>' for k in sorted(ch))
                ce = q.get("choice_explanations") or {}
                ceh = "".join(f'<div><b>{k}.</b> {h(ce[k])}</div>' for k in sorted(ce))
                kp = "".join(f"<li>{h(x)}</li>" for x in (q.get("key_point") or []))
                parts.append(
                    f'<div class="q"><div class="qs-stem">Q{i}. {h(q["stem"])}</div>{chr_}'
                    f'<div class="ans"><b>정답 {q["answer"]}.</b> {h(q["explanation"])}</div>'
                    f'<div class="ce">{ceh}</div>'
                    f'<div class="kp"><b>핵심</b><ul>{kp}</ul></div></div>')
            parts.append("</div>")
        parts.append("</section>")

    css = """
body{font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;color:#1c2733;line-height:1.55;max-width:860px;margin:0 auto;padding:24px;background:#faf7f2;}
h1{color:#0e7c7b;} .sub{color:#6b5a3e;font-size:14px;}
.dis{border:1px solid #e2d9c8;border-radius:12px;padding:16px 18px;margin:16px 0;background:#fff;page-break-inside:avoid;}
.dis h2{color:#0b5450;margin:0 0 10px;border-bottom:2px solid #0e7c7b;padding-bottom:4px;}
.lb{display:block;font-weight:900;font-size:13px;color:#0e7c7b;margin:10px 0 5px;}
table.tt{border-collapse:collapse;width:100%;font-size:14px;} .tt td{border:1px solid #d9ccb6;padding:6px 9px;vertical-align:top;} .tt td.k{font-weight:800;width:28%;background:#f4efe4;}
.gb{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:8px;}
.good{background:#e7f5ec;border-radius:8px;padding:8px 12px;} .bad{background:#fbeaea;border-radius:8px;padding:8px 12px;}
.good .lb{color:#15803d;} .bad .lb{color:#b91c1c;} .gb ul{margin:2px 0;padding-left:18px;font-size:14px;}
.qs{margin-top:12px;border-top:2px dashed #cbb;padding-top:8px;}
.q{border:1px solid #dbe4ef;border-radius:10px;padding:11px 13px;margin:9px 0;background:#f8fafc;page-break-inside:avoid;}
.qs-stem{font-weight:700;margin-bottom:7px;} .ch{padding:2px 0;} .ch b{color:#003366;}
.ans{margin-top:8px;padding:9px;background:#e6f3f2;border-radius:7px;} .ce{margin-top:6px;font-size:13px;color:#555;} .ce b{color:#991b1b;}
.kp{margin-top:5px;font-size:13px;} .kp ul{margin:2px 0;padding-left:16px;}
"""
    doc = (f"<!doctype html><html lang=ko><head><meta charset=utf-8><title>병기·예후 집중</title>"
           f"<style>{css}</style></head><body><h1>혈액종양 병기·예후인자 집중 정리</h1>"
           f"<p class=sub>{h(foc['note'])}</p>" + "".join(parts) + "</body></html>")
    (BASE / "병기예후_집중정리.html").write_text(doc, encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
        p = (BASE / "병기예후_집중정리.html").resolve()
        with sync_playwright() as pw:
            b = pw.chromium.launch(); pg = b.new_page()
            pg.goto(f"file://{p}")
            pg.pdf(path=str(BASE / "병기예후_집중정리.pdf"), format="A4",
                   margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"}, print_background=True)
            b.close()
        print("[pdf]", BASE / "병기예후_집중정리.pdf")
    except Exception as e:
        print("PDF skip:", e)


def emit_cloze():
    """좋은/나쁜 예후를 cloze 카드로 → 덱에 포함(system=종양·항암)."""
    foc = json.load(open(BASE / "prognosis_focus.json", encoding="utf-8"))
    cards = []
    for d in foc["diseases"]:
        nm = d["name"]
        if d["good"]:
            cards.append({"text": f"{nm}의 **좋은 예후** 인자: {{{{c1::" + " · ".join(d["good"][:4]) + "}}}}",
                          "extra": "병기·예후 집중", "concept": nm, "system": "종양·항암"})
        if d["bad"]:
            cards.append({"text": f"{nm}의 **나쁜 예후** 인자: {{{{c1::" + " · ".join(d["bad"][:4]) + "}}}}",
                          "extra": "병기·예후 집중 · verify", "concept": nm, "system": "종양·항암"})
    out = {"lecture_id": "예후병기집중", "source_name": "병기·예후인자 집중", "cards": cards}
    Path("data_private/exam_cards/cards_예후병기집중.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # extend allowlist
    al = Path("data_private/exam_cards/_include_lids.json")
    lids = json.loads(al.read_text(encoding="utf-8"))
    if "예후병기집중" not in lids:
        lids.append("예후병기집중"); al.write_text(json.dumps(lids, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[cloze] {len(cards)}장 → cards_예후병기집중.json")


if __name__ == "__main__":
    render_pdf()
    emit_cloze()
