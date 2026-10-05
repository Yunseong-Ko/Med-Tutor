#!/usr/bin/env python3
"""[출족] 혈액 및 종양학 PDF 텍스트 → 연도별 문항 구조화 파싱.

포맷: 섹션(교수/주제) 내 'N.' 문항번호 → stem + (YYYY) + 선지①~⑨ → 'N. 답 X' + 해설.
텍스트가 정렬(justify)로 토큰단위 줄바꿈되어 있어, 블록 단위로 재조합해 파싱.
출력: data_private/chuljok/parsed.json  [{qnum,topic,year,stem,choices{},answer,orig_explanation,page}]
"""
import json
import re
from pathlib import Path

SRC = Path("data_private/chuljok/fulltext.txt")
NUMLINE = re.compile(r"^\s*(\d+)\.\s*$")
YEAR = re.compile(r"\((20\d\d)\)")
TARGET = {"2020", "2021", "2022", "2023", "2026"}
TAGGROUP = re.compile(r"[\(\[]([^\(\)\[\]]{0,60}?)[\)\]]")
YR4 = re.compile(r"20(?:19|20|21|22|23|24|25|26)")


def years_of(text):
    """stem 안의 (…)/[…] 태그에서 4자리 연도(20XX)를 모두 추출."""
    ys = set()
    for g in TAGGROUP.findall(text):
        ys.update(YR4.findall(g))
    return sorted(ys)
CIRC = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
CH2NUM = {c: str(i + 1) for i, c in enumerate(CIRC)}
CHOICE = re.compile(r"^\s*([①-⑮])\s*(.*)")
DAP = re.compile(r"^\s*답\s*[:：]?\s*(.*)")
PAGE = re.compile(r"^===PAGE (\d+)===")
TOPIC = re.compile(r"교수님\s*[-–]\s*(.+)|^([가-힣A-Za-z][가-힣A-Za-z ]+)\s*교수님")


def collapse(lines):
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def main():
    text = SRC.read_text(encoding="utf-8")
    lines = text.split("\n")

    # 1) blocks: split at NUMLINE, track page + topic
    blocks = []  # (num, lines, page)
    cur = None
    page = 0
    topic = ""
    topics = {}  # page -> topic (last seen)
    for ln in lines:
        pm = PAGE.match(ln)
        if pm:
            page = int(pm.group(1))
            continue
        if "교수님" in ln:
            m = re.search(r"([가-힣]{2,4})\s*교수님\s*[-–]?\s*(.*)", ln)
            if m:
                topic = (m.group(1) + " " + m.group(2)).strip()
        nm = NUMLINE.match(ln)
        if nm:
            if cur:
                blocks.append(cur)
            cur = {"num": int(nm.group(1)), "lines": [], "page": page, "topic": topic}
            continue
        if cur is not None:
            cur["lines"].append(ln)
    if cur:
        blocks.append(cur)

    # 2) classify + pair stem-block with following answer-block(same num, has 답)
    def has_dap(b):
        return any(DAP.match(x) for x in b["lines"])

    def has_year(b):
        return bool(YEAR.search(collapse(b["lines"])))

    def has_choice(b):
        return any(CHOICE.match(x) for x in b["lines"])

    items = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if (has_year(b) or has_choice(b)) and not has_dap(b):
            # find answer block: next block with same num and 답
            ans = None
            j = i + 1
            while j < len(blocks) and j <= i + 2:
                if blocks[j]["num"] == b["num"] and has_dap(blocks[j]):
                    ans = blocks[j]
                    break
                j += 1
            items.append((b, ans))
            i = (j + 1) if ans else (i + 1)
        else:
            i += 1

    # 3) extract fields
    out = []
    for stem_b, ans_b in items:
        joined = stem_b["lines"]
        allyears = years_of(collapse(joined))
        tgt_years = [y for y in allyears if y in TARGET]
        year = max(tgt_years) if tgt_years else (max(allyears) if allyears else None)
        # stem = text before first choice marker; choices split by ①..
        stem_lines, choice_lines = [], []
        seen_choice = False
        for x in joined:
            if CHOICE.match(x):
                seen_choice = True
            (choice_lines if seen_choice else stem_lines).append(x)
        stem = collapse(stem_lines)
        # 연도 태그(괄호/대괄호, 연도 포함)를 stem 앞뒤에서 제거
        stem = re.sub(r"^\s*[\(\[][^\(\)\[\]]*20\d\d[^\(\)\[\]]*[\)\]]\s*", "", stem)
        stem = re.sub(r"\s*[\(\[][^\(\)\[\]]*20\d\d[^\(\)\[\]]*[\)\]]\s*$", "", stem).strip()
        # parse choices
        choices = {}
        cur_k = None
        buf = []
        for x in choice_lines:
            m = CHOICE.match(x)
            if m:
                if cur_k:
                    choices[cur_k] = collapse(buf)
                cur_k = CH2NUM.get(m.group(1), m.group(1))
                buf = [m.group(2)]
            elif cur_k:
                buf.append(x)
        if cur_k:
            choices[cur_k] = collapse(buf)
        # answer + explanation
        answer, expl = None, ""
        if ans_b:
            al = ans_b["lines"]
            # find 답 line
            for idx, x in enumerate(al):
                dm = DAP.match(x)
                if dm:
                    atxt = dm.group(1)
                    cm = re.search(r"[①-⑮]", atxt)
                    answer = CH2NUM.get(cm.group(0)) if cm else (re.search(r"\d+", atxt).group(0) if re.search(r"\d+", atxt) else atxt.strip())
                    expl = collapse(al[idx + 1:])
                    break
        out.append({"qnum": stem_b["num"], "topic": stem_b["topic"], "page": stem_b["page"],
                    "year": year, "years": allyears, "stem": stem, "choices": choices,
                    "answer": answer, "orig_explanation": expl})

    Path("data_private/chuljok/parsed.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # stats
    import collections
    yc = collections.Counter(o["year"] for o in out)
    print(f"파싱 문항 {len(out)}")
    for y in ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026", None]:
        if yc.get(y):
            print(f"  {y}: {yc[y]}")
    tgt = [o for o in out if o["year"] in TARGET]
    withch = sum(1 for o in tgt if len(o["choices"]) >= 2)
    withans = sum(1 for o in tgt if o["answer"])
    print(f"대상연도(2020·21·22·23·26): {len(tgt)} · 선지≥2 {withch} · 답있음 {withans}")


if __name__ == "__main__":
    main()
