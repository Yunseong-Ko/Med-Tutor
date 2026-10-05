#!/usr/bin/env python3
"""Validate and deterministically merge reviewed clinical-axis draft batches."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from scripts.audit_clinical_axes_expansion import audit_document
except ModuleNotFoundError:  # direct execution from scripts/
    from audit_clinical_axes_expansion import audit_document


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private" / "curriculum"
BATCH_DIR = DP / "clinical_axes_batches"
WORKLIST = DP / "clinical_axes_worklist.json"
OUT = DP / "clinical_axes_map.json"

REQUIRED_AXES = ("pathophysiology", "risk_factors", "prognosis", "treatment", "epidemiology")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_axis(cid: str, axis: dict) -> list[str]:
    errors = []
    if axis.get("id") != cid:
        errors.append(f"{cid}: id field mismatch")
    if axis.get("needs_review") is not True:
        errors.append(f"{cid}: needs_review must be true")
    for key in REQUIRED_AXES:
        if key not in axis or axis[key] in (None, [], {}):
            errors.append(f"{cid}: missing/non-populated {key}")
    path = axis.get("pathophysiology") or {}
    if not isinstance(path.get("summary"), str) or not path.get("key_steps"):
        errors.append(f"{cid}: invalid pathophysiology schema")
    prog = axis.get("prognosis") or {}
    if not isinstance(prog.get("factors"), list) or "staging_or_grading" not in prog or not prog.get("natural_history"):
        errors.append(f"{cid}: invalid prognosis schema")
    treatment = axis.get("treatment") or {}
    if not treatment.get("principles") or not isinstance(treatment.get("indicated_for"), list) or not isinstance(treatment.get("contraindicated_for"), list):
        errors.append(f"{cid}: invalid treatment schema")
    epi = axis.get("epidemiology") or {}
    for key in ("age", "sex", "population", "frequency"):
        if not isinstance(epi.get(key), str) or not epi[key].strip():
            errors.append(f"{cid}: invalid epidemiology.{key}")
    # Exact rates/percentages in auto-authored epidemiology are prohibited.
    epi_text = " ".join(str(epi.get(k, "")) for k in epi)
    if re.search(r"\d+(?:\.\d+)?\s*%|\bper\s+\d+|\d+\s*:\s*\d+", epi_text, re.I):
        errors.append(f"{cid}: precise epidemiology statistic detected")
    if not isinstance(axis.get("uncertainty_notes", []), list):
        errors.append(f"{cid}: uncertainty_notes must be a list")
    return errors


def collect_batches() -> tuple[dict, list[str], list[str]]:
    worklist_data = load(WORKLIST)
    work_items = worklist_data.get("items", [])
    work = {item["id"]: item for item in work_items}
    collected = {}
    sources = []
    errors = []
    for path in sorted(BATCH_DIR.glob("*.json")):
        data = load(path)
        refs = data.get("harrison_refs", {})
        axes = data.get("axes", {})
        sources.append(str(path.relative_to(ROOT)))
        quality_report = audit_document(
            data,
            source=str(path.relative_to(ROOT)),
            worklist_data=worklist_data,
        )
        for finding in quality_report.get("issues", []):
            if finding.get("blocking"):
                location = ".".join(
                    part for part in (str(finding.get("id") or ""), str(finding.get("path") or "")) if part
                )
                errors.append(
                    f"{path.name}: quality gate {finding.get('code')}"
                    + (f" at {location}" if location else "")
                )
        progress = data.get("_progress")
        if isinstance(progress, dict):
            selected = progress.get("selected_ids")
            if not isinstance(selected, list) or not all(isinstance(cid, str) for cid in selected):
                errors.append(f"{path.name}: invalid _progress.selected_ids")
            elif set(selected) != set(axes):
                missing = sorted(set(selected) - set(axes))
                errors.append(
                    f"{path.name}: incomplete resumable batch; "
                    f"completed={len(axes)}/{len(selected)} missing={missing[:5]}"
                )
        if set(refs) != set(axes):
            missing_refs = sorted(set(axes) - set(refs))
            orphan_refs = sorted(set(refs) - set(axes))
            errors.append(
                f"{path.name}: harrison_refs/axes mismatch; "
                f"missing_refs={missing_refs[:5]} orphan_refs={orphan_refs[:5]}"
            )
        for cid, axis in axes.items():
            if cid in collected:
                errors.append(f"duplicate batch id: {cid}")
                continue
            item = work.get(cid)
            if not item:
                errors.append(f"{cid}: absent from clinical_axes_worklist")
            elif not item.get("harrison") or item["harrison"].get("chapter") is None:
                errors.append(f"{cid}: worklist is not Harrison-grounded")
            else:
                expected = {k: item["harrison"].get(k) for k in ("chapter", "title", "page", "part")}
                actual = {k: (refs.get(cid) or {}).get(k) for k in ("chapter", "title", "page", "part")}
                if actual != expected:
                    errors.append(f"{cid}: Harrison ref mismatch: {actual!r} != {expected!r}")
            errors.extend(validate_axis(cid, axis))
            collected[cid] = axis
    if not sources:
        errors.append("no clinical-axis batch files found")
    return collected, sources, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    batch_axes, sources, errors = collect_batches()
    current = load(OUT)
    axes = current.get("axes", {})

    if args.check:
        for cid, axis in batch_axes.items():
            if axes.get(cid) != axis:
                errors.append(f"{cid}: merged output missing or differs from batch")
        if current.get("total") != len(axes):
            errors.append("clinical_axes_map total does not equal axes size")
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
    total = len(axes) if args.apply else len(axes)
    print(f"mode={'apply' if args.apply else 'check'} batches={len(sources)} batch_axes={len(batch_axes)} added={added} total={total} errors=0")


if __name__ == "__main__":
    main()
