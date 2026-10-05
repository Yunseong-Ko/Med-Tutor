"""소명 채점 하네스 PoC — 학생 기록을 gold case의 hidden_risk_points 기준으로 채점.

프로덕션: score_submission() 내부의 [LLM SEAM]에서 Claude API로 LLM-as-judge 호출
  (프롬프트: "학생 기록을 각 risk_point에 대해 covered(t/f)+근거문장으로 판정, 7축 0~4, 위험문구, 수정안").
이 PoC는 gold_case_gamjeong-ortho-001.json에 대해 '약한 답안'을 넣고, LLM 판정 결과를 시연 출력한다.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data_private/medlegal/processed"
GOLD = PROC / "gold_case_gamjeong-ortho-001.json"

# 학생 제출(약한 답안 — 흔한 미흡 패턴)
SAMPLE_SUBMISSION = {
    "submission_id": "demo-001", "case_id": "gamjeong-ortho-001",
    "learner_id": "anon", "note_type": "수술 설명·동의 기록", "attempt": 1,
    "note_text": "우측 5수지 골절로 도수정복 및 K강선 내고정술 시행함. "
                 "환자에게 수술에 대해 설명하고 동의서 받음. 수술 잘 됨.",
}


def score_submission(submission: dict, gold: dict) -> dict:
    """[LLM SEAM] 프로덕션에서는 여기서 Claude에 (note_text, hidden_risk_points, rubric)을 주고
    구조화 판정을 받는다. 아래는 그 판정의 PoC 출력(LLM이 생성했을 결과)."""
    return {
        "submission_id": submission["submission_id"], "case_id": submission["case_id"], "attempt": 1,
        "per_risk": [
            {"risk_id": "rp1", "covered": False, "evidence": None,
             "note": "회복 한계(수상 전 상태로 회복 어려움) 설명 없음"},
            {"risk_id": "rp2", "covered": False, "evidence": None,
             "note": "합병증(강직·변형·신전지연·재수술) 고지 없음"},
            {"risk_id": "rp3", "covered": True, "evidence": "'골절로 도수정복 및 K강선 내고정술'",
             "note": "골절 언급은 있으나 CT/적응증 근거 미약(부분)"},
            {"risk_id": "rp4", "covered": False, "evidence": None, "note": "보존적 치료 대안 설명 없음"},
            {"risk_id": "rp5", "covered": False, "evidence": None, "note": "경과관찰·재내원 기준 없음"},
            {"risk_id": "rp6", "covered": False, "evidence": "'동의서 받음'",
             "note": "동의서 언급뿐, 이해확인·일시·집도의 서명 불명"},
        ],
        "rubric_scores": {
            "기록 완성도": 2, "임상 판단 근거": 2, "환자 안전": 1,
            "설명의무·동의": 1, "추적·전원 연속성": 1, "기록 무결성": 2, "의료분쟁 예방 관점": 1,
        },
        "risky_phrases": [
            {"text": "수술 잘 됨", "reason": "합병증·예후 한계 미고지 상태의 낙관적 단정 — 기대격차·분쟁 위험"},
        ],
        "missing": [
            "수술 후 회복 한계 설명(rp1, 핵심)", "예상 합병증 고지(rp2)",
            "치료 대안 설명(rp4)", "경과관찰·재내원 기준(rp5)", "환자 이해확인·서명(rp6)",
        ],
        "score_total": 40,
        "recommended_revision": "설명·동의 기록에 ①회복 한계 ②합병증(강직·변형·신전지연·재수술) "
                                "③보존적 대안 ④경과관찰·재내원 기준 ⑤이해확인·서명을 추가하시오. "
                                "특히 술기가 적절해도 '회복 한계·합병증' 설명이 없으면 분쟁에 취약함.",
        "linked_precedents": gold.get("linked_precedents", []),
        "disclaimer": "교육용 피드백입니다. 법률 자문이 아닙니다.",
    }


def main():
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    result = score_submission(SAMPLE_SUBMISSION, gold)
    covered = sum(1 for r in result["per_risk"] if r["covered"])
    total_rp = len(result["per_risk"])
    print("=== 학생 제출 ===")
    print(" ", SAMPLE_SUBMISSION["note_text"])
    print(f"\n=== 채점 결과 (LLM-as-judge PoC) ===")
    print(f" 리스크포인트 충족: {covered}/{total_rp}  | 총점: {result['score_total']}")
    print(" 루브릭:", result["rubric_scores"])
    print(" 위험문구:", result["risky_phrases"][0]["text"], "→", result["risky_phrases"][0]["reason"])
    print(" 핵심 누락:")
    for m in result["missing"]:
        print("   -", m)
    print("\n 피드백:", result["recommended_revision"])
    out = PROC / "scoring_result_demo-001.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote -> {out}")


if __name__ == "__main__":
    main()
