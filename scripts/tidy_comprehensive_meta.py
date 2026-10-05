#!/usr/bin/env python3
"""임상의학종합평가 4개 신규 추출본의 표시용 메타데이터 정리.

파일명/source_exam/question_id는 건드리지 않는다(참조 깨짐 방지). 표시는 exam의
course_name·exam_date·round_label·period_label에서 나오므로 그 필드만 정리한다.
결과 표기 예: '임상의학종합평가 · 2026 · 4학년 · 1교시 · 40문항'
"""

import json
from pathlib import Path

DIR = Path("data_private/course_exams/extracted")
FILES = {
    "COURSE_4_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_1교시": "1교시",
    "COURSE_X_DATE_UNKNOWN_EXAM_2교시": "2교시",
    "COURSE_X_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_3교시": "3교시",
    "COURSE_X_DATE_UNKNOWN_EXAM_4교시": "4교시",
}


def main():
    for stem, period in FILES.items():
        path = DIR / f"{stem}.json"
        if not path.exists():
            print(f"[skip] 없음 {stem}")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        e = d["exam"]
        e["course_name"] = "임상의학종합평가"
        e["exam_date"] = "2026"
        e["grade"] = "4"
        e["round_label"] = "4학년"
        e["period_label"] = period
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        n = len(d.get("questions", []))
        print(f"[ok] {period}: 임상의학종합평가 · 2026 · 4학년 · {period} · {n}문항")


if __name__ == "__main__":
    raise SystemExit(main())
