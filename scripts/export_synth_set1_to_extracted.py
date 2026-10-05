#!/usr/bin/env python3
"""합성 세트1을 course-exam extracted 레코드 스키마로 내보내 연습 리더에 노출.

주의: AI 생성 초안(needs_review=True). 실제 학생 배포 전 의학검토 필요.
"""

import json
from pathlib import Path

SRC = Path("data_private/exam_sets/SYNTH_2026_SET1.json")
OUT = Path("data_private/course_exams/extracted/SYNTH_2026_MOCK_SET1.json")


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    src_qs = data["questions"]

    questions = []
    for q in src_qs:
        labels = {
            "concept_tags": q.get("concept_tags") or [],
            "labeling_status": "labeled",
            "labeling_source": "synthetic_gen_v1",
            "system": q.get("system"),
            "question_type": q.get("question_type"),
            "difficulty": q.get("difficulty"),
        }
        questions.append({
            "question_id": q["question_id"],
            "question_number": q["question_number"],
            "stem": q["stem"],
            "stimulus": None,
            "choices": q["choices"],
            "answer": q["answer"],
            "explanation": q.get("explanation"),
            "answer_rationale": q.get("answer_rationale"),
            "choice_explanations": q.get("choice_explanations"),
            "key_learning_points": q.get("key_learning_points") or [],
            "lab_values": q.get("lab_values") or [],
            "labels": labels,
            "media": {"media_refs": []},
            "needs_review": True,
            "review_status": "generated_draft",
            "generation": q.get("generation") or {},
        })

    record = {
        "exam": {
            "source_exam": "SYNTH_2026_MOCK_SET1",
            "source_file": "synthetic_generated",
            "course_id": "COURSE_SYNTH",
            "course_name": "합성 임상종합 모의고사",
            "grade": "4",
            "exam_date": "2026",
            "round_label": "세트1(AI생성 초안)",
            "period_label": "세트1",
            "parser_version": "synthetic_gen_v1",
        },
        "questions": questions,
        "question_index": [],
        "subjective_questions": [],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    ready = sum(1 for q in questions
                if q["stem"] and q["answer"] and len([v for v in q["choices"].values() if v]) >= 2)
    print(f"[done] 내보내기 완료 → {OUT.name} · 문항 {len(questions)} · practice_ready {ready}")


if __name__ == "__main__":
    raise SystemExit(main())
