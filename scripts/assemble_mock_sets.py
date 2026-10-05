#!/usr/bin/env python3
"""유사문항 변형 풀 → 4세트×80 평행 시험지 조립 (로컬·결정론).

원칙: 같은 seed의 변형은 서로 다른 세트에 배치(노출 분산) · 세트 내 과목 균형 ·
      초과분은 예비 풀 · 이미지형은 파일 존재 확인 후 유지.
입력: data_private/professor_items/generated/variants_all.json  [{seed_id,variant,subject?,concept,axis,stem,choices,answer,explanation,image?}]
      generated/variant_seeds.json (seed_id→subject)
출력: generated/set_{1..4}.json + generated/reserve.json + 조립 리포트(stdout 통계)
"""
import json
import random
from collections import defaultdict, Counter
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
IMG = Path("data_private/professor_items/images")
N_SETS, SET_SIZE = 4, 80


def main() -> int:
    items = json.loads((GEN / "variants_all.json").read_text(encoding="utf-8"))
    subj_of = {s["seed_id"]: s["subject"] for s in json.loads((GEN / "variant_seeds.json").read_text(encoding="utf-8"))}
    rng = random.Random(20260813)

    # seed별 변형 묶기 + 이미지 파일 확인
    by_seed = defaultdict(list)
    for it in items:
        if it.get("image") and not (IMG / it["image"]).exists():
            it["image"] = ""
        it["subject"] = subj_of.get(it["seed_id"], it.get("subject", "?"))
        by_seed[it["seed_id"]].append(it)
    seeds = sorted(by_seed.keys())
    rng.shuffle(seeds)

    # 배치: seed i의 v1→세트 i%4, v2→세트 (i+2)%4 (같은 seed 분리 보장)
    sets = [[] for _ in range(N_SETS)]
    for i, sid in enumerate(seeds):
        vs = sorted(by_seed[sid], key=lambda x: x.get("variant", 1))
        for j, it in enumerate(vs[:2]):
            sets[(i + j * 2) % N_SETS].append(it)

    # 세트별 80 트리밍(초과분→예비): 같은 concept 중복 우선 제거
    reserve = []
    for k in range(N_SETS):
        s = sets[k]
        rng.shuffle(s)
        seen_c = set()
        keep, extra = [], []
        for it in s:
            c = (it.get("concept") or "").lower()
            if c and c in seen_c:
                extra.append(it)
            else:
                seen_c.add(c)
                keep.append(it)
        pool = keep + extra
        sets[k] = pool[:SET_SIZE]
        reserve += pool[SET_SIZE:]

    # 세트 내 정렬: 과목 순 → 문항번호/관리번호 부여
    out_stats = []
    for k in range(N_SETS):
        sets[k].sort(key=lambda x: (x["subject"], x.get("concept", "")))
        for n, it in enumerate(sets[k], 1):
            it["no"] = n
            it["mgmt_no"] = f"MK25{k+1}{n:02d}"
            it["lab_box"] = it.get("lab_box", "")
        (GEN / f"set_{k+1}.json").write_text(json.dumps(sets[k], ensure_ascii=False, indent=1), encoding="utf-8")
        subj = Counter(it["subject"] for it in sets[k])
        ans = Counter(str(it["answer"]) for it in sets[k])
        n_img = sum(1 for it in sets[k] if it.get("image"))
        out_stats.append((k + 1, len(sets[k]), n_img, dict(ans)))
        print(f"세트{k+1}: {len(sets[k])}문항 · 이미지 {n_img} · 정답분포 {dict(sorted(ans.items()))}")
        print(f"   과목: {dict(subj.most_common())}")
    (GEN / "reserve.json").write_text(json.dumps(reserve, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"예비 풀: {len(reserve)}문항 → reserve.json")

    # 같은 seed 같은 세트 중복 검사
    dup = 0
    for k in range(N_SETS):
        c = Counter(it["seed_id"] for it in sets[k])
        dup += sum(1 for v in c.values() if v > 1)
    print(f"같은 seed 동일세트 중복: {dup} (0이어야 정상)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
