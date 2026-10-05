#!/usr/bin/env python3
"""합성 세트1 재균형: 난이도 재보정 + 기전(mechanism) 유형 4문항 채움 + 치료→처치 통일."""

import json
import collections
from pathlib import Path

TARGET = Path("data_private/exam_sets/SYNTH_2026_SET1.json")
SRC = "synthetic_gen_v1"

# 정직한 난이도 재보정 (하=고전적 단일최선답, 중=소견통합, 상=우선순위·다단계·드문상황)
DIFF = {
    1: "하", 2: "하", 3: "하", 4: "하", 5: "하", 6: "상", 7: "하", 8: "중", 9: "하", 10: "중",
    11: "중", 12: "하", 13: "중", 14: "중", 15: "중", 16: "중", 17: "중", 18: "중", 19: "하", 20: "중",
    21: "중", 22: "하", 23: "중", 24: "중", 25: "중", 26: "하", 27: "하", 28: "중", 29: "하", 30: "상",
    31: "상", 32: "하", 33: "중", 34: "중", 35: "중", 36: "중", 37: "상", 38: "중", 39: "중", 40: "상",
    41: "중", 42: "상", 43: "중", 44: "중", 45: "중", 46: "중", 47: "상", 48: "중", 49: "중", 50: "하",
    51: "하", 52: "하", 53: "중", 54: "중", 55: "상", 56: "중", 57: "중", 58: "하", 59: "하", 60: "상",
    61: "하", 62: "중", 63: "중", 64: "상", 65: "중", 66: "상", 67: "중", 68: "중", 69: "중", 70: "하",
    71: "하", 72: "상", 73: "중", 74: "하", 75: "중", 76: "상", 77: "중", 78: "하", 79: "상", 80: "중",
}


def ce(text, rationale, correct=False):
    return {"choice_text": text, "rationale": rationale, "explanation": rationale,
            "is_correct": correct, "source": SRC}


