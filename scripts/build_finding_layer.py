#!/usr/bin/env python3
"""Assemble the HPO-aligned finding layer + shared-finding distractor bridges.

Findings become first-class typed nodes (id, hpo_id, body_system, presented_by[diseases]).
A finding shared by >=2 diseases is a DISTRACTOR BRIDGE: those diseases are mutual differentials
via the shared presentation — the metapath the reference feedback said the layer exists to enable.

Outputs (data_private/, needs_review):
  curriculum/finding_registry.json      first-class finding nodes (HPO-xref, body-system grouped)
  curriculum/distractor_bridges.json    shared findings -> co-presenting disease sets
"""
from __future__ import annotations
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
WORK = DP / "curriculum" / "finding_hpo_worklist.json"
OUT_FIND = DP / "curriculum" / "finding_registry.json"
OUT_BRIDGE = DP / "curriculum" / "distractor_bridges.json"


def main(task_out: str) -> None:
    hpo = {r["id"]: r for r in json.loads(Path(task_out).read_text(encoding="utf-8"))["result"]["results"]}
    work = {w["id"]: w for w in json.loads(WORK.read_text(encoding="utf-8"))["items"]}

    findings, by_system = {}, Counter()
    for fid, w in work.items():
        h = hpo.get(fid, {})
        bs = h.get("body_system", "other")
        findings[fid] = {
            "finding_id": fid, "node_type": "finding",
            "hpo_id": h.get("hpo_id"), "hpo_label": h.get("hpo_label", ""),
            "body_system": bs,
            "presented_by": w["presented_by"], "n_diseases": w["n_diseases"],
            "source": "presents_with (migrated from diagnosed_by)", "needs_review": True,
        }
        by_system[bs] += 1

    # distractor bridges: findings co-presented by >=2 diseases
    bridges = []
    for fid, f in findings.items():
        if f["n_diseases"] >= 2:
            bridges.append({
                "finding": fid, "hpo_id": f["hpo_id"], "body_system": f["body_system"],
                "co_presenting_diseases": f["presented_by"],
                "note": "these diseases are mutual differentials via the shared presentation → distractor set",
            })
    bridges.sort(key=lambda b: -len(b["co_presenting_diseases"]))

    OUT_FIND.write_text(json.dumps({"total": len(findings), "by_system": dict(by_system),
                                    "findings": list(findings.values())}, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_BRIDGE.write_text(json.dumps({"total": len(bridges), "bridges": bridges}, ensure_ascii=False, indent=1), encoding="utf-8")

    hpo_matched = sum(1 for f in findings.values() if f["hpo_id"])
    print("── HPO finding layer ──")
    print(f"finding nodes: {len(findings)}  · HPO-matched {hpo_matched} ({hpo_matched/max(1,len(findings))*100:.0f}%)")
    print(f"by body_system: {dict(by_system.most_common())}")
    print(f"distractor bridges (shared findings): {len(bridges)}")
    for b in bridges[:8]:
        print(f"  {b['finding']} [{b['body_system']}] -> {b['co_presenting_diseases']}")


if __name__ == "__main__":
    main(sys.argv[1])
