"""Ingest 한국의료분쟁조정중재원 조정분석 현황 (data.go.kr id 3049716) into a
normalized JSONL schema, emit orthopedics / plastic-surgery subsets, and print
aggregate pattern stats for the 1-page analysis.

License of source data: KOGL/공공누리 (public, commercial use allowed with attribution).
Raw input + outputs stay under data_private/medlegal/ (gitignored).

Encoding note: this particular file is UTF-8 with BOM (utf-8-sig). Other Korean
government CSVs are often CP949 — _read_rows() falls back to cp949 if needed.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_private/medlegal/imports/kmedi_dispute_analysis_3049716.csv"
OUT_DIR = ROOT / "data_private/medlegal/processed"

# Korean source column -> clean snake_case key (order matches the CSV header)
COLUMNS = [
    ("연번", "serial_no"),
    ("진료과목", "clinical_dept"),
    ("제목", "title"),
    ("키워드", "keywords"),
    ("처리결과", "processing_result"),
    ("사고발생경위", "accident_circumstance"),
    ("분쟁내용", "dispute_content"),
    ("사안쟁점내용", "key_issues"),
    ("감정결과내용", "expert_opinion"),
    ("손해배상책임내용", "liability_content"),
    ("손해배상책임범위", "liability_scope"),
    ("처리결과내용", "resolution_details"),
]
KEYS = [k for _, k in COLUMNS]


def _read_rows(path: Path):
    for enc in ("utf-8-sig", "cp949"):
        try:
            with open(path, encoding=enc, newline="") as f:
                rows = list(csv.reader(f))
            return rows, enc
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"Could not decode {path} as utf-8-sig or cp949")


def _split_keywords(raw: str) -> list[str]:
    parts = re.split(r"[,/、·]", raw or "")
    return [p.strip() for p in parts if p.strip()]


def to_record(row: list[str]) -> dict:
    rec = {key: (row[i].strip() if i < len(row) else "") for i, (_, key) in enumerate(COLUMNS)}
    dept = rec["clinical_dept"]
    rec["dept_normalized"] = dept
    rec["is_ortho"] = "정형" in dept
    rec["is_plastic"] = "성형" in dept
    rec["keyword_list"] = _split_keywords(rec["keywords"])
    rec["needs_review"] = not rec["title"] or not dept  # flag malformed rows
    return rec


def write_jsonl(records: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    if not RAW.exists():
        raise SystemExit(
            f"Raw CSV not found at {RAW}.\n"
            "Download it from https://www.data.go.kr/data/3049716/fileData.do "
            "(다운로드 button) and place it there."
        )
    rows, enc = _read_rows(RAW)
    header, data = rows[0], rows[1:]
    records = [to_record(r) for r in data if any(c.strip() for c in r)]

    write_jsonl(records, OUT_DIR / "kmedi_disputes.jsonl")
    ortho = [r for r in records if r["is_ortho"]]
    plastic = [r for r in records if r["is_plastic"]]
    write_jsonl(ortho, OUT_DIR / "kmedi_disputes_ortho.jsonl")
    write_jsonl(plastic, OUT_DIR / "kmedi_disputes_plastic.jsonl")

    print(f"encoding={enc}  total={len(records)}  ortho={len(ortho)}  plastic={len(plastic)}")
    print(f"wrote -> {OUT_DIR}/kmedi_disputes.jsonl (+ _ortho / _plastic)")

    # ---- aggregate stats for the analysis doc ----
    def dist(recs, key):
        return collections.Counter(r[key] for r in recs).most_common()

    print("\n[처리결과 분포 / 전체]")
    for k, v in dist(records, "processing_result"):
        print(f"  {v:4d}  {k}")

    for label, recs in (("정형외과", ortho), ("성형외과", plastic)):
        print(f"\n[{label}] n={len(recs)}")
        print("  처리결과:", dict(dist(recs, "processing_result")))
        kw = collections.Counter(k for r in recs for k in r["keyword_list"])
        print("  top keywords:", ", ".join(f"{k}({v})" for k, v in kw.most_common(12)))


if __name__ == "__main__":
    sys.exit(main())
