#!/usr/bin/env python3
"""세트2 마무리: 난이도 재보정 + 무결성 검증 + extracted 레코드 내보내기."""

import json
import collections
from pathlib import Path

SRC = Path("data_private/exam_sets/SYNTH_2026_SET2.json")
OUT = Path("data_private/course_exams/extracted/SYNTH_2026_MOCK_SET2.json")

DIFF_HA = {5, 9, 10, 12, 13, 28, 31, 39, 40, 42, 48, 52, 56, 57, 61, 63, 65, 67, 71, 73, 74, 76, 78, 80}
DIFF_SANG = {1, 17, 19, 21, 23, 24, 26, 30, 33, 37, 44, 45, 59, 70, 77, 79}


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    for q in data["questions"]:
        n = q["question_number"]
        q["difficulty"] = "하" if n in DIFF_HA else "상" if n in DIFF_SANG else "중"
    SRC.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 무결성 검증
    qs = data["questions"]
    errs = []
    if [q["question_number"] for q in qs] != list(range(1, 81)):
        errs.append("번호 불연속")
    for q in qs:
        n = q["question_number"]
        if set((q.get("choices") or {}).keys()) != {"1", "2", "3", "4", "5"}:
            errs.append(f"Q{n} 선지키")
        cx = q.get("choice_explanations") or {}
        if set(cx.keys()) != {"1", "2", "3", "4", "5"}:
            errs.append(f"Q{n} 선지해설키")
        corr = [k for k, v in cx.items() if v.get("is_correct")]
        if corr != [q.get("answer")]:
            errs.append(f"Q{n} 정답불일치")
        if len(q.get("key_learning_points") or []) < 3:
            errs.append(f"Q{n} klp<3")

    # extracted 레코드 내보내기
    questions = []
    for q in qs:
        questions.append({
            "question_id": q["question_id"], "question_number": q["question_number"],
            "stem": q["stem"], "stimulus": None, "choices": q["choices"], "answer": q["answer"],
            "explanation": q.get("explanation"), "answer_rationale": q.get("answer_rationale"),
            "choice_explanations": q.get("choice_explanations"),
            "key_learning_points": q.get("key_learning_points") or [],
            "lab_values": q.get("lab_values") or [],
            "labels": {"concept_tags": q.get("concept_tags") or [], "labeling_status": "labeled",
                       "labeling_source": "synthetic_gen_v1", "system": q.get("system"),
                       "question_type": q.get("question_type"), "difficulty": q.get("difficulty")},
            "media": {"media_refs": []}, "needs_review": True,
            "review_status": "generated_draft", "generation": q.get("generation") or {},
        })
    record = {
        "exam": {"source_exam": "SYNTH_2026_MOCK_SET2", "source_file": "synthetic_generated",
                 "course_id": "COURSE_SYNTH", "course_name": "합성 임상종합 모의고사",
                 "grade": "4", "exam_date": "2026", "round_label": "세트2(AI생성 초안)",
                 "period_label": "세트2", "parser_version": "synthetic_gen_v1"},
        "questions": questions, "question_index": [], "subjective_questions": [],
    }
    OUT.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    dif = collections.Counter(q["difficulty"] for q in qs)
    print("무결성:", "OK 오류 없음" if not errs else f"오류 {errs}")
    print("난이도(재보정):", dict(dif.most_common()))
    print(f"내보내기 → {OUT.name} · 문항 {len(questions)}")


if __name__ == "__main__":
    raise SystemExit(main())
