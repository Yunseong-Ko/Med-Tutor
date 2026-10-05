#!/usr/bin/env python3
"""PNU 블루프린트의 CP 맥락/질환 → 온톨로지 개념 풀 매칭 + 커버리지 리포트.

각 CP의 질환 목록을 concept_registry에 매칭해 CP별 출제 가능 개념 풀을 만든다.
미매칭 질환은 레지스트리 확장 후보 목록으로 뽑는다 — 이것이 학교 특화의 핵심 갭 지도다.

출력: data_private/curriculum/pnu_cp_concept_pools.json
      data_private/curriculum/pnu_cp_coverage_report.md
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generation_grounding import load_registry, match_topic_to_concept  # noqa: E402

BP = Path("data_private/curriculum/pnu_pma_blueprint.json")
POOLS = Path("data_private/curriculum/pnu_cp_concept_pools.json")
REPORT = Path("data_private/curriculum/pnu_cp_coverage_report.md")

# 질환 목록 파편 정리: 붙임3의 셀이 "소아 학대: 만성골절, ..." 처럼 콜론 하위구조를 가짐
def clean_terms(contexts: list) -> list:
    out = []
    for c in contexts:
        c = re.sub(r"^[^:：]*[:：]", "", c).strip()      # "소아 학대:" 접두 제거
        c = re.sub(r"[()（）]", " ", c).strip()
        c = re.sub(r"\s+", " ", c)
        if 2 <= len(c) <= 30 and not c.isdigit():
            out.append(c)
    return list(dict.fromkeys(out))


def main() -> int:
    bp = json.loads(BP.read_text(encoding="utf-8"))
    concepts, _meta = load_registry()
    # 확장 레이어(신규 개념 보강, needs_review) — backbone은 하나, 여기서 매칭 대상에만 병합
    exp_p = Path("data_private/curriculum/pnu_expansion_concepts.json")
    n_exp = 0
    if exp_p.exists():
        exp = json.loads(exp_p.read_text(encoding="utf-8"))["concepts"]
        for cid, e in exp.items():
            if cid not in concepts:
                concepts[cid] = {"aliases": e.get("aliases") or [],
                                 "specialty": e.get("specialty") or "",
                                 "_expansion": True}
                n_exp += 1
    print(f"레지스트리 {len(concepts)-n_exp} + 확장 {n_exp} = 매칭 대상 {len(concepts)}개")
    pools, st = {}, Counter()
    unmatched_all = Counter()
    for cp_no, cp in bp["cps"].items():
        terms = clean_terms(cp["contexts"])
        matched, unmatched = [], []
        for t in terms:
            st["terms"] += 1
            try:
                m = match_topic_to_concept(t, concepts)
            except Exception:
                m = None
            cid = (m or {}).get("disease_concept_id") if isinstance(m, dict) else None
            status = (m or {}).get("status") if isinstance(m, dict) else None
            if cid and status in (None, "matched"):
                matched.append({"term": t, "concept_id": cid,
                                "method": (m or {}).get("match_method", ""),
                                "layer": "expansion" if concepts.get(cid, {}).get("_expansion") else "registry"})
                st["matched"] += 1
            else:
                unmatched.append(t)
                unmatched_all[t] += 1
        pools[cp_no] = {
            "name": cp["name"],
            "concepts": matched,
            "unmatched_terms": unmatched,
            "core_outcomes": cp["core_outcomes"],
            "specific_outcomes": cp["specific_outcomes"],
        }
        st["cps"] += 1
        if not matched:
            st["cp_zero"] += 1

    POOLS.write_text(json.dumps({"schema": "pnu_cp_concept_pools.v1", "pools": pools},
                                ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# PNU CP → 온톨로지 커버리지 리포트", ""]
    lines.append(f"- CP {st['cps']}개 · 질환 용어 {st['terms']}개 · 매칭 {st['matched']} "
                 f"({st['matched']*100//max(1,st['terms'])}%) · 개념 0개 CP: {st['cp_zero']}개")
    lines.append("")
    lines.append("## 개념 풀이 빈 CP (레지스트리 확장 최우선)")
    for cp_no, p in pools.items():
        if not p["concepts"]:
            lines.append(f"- CP{cp_no} {p['name']}: {', '.join(p['unmatched_terms'][:8])}")
    lines.append("")
    lines.append("## 미매칭 질환 상위 40 (레지스트리 확장 후보)")
    for t, n in unmatched_all.most_common(40):
        lines.append(f"- {t} ({n}회)")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"CP {st['cps']} · 용어 {st['terms']} · 매칭 {st['matched']} ({st['matched']*100//max(1,st['terms'])}%) · 빈 CP {st['cp_zero']}")
    print(f"[풀] {POOLS}\n[리포트] {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
