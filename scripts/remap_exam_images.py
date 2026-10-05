#!/usr/bin/env python3
"""임상의학종합평가 기출 이미지를 문항에 재매핑.

방법: PDF에서 각 문항의 (페이지,y) 위치를 구하고, 추출된 이미지(bbox)를
읽기순서(page,y)로 정렬해 '이미지 바로 위 문항'에 연결.
--commit 없으면 dry-run(파일 미수정, 매핑만 출력).
"""

import sys
import json
import re
from pathlib import Path

import fitz

BASE = Path("data_private/course_exams/extracted")
PDFS = {
    "1교시": ("/Users/goyunseong/Downloads/4학년 임종평 1교시(법규, 예방 제외).pdf",
              "COURSE_4_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_1교시"),
    "2교시": ("/Users/goyunseong/Downloads/(4학년)(2026-6-22)임상의학종합시험-2교시(객80)(1120-1305).pdf",
              "COURSE_X_DATE_UNKNOWN_EXAM_2교시"),
    "3교시": ("/Users/goyunseong/Downloads/(4학년)(2026-6-23)임상의학종합시험-3교시(객80)(0900-1045).pdf",
              "COURSE_X_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_3교시"),
    "4교시": ("/Users/goyunseong/Downloads/(4학년)(2026-6-23)임상의학종합시험-4교시(객80)(1120-1305).pdf",
              "COURSE_X_DATE_UNKNOWN_EXAM_4교시"),
}


def norm(s):
    return re.sub(r"\s", "", s or "")


def remap(lab, pdf, stem, commit):
    doc = fitz.open(pdf)
    pages_norm = [norm(doc[i].get_text()) for i in range(doc.page_count)]
    d = json.loads((BASE / f"{stem}.json").read_text(encoding="utf-8"))
    qs = d["questions"]
    by_num = {q["question_number"]: q for q in qs}

    # 문항 -> (page, y)
    qpos = {}
    for q in qs:
        s = norm(q.get("stem"))
        snip = s[6:30] if len(s) > 30 else s
        pg = next((i for i, pn in enumerate(pages_norm) if snip and snip in pn), None)
        y = 9999.0
        if pg is not None:
            raw = q.get("stem") or ""
            for a, b in [(0, 10), (0, 7), (4, 16), (2, 12)]:
                needle = raw[a:b].strip()
                if len(needle) < 4:
                    continue
                rects = doc[pg].search_for(needle)
                if rects:
                    y = min(r.y0 for r in rects)
                    break
        qpos[q["question_number"]] = (pg, y)

    assets = [a for a in (d.get("media_assets") or [])
              if (a.get("width") or 0) >= 150 and (a.get("height") or 0) >= 150]

    # 읽기순서 스트림
    stream = []
    for qn, (pg, y) in qpos.items():
        if pg is not None:
            stream.append((pg, y, 0, qn))       # 0=question (같은 y면 문항 먼저)
    for a in assets:
        pg = (a.get("page_number") or 1) - 1
        bb = a.get("bbox") or [0, 9999, 0, 9999]
        stream.append((pg, float(bb[1]), 1, a))  # 1=image
    stream.sort(key=lambda t: (t[0], t[1], t[2]))

    assign = {}
    last = None
    for pg, y, typ, val in stream:
        if typ == 0:
            last = val
        elif last is not None:
            assign.setdefault(last, []).append(val)

    # 출력/커밋
    print(f"\n===== {lab}: 이미지 {len(assets)}개 → 문항 {len(assign)}개 매핑 =====")
    for qn in sorted(assign):
        imgs = assign[qn]
        stemtxt = (by_num[qn].get("stem") or "")[:38]
        files = ", ".join(a["media_id"].split("_")[-1] for a in imgs)
        print(f"  Q{qn:>3} ({files}) ← {stemtxt}")

    if commit:
        for a in assets:
            a["linked_question_numbers"] = []
        for qn, imgs in assign.items():
            q = by_num[qn]
            refs = []
            for a in imgs:
                refs.append({"media_id": a["media_id"], "needs_review": True,
                             "caption": a.get("caption"), "modality": a.get("modality"),
                             "remapped": True})
                a.setdefault("linked_question_numbers", []).append(qn)
            media = q.get("media") or {}
            media["media_refs"] = refs
            q["media"] = media
        # 매핑 안 된 문항은 media_refs 비움(잘못된 기존링크 정리)
        for q in qs:
            if q["question_number"] not in assign:
                q["media"] = {"media_refs": []}
        (BASE / f"{stem}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [commit] {lab} 저장 완료")


def main():
    commit = "--commit" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    for lab, (pdf, stem) in PDFS.items():
        if only and lab not in only:
            continue
        if not Path(pdf).exists():
            print(f"[경고] PDF 없음: {pdf}")
            continue
        remap(lab, pdf, stem, commit)


if __name__ == "__main__":
    raise SystemExit(main())
