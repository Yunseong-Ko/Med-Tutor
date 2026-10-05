#!/usr/bin/env python3
"""One-time recovery of the immutable non-disease clinical-axis archive.

The seven source records were removed from the active clinical_axes_map after
retyping. Their exact authoring JSON remains in the original Claude workflow
result. This recovery tool extracts only those records, writes with exclusive
creation, and never overwrites an existing archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from scripts.build_typed_entity_registry import (
        QUARANTINE_ARCHIVE,
        QUARANTINE_REQUIRED_IDS,
        OUT as TYPED_REGISTRY,
    )
except ModuleNotFoundError:  # direct script execution
    from build_typed_entity_registry import (
        QUARANTINE_ARCHIVE,
        QUARANTINE_REQUIRED_IDS,
        OUT as TYPED_REGISTRY,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW = (
    Path.home()
    / ".claude/projects/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/"
    "de303da3-bc32-4d7d-8ccd-2e818e9e83d7/workflows/wf_f06926ff-185.json"
)
EXPECTED_RUN_ID = "wf_f06926ff-185"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def recover(source: Path, typed_registry_path: Path = TYPED_REGISTRY) -> dict[str, Any]:
    source_raw = source.read_bytes()
    workflow = json.loads(source_raw)
    if workflow.get("runId") != EXPECTED_RUN_ID:
        raise ValueError(f"unexpected workflow runId: {workflow.get('runId')!r}")
    results = ((workflow.get("result") or {}).get("results") or [])
    rows = {
        row.get("id"): row
        for row in results
        if isinstance(row, dict) and row.get("id") in QUARANTINE_REQUIRED_IDS
    }
    missing = sorted(QUARANTINE_REQUIRED_IDS - set(rows))
    if missing:
        raise ValueError("workflow is missing required original axes: " + ", ".join(missing))

    typed_entities = (load(typed_registry_path).get("entities") or {})
    quarantined: dict[str, dict[str, Any]] = {}
    record_hashes: dict[str, str] = {}
    for concept_id in sorted(QUARANTINE_REQUIRED_IDS):
        entity = typed_entities.get(concept_id)
        if not entity:
            raise ValueError(f"typed entity missing during archive recovery: {concept_id}")
        original_axes = rows[concept_id]
        canonical = json.dumps(original_axes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        record_hashes[concept_id] = sha256_bytes(canonical)
        quarantined[concept_id] = {
            "concept_id": concept_id,
            "entity_id": entity["entity_id"],
            "entity_type": entity["entity_type"],
            "quarantine_reason": "clinical axes were authored under an invalid disease typing",
            "generation_eligible": False,
            "axis_layer_eligible": False,
            "migration_status": "immutable_recovered_original",
            "recovery_source": f"{EXPECTED_RUN_ID}:result.results",
            "original_axes_sha256": record_hashes[concept_id],
            "original_axes": original_axes,
            "needs_review": True,
            "medical_approval": False,
        }

    return {
        "schema_version": "1.0.0",
        "_meta": {
            "created_at": "2026-07-12",
            "status": "immutable_quarantine_recovery_archive",
            "generated_by": "scripts/recover_typed_entity_quarantine_archive.py",
            "source_workflow_run_id": EXPECTED_RUN_ID,
            "source_workflow_path": str(source),
            "source_workflow_sha256": sha256_bytes(source_raw),
            "recovered_count": len(quarantined),
            "recovered_ids": sorted(quarantined),
            "original_axes_sha256": record_hashes,
            "active_clinical_axes_map_modified": False,
            "overwrite_policy": "exclusive_create_never_overwrite",
            "all_needs_review": True,
            "medical_approval": False,
        },
        "quarantined_axes": quarantined,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_WORKFLOW)
    parser.add_argument("--typed-registry", type=Path, default=TYPED_REGISTRY)
    parser.add_argument("--out", type=Path, default=QUARANTINE_ARCHIVE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = recover(args.source.expanduser().resolve(), args.typed_registry.expanduser().resolve())
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    out = args.out.expanduser().resolve()
    if args.check:
        if not out.exists() or out.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"immutable archive mismatch: {out}")
        print(f"archive_ok records={payload['_meta']['recovered_count']} sha256={sha256_bytes(out.read_bytes())}")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    except FileExistsError:
        raise SystemExit(f"refusing to overwrite immutable archive: {out}")
    out.chmod(0o444)
    print(f"archive_created records={payload['_meta']['recovered_count']} sha256={sha256_bytes(out.read_bytes())}")


if __name__ == "__main__":
    main()
