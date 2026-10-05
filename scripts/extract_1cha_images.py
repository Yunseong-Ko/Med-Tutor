#!/usr/bin/env python3
"""2026 1차 임종평 사진자료 PDF에서 이미지 추출 + '사진 N' 캡션으로 문항 매핑.

각 이미지 아래의 '사진 N' 또는 '사진 N-M' 캡션을 찾아 문항번호 N에 연결.
저장: data_private/course_exams/media/<exam_id>/
"""

import re
import sys
import json
from pathlib import Path

import fitz

BASE = "/Users/goyunseong/Downloads/2026년 1차 임상의학종합평가 시험지PDF/"
MEDIA = Path("data_private/course_exams/media")
CAP_RE = re.compile(r"사진\s*(\d{1,3})(?:\s*-\s*(\d))?")


def exam_id(gyo):
    return f"COMPREHENSIVE_2026_1CHA_{gyo}교시"


def caption_spans(page):
    """페이지에서 '사진 N(-M)' 캡션의 (qnum, sub, cx, cy) 목록."""
    out = []
    d = page.get_text("dict")
    for blk in d.get("blocks", []):
        for line in blk.get("lines", []):
            txt = "".join(sp.get("text", "") for sp in line.get("spans", []))
            m = CAP_RE.search(txt)
            if m:
                x0, y0, x1, y1 = line["bbox"]
                out.append((int(m.group(1)), m.group(2), (x0 + x1) / 2, y0))
    return out


def extract(gyo, commit):
    eid = exam_id(gyo)
    doc = fitz.open(BASE + f"출력용)2026_1차_임종평_{gyo}교시_사진자료.pdf")
    outdir = MEDIA / eid
    if commit:
        outdir.mkdir(parents=True, exist_ok=True)
    assets = []
    qmap = {}  # qnum -> [media_id]
    for pi in range(doc.page_count):
        page = doc[pi]
        caps = caption_spans(page)
        if not caps:
            continue
        infos = [ii for ii in page.get_image_info(xrefs=True)
                 if ii.get("width", 0) >= 60 and ii.get("height", 0) >= 60]
        for ii in infos:
            bx0, by0, bx1, by1 = ii["bbox"]
            icx, ibottom = (bx0 + bx1) / 2, by1
            # 이미지 아래 가장 가까운 캡션(수평 근접)
            below = [c for c in caps if c[3] >= by0 and abs(c[2] - icx) < (bx1 - bx0)]
            if not below:
                below = [c for c in caps if c[3] >= ibottom - 5]
            if not below:
                continue
            qnum, sub, _, _ = min(below, key=lambda c: (abs(c[3] - ibottom), abs(c[2] - icx)))
            xref = ii["xref"]
            suffix = f"{qnum}" + (f"-{sub}" if sub else "")
            mid = f"{eid}_SAJIN{suffix}_x{xref}"
            fname = f"SAJIN{suffix}_x{xref}.png"
            if commit:
                pix = fitz.Pixmap(doc, xref)
                if pix.n >= 5:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                pix.save(str(outdir / fname))
            assets.append({"media_id": mid, "file_path": str(outdir / fname),
                           "relative_path": f"{eid}/{fname}", "page_number": pi + 1,
                           "bbox": [bx0, by0, bx1, by1], "width": ii["width"], "height": ii["height"],
                           "sajin": suffix, "modality": None, "caption": f"사진 {suffix}",
                           "linked_question_numbers": [qnum], "needs_review": True})
            qmap.setdefault(qnum, []).append(mid)
    return eid, assets, qmap


def main():
    gyo = sys.argv[1] if len(sys.argv) > 1 else "1"
    commit = "--commit" in sys.argv
    eid, assets, qmap = extract(gyo, commit)
    print(f"[{gyo}교시] 이미지 {len(assets)}장 → 문항 {len(qmap)}개 매핑 (commit={commit})")
    for qn in sorted(qmap)[:8]:
        print(f"  Q{qn}: {[a.split('_')[-2] for a in qmap[qn]]}")
    if commit:
        Path("data_private/course_exams/extracted").mkdir(parents=True, exist_ok=True)
        tmp = Path(f"/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad/1cha_img_{gyo}.json")
        tmp.write_text(json.dumps({"exam_id": eid, "assets": assets, "qmap": qmap}, ensure_ascii=False, indent=1))
        print("  저장:", tmp)


if __name__ == "__main__":
    raise SystemExit(main())
