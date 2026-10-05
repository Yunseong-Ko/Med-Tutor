#!/usr/bin/env python3
"""워크플로가 저작한 한글 별칭을 검증 후 curriculum/alias_supplement_kr.json에 병합.

검증(결정론):
  1. id가 레지스트리에 실존
  2. 별칭 정규화 후 **개념 간 충돌 없음** — 같은 별칭이 두 개념에 붙으면 exact 매칭이
     ambiguous로 떨어지므로, 충돌 별칭은 양쪽 모두 폐기하고 로그.
  3. 기존 레지스트리 별칭과의 충돌도 동일 처리(기존 소유 개념 우선).
사용: python3 scripts/merge_kr_aliases.py <authored.json>
      authored.json = [{"id": ..., "kr": [...]}, ...]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generation_grounding import (  # noqa: E402
    ALIAS_SUPPLEMENT_PATH, load_registry, concept_terms, normalized_term,
)


def main() -> int:
    authored = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if isinstance(authored, dict):
        authored = authored.get("aliases", [])
    concepts, _ = load_registry()   # supplement 반영 전 기준으로도 무방(추가만 하므로)

    # 기존 소유권: 정규화 별칭 → 개념ID
    owner = {}
    for cid, c in concepts.items():
        for t in concept_terms(cid, c):
            owner.setdefault(normalized_term(t), cid)

    # 신규 별칭 수집 + 개념 간 충돌 탐지
    proposed = defaultdict(set)
    claims = defaultdict(set)   # 정규화 별칭 → 주장 개념들
    unknown = []
    for row in authored:
        cid = str(row.get("id", ""))
        if cid not in concepts:
            unknown.append(cid)
            continue
        for a in row.get("kr", []):
            a = str(a).strip()
            if not a:
                continue
            n = normalized_term(a)
            if not n:
                continue
            own = owner.get(n)
            if own and own != cid:
                claims[n].add(own); claims[n].add(cid)
                continue                      # 기존 소유 개념과 충돌 → 폐기
            claims[n].add(cid)
            proposed[cid].add(a)

    # 신규 별칭끼리의 교차 충돌 제거
    dropped = []
    for n, cids in claims.items():
        if len(cids) > 1:
            for cid in cids:
                for a in list(proposed.get(cid, ())):
                    if normalized_term(a) == n:
                        proposed[cid].discard(a)
                        dropped.append((a, sorted(cids)))

    sup_path = ALIAS_SUPPLEMENT_PATH
    sup = json.loads(sup_path.read_text(encoding="utf-8")) if sup_path.exists() else {}
    added_c, added_a = 0, 0
    for cid, aliases in proposed.items():
        if not aliases:
            continue
        cur = set(map(str, sup.get(cid, [])))
        new = sorted(aliases - cur)
        if new:
            sup[cid] = sorted(cur | aliases)
            added_c += 1
            added_a += len(new)
    sup_path.write_text(json.dumps(sup, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"저작 {len(authored)}행 → 병합 개념 {added_c} · 별칭 {added_a}")
    if unknown:
        print(f"  레지스트리에 없는 id {len(unknown)}: {unknown[:8]}")
    if dropped:
        uniq = {a: c for a, c in dropped}
        print(f"  충돌 폐기 {len(uniq)}: " +
              " · ".join(f"{a}({'/'.join(c)})" for a, c in list(uniq.items())[:8]))
    print(f"[병합] {sup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
