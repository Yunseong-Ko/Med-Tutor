#!/usr/bin/env python3
"""정답 포함본에서 추출한 정답을 기존 종합평가 파일에 병합·대조.

- 1·2교시: 정답이 비어 있던 파일에 정답을 채운다(문항번호 매칭). practice-ready로 전환.
- 3·4교시: 이미 있는 정답(숨은 마커 추출)과 정답키를 대조해 불일치를 보고(해설은 건드리지 않음).
"""

import glob
import json
from pathlib import Path

SCRATCH = "/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad/ans_extract"
EXTRACT = Path("data_private/course_exams/extracted")

# 기존 파일 (교시 -> stem)
TARGETS = {
    "1교시": "COURSE_4_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_1교시",
    "2교시": "COURSE_X_DATE_UNKNOWN_EXAM_2교시",
    "3교시": "COURSE_X_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_3교시",
    "4교시": "COURSE_X_DATE_UNKNOWN_EXAM_4교시",
}
FILL = {"1교시", "2교시"}     # 정답 채우기
VERIFY = {"3교시", "4교시"}   # 정답 대조


def build_answer_maps():
    """정답키 임시 추출본에서 {교시: {문항번호: 정답}} 구성."""
    maps = {}
    for f in glob.glob(f"{SCRATCH}/*.json"):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        period = (d.get("exam") or {}).get("period_label")
        if not period:
            continue
        amap = {}
        for q in d.get("questions", []):
            num = q.get("question_number")
            ans = q.get("answer")
            if num is not None and ans is not None:
                amap[int(num)] = str(ans)
        maps[period] = amap
    return maps


def main():
    maps = build_answer_maps()
    print("정답키 추출:", {k: len(v) for k, v in maps.items()})

    for period, stem in TARGETS.items():
        amap = maps.get(period)
        if not amap:
            print(f"[skip] {period}: 정답키 없음")
            continue
        path = EXTRACT / f"{stem}.json"
        if not path.exists():
            print(f"[skip] {period}: 대상 파일 없음")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))

        if period in FILL:
            filled = 0
            missing = []
            for q in d["questions"]:
                num = q.get("question_number")
                if num in amap:
                    q["answer"] = amap[num]
                    filled += 1
                elif q.get("answer") is None:
                    missing.append(num)
            path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[fill] {period}: 정답 {filled}개 채움" + (f" · 정답키 없는 문항 {missing}" if missing else ""))

        elif period in VERIFY:
            mism = []
            for q in d["questions"]:
                num = q.get("question_number")
                mine = q.get("answer")
                key = amap.get(num)
                if key is not None and mine is not None and str(mine) != str(key):
                    mism.append((num, mine, key))
            if mism:
                print(f"[verify] {period}: 불일치 {len(mism)}건 → (문항, 내값, 정답키)")
                for m in mism:
                    print(f"    Q{m[0]}: 내값 {m[1]} vs 정답키 {m[2]}")
            else:
                print(f"[verify] {period}: 전부 일치 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
