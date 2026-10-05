#!/usr/bin/env python3
"""생성 문항 풀에 플랫폼 품질게이트 일괄 적용 + 풀 간 비교 리포트.

플랫폼 파이프라인 그대로 사용:
  - item_quality_check.apply_generation_quality_gate (결함스캐너 + self-check + NBME 하드룰)
  - lint_generated_items.lint_batch (배치 레벨: 정답분포 χ², 근사중복, 케이스 품질)
  - lint_generated_items.rebalance_answer_positions (정답 위치 결정론 균등화)

사용:
  python3 scripts/gate_image_items.py --pool img_items_v3.json [--pool img_items_v4.json ...]
                                      [--rebalance]
출력: 각 풀 <이름>.gated.json + 콘솔 비교표
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from item_quality_check import apply_generation_quality_gate  # noqa: E402
from lint_generated_items import lint_batch, rebalance_answer_positions  # noqa: E402

GEN = Path("data_private/professor_items/generated")


def gate_pool(name: str, rebalance: bool) -> dict:
    p = GEN / name
    items = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items", [])
    for it in items:
        # 게이트 입력 정합: topic 필드
        it.setdefault("topic", it.get("dx") or it.get("concept", ""))
        apply_generation_quality_gate(it)
    if rebalance:
        items, moved = rebalance_answer_positions(items)
        # 재배치는 정답 위치·선지별 해설을 바꾸므로 판정을 다시 계산해야 한다.
        # (예전에는 재배치 전 판정을 출력해, 보고 수치와 저장 파일이 어긋났다.)
        for it in items:
            apply_generation_quality_gate(it)
    else:
        moved = 0
    rep = lint_batch(items)

    hard_fail = sum(1 for it in items if it["item_quality"]["hard_rule_failures"])
    flawed = sum(1 for it in items if it["item_quality"]["flaw_count"])
    clean = sum(1 for it in items
                if not it["item_quality"]["hard_rule_failures"]
                and not it["item_quality"]["flaw_count"])
    sc = Counter()
    for it in items:
        q = it["item_quality"]
        sc["self_pass"] += q["self_check_passed"]
        sc["self_total"] += q["self_check_total"]
    flaws = Counter()
    for it in items:
        for f in it["item_quality"].get("flaws") or []:
            flaws[f] += 1

    out = p.with_suffix("").name + ".gated.json"
    (GEN / out).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return {
        "name": name, "n": len(items), "clean": clean, "flawed": flawed,
        "hard_fail": hard_fail, "moved": moved,
        "self_rate": round(100 * sc["self_pass"] / max(1, sc["self_total"]), 1),
        "chi2": rep["answer_position_chi2_vs_uniform"],
        "longest_key_pct": rep["longest_is_key_pct"],
        "dupes": rep["near_duplicate_pairs"],
        "flaw_top": flaws.most_common(8),
        "out": out,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", action="append", required=True)
    ap.add_argument("--rebalance", action="store_true")
    args = ap.parse_args()

    rows = [gate_pool(n, args.rebalance) for n in args.pool]
    print(f"{'풀':<22}{'문항':>5}{'클린':>6}{'결함':>6}{'하드룰탈락':>9}{'self%':>7}{'χ²':>7}{'최장=정답%':>9}{'중복쌍':>6}")
    for r in rows:
        print(f"{r['name']:<22}{r['n']:>5}{r['clean']:>6}{r['flawed']:>6}{r['hard_fail']:>9}"
              f"{r['self_rate']:>7}{str(r['chi2']):>7}{r['longest_key_pct']:>9}{r['dupes']:>6}")
    for r in rows:
        print(f"\n[{r['name']}] 결함 상위: {r['flaw_top']}")
        if r["moved"]:
            print(f"  정답 위치 재배치 {r['moved']}건")
        print(f"  → {r['out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
