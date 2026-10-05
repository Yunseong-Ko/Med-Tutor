#!/usr/bin/env python3
"""추출 시 누락된 기출 이미지를 PDF에서 직접 뽑아 해당 문항에 부착.

대상: '사진' 명시인데 미연결이고 PDF 해당 페이지에 이미지가 있는 문항.
"""

import json
import re
from pathlib import Path

import fitz

BASE = Path("data_private/course_exams/extracted")
MEDIA = Path("data_private/course_exams/media")
TARGETS = {  # (교시 stem, [문항번호]) — 정밀진단으로 확인된 미연결
    "COURSE_X_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_3교시": (
        "/Users/goyunseong/Downloads/(4학년)(2026-6-23)임상의학종합시험-3교시(객80)(0900-1045).pdf", [78]),
    "COURSE_X_DATE_UNKNOWN_EXAM_4교시": (
        "/Users/goyunseong/Downloads/(4학년)(2026-6-23)임상의학종합시험-4교시(객80)(1120-1305).pdf", [25, 61, 78]),
}


def norm(s):
    return re.sub(r"\s", "", s or "")


def bbox_overlap(b1, b2):
    # 같은 이미지인지 대략 판정(중심 근접)
    cx1, cy1 = (b1[0] + b1[2]) / 2, (b1[1] + b1[3]) / 2
    return b2[0] - 5 <= cx1 <= b2[2] + 5 and b2[1] - 5 <= cy1 <= b2[3] + 5


def main():
    for stem, (pdf, qnums) in TARGETS.items():
        doc = fitz.open(pdf)
        pages_norm = [norm(doc[i].get_text()) for i in range(doc.page_count)]
        d = json.loads((BASE / f"{stem}.json").read_text(encoding="utf-8"))
        by_num = {q["question_number"]: q for q in d["questions"]}
        assets = d.setdefault("media_assets", [])
        existing = [(a.get("page_number"), a.get("bbox")) for a in assets]
        outdir = MEDIA / stem
        outdir.mkdir(parents=True, exist_ok=True)

        for qn in qnums:
            q = by_num[qn]
            s = norm(q.get("stem"))
            snip = s[6:30] if len(s) > 30 else s
            pg = next((i for i, pn in enumerate(pages_norm) if snip and snip in pn), None)
            if pg is None:
                print(f"  [{stem[-3:]} Q{qn}] 페이지 못찾음")
                continue
            # 문항 y
            qy = 0
            for a, b in [(0, 10), (0, 7), (4, 16)]:
                r = doc[pg].search_for((q.get("stem") or "")[a:b].strip())
                if r:
                    qy = min(x.y0 for x in r)
                    break
            # 페이지의 큰 이미지 중 문항 아래 + 아직 미추출인 것
            cands = [ii for ii in doc[pg].get_image_info(xrefs=True)
                     if ii.get("width", 0) >= 150 and ii.get("height", 0) >= 150
                     and ii["bbox"][1] >= qy - 5]
            cands.sort(key=lambda ii: ii["bbox"][1])
            picked = None
            for ii in cands:
                if not any(p == pg + 1 and bb and bbox_overlap(ii["bbox"], bb) for p, bb in existing):
                    picked = ii
                    break
            if not picked:
                # 아래에 없으면 페이지 전체에서 미추출 이미지
                for ii in sorted(doc[pg].get_image_info(xrefs=True), key=lambda x: x["bbox"][1]):
                    if ii.get("width", 0) >= 150 and not any(p == pg + 1 and bb and bbox_overlap(ii["bbox"], bb) for p, bb in existing):
                        picked = ii
                        break
            if not picked:
                print(f"  [{stem[-3:]} Q{qn}] 미추출 이미지 없음")
                continue
            xref = picked["xref"]
            pix = fitz.Pixmap(doc, xref)
            if pix.n >= 5:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            fname = f"EXTRA_Q{qn:03d}_p{pg+1}.png"
            pix.save(str(outdir / fname))
            mid = f"{stem}_EXTRA_Q{qn:03d}"
            assets.append({"media_id": mid, "file_path": str(MEDIA / stem / fname),
                           "relative_path": f"{stem}/{fname}", "page_number": pg + 1,
                           "bbox": list(picked["bbox"]), "width": pix.width, "height": pix.height,
                           "modality": None, "caption": None, "linked_question_numbers": [qn],
                           "needs_review": True, "match_confidence": 0.9, "source": "reextracted_from_pdf"})
            existing.append((pg + 1, list(picked["bbox"])))
            media = q.get("media") or {}
            refs = media.get("media_refs") or []
            refs.append({"media_id": mid, "needs_review": True, "remapped": True, "reextracted": True})
            media["media_refs"] = refs
            q["media"] = media
            print(f"  [{stem[-3:]} Q{qn}] 추출·부착 → {fname} ({pix.width}x{pix.height})")
        (BASE / f"{stem}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print("완료")


if __name__ == "__main__":
    raise SystemExit(main())
