#!/usr/bin/env python3
"""강의 원본(PPTX/PDF)에서 이미지 + 같은 슬라이드/페이지의 캡션 텍스트를 함께 추출.

목적: 혈액 도말·골수·조직 현미경 사진을 판독 카드로 만들기 위한 후보 수집.
슬라이드 텍스트(교수 캡션)를 이미지와 페어링해 뒤 단계(비전 판독)의 환각을 줄인다.

필터: 최소변 >= MINSIDE px, 면적 >= MINAREA, 종횡비 0.35~2.8(사진형), 동일이미지 dedup(해시).
출력: scratchpad staging dir/<lid>/img_XXX.png + manifest.json [{lid,unit,idx,img,w,h,context}]

사용: python3 scripts/extract_lecture_images.py --out <dir> --files "<f1>" "<f2>" ...
      (--files 없으면 SRC_BASE 하위 기본 타깃 목록)
"""

import argparse
import hashlib
import io
import json
import re
import unicodedata
from pathlib import Path

from PIL import Image

SRC_BASE = Path("/Users/goyunseong/Desktop/본2-1/혈액종양")
MINSIDE = 180
MINAREA = 55_000
AR_LO, AR_HI = 0.35, 2.8


def lid_of(path: Path) -> str:
    return unicodedata.normalize("NFC", path.stem).replace(" ", "_")


def keep(w, h) -> bool:
    if min(w, h) < MINSIDE or w * h < MINAREA:
        return False
    ar = w / h
    return AR_LO <= ar <= AR_HI


def clean(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()[:400]


def from_pptx(path: Path):
    """(context_text, image_bytes) 리스트 — 슬라이드별 페어."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    out = []
    prs = Presentation(str(path))

    def walk(shapes, texts, imgs):
        for sh in shapes:
            if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                walk(sh.shapes, texts, imgs)
                continue
            if sh.has_text_frame and sh.text_frame.text.strip():
                texts.append(sh.text_frame.text.strip())
            try:
                if sh.shape_type == MSO_SHAPE_TYPE.PICTURE or getattr(sh, "image", None):
                    imgs.append(sh.image.blob)
            except Exception:
                pass

    for slide in prs.slides:
        texts, imgs = [], []
        walk(slide.shapes, texts, imgs)
        ctx = clean(" / ".join(texts))
        for blob in imgs:
            out.append((ctx, blob))
    return out


def from_pdf(path: Path):
    import fitz
    out = []
    doc = fitz.open(str(path))
    for page in doc:
        ctx = clean(page.get_text())
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n >= 5:  # CMYK/alpha → RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                out.append((ctx, pix.tobytes("png")))
            except Exception:
                continue
    doc.close()
    return out


DEFAULT_TARGETS = [
    "20260713/20260713_6-7교시_2026 조혈계조직학 (여름계절수업) 20260713.pdf",
    "20260714/20260714_2교시_PB BM_김혜림.pdf",
    "20260714/20260714_1교시_혈액검사_김인숙_강의록.pdf",
    "20260714/20260714_3교시_철결핍성 빈혈-정기선.pdf",
    "20260714/20260714_4교시_기타 빈혈 감별진단-정기선.pdf",
    "20260714/20260714_6교시_대구성빈혈-정기선.pdf",
    "20260714/20260714_7교시_후천성용혈빈혈-김도영.pdf",
    "20260714/20260714_8교시-선천용혈빈혈-양유진.pdf",
    "20260714/20260714_9교시-소아 빈혈-양유진.pdf",
    "20260715/20260715_2교시_백혈구질환1-정기선.pdf",
    "20260715/20260715_3교시_백혈구질환2 및 비장질환_김도영.pdf",
    "20260715/20260715_6, 7교시_acute leukemia.pdf",
    "20260716/20260716_1교시_만성백혈병1-정기선.pdf",
    "20260716/20260716_2교시_만성백혈병2-정기선.pdf",
    "20260716/20260716_3교시_골수증식성질환-김도영.pdf",
    "20260716/20260716_4교시_PBS BME CS 김혜림.pdf",
    "20260716/20260716_6, 7교시_Lymphoma.pathol_2026.pdf",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--files", nargs="*", default=None)
    args = ap.parse_args()
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    files = args.files or [str(SRC_BASE / t) for t in DEFAULT_TARGETS]
    manifest = []
    seen = set()
    per = {}
    for fp in files:
        p = Path(fp)
        if not p.exists():
            print(f"  MISS {p.name}")
            continue
        lid = lid_of(p)
        pairs = from_pptx(p) if p.suffix.lower() == ".pptx" else from_pdf(p)
        d = out_root / lid
        d.mkdir(exist_ok=True)
        kept = 0
        for ctx, blob in pairs:
            h = hashlib.sha1(blob).hexdigest()[:16]
            if h in seen:
                continue
            try:
                im = Image.open(io.BytesIO(blob))
                w, hh = im.size
            except Exception:
                continue
            if not keep(w, hh):
                continue
            seen.add(h)
            idx = kept
            name = f"img_{idx:03d}.png"
            try:
                im.convert("RGB").save(d / name)
            except Exception:
                continue
            manifest.append({"lid": lid, "idx": idx, "img": str(d / name),
                             "w": w, "h": hh, "context": ctx})
            kept += 1
        per[lid] = kept
        print(f"  {p.name[:48]:48s} → {kept} 후보")
    (out_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 후보 이미지 {len(manifest)} · 강의 {len(per)}")
    print(f"manifest: {out_root/'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
