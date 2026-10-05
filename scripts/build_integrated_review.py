#!/usr/bin/env python3
"""시험 마지막 정리본 + 연관 문항 인터리브 → 통합 학습 HTML(읽으면서 풀기).

입력:
  --extracts   review 워크플로 고빈도 추출 JSON [{unit_id,topic,system,one_liner,must_know,differentials,memorize,traps}]
  --new-q      questions 워크플로 JSON [{unit_id,source_name,questions:[...]}]
  --units      data_private/exam_final/study_units.json  (date/period→lid 매칭·순서)
  --lq-dir     기존 lecture_questions 디렉터리(기본 data_private/lecture_questions)
  --out        출력 HTML

각 강의 섹션 = 고빈도 요약 + 연관 문항(신규 우선 + 기존 매칭, stem dedup) with 접이식 정답·해설.
계통 순서로 묶고, 끝에 30분 체크리스트·감별표·함정·암기 총정리.
전부 needs_review — 강의 슬라이드 재확인 전제.
"""

import argparse
import glob
import html
import json
import re
import unicodedata
from pathlib import Path

SYS_ORDER = ["조혈·기초", "RBC", "WBC", "지혈·혈전", "종양·항암", "검사", "이식", "기타"]


def norm_sys(s):
    s = re.sub(r"[\s/·]+", "", str(s or ""))
    for canon in SYS_ORDER:
        if re.sub(r"[·]", "", canon) in s or s in re.sub(r"[·]", "", canon):
            return canon
    if "조혈" in s or "기초" in s:
        return "조혈·기초"
    if "종양" in s or "항암" in s:
        return "종양·항암"
    if "지혈" in s or "혈전" in s or "응고" in s:
        return "지혈·혈전"
    return "기타"


def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def h(s):
    return html.escape(str(s or ""))


def norm_stem(s):
    return re.sub(r"\s+", "", str(s or ""))[:40].lower()


def lid_period_index(lq_dir):
    idx = {}
    for f in sorted(glob.glob(str(Path(lq_dir) / "q_*.json"))):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        lid = nfc(d.get("lecture_id"))
        m = re.match(r"(\d{8})_(\d+)", lid)
        if m:
            idx.setdefault(m.group(1), {})[int(m.group(2))] = d.get("questions") or []
    return idx


def q_html(q, i):
    ch = q.get("choices") or {}
    rows = "".join(
        f'<div class="ch"><b>{h(k)}</b> {h(ch[k])}</div>'
        for k in sorted(ch, key=lambda x: int(x) if str(x).isdigit() else 9) if ch.get(k))
    ans = q.get("answer")
    exp = f'<div class="exp"><b>정답 {h(ans)}.</b> {h(q.get("explanation"))}</div>'
    ce = q.get("choice_explanations") or {}
    if ce:
        exp += '<div class="ce">' + "".join(
            f'<div><b>{h(k)}.</b> {h(ce[k])}</div>' for k in sorted(ce) if ce.get(k)) + "</div>"
    kp = q.get("key_point") or []
    if kp:
        exp += "<div class=kp><b>핵심</b><ul>" + "".join(f"<li>{h(x)}</li>" for x in kp if x) + "</ul></div>"
    return (f'<div class="q"><div class="qs">Q{i}. {h(q.get("stem"))}</div>{rows}'
            f'<details><summary>정답·해설 보기</summary>{exp}</details></div>')


