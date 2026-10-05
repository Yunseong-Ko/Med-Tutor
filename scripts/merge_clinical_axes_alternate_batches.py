#!/usr/bin/env python3
"""Validate and merge authority-scoped non-Harrison clinical-axis batches."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.audit_clinical_axes_expansion import audit_document
    from scripts.merge_clinical_axes_batches import validate_axis
except ModuleNotFoundError:
    from audit_clinical_axes_expansion import audit_document
    from merge_clinical_axes_batches import validate_axis


ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "data_private" / "curriculum"
BATCH_DIR = CURRICULUM / "clinical_axes_alternate_batches"
WORKLIST = CURRICULUM / "clinical_axes_worklist.json"
OUT = CURRICULUM / "clinical_axes_map.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect() -> tuple[dict, list[str]]:
    worklist = load(WORKLIST)
    work = {row["id"]: row for row in worklist.get("items", [])}
    collected: dict[str, dict] = {}
    errors: list[str] = []
    for path in sorted(BATCH_DIR.glob("*.json")):
        data = load(path)
        axes = data.get("axes") or {}
        refs = data.get("source_refs") or {}
        if set(axes) != set(refs):
            errors.append(f"{path.name}: source_refs/axes mismatch")
        report = audit_document(data, source=str(path.relative_to(ROOT)), worklist_data=worklist)
        for finding in report.get("issues", []):
            if finding.get("blocking"):
                errors.append(
                    f"{path.name}: quality gate {finding.get('code')} at "
                    f"{finding.get('id') or ''}.{finding.get('path') or ''}"
                )
        for cid, axis in axes.items():
            if cid in collected:
                errors.append(f"duplicate alternate batch id: {cid}")
                continue
            if cid not in work:
                errors.append(f"{cid}: absent from worklist")
            elif (work[cid].get("harrison") or {}).get("chapter") is not None:
                errors.append(f"{cid}: use the Harrison batch path when Harrison grounding exists")
            if axis.get("evidence_refs") != refs.get(cid):
                errors.append(f"{cid}: embedded evidence_refs differ from source_refs")
            errors.extend(validate_axis(cid, axis))
            collected[cid] = axis
    if not collected:
        errors.append("no alternate-source batch records found")
    return collected, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    batch_axes, errors = collect()
    current = load(OUT)
    axes = current.get("axes", {})
    if args.check:
        for cid, axis in batch_axes.items():
            if axes.get(cid) != axis:
                errors.append(f"{cid}: merged output missing or differs from alternate batch")
    else:
        for cid, axis in batch_axes.items():
            if cid in axes and axes[cid] != axis:
                errors.append(f"{cid}: refusing to overwrite a differing existing axis")
    if errors:
        raise SystemExit("\n".join(errors))

    added = sum(cid not in axes for cid in batch_axes)
    if args.apply:
        axes.update(batch_axes)
        current["axes"] = dict(sorted(axes.items()))
        current["total"] = len(axes)
        OUT.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"mode={'apply' if args.apply else 'check'} alternate_axes={len(batch_axes)} added={added} total={len(axes)} errors=0")


if __name__ == "__main__":
    main()
