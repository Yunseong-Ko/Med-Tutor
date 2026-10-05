#!/usr/bin/env python3
"""단일 PDF 교과서 → 해리슨식 로컬 인덱스 (pages.jsonl + chapter_index + manifest).

해리슨 22e는 장별 분할 PDF였지만, 이 책들은 단일 파일이라 내장 목차(TOC)로 장 경계를 잡는다.
저작권: 전문을 외부로 보내지 않는다 — 로컬 인덱스·근거 포인터 용도로만 쓴다(해리슨과 동일 정책).

출력: data_private/textbooks/<book_id>/{pages.jsonl, chapter_index.json, manifest.json}
사용: python3 scripts/build_textbook_index.py --pdf <파일> --book-id sabiston_21e --title "Sabiston 21e"
"""
import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import fitz

OUT_ROOT = Path("data_private/textbooks")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def clean(v):
    """PDF 추출물의 고아 서러게이트 제거 — label 포함 모든 문자열에 적용해야 한다."""
    if v is None:
        return None
    return str(v).encode("utf-8", "replace").decode("utf-8")


def scan_chapters_from_text(doc) -> list:
    """TOC가 부실한 책: 본문 페이지 첫 부분에서 장 헤더를 직접 찾는다."""
    pat = re.compile(r"^\s*(?:CHAPTER|Chapter)\s+(\d{1,3})|^\s*제\s*(\d{1,2})\s*장", re.M)
    found, last = [], 0
    for i in range(doc.page_count):
        head = doc[i].get_text("text")[:400]
        m = pat.search(head)
        if not m:
            continue
        no = int(m.group(1) or m.group(2))
        if no == last + 1 or (no > last and no - last <= 3):   # 단조 증가(리스트·참조 오탐 차단)
            lines = [l.strip() for l in head.splitlines() if l.strip()]
            idx = next((k for k, l in enumerate(lines) if pat.match(l)), 0)
            title = lines[idx + 1] if idx + 1 < len(lines) else ""
            found.append({"chapter": no, "title": clean(title)[:120], "pdf_page": i + 1, "level": 0})
            last = no
    return found


def pick_chapters(toc: list) -> list:
    """TOC에서 '장' 수준 항목을 고른다. 'Chapter N'/숫자 접두 패턴 우선, 없으면 레벨 1."""
    pat = re.compile(r"^\s*(?:chapter\s*)?(\d{1,3})\s*[.:·]?\s+(.{3,})", re.I)
    hits = []
    for level, title, page in toc:
        t = unicodedata.normalize("NFC", clean(str(title))).strip()
        m = pat.match(t)
        if m and level <= 3:
            hits.append({"chapter": int(m.group(1)), "title": m.group(2).strip()[:120],
                         "pdf_page": page, "level": level})
    if len(hits) >= 10:
        # 같은 번호 중복(부/장 충돌) 제거 — 페이지 순으로 첫 것만
        seen, out = set(), []
        for h in sorted(hits, key=lambda x: x["pdf_page"]):
            if h["chapter"] in seen:
                continue
            seen.add(h["chapter"])
            out.append(h)
        return out
    lvl2 = [(l, clean(str(t)).strip(), p) for l, t, p in toc if l <= 2 and clean(str(t)).strip()]
    if len(lvl2) >= 15:
        return [{"chapter": i + 1, "title": t[:120], "pdf_page": p, "level": l}
                for i, (l, t, p) in enumerate(sorted(lvl2, key=lambda x: x[2]))]
    lvl1 = [{"chapter": i + 1, "title": clean(str(t)).strip()[:120], "pdf_page": p, "level": l}
            for i, (l, t, p) in enumerate(toc) if l == 1]
    return lvl1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--book-id", required=True)
    ap.add_argument("--title", required=True)
    args = ap.parse_args()

    src = Path(args.pdf)
    out = OUT_ROOT / args.book_id
    out.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(src)
    file_sha = sha(src.read_bytes())

    chapters = pick_chapters(doc.get_toc() or [])
    if len(chapters) < 12:
        scanned = scan_chapters_from_text(doc)
        if len(scanned) > len(chapters):
            print(f"  (TOC {len(chapters)}장 → 본문 스캔으로 {len(scanned)}장 채택)")
            chapters = scanned
    bounds = []
    for i, ch in enumerate(chapters):
        end = chapters[i + 1]["pdf_page"] - 1 if i + 1 < len(chapters) else doc.page_count
        bounds.append((ch["pdf_page"], end, ch))

    def chapter_of(p1: int):
        for s, e, ch in bounds:
            if s <= p1 <= e:
                return ch
        return None

    n_text = 0
    with (out / "pages.jsonl").open("w", encoding="utf-8") as f:
        for i in range(doc.page_count):
            page = doc[i]
            text = clean(page.get_text("text"))
            try:
                label = clean(page.get_label()) or None
            except Exception:
                label = None
            ch = chapter_of(i + 1)
            if text.strip():
                n_text += 1
            f.write(json.dumps({
                "pdf_page": i + 1,
                "printed_label": label,
                "chapter": ch["chapter"] if ch else None,
                "chapter_title": clean(ch["title"]) if ch else None,
                "chars": len(text),
                "text": text,
                "text_sha256": sha(text.encode("utf-8"))[:24],
            }, ensure_ascii=False) + "\n")

    (out / "chapter_index.json").write_text(json.dumps({
        "book_id": args.book_id, "title": args.title,
        "chapters": [{"chapter": ch["chapter"], "title": ch["title"],
                      "pdf_page_start": s, "pdf_page_end": e}
                     for s, e, ch in bounds],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    (out / "manifest.json").write_text(json.dumps({
        "schema": "paccine.textbook_index.v1",
        "book_id": args.book_id, "title": args.title,
        "source_file": src.name, "source_sha256": file_sha,
        "pages": doc.page_count, "pages_with_text": n_text,
        "chapters": len(bounds),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "policy": "local-only evidence pointers; full text never leaves this machine",
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[{args.book_id}] {doc.page_count}p (텍스트 {n_text}p) · 장 {len(bounds)}개 → {out}")
    if not bounds:
        print("  ! TOC에서 장을 못 찾음 — chapter_index 비어 있음(스캔본 가능성)")
    if n_text < doc.page_count * 0.5:
        print("  ! 텍스트 레이어 부족 — 스캔 PDF일 수 있음(OCR 필요)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