# 기전(mechanism) 유형으로 전환 — 주제는 유지, 질문을 약물 작용기전으로
MECH = {}
MECH[39] = dict(
    system="근골격·류마티스", qtype="기전", difficulty="중",
    tags=["gout", "allopurinol", "xanthine_oxidase_inhibitor"],
    stem="만성 통풍 환자에서 반복 발작과 통풍결절이 있어 요산 생성을 줄이기 위해 알로푸리놀을 장기 투여하기로 하였다. 이 약물의 주된 작용 기전은?",
    choices={"1": "잔틴산화효소를 억제하여 요산 생성을 줄임", "2": "콩팥에서 요산 배설을 촉진",
             "3": "요산분해효소로 요산을 알란토인으로 분해", "4": "사구체 여과율을 높여 요산 배설 증가",
             "5": "프로스타글랜딘 합성을 억제하여 염증을 줄임"},
    answer="1",
    explanation="알로푸리놀은 잔틴산화효소를 억제해 하이포잔틴→잔틴→요산 경로의 요산 생성을 감소시키는 요산저하제다.",
    rationale="알로푸리놀은 잔틴산화효소 억제제로 요산 '생성'을 줄인다(배설 촉진이 아님).",
    klp=["알로푸리놀·페북소스타트: 잔틴산화효소 억제(생성 감소).",
         "프로베네시드: 요산 배설 촉진(다른 기전).",
         "라스부리케이스: 요산분해효소(요산 분해)."],
    ce_map={"1": ce("잔틴산화효소 억제로 요산 생성 감소", "알로푸리놀의 작용 기전. 정답.", True),
            "2": ce("요산 배설 촉진", "프로베네시드의 기전으로 다르다."),
            "3": ce("요산분해효소로 분해", "라스부리케이스의 기전으로 다르다."),
            "4": ce("사구체 여과율 증가", "알로푸리놀의 기전이 아니다."),
            "5": ce("프로스타글랜딘 합성 억제", "NSAID의 급성기 소염 기전으로 요산저하가 아니다.")},
)
MECH[48] = dict(
    system="혈액·종양", qtype="기전", difficulty="중",
    tags=["acute_promyelocytic_leukemia", "atra", "differentiation"],
    stem="급성전골수세포백혈병(PML-RARA 양성) 환자에게 전트랜스레티노산(ATRA)을 투여한다. 이 약물이 백혈병세포에 작용하는 주된 기전은?",
    choices={"1": "미성숙 전골수구의 분화를 유도", "2": "DNA 이중나선을 직접 절단",
             "3": "미세소관 중합을 억제", "4": "엽산 대사를 억제", "5": "티로신인산화효소를 억제"},
    answer="1",
    explanation="ATRA는 PML-RARA 융합단백에 의해 분화가 차단된 전골수구의 분화를 유도해 성숙시킴으로써 관해를 유도한다.",
    rationale="ATRA는 세포독성이 아니라 전골수구의 '분화 유도'로 작용한다.",
    klp=["APL: PML-RARA로 분화 차단.",
         "ATRA: 분화 유도(세포독성 아님).",
         "조기 시작으로 DIC·출혈 사망 감소."],
    ce_map={"1": ce("미성숙 전골수구의 분화 유도", "ATRA의 분화유도 기전. 정답.", True),
            "2": ce("DNA 직접 절단", "블레오마이신 등 세포독성 기전으로 다르다."),
            "3": ce("미세소관 중합 억제", "빈카알칼로이드 기전으로 다르다."),
            "4": ce("엽산 대사 억제", "메토트렉세이트 기전으로 다르다."),
            "5": ce("티로신인산화효소 억제", "이마티닙 등 기전으로 다르다.")},
)
MECH[71] = dict(
    system="소화기·간담췌", qtype="기전", difficulty="하",
    tags=["gastroesophageal_reflux_disease", "proton_pump_inhibitor", "mechanism"],
    stem="위식도역류질환 환자에게 양성자펌프억제제를 처방하였다. 이 약물의 주된 작용 기전은?",
    choices={"1": "위벽세포의 H+/K+-ATPase(양성자펌프)를 비가역적으로 억제", "2": "히스타민 H2수용체를 차단",
             "3": "가스트린 분비를 촉진", "4": "위점막 프로스타글랜딘 합성을 증가", "5": "하부식도괄약근 압력을 낮춤"},
    answer="1",
    explanation="양성자펌프억제제는 위벽세포 정단막의 H+/K+-ATPase를 비가역적으로 억제해 위산 분비를 강력히 줄인다.",
    rationale="PPI는 위벽세포의 H+/K+-ATPase(양성자펌프)를 억제해 산분비를 차단한다.",
    klp=["PPI: H+/K+-ATPase 비가역 억제.",
         "H2차단제보다 강한 산억제.",
         "식전 복용으로 활성펌프 억제."],
    ce_map={"1": ce("H+/K+-ATPase 비가역 억제", "PPI의 작용 기전. 정답.", True),
            "2": ce("H2수용체 차단", "H2차단제의 기전으로 다르다."),
            "3": ce("가스트린 분비 촉진", "산분비를 늘려 치료 방향과 반대다."),
            "4": ce("프로스타글랜딘 합성 증가", "미소프로스톨 등과 관련되며 PPI 기전이 아니다."),
            "5": ce("하부식도괄약근 압력 감소", "역류를 악화시켜 치료 기전이 아니다.")},
)
MECH[74] = dict(
    system="순환기", qtype="기전", difficulty="하",
    tags=["deep_vein_thrombosis", "direct_oral_anticoagulant", "factor_xa"],
    stem="심부정맥혈전 환자에게 리바록사반과 같은 직접경구항응고제를 투여한다. 이 약물의 주된 작용 표적은?",
    choices={"1": "활성화 X인자(Xa)를 직접 억제", "2": "비타민 K 의존 응고인자 합성을 억제",
             "3": "혈소판 시클로옥시게나제(COX-1)를 억제", "4": "피브린 용해를 촉진",
             "5": "항트롬빈 비의존적으로 트롬빈 생성을 늘림"},
    answer="1",
    explanation="리바록사반·아픽사반 등은 활성화 X인자(Xa)를 직접 억제하여 응고연쇄를 차단하는 직접경구항응고제다.",
    rationale="'~xaban' 계열 직접경구항응고제는 활성화 X인자(Xa)를 직접 억제한다.",
    klp=["직접 Xa 억제제(리바록사반·아픽사반): Xa 직접 억제.",
         "와파린은 비타민 K 의존인자 합성 억제(다른 기전).",
         "다비가트란은 직접 트롬빈 억제."],
    ce_map={"1": ce("활성화 X인자(Xa) 직접 억제", "직접 Xa 억제제의 기전. 정답.", True),
            "2": ce("비타민 K 의존 응고인자 합성 억제", "와파린의 기전으로 다르다."),
            "3": ce("혈소판 COX-1 억제", "아스피린의 기전으로 다르다."),
            "4": ce("피브린 용해 촉진", "혈전용해제의 기전으로 다르다."),
            "5": ce("트롬빈 생성 증가", "항응고와 반대 방향이다.")},
)


def main():
    data = json.loads(TARGET.read_text(encoding="utf-8"))
    by_num = {q["question_number"]: q for q in data["questions"]}

    # 1) 치료 → 처치 통일
    for q in data["questions"]:
        if q.get("question_type") == "치료":
            q["question_type"] = "처치"

    # 2) 난이도 재보정
    for num, dif in DIFF.items():
        if num in by_num:
            by_num[num]["difficulty"] = dif

    # 3) 기전 유형 전환
    for num, m in MECH.items():
        q = by_num[num]
        q["system"] = m["system"]
        q["question_type"] = m["qtype"]
        q["difficulty"] = m["difficulty"]
        q["concept_tags"] = m["tags"]
        q["stem"] = m["stem"]
        q["choices"] = m["choices"]
        q["answer"] = m["answer"]
        q["explanation"] = m["explanation"]
        q["answer_rationale"] = m["rationale"]
        q["key_learning_points"] = m["klp"]
        q["choice_explanations"] = m["ce_map"]
        q["needs_review"] = True
        q["review_status"] = "generated_draft"
        q.setdefault("generation", {})["rebalanced"] = True

    TARGET.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    typ = collections.Counter(q["question_type"] for q in data["questions"])
    dif = collections.Counter(q["difficulty"] for q in data["questions"])
    print("[done] 재균형 완료")
    print("유형:", dict(typ.most_common()))
    print("난이도:", dict(dif.most_common()))


if __name__ == "__main__":
    raise SystemExit(main())
