#!/usr/bin/env python3
"""
One-shot driver: enrich heme-onc 2차 exam and print structural validation only.
Does NOT print raw question text, stems, choices, or explanations.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.enrich_course_exam_choice_explanations import (  # noqa: E402
    enrich_record,
    write_json_atomic,
)

TARGET = (
    _ROOT
    / "data_private"
    / "course_exams"
    / "extracted"
    / "COURSE_2_20260317_HEMATOLOGY_ONCOLOGY_2\uc790.json"
)

COURSE_ID = "hematology_oncology"

BANNED_PHRASES = [
    "\uc815\ub2f5 \uc120\uc9c0\uc640 \ub354 \uc9c1\uc811\uc801\uc73c\ub85c \uc5f0\uacb0\ub429\ub2c8\ub2e4",
    "\uc815\ub2f5 \uc120\uc9c0\uc640 \ub354 \uc9c1\uc811\uc801\uc73c\ub85c \uc5f0\uacb0",
    "\uc6d0\ubb38 \ud574\uc124\uc774 \uc9e7\uc544 \uac80\ud1a0\uac00 \ud544\uc694\ud569\ub2c8\ub2e4",
    "\uc800\uc7a5\ub41c \ud574\uc124\ub9cc\uc73c\ub85c\ub294 \ubc30\uc81c\ud558\uae30 \uc5b4\ub835\uc2b5\ub2c8\ub2e4",
    "\uc774 \uc120\uc9c0\ub294 \uc815\ub2f5\uc774 \uc544\ub2d9\ub2c8\ub2e4",
    "is not the answer",
    "\ub354 \uc9c1\uc811\uc801\uc73c\ub85c \uc5f0\uacb0\ub429\ub2c8\ub2e4",
    "\ud95c\ub358 \uac83\uc740",
]


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: target JSON not found at {TARGET}", file=sys.stderr)
        return 1

    record = json.loads(TARGET.read_text(encoding="utf-8"))

    enriched = enrich_record(
        record,
        course_id=COURSE_ID,
        use_rag=True,
        only_missing=False,
        include_anki=True,
    )

    write_json_atomic(TARGET, enriched)

    # --- Structural validation (counts only, no raw text) ---
    questions = enriched.get("questions") or []
    total = len(questions)
    has_qu = sum(1 for q in questions if q.get("question_understanding"))
    has_ce = sum(1 for q in questions if q.get("choice_explanations"))
    total_ce_rows = sum(
        len(q["choice_explanations"])
        for q in questions
        if isinstance(q.get("choice_explanations"), dict)
    )
    banned_hits = 0
    for q in questions:
        ce = q.get("choice_explanations") or {}
        for row in (ce.values() if isinstance(ce, dict) else []):
            if isinstance(row, dict):
                text = str(row.get("rationale") or "")
                if any(phrase in text for phrase in BANNED_PHRASES):
                    banned_hits += 1

    anki_count = sum(
        len(q.get("anki_cards") or []) for q in questions
    )
    needs_review_count = sum(
        1
        for q in questions
        for row in (
            (q.get("choice_explanations") or {}).values()
            if isinstance(q.get("choice_explanations"), dict)
            else []
        )
        if isinstance(row, dict) and row.get("needs_review")
    )

    result = {
        "status": "ok",
        "output": str(TARGET),
        "total_questions": total,
        "questions_with_question_understanding": has_qu,
        "questions_with_choice_explanations": has_ce,
        "total_choice_explanation_rows": total_ce_rows,
        "banned_phrase_hits": banned_hits,
        "anki_card_count": anki_count,
        "needs_review_choice_rows": needs_review_count,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
