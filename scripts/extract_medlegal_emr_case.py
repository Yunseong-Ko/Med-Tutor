#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.services.medlegal_emr_importer import import_emr_text_to_case


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a raw EMR text sample into a deidentified med-legal education case draft."
    )
    parser.add_argument("source", type=Path, help="Raw EMR text file")
    parser.add_argument("--case-id", default="", help="Stable case id to save under data_private/medlegal")
    parser.add_argument(
        "--title",
        default="수술 전후 설명·협진·입퇴원 기록 연속성 케이스",
        help="Educational case title",
    )
    args = parser.parse_args()

    raw_text = args.source.read_text(encoding="utf-8", errors="ignore")
    result = import_emr_text_to_case(
        raw_text,
        source_name=args.source.name,
        case_id=args.case_id or None,
        title=args.title,
    )
    preview = {
        "case_id": result["case_id"],
        "record_count": result["record_count"],
        "note_types": result["note_types"],
        "paths": result["paths"],
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
