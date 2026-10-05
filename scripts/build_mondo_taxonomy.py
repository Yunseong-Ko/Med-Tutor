#!/usr/bin/env python3
"""Turn imported MONDO ancestor chains into a 2-level category taxonomy for the registry.

Each MONDO-matched node gets taxonomy = {parents[], primary_category, top_category}, giving the
flat disease registry an authoritative hierarchical backbone (standard MONDO categories).
Output: data_private/curriculum/mondo_taxonomy_map.json  (build applies it via apply_mondo_taxonomy).
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
OUT = DP / "curriculum" / "mondo_taxonomy_map.json"

# recognized MONDO top-level categories. Ordered so ANATOMICAL/SYSTEM categories win over
# the behavioural "neoplasm/cancer" bucket → heme neoplasms group under hematologic, etc.
TOP_CATEGORIES = [
    "hematologic disorder", "hematopoietic and lymphoid system disorder",
    "cardiovascular disorder", "cardiovascular system disorder", "vascular disorder",
    "nervous system disorder", "central nervous system disorder",
    "respiratory system disorder", "respiratory tract disorder",
    "gastrointestinal system disorder", "digestive system disorder",
    "endocrine system disorder", "immune system disorder",
    "urinary system disorder", "kidney disorder",
    "reproductive system disorder", "psychiatric disorder", "mental disorder",
    "musculoskeletal system disorder", "connective tissue disorder",
    "integumentary system disorder", "skin disorder",
    "metabolic disease", "nutritional disorder", "inborn errors of metabolism",
    "infectious disease", "disorder of visual system", "disorder of ear",
    "cancer", "neoplasm",   # behavioural fallback if no system category present
]
GENERIC = {"disease", "disease or disorder", "human disease", "disease by anatomical system",
           "disease of anatomical entity", "syndromic disease", "acquired disease"}


def norm(s: str) -> str:
    return (s or "").strip().lower()


def pick_top(ancestor_labels: list) -> str | None:
    labset = [norm(a) for a in ancestor_labels]
    for cat in TOP_CATEGORIES:                    # first (most-general) recognized category present
        if cat in labset:
            return cat
    return None


def main(task_out: str) -> None:
    res = json.loads(Path(task_out).read_text(encoding="utf-8"))["result"]["results"]
    tax = {}
    top_counts = Counter()
    for r in res:
        anc = [a for a in (r.get("ancestors") or []) if norm(a["label"]) not in GENERIC]
        if not anc:
            continue
        labels = [a["label"] for a in anc]
        primary = labels[0]                        # most-specific meaningful parent
        top = pick_top(labels)
        tax[r["id"]] = {
            "parents": [{"mondo_id": a["mondo_id"], "label": a["label"]} for a in anc[:6]],
            "primary_category": primary,
            "top_category": top,
        }
        if top:
            top_counts[top] += 1
    OUT.write_text(json.dumps({"total": len(tax), "map": tax}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"taxonomy: {len(tax)} nodes with MONDO hierarchy  ->  {OUT.relative_to(ROOT)}")
    print(f"top-category distribution: {dict(top_counts.most_common())}")


if __name__ == "__main__":
    main(sys.argv[1])
