#!/usr/bin/env python3
"""concept_tags 기반 근거(citation) 부착 — 큐레이션 데모.

원칙(프라이버시 경계):
- 외부(PubMed)로 나가는 것은 concept_tags·과목명뿐. 문항 지문 원문은 절대 외부로 보내지 않는다.
- 근거는 draft로 저장하고, 사람(의학 검토) 확인 전에는 status="draft"로만 표시한다.
- 자동 top-hit는 관련성이 낮을 수 있으므로, 확신 매칭이 없으면 evidence를 비우고
  evidence_status="needs_review"로 플래그한다(이번 데모의 Q1 사례).

이 스크립트는 데모 목적상 세션에서 PubMed MCP로 검증한 인용을 하드코딩해 부착한다.
실제 자동화는 동일 스키마로 NCBI E-utilities를 호출하는 배치 스크립트로 확장한다.
"""

import json
import sys
from pathlib import Path

TARGET = Path(
    "data_private/course_exams/extracted/"
    "COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험.json"
)


def cite(pmid, doi, title, journal, year, pub_type, matched_concept):
    return {
        "source": "PubMed",
        "pmid": pmid,
        "doi": doi,
        "title": title,
        "journal": journal,
        "year": year,
        "type": pub_type,  # guideline | review
        "url": f"https://doi.org/{doi}",
        "matched_concept": matched_concept,
        "retrieved_via": "concept_tags",  # 지문 원문 미사용
        "status": "draft",  # 사람 검토 전
    }


# 세션에서 PubMed MCP로 조회·검증한 인용 (question_id -> evidence[])
EVIDENCE = {
    "COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험_Q003": [
        cite(
            "33818884", "10.1002/pbc.28473", "Neuroblastoma.",
            "Pediatr Blood Cancer", "2021", "review", "neuroblastoma",
        )
    ],
    "COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험_Q004": [
        cite(
            "37583880", "10.15586/jkcvhl.v10i3.281",
            "Recent Improvements in Adult Wilms Tumor Diagnosis and Management: Review of Literature.",
            "J Kidney Cancer VHL", "2023", "review", "Wilms_tumor",
        )
    ],
    "COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험_Q005": [
        cite(
            "33570647", "10.1182/bloodadvances.2020003264",
            "ASH ISTH NHF WFH 2021 guidelines on the management of von Willebrand disease.",
            "Blood Adv", "2021", "guideline", "von_Willebrand_disease",
        )
    ],
    "COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험_Q006": [
        cite(
            "39043543", "10.1016/j.jtha.2024.05.026",
            "ISTH clinical practice guideline for treatment of congenital hemophilia A and B (GRADE).",
            "J Thromb Haemost", "2024", "guideline", "hemophilia",
        )
    ],
}

# 확신 매칭이 없어 사람 검토로 넘기는 사례 (자동 결과가 POEMS 증례·무관 논문만 반환)
NEEDS_REVIEW = {
    "COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험_Q001": (
        "concept_tags 자동검색이 관련성 낮은 결과(POEMS 증례 등)만 반환 — "
        "사람이 림프절병증 평가 리뷰를 직접 지정 필요"
    ),
}


def main():
    if not TARGET.exists():
        print(f"[error] not found: {TARGET}", file=sys.stderr)
        return 1
    data = json.loads(TARGET.read_text(encoding="utf-8"))
    questions = data.get("questions", [])
    touched = 0
    for q in questions:
        qid = q.get("question_id")
        if qid in EVIDENCE:
            q["evidence"] = EVIDENCE[qid]
            q["evidence_status"] = "draft"
            touched += 1
        elif qid in NEEDS_REVIEW:
            q["evidence"] = []
            q["evidence_status"] = "needs_review"
            q["evidence_note"] = NEEDS_REVIEW[qid]
            touched += 1
    TARGET.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[done] evidence attached to {touched} questions in {TARGET.name}")
    for qid in list(EVIDENCE) + list(NEEDS_REVIEW):
        q = next((x for x in questions if x.get("question_id") == qid), None)
        if q:
            ev = q.get("evidence", [])
            print(f"  {qid.split('_')[-1]}: {q.get('evidence_status')} · {len(ev)} cite"
                  + (f" · {ev[0]['journal']} {ev[0]['year']}" if ev else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
