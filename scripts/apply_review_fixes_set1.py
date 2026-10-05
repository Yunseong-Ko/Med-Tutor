#!/usr/bin/env python3
"""의학검토 반영: Q47 안전 가드레일, 기전문항 style_tag, Q3 hCG 주의 문구."""

import json
from pathlib import Path

TARGET = Path("data_private/exam_sets/SYNTH_2026_SET1.json")


def main():
    data = json.loads(TARGET.read_text(encoding="utf-8"))
    by_num = {q["question_number"]: q for q in data["questions"]}

    # 1) Q47 SIADH: 교정 속도 안전 가드레일 보강 (정답 불변)
    q47 = by_num[47]
    q47["explanation"] = (
        "경련·혼돈을 동반한 중증 증상성 저나트륨혈증은 고장성(3%) 식염수를 신중히 투여해 나트륨을 조심스럽게 올린다. "
        "단, 과교정에 의한 삼투성 탈수초증후군(ODS)을 예방하기 위해 교정 속도를 제한한다(대개 24시간 이내 8 mEq/L 미만, 첫 몇 시간은 증상 완화까지만 신속 교정)."
    )
    q47["key_learning_points"] = [
        "증상성 중증 저나트륨혈증(경련·혼돈): 3% 고장식염수 신중 투여.",
        "교정 속도 제한: 대개 24시간 이내 8 mEq/L 미만(과교정 시 삼투성 탈수초증후군).",
        "첫 몇 시간은 증상 완화 목표로만 급속 교정, 이후 완만 교정·혈청 나트륨 추적.",
    ]
    ce47 = q47["choice_explanations"]["1"]
    ce47["rationale"] = ce47["explanation"] = (
        "증상성 중증 저나트륨혈증의 초기 처치. 단 24시간 내 8 mEq/L 미만으로 교정 속도를 제한한다. 정답."
    )

    # 2) 기전형 문항 style_tag 구분
    for n in (39, 48, 71, 74):
        q = by_num[n]
        q["style_tag"] = "지식형·약리기전"
        q.setdefault("labels_hint", {})["style"] = "knowledge_pharmacology"

    # 3) Q3 자궁외임신: 단일 hCG 수치 의존 완화 주의 문구
    q3 = by_num[3]
    q3["explanation"] = (
        "베타 hCG가 판별역치(기관·장비에 따라 대개 1,500~2,000, 보수적으로 최대 ~3,500 mIU/mL)를 넘는데도 "
        "질초음파에서 자궁내 임신낭이 없으면 자궁외임신을 강하게 의심한다. 단, 단일 수치만으로 확진하지 않고 "
        "임상 경과·연속 hCG·초음파를 종합해 판단한다."
    )
    q3["key_learning_points"] = [
        "자궁외임신: 무월경·하복통·질출혈.",
        "판별역치 이상 hCG인데 자궁내 임신낭 없음이 핵심 단서(수치 단독 확진 금물).",
        "연속 hCG·초음파·임상 경과 종합, 불안정·파열 시 응급 수술.",
    ]

    TARGET.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[done] 검토 반영: Q47 안전 가드레일 / Q39·48·71·74 style_tag / Q3 hCG 주의 문구")


if __name__ == "__main__":
    raise SystemExit(main())
