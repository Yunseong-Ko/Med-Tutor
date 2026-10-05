"""소명 훈련 케이스 생성기 — 감정분석 사례 → EMR 기록 훈련 케이스 객체.

학습 루프(설계):
  케이스 제시(결과 숨김) → 학생이 기록 작성 → 실제 감정결과 기준 채점 → 예방팁·판례 근거 → 재작성.

입력: data_private/medlegal/processed/kmedi_gamjeong.jsonl (109; 정형 38)
출력: data_private/medlegal/processed/training_cases_ortho.json

각 케이스는 visible_chart(학생이 봄) / answer_key(채점용, 숨김) / rubric / 생성 TODO 로 구성.
answer_key.expert_opinion(감정결과)에서 '실제로 책임이 인정된 지점'을 역산해 채점 기준으로 씀 → 정답이 임의적이지 않음.
hidden_risk_points 추출·모범기록·판례 토픽매칭은 LLM+교수 검토 단계(플래그).
"""
from __future__ import annotations

import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data_private/medlegal/processed"

# 7축 기본 루브릭 (MedLegal 설계)
BASE_RUBRIC = [
    "기록 완성도(주호소·경과·평가·계획)",
    "임상 판단 근거(감별·배제·불확실성)",
    "환자 안전(red flag·악화대응·재내원기준)",
    "설명의무·동의·거부 기록",
    "추적·전원·협진 연속성",
    "기록 무결성(일시·작성자·수정)",
    "의료분쟁 예방 관점(위험 문구)",
]

# 키워드 → 요구 기록 유형(휴리스틱; 교수 검토로 확정)
def required_notes(keywords: str, summary: str) -> list[str]:
    blob = (keywords or "") + " " + (summary or "")
    notes = ["경과기록(SOAP)"]
    if re.search(r"수술|시술|마취|삽입|고정|이식", blob):
        notes.append("수술/시술 설명·동의 기록")
    if re.search(r"퇴원|귀가", blob):
        notes.append("퇴원기록·재내원 기준")
    if re.search(r"거부|자의|전원|의뢰", blob):
        notes.append("검사·치료 거부/전원 기록")
    if len(notes) == 1:
        notes.append("설명·동의 기록")
    return notes


def to_training_case(r: dict, idx: int) -> dict:
    tip = r.get("prevention_tip", "")
    tip = "" if "해당사항없음" in tip else tip
    return {
        "case_id": f"gamjeong-ortho-{idx:03d}",
        "specialty": r.get("clinical_dept", ""),
        "title": r.get("title", ""),
        "learner_level": "clerkship/전공의",
        # 학생이 보는 부분 (결과·판단 숨김)
        "visible_chart": {
            "사건개요": r.get("case_summary", ""),
            "치료과정": r.get("treatment_course", ""),
        },
        "task": {
            "required_notes": required_notes(r.get("keywords", ""), r.get("case_summary", "")),
            "instruction": "위 상황에서 필요한 진료기록과 설명/동의 기록을 작성하시오.",
        },
        # 채점용(숨김) — 실제 분쟁에서 문제된 지점
        "answer_key": {
            "expert_opinion(감정결과)": r.get("expert_opinion", ""),
            "issue_patient(환자측 쟁점)": r.get("issue_patient", ""),
            "issue_hospital(병원측 쟁점)": r.get("issue_hospital", ""),
            "mediation_result(조정결과)": r.get("mediation_result", ""),
            "prevention_tip(예방팁)": tip,
        },
        "rubric": BASE_RUBRIC,
        "linked_precedents": [],  # TODO: 판례 인덱스와 토픽 매칭
        "needs_faculty_review": True,
        "generation_todo": [
            "hidden_risk_points 추출(LLM: 감정결과→'없어서 책임된 기록 항목' N개)",
            "모범 기록 예시 생성(LLM)",
            "판례 토픽 매칭(precedent_index.json)",
            "교수 검토·승인",
        ],
    }


def main():
    src = PROC / "kmedi_gamjeong.jsonl"
    rows = [json.loads(l) for l in src.open(encoding="utf-8") if l.strip()]
    ortho = [r for r in rows if r.get("is_ortho")]
    cases = [to_training_case(r, i + 1) for i, r in enumerate(ortho)]
    out = PROC / "training_cases_ortho.json"
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")

    with_tip = sum(1 for c in cases if c["answer_key"]["prevention_tip(예방팁)"])
    import collections
    note_dist = collections.Counter(n for c in cases for n in c["task"]["required_notes"])
    print(f"훈련 케이스(정형): {len(cases)}건  예방팁 보유 {with_tip}")
    print("  요구 기록 유형 분포:", dict(note_dist))
    print(f"wrote -> {out}")
    print("\n[샘플 1건]")
    s = cases[0]
    print(" case_id:", s["case_id"], "|", s["title"])
    print(" required_notes:", s["task"]["required_notes"])
    print(" 사건개요:", s["visible_chart"]["사건개요"][:90], "...")
    print(" 예방팁:", (s["answer_key"]["prevention_tip(예방팁)"][:90] or "(없음)"), "...")


if __name__ == "__main__":
    main()
