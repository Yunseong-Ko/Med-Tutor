#!/usr/bin/env python3
"""Apply Korean-topic disease recovery to qbank_relabeled.json (Step 3, merge + validate).

Reads:
  - the LLM recovery workflow output (task .output JSON; result.results = per-item recovery)
  - data_private/curriculum/recovery_deterministic.json  (zero-risk alias/title matches)
  - data_private/concept_registry.json                   (275 keys — the ONLY valid disease ids)
  - data_private/embedding/qbank_relabeled.json

Trust model: the model's self-reported registry hits are NOT trusted. Every disease_concept_id
is re-checked against the 275 registry keys in code. A claimed id that is not a key AND not in
proposed_ids is treated as a hallucinated hit and dropped (logged). Proposed new ids + dropped
non-registry ids become the growth queue for the next registry expansion.

Writes:
  data_private/embedding/qbank_relabeled.json            (updated in place: disease_concept_id filled)
  data_private/embedding/recovery_report.md
  data_private/embedding/recovery_growth_queue.csv       (proposed new disease ids to add next)
"""
from __future__ import annotations
import json
import re
import sys
import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
REGISTRY = DP / "concept_registry.json"
RELABELED = DP / "embedding" / "qbank_relabeled.json"
DET = DP / "curriculum" / "recovery_deterministic.json"
WORKLIST = DP / "curriculum" / "recovery_worklist.json"

OUT_REPORT = DP / "embedding" / "recovery_report.md"
OUT_GROWTH = DP / "embedding" / "recovery_growth_queue.csv"

PASS_DIR = DP / "curriculum"   # canonical recovery_pass*.json files (one per recovery workflow)


