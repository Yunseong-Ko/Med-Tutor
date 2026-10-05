#!/usr/bin/env python3
"""과별 교과서 쪽 라벨 감사 — data_private/textbooks/<book_id>/pages.jsonl 의 쪽 수·printed_label·chapter 보유율(T-TBX-01).

리포트(`data_private/textbooks/_audit/page_label_report.json`)에는 개수·비율만 쓴다. 본문 텍스트·라벨 문자열은 넣지 않는다.

라벨 단조성: pdf_page 순서에서 숫자 라벨만 이어 보며,
- label_monotonic_violations = 직전 숫자 라벨보다 작아진 횟수(감소)
- label_repeat_count        = 직전 숫자 라벨과 같은 횟수(반복)

본문 추출 품질(근거 대조 가능 여부) — 책마다 `quality.json`(추가 파일, 본문 없음)을 쓴다:
- garbled 문자 = 글자(str.isalpha)·숫자(str.isdigit)·공백(str.isspace)·COMMON_PUNCT 어느 것도 아닌 문자.
  쪽 비율 = garbled 문자 수 / 그 쪽 전체 문자 수. 문자 수가 MIN_PAGE_CHARS 미만인 쪽(표지·빈 쪽·그림 쪽)은 측정에서 뺀다.
- 책 지표 = 측정 쪽 비율의 중앙값(garbled_ratio_median)과 90백분위(garbled_ratio_p90).
- usable_for_evidence = False 조건(하나라도): 중앙값 >= GARBLED_MEDIAN_MAX(0.02), 또는 장 보유율 0(장 단위 근거 선택 불가), 또는 측정 쪽이 없음.
  임계값 0.02는 정상 의학서(숫자·단위·그리스 문자·기호 포함)가 1% 안팎이라는 가정에서 잡은 것이며, 실측 분포를 보고 맞춘 값이 아니다 — 결과는 그대로 보고한다.

사용: python scripts/audit_textbook_page_labels.py [--textbooks-dir DIR] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data_private" / "textbooks"


MIN_PAGE_CHARS = 200
GARBLED_MEDIAN_MAX = 0.02
COMMON_PUNCT = frozenset(".,;:!?()[]{}'\"‘’“”‚„-‐‑–—/\\%&+=<>*#@°±×÷≥≤≈→←↑↓µμ·•…§†‡™®©$€£_~^|")
QUALITY_FILENAME = "quality.json"


def garbled_ratio(text: str) -> float:
    """글자·숫자·공백·COMMON_PUNCT 밖 문자의 비율(전체 문자 대비)."""
    if not text:
        return 0.0
    bad = sum(1 for ch in text if not (ch.isalpha() or ch.isdigit() or ch.isspace() or ch in COMMON_PUNCT))
    return bad / len(text)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]


def quality_verdict(row: dict) -> dict:
    """audit_book 결과 → quality.json 내용(지표 + 판정). 본문·라벨 문자열 없음."""
    reasons = []
    if not row.get("pages_measured"):
        reasons.append("no_measurable_pages")
    elif row["garbled_ratio_median"] >= GARBLED_MEDIAN_MAX:
        reasons.append(f"garbled_ratio_median>={GARBLED_MEDIAN_MAX}")
    if not row.get("pages_with_chapter"):
        reasons.append("no_chapter_assignment")
    return {
        "schema": "paccine.textbook_quality.v1",
        "usable_for_evidence": not reasons,
        "reasons": reasons,
        "garbled_ratio_median": row.get("garbled_ratio_median", 0.0),
        "garbled_ratio_p90": row.get("garbled_ratio_p90", 0.0),
        "pages_measured": row.get("pages_measured", 0),
        "pages_with_chapter": row.get("pages_with_chapter", 0),
        "thresholds": {"garbled_median_max": GARBLED_MEDIAN_MAX, "min_page_chars": MIN_PAGE_CHARS},
        "note": "metrics only; no textbook text",
    }


def _ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def audit_book(pages_path: Path) -> dict:
    pages = labeled = numeric = chaptered = decreases = repeats = 0
    prev: int | None = None
    ratios: list[float] = []
    rows = []
    with pages_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append((row.get("pdf_page") if isinstance(row.get("pdf_page"), int) else len(rows) + 1, row))
    rows.sort(key=lambda t: t[0])
    for _, row in rows:
        pages += 1
        text = row.get("text") if isinstance(row.get("text"), str) else ""
        if len(text) >= MIN_PAGE_CHARS:
            ratios.append(garbled_ratio(text))
        label = row.get("printed_label")
        label = str(label).strip() if label is not None else ""
        if label:
            labeled += 1
            if label.isdigit():
                numeric += 1
                value = int(label)
                if prev is not None:
                    if value < prev:
                        decreases += 1
                    elif value == prev:
                        repeats += 1
                prev = value
        if row.get("chapter") not in (None, ""):
            chaptered += 1
    return {
        "pages": pages,
        "pages_with_printed_label": labeled,
        "printed_label_rate": _ratio(labeled, pages),
        "pages_with_numeric_label": numeric,
        "numeric_label_ratio_of_labeled": _ratio(numeric, labeled),
        "pages_with_chapter": chaptered,
        "chapter_rate": _ratio(chaptered, pages),
        "label_monotonic_violations": decreases,
        "label_repeat_count": repeats,
        "pages_measured": len(ratios),
        "garbled_ratio_median": round(_percentile(ratios, 0.5), 4),
        "garbled_ratio_p90": round(_percentile(ratios, 0.9), 4),
    }


def build_report(textbooks_dir: Path) -> dict:
    books = {}
    for pages_path in sorted(textbooks_dir.glob("*/pages.jsonl")):
        if pages_path.parent.name.startswith("_"):
            continue
        books[pages_path.parent.name] = audit_book(pages_path)
        books[pages_path.parent.name]["usable_for_evidence"] = quality_verdict(books[pages_path.parent.name])["usable_for_evidence"]
    return {
        "schema": "paccine.textbook_page_label_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "counts and ratios only; no textbook text",
        "books": books,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--textbooks-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.textbooks_dir.is_dir():
        print(f"textbooks dir not found: {args.textbooks_dir}", file=sys.stderr)
        return 2
    report = build_report(args.textbooks_dir)
    out = args.out or args.textbooks_dir / "_audit" / "page_label_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for book_id, row in report["books"].items():
        verdict = quality_verdict(row)
        (args.textbooks_dir / book_id / QUALITY_FILENAME).write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for book_id, row in report["books"].items():
        print(f"{book_id}: pages={row['pages']} labeled={row['pages_with_printed_label']} numeric={row['pages_with_numeric_label']} "
              f"chapter={row['pages_with_chapter']} decreases={row['label_monotonic_violations']} repeats={row['label_repeat_count']} "
              f"garbled_median={row['garbled_ratio_median']} p90={row['garbled_ratio_p90']} measured={row['pages_measured']} usable={row['usable_for_evidence']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
