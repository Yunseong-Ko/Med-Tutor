#!/usr/bin/env python3
"""공사모 채팅 · 김민훈 예상소재 → 노트정리 + 예상문항 스터디 PDF/HTML.

입력: data_private/chat_exam/kimminhun_picks_data.json (노트 소재)
      data_private/chat_exam/kimminhun_picks_questions.json (객관식·서술형)
출력: data_private/exam_final/김민훈_예상소재_노트문항.{html,pdf}
사실은 강의·표준의학 보강, 전부 needs_review. 개인 학습용.
"""

import html
import json
from pathlib import Path

BASE = Path("data_private/exam_final")
CIRC = {"1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤"}
TAGCLS = {"essay": ("서술형 예상", "t-essay"), "high": ("나올확률 높음", "t-high"), "note": ("언급 소재", "t-note")}


def h(s):
    return html.escape(str(s or ""))


def main():
    data = json.load(open(Path("data_private/chat_exam/kimminhun_picks_data.json"), encoding="utf-8"))
    qs = json.load(open(Path("data_private/chat_exam/kimminhun_picks_questions.json"), encoding="utf-8"))
    mcq, essay = qs["mcq"], qs["essay"]

    # 노트정리
    note = []
    for grp in data["note"]:
        note.append(f'<h2 class="grp">{h(grp["topic"])}</h2>')
        for it in grp["items"]:
            label, cls = TAGCLS.get(it["tag"], ("", "t-note"))
            note.append(f'<div class="ni"><span class="tag {cls}">{label}</span>'
                        f'<span class="dt">{h(it["date"])}</span>{h(it["fact"])}</div>')

    # 객관식(정답·해설 표시 스터디형)
    mc = []
    for i, q in enumerate(mcq, 1):
        ch = q["choices"]
        rows = "".join(f'<div class="ch">{CIRC.get(k, k)} {h(ch[k])}</div>' for k in sorted(ch))
        ce = q.get("choice_explanations") or {}
        ceh = "".join(f'<div>{CIRC.get(k, k)} {h(ce[k])}</div>' for k in sorted(ce)) if ce else ""
        kp = " · ".join(h(x) for x in (q.get("key_point") or []))
        mc.append(
            f'<div class="q"><div class="qs"><span class="qn">{i}</span>{h(q["stem"])}'
            f'<span class="src">김민훈 {h(q.get("src", ""))}</span></div>'
            f'<div class="chs">{rows}</div>'
            f'<div class="ans"><b>정답 {CIRC.get(str(q["answer"]), q["answer"])}</b> {h(q["explanation"])}</div>'
            f'<div class="ce">{ceh}</div><div class="kp"><b>핵심</b> {kp}</div></div>')

    es = []
    for i, e in enumerate(essay, 1):
        pts = "".join(f"<li>{h(x)}</li>" for x in e["points"])
        es.append(f'<div class="e"><div class="eq"><span class="en">서술 {i}</span>{h(e["q"])}</div>'
                  f'<div class="ea"><b>모범답안 포인트</b><ul>{pts}</ul></div></div>')

    cover = ('<section class="cover"><div class="cbrand">공사모 채팅 · 최근 2주</div>'
             '<h1 class="ctitle">김민훈 예상소재</h1><div class="csub">노트정리 + 예상문항 (혈종 파이널)</div>'
             f'<div class="cmeta"><span><b>{sum(len(g["items"]) for g in data["note"])}</b><small>소재</small></span>'
             f'<span><b>{len(mcq)}</b><small>객관식</small></span><span><b>{len(essay)}</b><small>서술형</small></span></div>'
             f'<div class="cnote">{h(data["disclaimer"])}</div></section>')

    closing = ('<section class="closing"><div class="xmark">끝.</div>'
               '<div class="xdisc">⚠️ 친구(김민훈)의 시험 예측 정리 — 공식 출제정보 아님. 사실은 강의·표준의학으로 보강했으나 전부 needs_review. 시험 전 강의 슬라이드로 재확인.</div>'
               '<div class="xcheer">서술형까지 챙기자 💪</div></section>')

    css = """
@page{margin:14mm;}
body{font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;background:#fff;color:#111827;line-height:1.6;max-width:840px;margin:0 auto;padding:24px;font-size:15px;}
.cover{page-break-after:always;min-height:84vh;display:flex;flex-direction:column;justify-content:center;text-align:center;background:linear-gradient(160deg,#1f2d5a,#0e7c7b);color:#fff;border-radius:18px;padding:40px;}
.cbrand{letter-spacing:3px;font-weight:800;font-size:13px;opacity:.85;} .ctitle{color:#fff;font-size:42px;margin:16px 0 6px;} .csub{font-size:18px;opacity:.92;font-weight:600;}
.cmeta{display:flex;justify-content:center;gap:30px;margin:28px 0;} .cmeta b{font-size:32px;} .cmeta small{opacity:.85;font-size:12px;display:block;} .cnote{font-size:12px;opacity:.82;line-height:1.7;max-width:600px;margin:0 auto;}
.sec-h{color:#0e7c7b;font-size:26px;border-bottom:3px solid #0e7c7b;padding-bottom:6px;margin-top:30px;} .psec{page-break-before:always;}
h2.grp{color:#0e7c7b;font-size:17px;border-left:6px solid #0e7c7b;padding:2px 0 2px 10px;margin:22px 0 8px;}
.ni{padding:8px 2px 8px 4px;border-bottom:1px solid #eef1f5;} .tag{font-size:11px;font-weight:800;padding:1px 7px;border-radius:999px;margin-right:6px;} .t-essay{background:#fdecec;color:#c0322f;} .t-high{background:#fff4e0;color:#b45309;} .t-note{background:#eef2f7;color:#475569;} .dt{color:#9aa4b0;font-size:12px;margin-right:8px;}
.q{padding:11px 2px 13px;border-bottom:1px solid #eef1f5;page-break-inside:avoid;} .qs{font-weight:600;margin-bottom:8px;} .qn{display:inline-block;min-width:24px;height:24px;line-height:24px;text-align:center;background:#0e7c7b;color:#fff;border-radius:50%;font-weight:800;font-size:12px;margin-right:7px;} .src{float:right;font-size:11px;color:#a9b2bd;font-weight:600;}
.chs{padding-left:31px;} .ch{padding:3px 0;} .ans{margin:8px 0 0 31px;padding:8px 11px;background:#e6f3f2;border-radius:8px;font-size:14px;} .ans b{color:#0b5450;} .ce{margin:5px 0 0 31px;font-size:12.5px;color:#555;} .ce div{padding:1px 0;} .kp{margin:5px 0 0 31px;font-size:12.5px;color:#6d28d9;}
.e{border:1px solid #e2d9c8;border-radius:10px;padding:12px 14px;margin:10px 0;background:#fbf7ef;page-break-inside:avoid;} .eq{font-weight:700;color:#7a1f3d;} .en{display:inline-block;background:#7a1f3d;color:#fff;border-radius:6px;padding:1px 8px;font-size:12px;margin-right:8px;} .ea{margin-top:8px;} .ea ul{margin:4px 0;padding-left:20px;} .ea b{color:#0b5450;font-size:13px;}
.closing{page-break-before:always;text-align:center;padding-top:30px;} .xmark{font-size:38px;font-weight:900;color:#0e7c7b;} .xdisc{max-width:640px;margin:20px auto;font-size:13px;color:#7a4a2a;background:#fbeee2;padding:12px 14px;border-radius:10px;} .xcheer{margin-top:10px;font-size:20px;font-weight:800;color:#0b5450;}
"""
    doc = (f"<!doctype html><html lang=ko><head><meta charset=utf-8><title>김민훈 예상소재 · 노트+문항</title>"
           f"<style>{css}</style></head><body>{cover}"
           f'<section class="nsec"><h1 class="sec-h">📝 노트정리 — 김민훈 예상소재</h1>' + "".join(note) + "</section>"
           f'<section class="psec"><h1 class="sec-h">✅ 예상 객관식 {len(mcq)}</h1>' + "".join(mc) + "</section>"
           f'<section class="psec"><h1 class="sec-h">🔴 서술형 예상 {len(essay)}</h1>' + "".join(es) + "</section>"
           f"{closing}</body></html>")
    (BASE / "김민훈_예상소재_노트문항.html").write_text(doc, encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
        p = (BASE / "김민훈_예상소재_노트문항.html").resolve()
        foot = ('<div style="font-size:9px;width:100%;text-align:center;color:#9aa4b0;">'
                '김민훈 예상소재(공사모) · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        with sync_playwright() as pw:
            b = pw.chromium.launch(); pg = b.new_page(); pg.goto(f"file://{p}")
            pg.pdf(path=str(BASE / "김민훈_예상소재_노트문항.pdf"), format="A4", print_background=True,
                   display_header_footer=True, header_template="<div></div>", footer_template=foot,
                   margin={"top": "12mm", "bottom": "15mm", "left": "12mm", "right": "12mm"})
            b.close()
        print("[pdf]", BASE / "김민훈_예상소재_노트문항.pdf")
    except Exception as e:
        print("PDF skip:", e)
    print(f"노트 소재 {sum(len(g['items']) for g in data['note'])} · 객관식 {len(mcq)} · 서술형 {len(essay)}")


if __name__ == "__main__":
    main()
