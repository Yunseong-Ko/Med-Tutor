#!/usr/bin/env python3
"""Build P2 concept-node authoring packets: group qbank items by disease_concept_id,
attach Harrison ref + rich item fields (diagnosis, differential_dx, finding_tags,
misconceptions) so a P2 agent can author edges grounded in real items.

Output: data_private/curriculum/p2_inputs.json  {concepts:[{disease_concept_id, in_registry,
        harrison_ref, node_type, questions:[...]}]}  sorted by item count desc.
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
reg = json.loads((DP / "concept_registry.json").read_text(encoding="utf-8"))["concepts"]
rel = json.loads((DP / "embedding" / "qbank_relabeled.json").read_text(encoding="utf-8"))["items"]
qb = {it["id"]: it for it in json.loads((DP / "embedding" / "consolidated_qbank.json").read_text(encoding="utf-8"))["items"]}
reg_keys = set(reg.keys())

groups = defaultdict(list)
for r in rel:
    for cid in r["disease_concept_id"]:
        groups[cid].append(r["id"])

packets = []
for cid, item_ids in groups.items():
    c = reg.get(cid, {})
    h = (c.get("evidence") or {}).get("harrison") or {}
    qs = []
    for iid in item_ids:
        it = qb.get(iid, {})
        qs.append({
            "question_number": it.get("question_number"),
            "topic": it.get("topic"), "subtopic": it.get("subtopic"),
            "diagnosis": it.get("diagnosis"),
            "differential_dx": it.get("differential_dx"),
            "finding_tags": next((rr["finding_tags"] for rr in rel if rr["id"] == iid), []),
            "misconceptions": it.get("misconceptions"),
            "assessment_domain": next((rr["assessment_domain"] for rr in rel if rr["id"] == iid), None),
        })
    existing_edges = c.get("edges") or {}
    has_edges = any((existing_edges.get(k) or []) for k in ("differential_of", "caused_by", "treated_with", "diagnosed_by"))
    packets.append({
        "disease_concept_id": cid,
        "in_registry": cid in reg_keys,
        "has_edges": has_edges,
        "node_type": c.get("node_type", "disease"),
        "harrison_ref": (
            {"chapter": h.get("chapter"), "title": h.get("title"), "page": h.get("page"), "part": h.get("part")}
            if h.get("chapter") else None
        ),
        "aliases": c.get("aliases", []),
        "n_items": len(item_ids),
        "questions": qs,
    })

packets.sort(key=lambda p: -p["n_items"])
out = DP / "curriculum" / "p2_inputs.json"
out.write_text(json.dumps({"total": len(packets), "concepts": packets}, ensure_ascii=False, indent=1), encoding="utf-8")

hubs2 = sum(1 for p in packets if p["n_items"] >= 2)
hubs3 = sum(1 for p in packets if p["n_items"] >= 3)
print(f"P2 packets: {len(packets)} covered concepts -> {out.relative_to(ROOT)}")
print(f"  hubs >=3 items: {hubs3} · >=2 items: {hubs2} · ==1 item: {len(packets)-hubs2}")
print("  top 15 by item count:")
for p in packets[:15]:
    print(f"    {p['n_items']:2d}  {p['disease_concept_id']}")
