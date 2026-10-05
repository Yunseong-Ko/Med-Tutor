#!/usr/bin/env python3
"""Extract the ontology's bridge/resource layer from P2 edges.

The disease graph only shows disease↔disease edges. But P2 authored ~3700 edges to
out-of-registry endpoints (tests, drugs, causes) — the CONTENT of questions. Endpoints
shared by >=2 diseases are BRIDGES: promoting them to typed resource nodes turns the graph
into a disease↔finding/test/drug/cause knowledge graph (useful for distractor generation).

Also surfaces differential_of endpoints that are themselves diseases not yet in the registry
= wave-4 disease candidates.

Deterministic. Outputs (data_private/, needs_review):
  curriculum/bridge_layer.json        resource bridge nodes (test/finding/treatment/cause)
  curriculum/wave4_disease_candidates.json  differential bridges that look like diseases
"""
from __future__ import annotations
import json
import re
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
REGISTRY = DP / "concept_registry.json"
OUT_BRIDGE = DP / "curriculum" / "bridge_layer.json"
OUT_WAVE4 = DP / "curriculum" / "wave4_disease_candidates.json"

# generic, non-specific endpoints that make poor nodes (process/placeholder verbs)
GENERIC = {
    "clinical_diagnosis", "clinical_examination", "physical_examination", "history_taking",
    "observation", "supportive_care", "conservative_management", "symptomatic_treatment",
    "watchful_waiting", "reassurance", "counseling", "lifestyle_modification", "monitoring",
    "follow_up", "referral", "hospitalization", "medication", "medical_therapy", "surgery",
    "surgical_management", "surgical_resection", "supportive_treatment", "conservative_treatment",
    "laboratory_tests", "imaging", "biopsy", "blood_test", "screening", "prevention",
    "patient_education", "hydration", "rest", "analgesia", "pain_management",
}
EDGE_TO_RES = {
    "diagnosed_by": "test_or_finding",
    "treated_with": "treatment_or_drug",
    "caused_by": "cause_or_risk_factor",
    "differential_of": "differential",
}


def main() -> None:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))["concepts"]
    reg_keys = set(reg)
    endp = defaultdict(lambda: {"diseases": set(), "types": Counter()})
    for cid, c in reg.items():
        for et, arr in (c.get("edges") or {}).items():
            for e in (arr or []):
                if e.get("in_registry"):
                    continue
                eid = e["id"]
                endp[eid]["diseases"].add(cid)
                endp[eid]["types"][et] += 1

    bridges, wave4 = [], []
    for eid, v in endp.items():
        deg = len(v["diseases"])
        if deg < 2 or eid in GENERIC or eid in reg_keys:
            continue
        dom_edge = v["types"].most_common(1)[0][0]
        res_type = EDGE_TO_RES.get(dom_edge, "other")
        rec = {
            "id": eid, "resource_type": res_type, "dominant_edge": dom_edge,
            "degree": deg, "diseases": sorted(v["diseases"]),
            "edge_types": dict(v["types"]), "needs_review": True,
        }
        # differential_of endpoints that look like a disease -> wave-4 disease candidate
        if res_type == "differential" and deg >= 2:
            wave4.append({"id": eid, "degree": deg, "connected_diseases": sorted(v["diseases"])[:6]})
        else:
            bridges.append(rec)

    bridges.sort(key=lambda x: -x["degree"])
    wave4.sort(key=lambda x: -x["degree"])
    OUT_BRIDGE.write_text(json.dumps({"total": len(bridges), "bridges": bridges}, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_WAVE4.write_text(json.dumps({"total": len(wave4), "candidates": wave4}, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter as C
    print("── Bridge/resource layer ──")
    print(f"bridge resource nodes (>=2 diseases, non-generic): {len(bridges)}")
    print(f"  by type: {dict(C(b['resource_type'] for b in bridges))}")
    print(f"  degree>=5: {sum(1 for b in bridges if b['degree']>=5)} · >=3: {sum(1 for b in bridges if b['degree']>=3)}")
    print(f"wave-4 disease candidates (differential bridges not in registry): {len(wave4)}")
    print(f"  -> {OUT_BRIDGE.relative_to(ROOT)} · {OUT_WAVE4.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
