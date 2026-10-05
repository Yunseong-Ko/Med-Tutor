#!/usr/bin/env python3
"""1차 임종평 파싱 실패 4문항 수동 패치 (검사table로 선지 분리 실패한 케이스)."""

import json
from pathlib import Path

EXTRACTED = Path("data_private/course_exams/extracted")

PATCH = {
    "1교시": (46, "72세 남자가 1일 전부터 소변이 나오지 않아 응급실에 왔다. 6개월 전부터 배뇨 시 힘을 주어야 하고 소변줄기가 약해졌다고 한다. 혈압 150/90 mmHg, 맥박 84회/분, 호흡 18회/분, 체온 36.6℃이다. 아랫배가 팽창되어 있으며 압통이 있다. 검사 결과는 다음과 같다. 조치는?",
             {"1": "방광창냄술", "2": "도뇨관 삽입", "3": "복부 컴퓨터단층촬영",
              "4": "소변나트륨분획배설률 측정", "5": "단회뇨 단백질/크레아티닌 비"}, []),
    "2교시": (21, "30세 여자가 3주 전부터 왼쪽 무릎이 아프고, 계속 열이 난다며 병원에 왔다. 1년 전부터 매달 입안이 헐며, 햇빛에 노출된 피부가 쉽게 붉어진다고 한다. 혈압 110/60 mmHg, 맥박 90회/분, 호흡 16회/분, 체온 38.1℃이다. 왼쪽 무릎에서 부종과 압통이 있다. 검사 결과는 다음과 같다. 진단을 위한 검사는?",
             {"1": "요산", "2": "항핵항체", "3": "HLA-B27", "4": "항중성구세포질항체",
              "5": "항고리시트룰린펩타이드(CCP)항체"}, []),
    "3교시": (11, "29세 여자가 3개월 전부터 한 달에 한두 번 갑자기 몹시 불안해진다며 병원에 왔다. 별일 없이 지내다가도 갑자기 심장이 두근거리고 식은땀이 나며 숨쉬기가 어렵고 어지럽다고 한다. 이것을 '발작'이라 부르며 10분 이내 최고로 심해지고 이후 한두 시간 불안하다. 1개월 전부터는 심장마비가 올 것 같은 두려움과 미칠 것 같은 느낌도 들어 괴롭고, 또 '발작'이 올까 봐 외출도 피한다. 혈압 145/92 mmHg, 맥박 90회/분, 호흡 22회/분, 체온 36.8℃이다. 심전도, 가슴 X선, 혈액검사 결과는 정상이다. 치료는?",
             {"1": "아스피린", "2": "테오필린", "3": "알프라졸람", "4": "할로페리돌",
              "5": "나이트로글리세린"}, []),
    "4교시": (26, "74세 여자가 1개월 전부터 맥이 고르지 못하다고 병원에 왔다. 3년 전부터 허혈 뇌경색으로 약물 치료 중이다. 혈압 128/61 mmHg, 맥박 71회/분, 호흡 13회/분, 체온 36.7℃이다. 촉진 시 맥박이 불규칙하다. 심전도(사진 15)이다. 진단은?",
             {"1": "동휴지", "2": "굴부정맥", "3": "심방세동", "4": "심방조기박동",
              "5": "가속접합부리듬"}, ["15"]),
}


def main():
    for gyo, (num, stem, choices, sajin_refs) in PATCH.items():
        eid = f"COMPREHENSIVE_2026_1CHA_{gyo}"
        p = EXTRACTED / f"{eid}.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        assets = {a["media_id"]: a for a in d["media_assets"]}
        by_sajin = {}
        for a in d["media_assets"]:
            by_sajin.setdefault(a["sajin"].split("-")[0], []).append(a)
        refs = []
        for sn in sajin_refs:
            for a in sorted(by_sajin.get(sn, []), key=lambda a: a["sajin"]):
                refs.append({"media_id": a["media_id"], "caption": a["caption"],
                             "sajin": a["sajin"], "needs_review": True})
        rec = next((q for q in d["questions"] if q["question_number"] == num), None)
        newq = {
            "question_id": f"{eid}_Q{num:03d}", "source_exam": eid, "exam_date": "2026-1차",
            "grade": "4", "course_name": "임상의학종합평가", "round_label": "1차",
            "period_label": gyo, "question_number": num, "stem": stem, "stimulus": None,
            "choices": choices, "answer": None, "media": {"media_refs": refs},
            "labels": {}, "review_status": "extracted", "needs_review": True,
            "review_reasons": ["수동패치"], "parser_version": "1cha_v1",
        }
        if rec:
            d["questions"][d["questions"].index(rec)] = newq
        else:
            d["questions"].append(newq)
            d["questions"].sort(key=lambda q: q["question_number"])
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{gyo}] Q{num} 패치 (선지 {len(choices)}, 이미지 {len(refs)})")


if __name__ == "__main__":
    raise SystemExit(main())
