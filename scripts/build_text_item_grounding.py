#!/usr/bin/env python3
"""텍스트 문항용 블루프린트 재구성 + 플랫폼 grounding 팩 생성.

기존 blueprint_80.json은 '기타' 버킷이 26/80으로 비대했다 — 레지스트리 602개념 중
277개에 specialty가 없었기 때문. 이제 specialty 백필이 끝났으므로 27개 분과 기준으로
다시 짠다.

원칙:
  - 원본 시험 텍스트는 어떤 경로로도 읽지 않는다 (concept_registry + Harrison 포인터만).
  - 이미 이미지 문항으로 쓰인 개념은 제외해 시험지 내 중복을 막는다.
  - 분과 배분은 임상의학종합평가 실측 비율(내과계 우세)을 따른다.
출력: generated/text_blueprint.json, generated/text_grounding_packs.json
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_image_item_grounding import condense  # noqa: E402
from generation_grounding import build_generation_grounding  # noqa: E402

GEN = Path("data_private/professor_items/generated")
REG = Path("data_private/concept_registry.json")
SUPP = Path("data_private/curriculum/specialty_supplement.json")

# 임상의학종합평가 4교시 실측 분과 비율(교시당 50문항 텍스트분 기준 가중치).
# 합이 1.0이 되도록 정규화해서 쓴다.
WEIGHTS = {
    "소화기내과": 0.115, "순환기내과": 0.100, "호흡기내과": 0.095,
    "감염내과": 0.070, "내분비대사내과": 0.065, "신장내과": 0.055,
    "혈액종양내과": 0.055, "류마티스내과": 0.030, "알레르기내과": 0.020,
    "신경과": 0.060, "정신건강의학과": 0.045,
    "소아청소년과": 0.090, "산부인과": 0.085,
    "외과": 0.045, "정형외과": 0.015, "비뇨의학과": 0.015,
    "이비인후과": 0.010, "안과": 0.010, "피부과": 0.010,
    "응급의학과": 0.010,
}


def load_concepts() -> dict:
    reg = json.loads(REG.read_text(encoding="utf-8"))["concepts"]
    supp = json.loads(SUPP.read_text(encoding="utf-8")) if SUPP.exists() else {}
    out = {}
    for cid, c in reg.items():
        sp = str(c.get("specialty") or supp.get(cid) or "").strip()
        if not sp:
            continue
        out[cid] = {"concept": c, "specialty": sp,
                    "primary": sp.split("/")[0].strip()}
    return out


def concept_score(c: dict) -> int:
    """근거·감별이 풍부한 개념을 우선한다 (문항 방어력이 높다)."""
    edges = c.get("edges") if isinstance(c.get("edges"), dict) else {}
    s = sum(len(edges.get(k) or []) for k in
            ("differential_of", "treated_with", "diagnosed_by", "presents_with"))
    if (c.get("evidence") or {}).get("harrison"):
        s += 3
    s += min(len(c.get("aliases") or []), 5)
    return s


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=200, help="목표 개념 수")
    ap.add_argument("--out-prefix", default="text", help="출력 파일 접두어")
    ap.add_argument("--exclude", nargs="*", default=[],
                    help="이미 문항을 만든 풀 JSON — 그 개념들을 추가 제외")
    args = ap.parse_args()

    used = set()
    sel_path = GEN / "img_items_selected.json"
    if sel_path.exists():
        used = {it.get("disease_concept_id") for it in
                json.loads(sel_path.read_text(encoding="utf-8"))}
    for extra in args.exclude:
        p = GEN / extra
        if p.exists():
            for it in json.loads(p.read_text(encoding="utf-8")):
                used.add(it.get("concept") or it.get("disease_concept_id"))
    used.discard(None)
    used.discard("")
    print(f"이미 쓴 개념 {len(used)}개 제외")

    pool = load_concepts()
    by_dept = defaultdict(list)
    for cid, row in pool.items():
        if cid in used:
            continue
        by_dept[row["primary"]].append((concept_score(row["concept"]), cid))
    for d in by_dept:
        by_dept[d].sort(key=lambda x: (-x[0], x[1]))

    # 200문항(4세트×50)을 분과 가중치로 배분
    total = args.count
    wsum = sum(WEIGHTS.values())
    plan, assigned = {}, 0
    for dept, w in sorted(WEIGHTS.items(), key=lambda x: -x[1]):
        n = min(int(round(total * w / wsum)), len(by_dept.get(dept, [])))
        plan[dept] = n
        assigned += n
    # 반올림 잔여는 개념이 남은 분과에 순차 배정
    for dept in sorted(plan, key=lambda d: -WEIGHTS[d]):
        while assigned < total and plan[dept] < len(by_dept.get(dept, [])):
            plan[dept] += 1
            assigned += 1

    chosen = []
    for dept, n in plan.items():
        for _, cid in by_dept.get(dept, [])[:n]:
            chosen.append({"concept_id": cid, "department": dept,
                           "specialty": pool[cid]["specialty"]})
    print(f"블루프린트: {len(chosen)}개념 / 목표 {total}")
    print("  분과:", dict(Counter(c['department'] for c in chosen).most_common()))

    packs, ok, fail = {}, 0, 0
    for row in chosen:
        cid = row["concept_id"]
        try:
            g = build_generation_grounding(topic=cid)
        except Exception:
            fail += 1
            continue
        # 반환값은 {topic, match, pack, blocked, ...} 래퍼다. 실제 팩은 g["pack"].
        pack = (g or {}).get("pack") or {}
        if g.get("blocked") or not pack.get("disease_concept_id"):
            fail += 1
            continue
        small = condense(pack)
        small["department"] = row["department"]
        packs[cid] = small
        ok += 1
    print(f"grounding 팩: 성공 {ok} · 실패 {fail}")

    (GEN / f"{args.out_prefix}_blueprint.json").write_text(
        json.dumps(chosen, ensure_ascii=False, indent=1), encoding="utf-8")
    (GEN / f"{args.out_prefix}_grounding_packs.json").write_text(
        json.dumps(packs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[출력] {GEN}/{args.out_prefix}_blueprint.json · {args.out_prefix}_grounding_packs.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