def lst(title, items, cls=""):
    items = [x for x in (items or []) if x]
    if not items:
        return ""
    return (f'<div class="blk {cls}"><span class="bt">{title}</span><ul>'
            + "".join(f"<li>{h(x)}</li>" for x in items) + "</ul></div>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extracts", required=True)
    ap.add_argument("--new-q", required=True)
    ap.add_argument("--units", default="data_private/exam_final/study_units.json")
    ap.add_argument("--lq-dir", default="data_private/lecture_questions")
    ap.add_argument("--out", default="data_private/exam_final/시험정리본_문항통합.html")
    args = ap.parse_args()

    extracts = json.load(open(args.extracts, encoding="utf-8"))
    if isinstance(extracts, dict):
        extracts = extracts.get("extracts") or extracts.get("per") or []
    newq = json.load(open(args.new_q, encoding="utf-8"))
    if isinstance(newq, dict):
        newq = newq.get("per") or []
    units = json.load(open(args.units, encoding="utf-8"))
    lq = lid_period_index(args.lq_dir)

    newq_by_unit = {nfc(r.get("unit_id")): (r.get("questions") or []) for r in newq}
    unit_meta = {nfc(u["unit_id"]): u for u in units}
    ex_by_unit = {nfc(e.get("unit_id")): e for e in extracts}

    def questions_for(unit_id):
        seen, out = set(), []
        for q in newq_by_unit.get(unit_id, []):
            k = norm_stem(q.get("stem"))
            if k and k not in seen:
                seen.add(k); out.append(q)
        u = unit_meta.get(unit_id)
        if u:
            for p in u["periods"]:
                for q in lq.get(u["date"], {}).get(p, []):
                    k = norm_stem(q.get("stem"))
                    if k and k not in seen:
                        seen.add(k); out.append(q)
        return out

    # group by system (from extract)
    groups = {s: [] for s in SYS_ORDER}
    for uid, e in ex_by_unit.items():
        groups[norm_sys(e.get("system"))].append(uid)

    all_diff, all_trap, all_mem, checklist = [], [], [], []
    toc_by_sys = {}
    body = []
    for s in SYS_ORDER:
        uids = groups.get(s) or []
        if not uids:
            continue
        sys_anchor = "sys-" + re.sub(r"[^\w]+", "-", s)
        body.append(f'<h2 class="sys" id="{sys_anchor}">{h(s)}</h2>')
        for uid in sorted(uids, key=lambda x: (unit_meta.get(x, {}).get("date", ""), unit_meta.get(x, {}).get("periods", [0])[0])):
            e = ex_by_unit[uid]
            anchor = "u-" + re.sub(r"[^\w]+", "-", uid)
            qs = questions_for(uid)
            toc_by_sys.setdefault(s, []).append((e.get("topic"), anchor, len(qs)))
            body.append(f'<section class="unit" id="{anchor}"><h3>{h(e.get("topic"))}</h3>')
            if e.get("one_liner"):
                body.append(f'<p class="one">{h(e["one_liner"])}</p>')
            body.append(lst("꼭 볼 것", e.get("must_know"), "must"))
            body.append(lst("감별", e.get("differentials"), "diff"))
            body.append(lst("암기", e.get("memorize"), "mem"))
            body.append(lst("함정", e.get("traps"), "trap"))
            if qs:
                body.append(f'<div class="qwrap"><span class="bt">📝 연관 문항 {len(qs)}</span>')
                for i, q in enumerate(qs, 1):
                    body.append(q_html(q, i))
                body.append("</div>")
            body.append("</section>")
            for d in (e.get("differentials") or []):
                all_diff.append((e.get("topic"), d))
            all_trap += [(e.get("topic"), t) for t in (e.get("traps") or [])]
            all_mem += [(e.get("topic"), m) for m in (e.get("memorize") or [])]
            if e.get("must_know"):
                checklist.append((e.get("topic"), e["must_know"][0]))

    def pairs_table(title, pairs):
        if not pairs:
            return ""
        rows = "".join(f"<tr><td>{h(t)}</td><td>{h(x)}</td></tr>" for t, x in pairs)
        return f'<h2>{title}</h2><table class="tt"><tr><th>강의</th><th>내용</th></tr>{rows}</table>'

    tail = []
    tail.append("<h2>⚡ 시험 직전 30분 체크리스트</h2><ul class='chk'>" +
                "".join(f"<li><b>{h(t)}</b> — {h(x)}</li>" for t, x in checklist) + "</ul>")
    tail.append(pairs_table("🔀 감별표 모음", all_diff))
    tail.append(pairs_table("⚠️ 함정 모음", all_trap))
    tail.append(pairs_table("🧠 암기 총정리", all_mem))

    n_q = sum(len(questions_for(uid)) for uid in ex_by_unit)
    n_lec = len(ex_by_unit)
    n_sys = sum(1 for s in SYS_ORDER if toc_by_sys.get(s))

    # ── 표지 ──
    cover = (
        '<section class="cover">'
        '<div class="cbrand">P:accine · 본2-1</div>'
        '<h1 class="ctitle">혈액종양<br>시험 마지막 정리본</h1>'
        '<div class="csub">읽으면서 푸는 · 문항 통합본</div>'
        '<div class="cmeta">'
        f'<span><b>{n_lec}</b><small>강의</small></span>'
        f'<span><b>{n_q}</b><small>연관 문항</small></span>'
        f'<span><b>{n_sys}</b><small>계통</small></span>'
        '</div>'
        '<div class="cnote">학생 본인 노트 기반 · 강의자료로 보강 · 전부 needs_review<br>'
        '수치·분류·치료는 시험 전 강의 슬라이드/최신 지침으로 재확인</div>'
        '</section>')

    # ── 목차 ──
    toc_rows = []
    for s in SYS_ORDER:
        entries = toc_by_sys.get(s)
        if not entries:
            continue
        sys_anchor = "sys-" + re.sub(r"[^\w]+", "-", s)
        toc_rows.append(f'<div class="tsys"><a href="#{sys_anchor}">{h(s)}</a></div>')
        for topic, anchor, nq in entries:
            qb = f'<span class="tq">Q{nq}</span>' if nq else ''
            toc_rows.append(f'<div class="titem"><a href="#{anchor}">{h(topic)}</a>{qb}</div>')
    toc = ('<section class="toc"><h2 class="pgh">목차</h2>'
           + "".join(toc_rows)
           + '<div class="tappendix"><b>부록</b> · 시험 직전 30분 체크리스트 · 감별표 모음 · 함정 모음 · 암기 총정리</div>'
           + '</section>')

    # ── 맨뒷장 마감 ──
    closing = (
        '<section class="closing">'
        '<div class="xmark">끝.</div>'
        '<h2 class="pgh">이 정리본 사용법</h2>'
        '<ol class="use">'
        '<li>계통 순서(조혈·기초→RBC→WBC→지혈→종양→검사/이식)대로 <b>큰 그림</b>을 잡는다.</li>'
        '<li>각 강의 <b>꼭 볼 것·감별·암기·함정</b>을 먼저 읽는다.</li>'
        '<li>바로 아래 <b>연관 문항</b>을 풀고 <b>정답·해설</b>을 펼쳐 확인한다.</li>'
        '<li>마지막에 <b>부록(30분 체크리스트·감별표·암기 총정리)</b>로 회독한다.</li>'
        '</ol>'
        '<div class="xdisc">⚠️ 전 내용 needs_review — 자동 생성물입니다. 병기 수치·세포유전 분류·약제·치료 순서는 '
        '시험 전 <b>강의 슬라이드와 최신 지침</b>으로 반드시 재확인하세요. 개인 학습용.</div>'
        f'<div class="xfoot">혈액종양 시험 정리본 · {n_lec}강의 · {n_q}문항 · P:accine 학습도구</div>'
        '<div class="xcheer">시험 잘 보세요 💪</div>'
        '</section>')

    css = """
@page{margin:14mm;}
body{font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;background:#faf7f2;color:#1c2733;line-height:1.6;max-width:900px;margin:0 auto;padding:28px;}
h1{color:#0e7c7b;} h2.sys{color:#0e7c7b;border-bottom:3px solid #0e7c7b;padding-bottom:4px;margin-top:34px;}
.cover,.toc,.closing{page-break-after:always;}
.closing{page-break-after:auto;page-break-before:always;}
.content{padding-top:6px;}
.cover{min-height:88vh;display:flex;flex-direction:column;justify-content:center;text-align:center;background:linear-gradient(160deg,#0e7c7b 0%,#0b5450 100%);color:#fff;border-radius:18px;padding:40px;margin-bottom:0;}
.cbrand{letter-spacing:3px;font-weight:800;font-size:14px;opacity:.85;}
.ctitle{color:#fff;font-size:44px;line-height:1.2;margin:18px 0 8px;}
.csub{font-size:19px;opacity:.92;font-weight:600;}
.cmeta{display:flex;justify-content:center;gap:34px;margin:34px 0;}
.cmeta span{display:flex;flex-direction:column;} .cmeta b{font-size:34px;} .cmeta small{opacity:.85;font-size:13px;letter-spacing:1px;}
.cnote{font-size:13px;opacity:.85;line-height:1.7;margin-top:8px;}
.pgh{color:#0e7c7b;font-size:26px;border-bottom:3px solid #0e7c7b;padding-bottom:6px;}
.toc a{color:#0b5450;text-decoration:none;} .tsys{margin-top:14px;font-weight:900;font-size:17px;border-left:5px solid #0e7c7b;padding-left:8px;}
.titem{display:flex;justify-content:space-between;align-items:center;padding:3px 0 3px 18px;font-size:14px;border-bottom:1px dotted #ddd3bf;}
.tq{background:#e6f3f2;color:#0b5450;font-weight:800;font-size:11px;padding:1px 7px;border-radius:999px;}
.tappendix{margin-top:20px;padding:10px 12px;background:#fbf5e9;border-radius:8px;font-size:13px;color:#6b5a3e;}
.closing{text-align:center;padding-top:30px;} .xmark{font-size:40px;font-weight:900;color:#0e7c7b;}
.use{text-align:left;max-width:620px;margin:14px auto;line-height:1.9;} .use li{margin:4px 0;}
.xdisc{max-width:640px;margin:22px auto;font-size:13px;color:#7a4a2a;background:#fbeee2;padding:12px 14px;border-radius:10px;line-height:1.7;text-align:left;}
.xfoot{margin-top:20px;color:#8a7a5c;font-size:12px;} .xcheer{margin-top:8px;font-size:22px;font-weight:800;color:#0b5450;}
h2{color:#0b5450;margin-top:30px;} .unit{border:1px solid #e6ddcd;border-radius:12px;padding:16px 18px;margin:14px 0;background:#fff;}
.unit h3{margin:0 0 8px;color:#173b3a;} .one{font-weight:700;color:#5a4a2e;background:#fbf5e9;padding:8px 12px;border-radius:8px;}
.blk{margin:10px 0;} .bt{display:block;font-weight:800;color:#0e7c7b;font-size:13px;margin-bottom:4px;}
.blk ul{margin:0;padding-left:20px;} .diff .bt{color:#b45309;} .trap .bt{color:#b91c1c;} .mem .bt{color:#6d28d9;}
.qwrap{margin-top:14px;border-top:2px dashed #cbb;padding-top:10px;}
.q{border:1px solid #dbe4ef;border-radius:10px;padding:12px 14px;margin:10px 0;background:#f8fafc;}
.qs{font-weight:700;margin-bottom:8px;} .ch{padding:3px 0;} .ch b{color:#003366;}
details{margin-top:8px;} summary{cursor:pointer;color:#0e7c7b;font-weight:800;font-size:14px;}
.exp{margin-top:8px;padding:10px;background:#e6f3f2;border-radius:8px;} .ce{margin-top:6px;font-size:14px;color:#444;} .ce b{color:#991b1b;}
.kp{margin-top:6px;} .kp ul{margin:2px 0;padding-left:18px;}
table.tt{border-collapse:collapse;width:100%;font-size:14px;} .tt th,.tt td{border:1px solid #d9ccb6;padding:6px 9px;text-align:left;vertical-align:top;} .tt th{background:#0e7c7b;color:#fff;}
ul.chk li{margin:3px 0;} ul.chk b{color:#0b5450;}
"""
    doc = (f"<!doctype html><html lang=ko><head><meta charset=utf-8>"
           f"<title>혈액종양 시험 정리본 · 문항통합</title><style>{css}</style></head><body>"
           + cover + toc
           + '<div class="content">' + "".join(body) + "".join(tail) + '</div>'
           + closing + "</body></html>")
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(doc, encoding="utf-8")
    print(f"[done] {outp}")
    print(f"  강의 {len(ex_by_unit)} · 연관 문항 {n_q}")


if __name__ == "__main__":
    raise SystemExit(main())
