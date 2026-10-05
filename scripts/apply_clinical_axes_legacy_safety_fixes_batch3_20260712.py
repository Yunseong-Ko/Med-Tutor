#!/usr/bin/env python3
"""Replace unsupported precise epidemiology ratios with reviewable qualitative text."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data_private" / "curriculum" / "clinical_axes_map.json"
REPLACEMENTS = {
    ("chronic_urticaria", "sex"): ("Female predominance (~2:1)", "More often reported in females"),
    ("conversion_disorder", "sex"): ("Female predominance (roughly 2-3:1)", "More often reported in females"),
    ("croup", "sex"): ("Slight male predominance (~1.4:1)", "Slight male predominance"),
    ("neonatal_alloimmune_thrombocytopenia", "population"): (
        "HPA-1a-negative mothers (~2% of the Caucasian population); Caucasian predominance for HPA-1a",
        "Pregnancies in which the mother lacks a platelet antigen carried by the fetus; the relevant antigen distribution varies by ancestry",
    ),
    ("persistent_depressive_disorder", "sex"): ("Female predominance (roughly 2:1)", "More often reported in females"),
    ("projectile_vomiting", "sex"): ("Male predominance (pyloric stenosis ~4:1)", "Male predominance when the cause is infantile hypertrophic pyloric stenosis"),
    ("restless_legs_syndrome", "sex"): ("Female predominance (roughly 2:1)", "More often reported in females"),
    ("transient_synovitis", "sex"): ("Male predominance (roughly 2:1)", "More often reported in boys"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    data = json.loads(PATH.read_text(encoding="utf-8"))
    changed: list[str] = []
    conflicts: list[str] = []
    for (cid, field), (old, new) in REPLACEMENTS.items():
        current = data["axes"][cid]["epidemiology"].get(field)
        if current == old:
            data["axes"][cid]["epidemiology"][field] = new
            changed.append(f"{cid}.epidemiology.{field}")
        elif current != new:
            conflicts.append(f"{cid}.epidemiology.{field}")
    if conflicts:
        raise SystemExit("unexpected values: " + ", ".join(conflicts))
    if args.apply and changed:
        PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": "apply" if args.apply else "check", "changed": changed, "conflicts": conflicts}))


if __name__ == "__main__":
    main()
