#!/usr/bin/env python3
"""쪽 번호 없는 교과서의 절(section) 인덱스 빌더 (T-TBX-03, 2026-10-05).

전자책 재조판 PDF(Williams 25e·Berek 16e)는 인쇄 쪽 번호가 파일에 없어 "Ch.N › 절 제목"으로 인용한다.
이 스크립트는 `data_private/textbooks/<book_id>/section_index.json`(추가 파일)만 만든다 —
`pages.jsonl`·`chapter_index.json`·`manifest.json`은 읽기만 하고 수정하지 않는다. 장 경계는 chapter_index.json을 그대로 따른다.

소스 선택(--source auto):
  - toc  : PDF 목차가 장 아래 단계를 갖고 있으면 그것을 쓴다(Berek 16e).
  - font : 아니면 본문보다 큰 굵은 글씨 한 줄짜리 제목을 검출한다(Williams 25e). 그림·표 캡션, 장 표지의 개요·'CHAPTER N' 줄,
           머리말·꼬리말 반복 줄, 색인 알파벳 같은 너무 짧은 줄은 제외한다.

항목: {section_id("<장>.<순번>"), chapter, level(장 아래 상대 단계 1~), title, path[], pdf_page_start, pdf_page_end}.
저작권: 전문을 외부로 보내지 않는다. 이 파일에는 제목 문자열·숫자만 들어가며 본문은 들어가지 않는다.

사용: python3 scripts/build_textbook_sections.py --book-id berek_novak_16e --pdf "<파일>"
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEXTBOOKS_DIR = ROOT / "data_private" / "textbooks"
SCHEMA = "paccine.textbook_sections.v1"

MAX_TITLE_CHARS = 300               # 안전 상한(단어 경계에서 자름) — 실제 제목은 이보다 훨씬 짧아 잘리지 않아야 한다(T-TBX-03 QA: 120자 절단 수정)
NON_CITABLE_TITLES = frozenset({"references", "bibliography", "suggested readings", "suggested reading", "further reading", "further readings"})   # 참고문헌 제목은 근거로 인용 불가
MIN_TITLE_ALPHA = 3                 # 'A', 'B' 같은 색인 알파벳·쪽 번호 제외
HEADING_SIZE_RATIO = (1.15, 1.6)    # 본문 글자 크기 대비 제목 후보 범위(그보다 크면 장 제목·부 제목)
HEADER_REPEAT_PAGES = 8             # 같은 줄이 이만큼 이상의 쪽에 되풀이되고 쪽 위·아래 가장자리에 있으면 머리말·꼬리말
MARGIN_FRACTION = 0.08
MERGE_GAP_RATIO = 1.35              # 같은 크기·같은 x의 연속 굵은 줄이 이 간격 안이면 한 제목이 줄바꿈된 것으로 합친다
_CAPTION_RE = re.compile(r"^\s*(FIGURE|FIG\.|TABLE|BOX|ALGORITHM|VIDEO|PLATE)\b", re.I)
_CHAPTER_LABEL_RE = re.compile(r"^\s*CHAPTER\s+\d+\s*$", re.I)
_CHAPTER_TOC_RE = re.compile(r"^\s*chapter\s+(\d+)\s*[:.]", re.I)


def clean_title(value: str) -> str:
    """제목 표시용 정리: 서러게이트·소프트 하이픈 제거, 앞쪽 기호·공백 제거, 공백 축약."""
    text = str(value or "").encode("utf-8", "replace").decode("utf-8").replace("­", "")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"^[^\w(\[]+", "", text.strip())
    text = " ".join(text.split())
    if len(text) > MAX_TITLE_CHARS:
        cut = text[:MAX_TITLE_CHARS]
        text = (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip()
    return text


def is_citable_title(title: str) -> bool:
    """참고문헌류 제목(정규화: 소문자·공백 축약·끝 구두점 제거)이면 False."""
    norm = " ".join(str(title or "").lower().split()).strip(" .:;")
    return norm not in NON_CITABLE_TITLES


def load_chapters(book_dir: Path) -> list[dict]:
    payload = json.loads((book_dir / "chapter_index.json").read_text(encoding="utf-8"))
    chapters = payload.get("chapters") if isinstance(payload, dict) else payload
    out = []
    for row in chapters or []:
        out.append({"chapter": int(row["chapter"]), "title": row.get("title") or "", "start": int(row["pdf_page_start"]), "end": int(row["pdf_page_end"])})
    out.sort(key=lambda c: c["start"])
    return out


def load_page_chars(book_dir: Path) -> dict[int, tuple[int | None, int]]:
    """pdf_page → (chapter, chars). 본문 텍스트는 읽자마자 버린다(길이만 보관)."""
    out: dict[int, tuple[int | None, int]] = {}
    with (book_dir / "pages.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            out[int(row["pdf_page"])] = (row.get("chapter"), int(row.get("chars") or 0))
    return out


# ── 소스 1: PDF 목차 ───────────────────────────────────────────────────────────
def chapter_level_of(toc: list, chapters: list[dict]) -> tuple[int | None, int]:
    """장 시작 쪽과 가장 많이 겹치는 목차 단계(= 장 단계)와 겹친 수."""
    starts = {c["start"] for c in chapters}
    hits = collections.Counter(level for level, _title, page in toc if page in starts)
    if not hits:
        return None, 0
    level, count = hits.most_common(1)[0]
    return level, count


def deeper_toc_count(toc: list, chapter_level: int | None) -> int:
    return 0 if chapter_level is None else sum(1 for level, _t, _p in toc if level > chapter_level)


def sections_from_toc(toc: list, chapters: list[dict], chapter_level: int) -> tuple[list[dict], dict]:
    """목차를 순서대로 훑어 장 단계 항목으로 현재 장을 정하고, 그 아래 단계 항목을 절로 모은다."""
    by_start = {c["start"]: c for c in chapters}
    by_no = {c["chapter"]: c for c in chapters}
    current: dict | None = None
    raw: list[dict] = []
    dropped = 0
    for level, title, page in toc:
        if level == chapter_level:
            match = _CHAPTER_TOC_RE.match(title or "")
            current = by_start.get(page) or (by_no.get(int(match.group(1))) if match else None)
            continue
        if level < chapter_level:
            current = None
            continue
        if current is None or not (current["start"] <= page <= current["end"]):
            dropped += 1
            continue
        raw.append({"chapter": current["chapter"], "level": level - chapter_level, "title": clean_title(title), "start": int(page)})
    return finalize(raw, chapters), {"toc_deeper_entries": deeper_toc_count(toc, chapter_level), "toc_entries_dropped": dropped}


# ── 소스 2: 글꼴 기반 제목 검출 ──────────────────────────────────────────────────
def _heading_level(text: str, x0: float, left_margin: float) -> int:
    """Williams식 위계: 대문자만 = 1단계, 글머리 기호(앞 공백·들여쓰기) = 2단계, 나머지 제목형 = 3단계."""
    stripped = text.strip()
    if not re.search(r"[a-z]", stripped):
        return 1
    if text[:1].isspace() or x0 - left_margin >= 6:
        return 2
    return 3


def detect_body_size(doc, pages: list[int]) -> float:
    sizes: collections.Counter = collections.Counter()
    for pno in pages:
        for block in doc[pno - 1].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if not span["flags"] & 16 and span["text"].strip():
                        sizes[round(span["size"], 1)] += len(span["text"])
    return sizes.most_common(1)[0][0] if sizes else 0.0


def heading_lines(doc, pno: int, body: float) -> list[dict]:
    """한 쪽의 제목 후보 줄: 줄의 모든 span이 굵고 글자 크기가 본문보다 한 단계 큰 한 줄."""
    page = doc[pno - 1]
    height = float(page.rect.height)
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans or not all(s["flags"] & 16 for s in spans):
                continue
            size = round(spans[0]["size"], 1)
            if not (body * HEADING_SIZE_RATIO[0] <= size <= body * HEADING_SIZE_RATIO[1]):
                continue
            text = "".join(s["text"] for s in spans)
            out.append({"page": pno, "x0": float(line["bbox"][0]), "y0": float(line["bbox"][1]), "y1": float(line["bbox"][3]), "size": size, "text": text, "height": height})
    out.sort(key=lambda r: (r["y0"], r["x0"]))
    return out


def _is_caps(text: str) -> bool:
    return not re.search(r"[a-z]", text)


def merge_wrapped(lines: list[dict]) -> list[dict]:
    """줄바꿈된 한 제목 합치기: 같은 크기의 굵은 줄이 바로 아래(줄 간격 이내)에 이어지고, 글머리 기호(앞 공백)로 시작하지 않으며,
    같은 x(이때는 대문자/제목형도 같아야 함)이거나 걸이 들여쓰기(오른쪽 12pt 이내)이면 앞 줄의 연속으로 본다."""
    merged: list[dict] = []
    for line in lines:
        prev = merged[-1] if merged else None
        dx = line["x0"] - prev["x0"] if prev else 0.0
        if (
            prev
            and prev["size"] == line["size"]
            and 0 < line["y0"] - prev["y0"] <= prev["size"] * MERGE_GAP_RATIO
            and not line["text"][:1].isspace()
            and -2 <= dx <= 12
            and (dx > 2 or _is_caps(prev["text"]) == _is_caps(line["text"]))   # 걸이 들여쓰기 줄은 대소문자 무관
        ):
            prev["text"] = prev["text"].rstrip() + " " + line["text"].strip()
            prev["y0"] = line["y0"]
            prev["merged"] = prev.get("merged", 1) + 1
            continue
        merged.append(dict(line))
    return merged


def sections_from_fonts(doc, chapters: list[dict]) -> tuple[list[dict], dict]:
    pages = [p for c in chapters for p in range(c["start"], min(c["end"], doc.page_count) + 1)]
    step = max(1, len(pages) // 150)
    body = detect_body_size(doc, pages[::step])
    candidates: list[tuple[dict, dict]] = []   # (chapter, line)
    for chapter in chapters:
        for pno in range(chapter["start"], min(chapter["end"], doc.page_count) + 1):
            for line in merge_wrapped(heading_lines(doc, pno, body)):
                candidates.append((chapter, line))
    # 머리말·꼬리말: 여러 쪽에 되풀이되고 쪽 가장자리에 있는 줄
    pages_of = collections.defaultdict(set)
    for _c, line in candidates:
        pages_of[" ".join(line["text"].split()).lower()].add(line["page"])
    stats = collections.Counter()
    raw: list[dict] = []
    left_margin = min((line["x0"] for _c, line in candidates), default=0.0)
    for chapter, line in candidates:
        title = clean_title(line["text"])
        key = " ".join(line["text"].split()).lower()
        if _CAPTION_RE.match(title):
            stats["excluded_caption"] += 1
        elif _CHAPTER_LABEL_RE.match(title):
            stats["excluded_chapter_label"] += 1
        elif sum(ch.isalpha() for ch in title) < MIN_TITLE_ALPHA:
            stats["excluded_too_short"] += 1
        elif len(pages_of[key]) >= HEADER_REPEAT_PAGES and (line["y0"] < line["height"] * MARGIN_FRACTION or line["y1"] > line["height"] * (1 - MARGIN_FRACTION)):
            stats["excluded_running_header"] += 1
        else:
            raw.append({"chapter": chapter["chapter"], "level": _heading_level(line["text"], line["x0"], left_margin), "title": title, "start": line["page"]})
    info = {"body_font_size": body, "heading_candidates": len(candidates), "wrapped_headings_merged": sum(1 for _c, ln in candidates if ln.get("merged")), **{k: v for k, v in stats.items()}}
    return finalize(raw, chapters), info


# ── 공통: 순번·경로·끝 쪽 ─────────────────────────────────────────────────────────
def finalize(raw: list[dict], chapters: list[dict]) -> list[dict]:
    """문서 순서의 원시 항목(chapter, level, title, start) → section_id·path·pdf_page_end를 채운 항목."""
    by_no = {c["chapter"]: c for c in chapters}
    out: list[dict] = []
    per_chapter: dict[int, list[dict]] = collections.defaultdict(list)
    for entry in raw:
        per_chapter[entry["chapter"]].append(entry)
    for chapter_no in sorted(per_chapter):
        entries = sorted(enumerate(per_chapter[chapter_no]), key=lambda t: (t[1]["start"], t[0]))   # 쪽 순, 같은 쪽은 문서 순서 유지
        entries = [e for _i, e in entries]
        chapter = by_no[chapter_no]
        stack: list[dict] = []
        for seq, entry in enumerate(entries, start=1):
            while stack and stack[-1]["level"] >= entry["level"]:
                stack.pop()
            stack.append(entry)
            entry["path"] = [e["title"] for e in stack]
            entry["seq"] = seq
        for index, entry in enumerate(entries):
            end = chapter["end"]
            for later in entries[index + 1:]:
                if later["level"] <= entry["level"]:
                    end = later["start"] - 1
                    break
            out.append(
                {
                    "section_id": f"{chapter_no}.{entry['seq']}",
                    "chapter": chapter_no,
                    "level": entry["level"],
                    "title": entry["title"],
                    "path": entry["path"],
                    "pdf_page_start": entry["start"],
                    "pdf_page_end": max(entry["start"], min(end, chapter["end"])),
                    "citable": is_citable_title(entry["title"]),
                }
            )
    return out


def summarize(sections: list[dict], chapters: list[dict], page_chars: dict[int, tuple[int | None, int]]) -> dict:
    per_chapter = collections.Counter(s["chapter"] for s in sections)
    counts = [per_chapter.get(c["chapter"], 0) for c in chapters]
    titles = collections.Counter(s["title"].lower() for s in sections)
    lengths = sorted(len(s["title"]) for s in sections)
    # 쪽 → 절: 그 장 안에서 시작 쪽이 이 쪽 이하인 가장 마지막 절. 첫 절 이전 쪽(장 표지)은 절 없음.
    first_start = {}
    for s in sections:
        first_start[s["chapter"]] = min(first_start.get(s["chapter"], 10**9), s["pdf_page_start"])
    body_pages = [(p, ch) for p, (ch, chars) in page_chars.items() if ch is not None and chars > 0]
    in_section = sum(1 for p, ch in body_pages if ch in first_start and p >= first_start[ch])

    def pct(values: list[int], q: float) -> int:
        return values[min(len(values) - 1, int(q * (len(values) - 1)))] if values else 0

    return {
        "sections": len(sections),
        "chapters": len(chapters),
        "chapters_with_zero_sections": sum(1 for n in counts if n == 0),
        "sections_per_chapter": {"min": min(counts, default=0), "p25": pct(sorted(counts), 0.25), "median": statistics.median(counts) if counts else 0, "p75": pct(sorted(counts), 0.75), "max": max(counts, default=0)},
        "level_counts": dict(sorted(collections.Counter(s["level"] for s in sections).items())),
        "body_pages": len(body_pages),
        "body_pages_in_a_section": in_section,
        "body_pages_in_a_section_pct": round(100 * in_section / len(body_pages), 2) if body_pages else 0.0,
        "title_chars": {"min": lengths[0] if lengths else 0, "p50": pct(lengths, 0.5), "p95": pct(lengths, 0.95), "max": lengths[-1] if lengths else 0},
        "non_citable_sections": sum(1 for s in sections if s.get("citable") is False),
        "duplicate_titles": sum(1 for n in titles.values() if n > 1),
        "sections_with_duplicate_title": sum(n for n in titles.values() if n > 1),
    }


def main() -> int:
    import fitz   # 지연 import: 테스트가 함수만 가져다 쓸 때 PyMuPDF 없이도 import 가능

    ap = argparse.ArgumentParser()
    ap.add_argument("--book-id", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--source", choices=["auto", "toc", "font"], default="auto")
    ap.add_argument("--textbooks-dir", default=str(DEFAULT_TEXTBOOKS_DIR))
    args = ap.parse_args()

    book_dir = Path(args.textbooks_dir) / args.book_id
    chapters = load_chapters(book_dir)
    page_chars = load_page_chars(book_dir)
    doc = fitz.open(args.pdf)
    toc = doc.get_toc() or []
    chapter_level, matched = chapter_level_of(toc, chapters)
    deeper = deeper_toc_count(toc, chapter_level)
    source = args.source
    if source == "auto":
        source = "toc" if chapter_level is not None and matched >= 0.9 * len(chapters) and deeper >= len(chapters) else "font"
    if source == "toc":
        if chapter_level is None:
            raise SystemExit("목차에서 장 단계를 찾지 못했습니다(chapter_index와 겹치는 항목 없음).")
        sections, info = sections_from_toc(toc, chapters, chapter_level)
        info["toc_chapter_level"] = chapter_level
        info["toc_entries_total"] = len(toc)
    else:
        sections, info = sections_from_fonts(doc, chapters)
    summary = summarize(sections, chapters, page_chars)
    payload = {
        "schema": SCHEMA,
        "book_id": args.book_id,
        "source": source,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source_info": info,
        "summary": summary,
        "sections": sections,
        "policy": "local-only section titles and page numbers; no body text",
    }
    (book_dir / "section_index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{args.book_id}] source={source} sections={len(sections)} → {book_dir / 'section_index.json'}")
    print(json.dumps({"source_info": info, "summary": summary}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
