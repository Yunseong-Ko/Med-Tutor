#!/usr/bin/env python3
"""합성 문항 개선:
 A) Lab을 구조화 필드(lab_values)로 분리 + 줄글의 정성 서술("상승해 있다") 제거 → 학생이 수치 직접 해석
 B) 영상소견 텍스트 서술 제거 → 학생이 이미지 직접 판독
"""

import json
import re
from pathlib import Path

SRC = {"SET1": Path("data_private/exam_sets/SYNTH_2026_SET1.json"),
       "SET2": Path("data_private/exam_sets/SYNTH_2026_SET2.json")}

# 이미 lab_values_text가 없는 문항에 새 검사 패널 부여(구조화 파싱은 아래 공통)
EXTRA_LABS = {
    ("SET1", 28): "백혈구 42,000/mm³(모세포 다수), 혈색소 8.0 g/dL, 혈소판 45,000/mm³",
    ("SET2", 29): "혈소판 12,000/mm³(참고치 150,000~400,000), 혈색소 정상, 백혈구 정상, 말초혈액 이상세포 없음",
}
APPEND_LABS = {
    ("SET2", 77): ", 소변 잠혈 양성(현미경 적혈구 거의 없음)",
}

# 줄글 편집: (old, new). 정성 서술 제거 + 영상소견 서술을 '아래 자료를 보라'로 전환
REPLACE = {
    ("SET1", 1):  [("혈청 리파아제가 정상 상한의 5배로 상승해 있다. ", "")],
    ("SET1", 8):  [("심전도에서 뾰족한 T파와 넓어진 QRS가 관찰된다", "심전도는 다음과 같다")],
    ("SET1", 11): [("수액 소생 후 시행한 상부위장관 내시경에서 십이지장 구부에 노출혈관을 동반한 궤양이 확인된다", "수액 소생 후 상부위장관 내시경을 시행하였다(아래 자료)")],
    ("SET1", 14): [("안드로겐이 경도 상승해 있고 임신반응은 음성이다", "임신반응은 음성이다")],
    ("SET1", 15): [("심전도에서 심방세동이 확인되고 혈역학은 안정적이다", "심전도는 다음과 같다. 혈역학은 안정적이다")],
    ("SET1", 19): [("염증수치가 상승해 있다. ", "")],
    ("SET1", 21): [("염증수치가 상승해 있고 빈혈이 있다. ", "")],
    ("SET1", 22): [("식도조영술에서 하부식도가 새부리 모양으로 좁아져 있다", "식도조영술 소견은 다음과 같다")],
    ("SET1", 26): [("갑상샘자극호르몬은 억제되고 유리 T4는 상승해 있다. ", "")],
    ("SET1", 27): [("소변에서 다량의 단백뇨가 있고, 혈청 알부민은 낮으며 혈중 지질은 상승해 있다. ", "")],
    ("SET1", 28): [("혈액검사에서 백혈구가 증가하고 말초혈액펴바른표본에 미성숙 모세포가 다수 관찰되며, 빈혈과 혈소판감소가 동반된다", "말초혈액펴바른표본은 다음과 같다")],
    ("SET1", 42): [("발열과 반동압통이 생기고 젖산이 상승하며 백혈구가 크게 증가하였다", "발열과 반동압통이 생겼다")],
    ("SET1", 49): [("가슴 X선에서 우상엽 침윤과 공동이 보이고, 객담 항산균도말과 결핵균 핵산증폭검사가 양성이다", "가슴 X선 소견은 다음과 같다. 객담 항산균도말과 결핵균 핵산증폭검사가 양성이다")],
    ("SET1", 53): [("복수가 있으며 CA-125가 크게 상승해 있다", "복수가 있다")],
    ("SET1", 54): [("심전도에서 P파와 QRS가 서로 무관하게 나타나는 완전방실차단이 확인되고 심실박동수는 38회/분이다", "심전도는 다음과 같으며 심실박동수는 38회/분이다")],
    ("SET1", 61): [("백혈구가 증가해 있다. ", "")],
    ("SET1", 62): [("좌하복부 압통이 있고 백혈구가 증가해 있다", "좌하복부 압통이 있다")],
    ("SET1", 64): [("있으며 혈청 크레아티닌이 상승해 있다", "있다")],
    ("SET1", 69): [("젖산이 상승해 있다. ", "")],

    ("SET2", 1):  [("담도확장과 총담관결석이 확인되고 백혈구·빌리루빈이 상승해 있다", "담도확장과 총담관결석이 확인된다")],
    ("SET2", 2):  [("초기 트로포닌이 경계 상승했다. ", "")],
    ("SET2", 6):  [("혈청 칼슘이 높은데 부갑상샘호르몬도 함께 상승해(부적절하게 정상~높음) 있다. ", "")],
    ("SET2", 8):  [("혈청 크레아티닌이 상승하고 혈액요소질소/크레아티닌 비가 높으며, 소변 나트륨분획배설률(FENa)이 1% 미만이다. ", "")],
    ("SET2", 21): [("젖산이 상승해 있다. ", "")],
    ("SET2", 22): [("혈중 암모니아가 상승해 있다. ", "")],
    ("SET2", 29): [("혈소판만 12,000/mm³로 감소해 있다. 비장종대는 없고 말초혈액에 이상세포는 없다", "비장종대는 없다. 말초혈액펴바른표본은 다음과 같다")],
    ("SET2", 34): [("심전도 모니터에서 심실세동이 확인된다", "심전도 모니터 소견은 다음과 같다")],
    ("SET2", 59): [("카복시헤모글로빈이 상승해 있다. ", "")],
    ("SET2", 61): [("간효소(AST·ALT)가 크게 상승해 있다. ", "")],
    ("SET2", 64): [("심전도에서 광범위 ST분절 상승이 보인다", "심전도는 다음과 같다")],
    ("SET2", 69): [("염증수치가 상승해 있다. ", "")],
    ("SET2", 77): [("혈청 크레아티닌인산화효소(CK)가 크게 상승하고 소변 잠혈은 양성이나 적혈구는 거의 없다", "검사 결과는 아래와 같다")],
    ("SET2", 79): [("구획 내압이 상승해 있다. ", "")],
}


