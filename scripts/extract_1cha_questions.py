#!/usr/bin/env python3
"""2026 1차 임상의학종합평가 한글시험지(2단 편집)에서 문항 추출 → 텍스트 파싱.

문항: 'N.' 시작 + 스템 + ①~⑤ 선지. 2단은 컬럼별(좌→우) 읽기순서로 정렬.
"""

import re
import sys
import fitz

BASE = "/Users/goyunseong/Downloads/2026년 1차 임상의학종합평가 시험지PDF/"
CIRCLED = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}
CIRC_RE = re.compile(r"[①②③④⑤]")


def page_reading_text(page):
    """2단 편집: 헤더/푸터 제외, 좌컬럼→우컬럼 순서로 블록 텍스트."""
    W = page.rect.width
    H = page.rect.height
    mid = W / 2
    blocks = page.get_text("blocks")  # (x0,y0,x1,y1,text,bno,btype)
    body = []
    for b in blocks:
        x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
        if not text.strip():
            continue
        if y0 < H * 0.04 or y1 > H * 0.96:  # 헤더/푸터
            continue
        col = 0 if (x0 + x1) / 2 < mid else 1
        body.append((col, y0, text))
    body.sort(key=lambda t: (t[0], t[1]))
    return "\n".join(t[2] for t in body)


def extract(gyo):
    doc = fitz.open(BASE + f"출력용)2026_1차_임종평_{gyo}교시_한글시험지.pdf")
    # 문항 페이지: 헤더에 '임상의학종합평가' 있고 'N.' 문항이 있는 페이지
    chunks = []
    for i in range(doc.page_count):
        t = doc[i].get_text()
        if "임상의학종합평가" in t and re.search(r"(?m)^\s*\d{1,3}\.", t):
            chunks.append(page_reading_text(doc[i]))
    full = "\n".join(chunks)
    # 지시문 제거
    full = re.sub(r"※[^\n]*고르시오\.?", "", full)
    # 문항 경계: 줄 시작 'N.' (1~80)
    # 선지 앞의 번호와 구분 위해, '숫자.' 뒤 공백+한글/영문 시작을 문항으로
    parts = re.split(r"(?m)^\s*(\d{1,3})\.\s", full)
    # parts = ['', '1', 'stem+choices', '2', 'stem+choices', ...]
    questions = {}
    for k in range(1, len(parts), 2):
        num = int(parts[k])
        if not (1 <= num <= 80):
            continue
        blob = parts[k + 1]
        # 선지 분리
        segs = CIRC_RE.split(blob)
        markers = CIRC_RE.findall(blob)
        stem = re.sub(r"\s+", " ", segs[0]).strip()
        choices = {}
        for mk, seg in zip(markers, segs[1:]):
            choices[CIRCLED[mk]] = re.sub(r"\s+", " ", seg).strip()
        # 다음 문항 번호가 선지 뒤에 붙어온 경우 마지막 선지에서 잘라내기
        if "5" in choices:
            choices["5"] = re.sub(r"\s*\d{1,3}\.\s*$", "", choices["5"]).strip()
        questions[num] = {"stem": stem, "choices": choices}
    return questions


def main():
    gyo = sys.argv[1] if len(sys.argv) > 1 else "1"
    qs = extract(gyo)
    print(f"[{gyo}교시] 추출 문항 {len(qs)}/80")
    # 품질 점검: 선지 5개 미만
    bad = [n for n in qs if len(qs[n]["choices"]) != 5]
    print("선지≠5 문항:", bad or "없음")
    # 샘플 출력
    for n in [1, 2, 40, 80]:
        if n in qs:
            q = qs[n]
            print(f"\n--- Q{n} ---")
            print("stem:", q["stem"][:110])
            for k in ["1", "2", "3", "4", "5"]:
                print(f"  {k}. {q['choices'].get(k,'(없음)')[:50]}")


if __name__ == "__main__":
    raise SystemExit(main())
