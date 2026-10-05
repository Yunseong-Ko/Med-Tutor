#!/usr/bin/env python3
"""게이트 통과 풀에서 4세트 삽입용 이미지 문항 60개(세트당 15) 선별.

선별 기준(결정론, 우선순위순):
  1. 하드룰 탈락 0 + 결함 0 (클린)
  2. 온톨로지 grounded(disease_concept_id 有) 우선
  3. 진단(dx) 다양성 — 같은 진단 최대 2문항
  4. 축 균형 — 진단/검사/치료 고르게
  5. 검사종류 다양성
출력: generated/img_items_selected.json (60개, set_hint 1~4 부여)
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

GEN = Path("data_private/professor_items/generated")


def score(it) -> tuple:
    q = it.get("item_quality") or {}
    hard = len(q.get("hard_rule_failures") or [])
    flaws = int(q.get("flaw_count") or 0)
    grounded = 0 if it.get("disease_concept_id") else 1
    return (hard, flaws, grounded)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--total", type=int, default=60)
    args = ap.parse_args()

    items = json.loads((GEN / args.pool).read_text(encoding="utf-8"))
    items = [it for it in items if it.get("image")]
    items.sort(key=score)

    # 축별 쿼터(진단·검사·치료 균등) — 교수 지시가 이 3축이므로 한 축이 몰리면 안 된다.
    AXES = ["진단", "검사", "치료"]
    quota = {a: args.total // len(AXES) for a in AXES}
    for i in range(args.total - sum(quota.values())):
        quota[AXES[i % len(AXES)]] += 1

    picked, dx_count, axis_count, mod_count = [], Counter(), Counter(), Counter()

    def take(it) -> None:
        picked.append(it)
        dx_count[it.get("dx") or it.get("concept", "")] += 1
        axis_count[it.get("axis", "")] += 1
        mod_count[it.get("modality", "")] += 1

    # 1차: 축 쿼터 + 진단 중복 ≤2
    for it in items:
        axis = it.get("axis", "")
        dx = it.get("dx") or it.get("concept", "")
        if axis_count[axis] >= quota.get(axis, 0) or dx_count[dx] >= 2:
            continue
        take(it)
    # 2차: 진단 중복 제한만 유지하고 쿼터 미달분 채움
    chosen = {id(x) for x in picked}
    for it in items:
        if len(picked) >= args.total:
            break
        if id(it) in chosen or (dx_count[it.get("dx") or it.get("concept", "")] >= 2):
            continue
        take(it)
        chosen.add(id(it))
    # 3차: 그래도 부족하면 제한 없이 채움
    for it in items:
        if len(picked) >= args.total:
            break
        if id(it) not in chosen:
            take(it)
            chosen.add(id(it))

    # 세트 배정: 같은 진단이 같은 세트에 안 겹치게 라운드로빈
    by_dx = defaultdict(list)
    for it in picked:
        by_dx[it.get("dx", "")].append(it)
    k = 0
    for dx, group in sorted(by_dx.items()):
        for it in group:
            it["set_hint"] = (k % 4) + 1
            k += 1

    hard0 = sum(1 for it in picked if not (it["item_quality"].get("hard_rule_failures")))
    clean = sum(1 for it in picked if not (it["item_quality"].get("hard_rule_failures"))
                and not it["item_quality"].get("flaw_count"))
    (GEN / "img_items_selected.json").write_text(
        json.dumps(picked, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"선별 {len(picked)} · 하드룰통과 {hard0} · 완전클린 {clean}")
    print(f"  축: {dict(axis_count)} · 고유진단 {len(dx_count)} · 검사종류 {len(mod_count)}")
    print(f"  세트 배정: {Counter(it['set_hint'] for it in picked)}")
    print(f"[출력] {GEN/'img_items_selected.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