def parse_labs(text):
    """콤마로 구분된 검사 문자열 → [{item, ref}] (참고치 분리)."""
    rows = []
    for chunk in text.split(", "):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.search(r"\(참고치\s*([^)]+)\)", chunk)
        ref = m.group(1).strip() if m else ""
        item = re.sub(r"\s*\(참고치[^)]*\)", "", chunk).strip()
        rows.append({"item": item, "ref": ref})
    return rows


def main():
    warns = []
    for s, path in SRC.items():
        d = json.loads(path.read_text(encoding="utf-8"))
        bn = {q["question_number"]: q for q in d["questions"]}
        for q in d["questions"]:
            n = q["question_number"]
            key = (s, n)
            # 1) 구조화 lab_values
            lab_text = q.get("lab_values_text")
            if key in EXTRA_LABS:
                lab_text = EXTRA_LABS[key]
            if key in APPEND_LABS and lab_text:
                lab_text = lab_text + APPEND_LABS[key]
            if lab_text:
                q["lab_values"] = parse_labs(lab_text)
                # 줄글의 인라인 검사블록 제거
                q["stem"] = re.sub(r"\s*검사 결과는 다음과 같다:.*?\. ", " ", q["stem"])
            # 2) 줄글 정성서술/영상소견 제거
            for old, new in REPLACE.get(key, []):
                if old in q["stem"]:
                    q["stem"] = q["stem"].replace(old, new)
                else:
                    warns.append(f"{s} Q{n}: 미매칭 → {old[:30]}")
            # 공백 정리
            q["stem"] = re.sub(r"\s{2,}", " ", q["stem"]).strip()
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        nlab = sum(1 for q in d["questions"] if q.get("lab_values"))
        print(f"[{s}] lab_values 구조화 {nlab}문항")
    if warns:
        print("경고(미매칭):")
        for w in warns:
            print("  ", w)
    else:
        print("모든 줄글 편집 매칭 성공")


if __name__ == "__main__":
    raise SystemExit(main())
