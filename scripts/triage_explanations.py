#!/usr/bin/env python3
"""해설 품질 트리아지 — 세트별로 재작성이 필요한 문항을 분류해 워크리스트를 만든다.

Tier1: 통합 해설 약함/없음
Tier2: 선지별 해설이 모든 선지를 못 덮음
Tier3: 근거(evidence) 없음
label:  concept_tags 없음(검색·근거의 전제)

출력: data_private/course_exams/explanation_triage.json (세트별 카운트 + 문항 id 목록)
"""

import json
import glob
from pathlib import Path

EXTRACT_DIR = Path("data_private/course_exams/extracted")
OUT = Path("data_private/course_exams/explanation_triage.json")


def is_weak(text: str) -> bool:
    t = (text or "").strip()
    return (not t) or len(t) < 40 or any(
        k in t for k in ("작성 필요", "검토 필요", "미추출")
    )


def choice_keys(q: dict):
    c = q.get("choices") or {}
    if isinstance(c, dict):
        return list(c.keys())
    if isinstance(c, list):
        return [str(i) for i in range(len(c))]
    return []


def full_choice_expl(q: dict) -> bool:
    ce = q.get("choice_explanations") or {}
    keys = choice_keys(q)
    if not ce or not keys:
        return False
    covered = sum(
        1 for k in keys
        if isinstance(ce.get(k), dict) and (ce[k].get("rationale") or ce[k].get("explanation"))
    )
    return covered >= len(keys)


def main():
    report = {"generated_from": str(EXTRACT_DIR), "sets": [], "totals": {}}
    totals = {"questions": 0, "tier1": 0, "tier2": 0, "tier3": 0, "unlabeled": 0}
    for f in sorted(glob.glob(str(EXTRACT_DIR / "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        qs = [q for q in d.get("questions", []) if q.get("stem") and choice_keys(q)]
        entry = {"file": Path(f).name, "questions": len(qs),
                 "tier1_weak_expl": [], "tier2_no_choice_expl": [],
                 "tier3_no_evidence": [], "unlabeled": []}
        for q in qs:
            qid = q.get("question_id") or str(q.get("question_number"))
            L = q.get("labels") or {}
            if is_weak(q.get("explanation")) and is_weak(q.get("answer_rationale")):
                entry["tier1_weak_expl"].append(qid)
            if not full_choice_expl(q):
                entry["tier2_no_choice_expl"].append(qid)
            if not q.get("evidence"):
                entry["tier3_no_evidence"].append(qid)
            if not (L.get("concept_tags")):
                entry["unlabeled"].append(qid)
        totals["questions"] += len(qs)
        totals["tier1"] += len(entry["tier1_weak_expl"])
        totals["tier2"] += len(entry["tier2_no_choice_expl"])
        totals["tier3"] += len(entry["tier3_no_evidence"])
        totals["unlabeled"] += len(entry["unlabeled"])
        report["sets"].append(entry)
    report["totals"] = totals
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {OUT}")
    print(f"  문항 {totals['questions']} | Tier1(해설약함) {totals['tier1']} | "
          f"Tier2(선지해설없음) {totals['tier2']} | Tier3(근거없음) {totals['tier3']} | "
          f"라벨없음 {totals['unlabeled']}")
    print("  세트별 Tier1(재작성 우선):")
    for s in sorted(report["sets"], key=lambda x: -len(x["tier1_weak_expl"]))[:8]:
        print(f"    {len(s['tier1_weak_expl']):>3}/{s['questions']:<3} {s['file'][:46]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
