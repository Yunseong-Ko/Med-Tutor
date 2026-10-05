#!/usr/bin/env python3
"""Step 2 준비 — 혈액종양 246문항을 해설 재작성용 컴팩트 청크로 분할.

각 문항의 재작성에 필요한 최소 컨텍스트(지문·선지·정답·라벨·ontology_grounding·
기존해설 요약)만 뽑아 청크 파일로 저장한다. 병렬 서브에이전트가 청크를 읽어
해설을 생성하고, 이후 writeback 스크립트가 원본에 병합한다(원본 보존).
"""

import json
from pathlib import Path

OUT = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad/hemeonc_chunks")
FILES = [
    "data_private/course_exams/extracted/COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험.json",
    "data_private/course_exams/extracted/COURSE_2_20260306_HEMATOLOGY_ONCOLOGY_1차.json",
    "data_private/course_exams/extracted/COURSE_2_20260317_HEMATOLOGY_ONCOLOGY_2차.json",
]
CHUNK = 13


def compact(q, fp, idx):
    g = q.get("ontology_grounding")
    grounding = None
    if g:
        h = g.get("harrison") or {}
        grounding = {
            "disease_concept_id": g.get("disease_concept_id"),
            "label": g.get("label"),
            "harrison": {"chapter": h.get("chapter"), "title": h.get("title"), "page": h.get("page"),
                         "accessmedicine": h.get("accessmedicine")} if h else None,
            "differentials": (g.get("differentials") or [])[:6],
            "treated_with": (g.get("treated_with") or [])[:5],
            "diagnosed_by": (g.get("diagnosed_by") or [])[:5],
        }
    lab = q.get("labels") or {}
    return {
        "file": fp, "idx": idx,
        "qid": q.get("question_id") or f"{Path(fp).stem}#{q.get('question_number')}",
        "question_number": q.get("question_number"),
        "stem": q.get("stem"),
        "stimulus": q.get("stimulus") or "",
        "choices": q.get("choices"),
        "answer": q.get("answer"),
        "topic": lab.get("topic"), "subtopic": lab.get("subtopic"),
        "assessment_domain": lab.get("assessment_domain"),
        "grounding": grounding,
        "prior_explanation": str(q.get("explanation") or "")[:400],
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = []
    for fp in FILES:
        d = json.loads(Path(fp).read_text(encoding="utf-8"))
        for i, q in enumerate(d.get("questions", [])):
            items.append(compact(q, fp, i))
    chunks = [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)]
    for n, ch in enumerate(chunks):
        (OUT / f"chunk_{n:02d}.json").write_text(json.dumps(ch, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"총 {len(items)}문항 → {len(chunks)}청크 (청크당 {CHUNK}), 저장: {OUT}")
    print("청크 파일:", ", ".join(f"chunk_{n:02d}.json" for n in range(len(chunks))))


if __name__ == "__main__":
    main()