def load_all_llm_results() -> tuple[list, list]:
    """Merge results across all recovery passes (recovery_pass*.json). Later passes only
    cover items uncovered by earlier ones, so concatenation is conflict-free."""
    results, files = [], []
    for p in sorted(PASS_DIR.glob("recovery_pass*.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        r = obj.get("result", obj)
        rs = r.get("results", r if isinstance(r, list) else [])
        results += rs
        files.append(p.name)
    return results, files


def main() -> None:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))["concepts"]
    reg_keys = set(reg.keys())
    # alias index: normalized alias/id -> canonical id, so recovery variants (adhd -> attention_deficit_...)
    # and abbreviations remap onto the canonical seed instead of being lost.
    def _n(x: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(x).lower())
    alias_index = {}
    for cid, c in reg.items():
        alias_index.setdefault(_n(cid), cid)
        for al in c.get("aliases", []):
            alias_index.setdefault(_n(al), cid)
    relabeled = json.loads(RELABELED.read_text(encoding="utf-8"))["items"]
    det_items = json.loads(DET.read_text(encoding="utf-8"))["items"]
    worklist = {it["id"]: it for it in json.loads(WORKLIST.read_text(encoding="utf-8"))["items"]}
    llm_results, pass_files = load_all_llm_results()

    # deterministic recoveries (already registry-valid by construction)
    det_map = {d["id"]: [x for x in d["disease_concept_id"] if x in reg_keys] for d in det_items}

    # validate LLM results against the registry keys
    llm_map = {}
    growth = Counter()
    growth_ex = defaultdict(list)
    hallucinated = []  # claimed registry hit that is neither a key nor declared proposed
    remapped = 0
    for r in llm_results:
        rid = r.get("id")
        claimed = r.get("disease_concept_id") or []
        proposed = set(r.get("proposed_ids") or [])
        valid = []
        for c in claimed:
            if c in reg_keys:
                valid.append(c)
            elif _n(c) in alias_index:              # variant/abbrev -> canonical seed
                valid.append(alias_index[_n(c)])
                if c not in reg_keys:
                    remapped += 1
            elif c in proposed:                     # genuine new disease not yet a seed
                growth[c] += 1
                if len(growth_ex[c]) < 3:
                    growth_ex[c].append(r.get("topic") or worklist.get(rid, {}).get("topic", ""))
            else:
                hallucinated.append({"id": rid, "bad_id": c, "topic": r.get("topic")})
        for p in proposed:
            if p not in reg_keys and _n(p) not in alias_index and p not in claimed:
                growth[p] += 1
        valid = list(dict.fromkeys(valid))          # dedupe, preserve order
        if valid:
            llm_map[rid] = valid[:3]

    # idempotency guard: revert any prior recovery fills so re-runs re-derive cleanly
    # (English-join ids from build are preserved; only Korean-recovered ids are cleared)
    for item in relabeled:
        if item.get("disease_id_source") in ("deterministic_korean", "llm_korean_recovery"):
            item["disease_concept_id"] = []
            item["disease_id_source"] = None

    # merge into relabeled (fill only where the English join left it empty)
    filled_det = filled_llm = 0
    for item in relabeled:
        if item["disease_concept_id"]:
            item["disease_id_source"] = "english_concept_tags"
            continue
        if det_map.get(item["id"]):
            item["disease_concept_id"] = det_map[item["id"]]
            item["disease_id_source"] = "deterministic_korean"
            filled_det += 1
        elif llm_map.get(item["id"]):
            item["disease_concept_id"] = llm_map[item["id"]]
            item["disease_id_source"] = "llm_korean_recovery"
            filled_llm += 1
        else:
            item["disease_id_source"] = None
    RELABELED.write_text(json.dumps({"total": len(relabeled), "items": relabeled}, ensure_ascii=False, indent=2), encoding="utf-8")

    total = len(relabeled)
    with_id = sum(1 for i in relabeled if i["disease_concept_id"])
    by_src = Counter(i.get("disease_id_source") for i in relabeled)
    distinct_ids = {x for i in relabeled for x in i["disease_concept_id"]}

    # growth queue CSV
    rows = sorted(growth.items(), key=lambda kv: -kv[1])
    with OUT_GROWTH.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["proposed_disease_concept_id", "count", "example_topics"])
        for cid, n in rows:
            w.writerow([cid, n, "; ".join(growth_ex.get(cid, [])[:3])])

    lines = [
        "# Korean-topic Disease Recovery — Report (Step 3)",
        "",
        f"> LLM sources: {', '.join(pass_files)} · all outputs needs_review=true",
        "",
        "## Coverage progression",
        f"- English concept_tags join:  112/672 (16.7%)  [baseline]",
        f"- + deterministic Korean:      +{filled_det}",
        f"- + LLM Korean recovery:       +{filled_llm}",
        f"- **Final: {with_id}/{total} ({with_id/total*100:.1f}%) items with ≥1 disease_concept_id**",
        f"- Distinct registry ids used:  {len(distinct_ids)} / {len(reg_keys)}",
        "",
        "## disease_id_source breakdown",
    ]
    for src, n in by_src.most_common():
        lines.append(f"- {src}: {n}")
    lines += [
        "",
        "## Growth queue (proposed new disease ids not yet in the registry)",
        f"- {len(growth)} distinct proposed ids → {OUT_GROWTH.name} (rank by frequency).",
        f"- Top: {[c for c, _ in rows[:15]]}",
        "",
        "## Integrity",
        f"- Hallucinated registry-hits dropped (claimed as hit, not a key, not declared proposed): {len(hallucinated)}",
    ]
    if hallucinated[:8]:
        for h in hallucinated[:8]:
            lines.append(f"  - {h['id']}: '{h['bad_id']}' ({h['topic']})")
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("── Topic recovery applied ──")
    print(f"filled: deterministic +{filled_det} · llm +{filled_llm} · alias-remapped ids {remapped}")
    print(f"coverage: {with_id}/{total} ({with_id/total*100:.1f}%) · distinct ids {len(distinct_ids)}/{len(reg_keys)}")
    print(f"growth queue: {len(growth)} proposed ids -> {OUT_GROWTH.relative_to(ROOT)}")
    print(f"hallucinated dropped: {len(hallucinated)}")
    print(f"source breakdown: {dict(by_src)}")


if __name__ == "__main__":
    main()
