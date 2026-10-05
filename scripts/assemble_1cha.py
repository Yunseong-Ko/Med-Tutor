#!/usr/bin/env python3
"""2026 1차 임종평: 문항(한글시험지) + 이미지(사진자료) 조립 → 추출 JSON.

문항 텍스트의 '사진 N' 참조로 이미지 연결. answer는 없음(문제지만).
출력: data_private/course_exams/extracted/COMPREHENSIVE_2026_1CHA_N교시.json
"""

import re
import sys
import json
import importlib.util
from pathlib import Path

EXTRACTED = Path("data_private/course_exams/extracted")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


QE = load("qe", "scripts/extract_1cha_questions.py")
IE = load("ie", "scripts/extract_1cha_images.py")

SAJIN_REF = re.compile(r"사진\s*(\d{1,3})")


def assemble(gyo, commit):
    eid = IE.exam_id(gyo)
    questions = QE.extract(gyo)
    _, assets, _ = IE.extract(gyo, commit)
    # 사진번호 -> [asset]
    by_sajin = {}
    for a in assets:
        base = a["sajin"].split("-")[0]
        by_sajin.setdefault(base, []).append(a)
    # 사진 순서 정렬(-1,-2)
    for k in by_sajin:
        by_sajin[k].sort(key=lambda a: a["sajin"])

    out_questions = []
    used_assets = set()
    for num in range(1, 81):
        q = questions.get(num)
        if not q:
            out_questions.append({"question_number": num, "stem": None, "choices": {},
                                  "needs_review": True, "review_reasons": ["추출 실패"]})
            continue
        blob = q["stem"] + " " + " ".join(q["choices"].values())
        refs = []
        for sn in dict.fromkeys(SAJIN_REF.findall(blob)):  # 순서보존 중복제거
            for a in by_sajin.get(sn, []):
                refs.append({"media_id": a["media_id"], "caption": a["caption"],
                             "sajin": a["sajin"], "needs_review": True})
                used_assets.add(a["media_id"])
        rec = {
            "question_id": f"{eid}_Q{num:03d}",
            "source_exam": eid, "exam_date": "2026-1차", "grade": "4",
            "course_name": "임상의학종합평가", "round_label": "1차", "period_label": f"{gyo}교시",
            "question_number": num, "stem": q["stem"], "stimulus": None,
            "choices": q["choices"], "answer": None,
            "media": {"media_refs": refs},
            "labels": {}, "review_status": "extracted", "needs_review": True,
            "review_reasons": ([] if len(q["choices"]) == 5 else ["선지≠5·검토필요"]),
            "parser_version": "1cha_v1",
        }
        out_questions.append(rec)

    orphans = [a for a in assets if a["media_id"] not in used_assets]
    data = {
        "exam_id": eid, "source_exam": eid, "course_name": "임상의학종합평가",
        "exam_date": "2026-1차", "period_label": f"{gyo}교시",
        "questions": out_questions, "media_assets": assets,
    }
    if commit:
        EXTRACTED.mkdir(parents=True, exist_ok=True)
        (EXTRACTED / f"{eid}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    linked = sum(1 for q in out_questions if q.get("media", {}).get("media_refs"))
    bad = [q["question_number"] for q in out_questions if q.get("stem") and len(q.get("choices") or {}) != 5]
    missing = [q["question_number"] for q in out_questions if not q.get("stem")]
    print(f"[{gyo}교시] 문항 {sum(1 for q in out_questions if q.get('stem'))}/80 · 이미지연결 {linked} · "
          f"자산 {len(assets)}(고아 {len(orphans)}) · 선지≠5 {bad} · 누락 {missing} · commit={commit}")
    return data


def main():
    gyo = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None
    commit = "--commit" in sys.argv
    for g in ([gyo] if gyo else ["1", "2", "3", "4"]):
        assemble(g, commit)


if __name__ == "__main__":
    raise SystemExit(main())
