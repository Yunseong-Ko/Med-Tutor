#!/usr/bin/env python3
"""Assemble an ontology evidence pack per target disease for ontology-grounded item generation.

The point of the demo: DISTRACTORS come from the ontology, not the LLM's imagination.
For a target disease we pull three distractor sources and label each choice's provenance:
  - differential_of edges          (explicit pedagogical differentials)
  - is_a siblings                  (diseases sharing a MONDO is_a parent)
  - shared-finding bridges         (diseases co-presenting a finding, from distractor_bridges)
plus the stem material: presents_with (cues), diagnosed_by (tests), treated_with, causes.

Auto-selects target diseases that have enough diagnostic graph signal OR authored
clinical axes for pathophysiology/risk/prognosis/treatment/epidemiology items.
Output: data_private/curriculum/item_evidence_packs.json
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
REG = DP / "concept_registry.json"
BRIDGES = DP / "curriculum" / "distractor_bridges.json"
OUT = DP / "curriculum" / "item_evidence_packs.json"


def ids(edges, key):
    return [e["id"] for e in (edges.get(key) or [])]


def ko_of(c):
    for a in c.get("aliases", []):
        if any("가" <= ch <= "힣" for ch in a):
            return a
    return c["disease_concept_id"]


def main(argv):
    reg = json.loads(REG.read_text(encoding="utf-8"))["concepts"]
    bridges = json.loads(BRIDGES.read_text(encoding="utf-8"))["bridges"]
    # disease -> shared-finding co-presenters
    copres = defaultdict(set)
    for b in bridges:
        ds = b["co_presenting_diseases"]
        for d in ds:
            copres[d].update(x for x in ds if x != d)
    # is_a parent -> members (for siblings)
    parent_members = defaultdict(set)
    for cid, c in reg.items():
        for p in c.get("is_a", []):
            parent_members[p["id"]].add(cid)

    def siblings(cid):
        c = reg[cid]; sib = set()
        for p in c.get("is_a", [])[:3]:            # nearest few parents only (avoid over-general)
            sib.update(parent_members[p["id"]])
        sib.discard(cid)
        return sib

    targets = argv or None
    packs = []
    for cid, c in reg.items():
        if targets and cid not in targets:
            continue
        e = c.get("edges") or {}
        dof = [x for x in ids(e, "differential_of") if x in reg]
        pres = ids(e, "presents_with")
        dx = ids(e, "diagnosed_by")
        sib = [x for x in siblings(cid) if x in reg]
        cop = [x for x in copres.get(cid, set()) if x in reg]
        pool = []
        prov = {}
        for x in dof:
            if x not in prov: prov[x] = "differential_of"; pool.append(x)
        for x in cop:
            if x not in prov: prov[x] = "shared_finding_bridge"; pool.append(x)
        for x in sib:
            if x not in prov: prov[x] = "is_a_sibling"; pool.append(x)
        # Diagnostic items need graph cues + distractors. Axis-based items can be
        # generated from clinical_axes and indicated/contraindicated edges even
        # when P2 diagnostic edges have not yet been authored.
        diagnostic_signal = (len(pool) >= 3) and (len(pres) + len(dx) >= 2)
        axis_signal = bool(c.get("clinical_axes"))
        signal = diagnostic_signal or axis_signal
        if targets or signal:
            h = (c.get("evidence") or {}).get("harrison") or {}
            x = (c.get("evidence") or {}).get("ontology_xref") or {}
            packs.append({
                "target": cid, "target_ko": ko_of(c), "node_type": c.get("node_type"),
                "specialty": c.get("specialty"), "top_category": (c.get("taxonomy") or {}).get("top_category"),
                "harrison": (f"Ch{h['chapter']} p{h['page']} ({h['title']})" if h.get("chapter") else None),
                "mondo_id": x.get("mondo_id"),
                "presents_with": pres, "diagnosed_by": dx,
                "treated_with": ids(e, "treated_with"),
                "causes": {"due_to": ids(e, "due_to"), "predisposes": ids(e, "predisposes"),
                           "causative_agent": ids(e, "causative_agent")},
                "distractor_pool": [{"id": p, "ko": ko_of(reg[p]), "provenance": prov[p]} for p in pool[:8]],
                "clinical_axes": c.get("clinical_axes"),   # pathophysiology/risk_factors/prognosis/treatment/epidemiology
                "indicated_for": ids(e, "indicated_for"),
                "contraindicated_for": ids(e, "contraindicated_for"),
            })
    packs.sort(key=lambda p: -len(p["distractor_pool"]))
    OUT.write_text(json.dumps({"total": len(packs), "packs": packs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"evidence packs: {len(packs)}  ->  {OUT.relative_to(ROOT)}")
    for p in packs[:12]:
        print(f"  {p['target']:34} pool={len(p['distractor_pool'])} pres={len(p['presents_with'])} dx={len(p['diagnosed_by'])}")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
