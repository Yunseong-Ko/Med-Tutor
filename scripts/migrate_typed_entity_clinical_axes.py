#!/usr/bin/env python3
"""Remove invalid disease-axis records after preserving them in typed quarantine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "data_private" / "curriculum"
AXES_MAP = CURRICULUM / "clinical_axes_map.json"
QUARANTINE = CURRICULUM / "typed_entity_clinical_axes_quarantine_20260712.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    data = json.loads(AXES_MAP.read_text(encoding="utf-8"))
    quarantine = json.loads(QUARANTINE.read_text(encoding="utf-8"))
    records = quarantine.get("quarantined_axes") or {}
    axes = data.get("axes") or {}
    removed: list[str] = []
    conflicts: list[str] = []
    for cid, record in records.items():
        original = record.get("original_axes")
        current = axes.get(cid)
        if current is None:
            continue
        if current != original:
            conflicts.append(cid)
            continue
        del axes[cid]
        removed.append(cid)
    if conflicts:
        raise SystemExit("quarantine/source mismatch: " + ", ".join(sorted(conflicts)))
    if args.apply and removed:
        data["axes"] = dict(sorted(axes.items()))
        data["total"] = len(axes)
        AXES_MAP.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "check",
                "quarantined_records": len(records),
                "removed": sorted(removed),
                "remaining_axes": len(axes),
                "medical_approval": False,
            }
        )
    )


if __name__ == "__main__":
    main()
