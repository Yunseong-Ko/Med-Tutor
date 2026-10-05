#!/usr/bin/env python3
"""생성 문항 JSON → 시험지 양식 DOCX (교시별) + 정답표 별도.

양식: [No n] [관리번호 : MKxxxxx] + 문두 + (검사수치 표) + 이미지 + ①~⑤
정답은 본문에 넣지 않음(정답표 별도 파일) — 배포 안전.
입력: --items data_private/professor_items/generated/set_<k>.json
      [{no, mgmt_no, stem, lab_box, image, choices{1..5}, answer, explanation}]
출력: exports/모의고사_<세트명>.docx + 모의고사_<세트명>_정답표.docx
"""
import argparse
import json
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

try:
    from scripts.lab_box_render import add_lab_box
except ImportError:  # 직접 실행(python3 scripts/…) 시
    from lab_box_render import add_lab_box

BASE = Path("data_private/professor_items")
IMG_DIR = BASE / "images"
CIRC = {"1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤"}


def add_item(doc, it):
    p = doc.add_paragraph()
    r = p.add_run(f"[No {it['no']}] [관리번호 : {it.get('mgmt_no','')}] ")
    r.bold = True
    p.add_run(str(it.get("stem", "")))
    if it.get("lab_box"):
        # 설문 T3 반영: 2열 표(검사·결과). 파싱 실패 시 기존 1칸 박스 폴백.
        add_lab_box(doc, it["lab_box"])
    img = it.get("image")
    if img and (IMG_DIR / img).exists():
        ip = doc.add_paragraph(); ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
        try:
            ip.add_run().add_picture(str(IMG_DIR / img), width=Cm(9))
        except Exception:
            ip.add_run(f"[이미지: {img}]")
    for k in sorted(it.get("choices", {}), key=lambda x: int(x)):
        v = it["choices"][k]
        if v:
            doc.add_paragraph(f"{CIRC.get(k,k)} {v}")
    doc.add_paragraph("")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--title", default="모의고사")
    args = ap.parse_args()
    data = json.loads(Path(args.items).read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data

    doc = Document()
    st = doc.styles["Normal"]; st.font.name = "맑은 고딕"; st.font.size = Pt(11)
    h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hr = h.add_run(args.title); hr.bold = True; hr.font.size = Pt(16)
    doc.add_paragraph("")
    for it in items:
        add_item(doc, it)
    outdir = BASE / "exports"; outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{args.title}.docx"
    doc.save(out)

    # 정답표 (별도)
    kd = Document()
    kh = kd.add_paragraph(); kh.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kr = kh.add_run(f"{args.title} — 정답표 (배포 금지)"); kr.bold = True; kr.font.size = Pt(14)
    kr.font.color.rgb = RGBColor(0xB9, 0x1C, 0x1C)
    t = kd.add_table(rows=0, cols=10); t.style = "Table Grid"
    row = None
    for i, it in enumerate(items):
        if i % 5 == 0:
            row = t.add_row().cells
        row[(i % 5) * 2].text = f"No {it['no']}"
        row[(i % 5) * 2 + 1].text = CIRC.get(str(it.get("answer", "")), str(it.get("answer", "")))
    key_out = outdir / f"{args.title}_정답표.docx"
    kd.save(key_out)
    print(f"[docx] {out}  ({len(items)}문항)")
    print(f"[정답표] {key_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
