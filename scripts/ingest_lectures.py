#!/usr/bin/env python3
"""강의자료(PPTX/PDF) → 섹션 텍스트 JSON (S1 인제스트).

원칙: 원문은 data_private에만. 개념 카드·문항 생성의 입력 컨텍스트로만 사용(학생 원문 노출 아님).
NFD 경로 안전: base 디렉토리를 os.scandir로 순회(하드코딩 NFC 금지).
PPTX=python-pptx(슬라이드 텍스트+노트), PDF=fitz(페이지 텍스트; 스캔본은 텍스트 희박→이미지-only).

출력: data_private/lectures/<lecture_id>/sections.json
  { lecture_id, source_name, kind, section_count, scanned(bool), sections:[{idx,title,text,char}] }
"""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path

BASE_DEFAULT = "/Users/goyunseong/Desktop/본2-1/혈액종양"
OUT_ROOT = Path("data_private/lectures")


def slug(name: str) -> str:
    s = unicodedata.normalize("NFC", name)
    s = re.sub(r"\.(pdf|pptx)$", "", s, flags=re.I)
    s = re.sub(r"[^\w가-힣]+", "_", s).strip("_")
    return s[:80]


def scan_files(base: str, keywords):
    """base를 재귀 순회(os.walk, NFD 안전). 날짜 서브디렉토리 안의 파일까지.
    keywords 중 하나라도 파일명에 있으면 채택(없으면 전체)."""
    out = []
    for root, _dirs, names in os.walk(base):
        for name in names:
            low = name.lower()
            if not (low.endswith(".pdf") or low.endswith(".pptx")):
                continue
            nfc = unicodedata.normalize("NFC", name)
            if keywords and not any(unicodedata.normalize("NFC", k) in nfc for k in keywords):
                continue
            out.append(os.path.join(root, name))
    return sorted(out)


def ingest_pptx(path):
    from pptx import Presentation
    pr = Presentation(path)
    sections = []
    for i, slide in enumerate(pr.slides, 1):
        title = ""
        body = []
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            t = sh.text_frame.text.strip()
            if not t:
                continue
            if sh == slide.shapes.title or (not title and len(t) < 60):
                title = title or t
            body.append(t)
        note = ""
        if slide.has_notes_slide:
            note = (slide.notes_slide.notes_text_frame.text or "").strip()
        text = "\n".join(dict.fromkeys(body))  # dedupe preserve order
        if note:
            text += f"\n[노트] {note}"
        sections.append({"idx": i, "title": re.sub(r"\s+", " ", title)[:120], "text": text, "char": len(text)})
    return sections, False


def ingest_pdf(path):
    import fitz
    d = fitz.open(path)
    sections = []
    total_txt = 0
    for i in range(d.page_count):
        t = d[i].get_text().strip()
        total_txt += len(t)
        first = t.split("\n", 1)[0] if t else ""
        sections.append({"idx": i + 1, "title": re.sub(r"\s+", " ", first)[:120], "text": t, "char": len(t)})
    scanned = total_txt < 200 * max(1, d.page_count) // 10  # 페이지당 평균 <20자면 스캔 의심
    return sections, scanned


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = args[0] if args else BASE_DEFAULT
    keywords = args[1:]  # 파일명 필터(파일럿용). 없으면 전체.
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    files = scan_files(base, keywords)
    print(f"대상 {len(files)}개 (필터: {keywords or '전체'})")
    for p in files:
        name = os.path.basename(p)
        lid = slug(name)
        kind = "pptx" if p.lower().endswith(".pptx") else "pdf"
        try:
            sections, scanned = (ingest_pptx(p) if kind == "pptx" else ingest_pdf(p))
        except Exception as e:
            print(f"  ERR {type(e).__name__}: {name[:40]}")
            continue
        nonempty = [s for s in sections if s["char"] > 5]
        rec = {
            "lecture_id": lid,
            "source_name": unicodedata.normalize("NFC", name),
            "kind": kind,
            "scanned": scanned,
            "section_count": len(sections),
            "nonempty_sections": len(nonempty),
            "total_chars": sum(s["char"] for s in sections),
            "sections": sections,
            "needs_review": True,
        }
        outdir = OUT_ROOT / lid
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "sections.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        flag = " [스캔의심]" if scanned else ""
        print(f"  {lid[:46]:46s} {kind} · {len(sections)}섹션 · {rec['total_chars']}자{flag}")


if __name__ == "__main__":
    main()
