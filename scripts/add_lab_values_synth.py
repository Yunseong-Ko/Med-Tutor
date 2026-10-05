#!/usr/bin/env python3
"""합성 문항에 구체적 검사 수치(참고치 포함)를 본문 마지막 질문 앞에 삽입."""

import json
from pathlib import Path

# (set, qnum) -> 검사 결과 문자열(참고치 포함)
LABS = {
    ("SET1", 1):  "백혈구 13,500/mm³, 혈청 리파아제 1,050 U/L(참고치 13~60), 아밀라아제 610 U/L, 칼슘 8.8 mg/dL",
    ("SET1", 14): "총 테스토스테론 0.85 ng/mL(참고치 0.1~0.5), 황체형성호르몬 14 mIU/mL, 난포자극호르몬 5 mIU/mL, 프로락틴·갑상샘자극호르몬 정상",
    ("SET1", 19): "적혈구침강속도 52 mm/시간(참고치 <20), C-반응단백질 24 mg/L(참고치 <5), 류마티스인자 양성",
    ("SET1", 21): "혈색소 10.2 g/dL, 적혈구침강속도 45 mm/시간(참고치 <20), C-반응단백질 38 mg/L(참고치 <5), 대변 칼프로텍틴 480 µg/g(참고치 <50)",
    ("SET1", 23): "N-말단프로B형나트륨이뇨펩타이드(NT-proBNP) 3,200 pg/mL, 크레아티닌 0.9 mg/dL, 나트륨 138 mEq/L, 포도당 188 mg/dL",
    ("SET1", 26): "갑상샘자극호르몬 <0.01 mIU/L(참고치 0.3~4.5), 유리 T4 3.4 ng/dL(참고치 0.8~1.8)",
    ("SET1", 27): "24시간 소변 단백 6.5 g, 혈청 알부민 2.1 g/dL, 총콜레스테롤 330 mg/dL, 크레아티닌 0.9 mg/dL",
    ("SET1", 42): "백혈구 19,200/mm³, 젖산 3.9 mmol/L(참고치 <2), C-반응단백질 160 mg/L(참고치 <5)",
    ("SET1", 53): "암항원(CA)-125 720 U/mL(참고치 <35), CA19-9 경도 상승, 혈색소 10.8 g/dL",
    ("SET1", 61): "백혈구 14,800/mm³(중성구 86%), C-반응단백질 42 mg/L(참고치 <5)",
    ("SET1", 62): "백혈구 13,200/mm³, C-반응단백질 68 mg/L(참고치 <5)",
    ("SET1", 64): "크레아티닌 2.1 mg/dL(기저 정상), 요검사에서 단백뇨, 혈색소 정상",
    ("SET1", 69): "백혈구 18,500/mm³, 젖산 4.2 mmol/L(참고치 <2), C-반응단백질 220 mg/L(참고치 <5)",
    ("SET1", 78): "뇌척수액: 단백 92 mg/dL(참고치 15~45), 백혈구 3/mm³ (단백세포해리)",

    ("SET2", 1):  "백혈구 19,800/mm³, 총빌리루빈 4.8 mg/dL, 알칼리인산분해효소 상승, 젖산 3.5 mmol/L(참고치 <2)",
    ("SET2", 2):  "트로포닌 I 0.09 ng/mL(참고치 <0.04), 크레아티닌키나아제-MB 경도 상승",
    ("SET2", 6):  "혈청 칼슘 11.8 mg/dL(참고치 8.5~10.5), 부갑상샘호르몬 128 pg/mL(참고치 15~65), 인 2.2 mg/dL(참고치 2.5~4.5)",
    ("SET2", 8):  "크레아티닌 2.4 mg/dL(기저 0.9), 혈액요소질소 62 mg/dL(BUN/Cr 26), 나트륨분획배설률(FENa) 0.5%",
    ("SET2", 21): "젖산 4.5 mmol/L(참고치 <2), 백혈구 19,000/mm³, 대사산증",
    ("SET2", 22): "혈중 암모니아 118 µmol/L(참고치 <50), 간효소 경도 상승",
    ("SET2", 59): "카복시헤모글로빈 24%(비흡연 참고치 <3), 대사산증",
    ("SET2", 61): "AST 1,850 U/L, ALT 2,240 U/L(참고치 <40), 총빌리루빈 6.2 mg/dL",
    ("SET2", 69): "적혈구침강속도 78 mm/시간(참고치 <20), C-반응단백질 92 mg/L(참고치 <5), 백혈구 12,500/mm³",
    ("SET2", 77): "크레아티닌키나아제(CK) 42,000 U/L(참고치 <200), 크레아티닌 1.8 mg/dL, 칼륨 5.8 mEq/L",
    ("SET2", 79): "구획내압 45 mmHg(참고치 <10), 크레아티닌키나아제 상승",
}

TARGETS = {"SET1": "SYNTH_2026_SET1", "SET2": "SYNTH_2026_SET2"}


def insert_labs(stem, labs):
    stem = stem.rstrip()
    # 마지막 질문 문장 앞에 삽입
    idx = stem.rfind(". ")
    block = f"검사 결과는 다음과 같다: {labs}."
    if idx > 0:
        return stem[:idx + 1] + " " + block + " " + stem[idx + 2:]
    return block + " " + stem


def main():
    by_set = {}
    for (s, n), v in LABS.items():
        by_set.setdefault(s, {})[n] = v

    for s, name in TARGETS.items():
        p = Path(f"data_private/exam_sets/{name}.json")
        d = json.loads(p.read_text(encoding="utf-8"))
        bn = {q["question_number"]: q for q in d["questions"]}
        cnt = 0
        for n, labs in by_set.get(s, {}).items():
            q = bn[n]
            if q.get("labs_added"):
                continue
            q["stem"] = insert_labs(q["stem"], labs)
            q["labs_added"] = True
            q["lab_values_text"] = labs
            cnt += 1
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{s}] 검사 수치 삽입 {cnt}문항")


if __name__ == "__main__":
    raise SystemExit(main())
