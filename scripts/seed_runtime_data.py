#!/usr/bin/env python3
"""Seed and verify the persistent P:accine runtime data directory.

Railway mounts a volume at container start and the mount hides files baked at
the same path. The Docker image therefore stores an allow-listed bundle in
``/app/runtime_seed``. This script copies missing seed files into the mounted
``/app/data_private`` directory without overwriting learner or faculty work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


SEED_SCHEMA = "paccine.runtime_seed.v1"

REQUIRED_FILES = (
    "concept_registry.json",
    "curriculum/axis_registry.json",
    "curriculum/distractor_bridges.json",
    "curriculum/typed_entity_registry.json",
    "student/qbank.json",
    "student/qbank_enrichment.draft.json",
    "student/qbank_enrichment.releases.json",
    "concept_notes/hemeonc_concept_notes.json",
    "ontology/question_links.json",
    "harrison/22e/pages.jsonl",
    "kr_guidelines/verified_latest_registry.json",
    "kr_guidelines/ontology_overlay.json",
    "guideline_map/source_map.json",
    "guideline_map/atomic_claim_candidates.json",
    "rag/item_writing/rag_index.json",
    "studio/student_releases.json",
)

SYNCED_OVERLAY_FILES = (
    "student/qbank_enrichment.draft.json",
    "student/qbank_enrichment.releases.json",
)

REQUIRED_GLOBS = (
    "studio/question_bank/*.question_set.json",
    "course_exams/extracted/*.json",
    "course_exams/media/**/*",
    "medlegal/cases/*.case.json",
)

MUTABLE_DIRECTORIES = (
    "anki_exports",
    "course_exams/analytics",
    "course_exams/cbt_exports",
    "course_exams/extracted",
    "course_exams/markdown",
    "course_exams/media",
    "course_exams/previews",
    "course_exams/uploads",
    "kr_guidelines/source_files",
    "medlegal/imports",
    "medlegal/submissions",
    "studio/converted",
    "studio/export_sets",
    "studio/extracted",
    "studio/generated",
    "studio/generation_jobs",
    "studio/images",
    "studio/media_bank/assets",
    "studio/question_bank",
    "studio/review_sets",
    "studio/uploads",
)


def _copy_missing_tree(source: Path, destination: Path) -> tuple[int, int]:
    copied_files = 0
    copied_bytes = 0
    if not source.exists():
        return copied_files, copied_bytes
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not path.is_file() or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        # Some Korean source filenames already approach ext4's 255-byte limit.
        # Use a short digest for the atomic temporary name instead of appending
        # to the original filename.
        digest = hashlib.sha256(str(relative).encode("utf-8")).hexdigest()[:20]
        temporary = target.with_name(f".seed-{digest}-{os.getpid()}")
        shutil.copy2(path, temporary)
        os.replace(temporary, target)
        copied_files += 1
        copied_bytes += path.stat().st_size
    return copied_files, copied_bytes


def _load_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _real_faculty_decision(entry: object) -> bool:
    """Return whether an overlay row records a real faculty decision."""
    if not isinstance(entry, dict):
        return False
    reviewer_id = str(entry.get("reviewer_id") or "").strip()
    reviewed_at = str(entry.get("reviewed_at") or "").strip()
    if not reviewer_id or reviewer_id.startswith("demo:") or not reviewed_at:
        return False
    return bool(
        (
            entry.get("approved") is True
            and entry.get("medical_approval") is True
            and entry.get("demo_release") is not True
            and entry.get("needs_real_faculty_review") is not True
        )
        or entry.get("review_status") == "rejected"
    )


def _release_preference(existing: object, incoming: object) -> object:
    """Merge releases without erasing decisions made on the persistent server."""
    existing_real = _real_faculty_decision(existing)
    incoming_real = _real_faculty_decision(incoming)
    if existing_real and not incoming_real:
        return existing
    if incoming_real and not existing_real:
        return incoming
    if existing_real and incoming_real:
        existing_at = str(existing.get("reviewed_at") or "") if isinstance(existing, dict) else ""
        incoming_at = str(incoming.get("reviewed_at") or "") if isinstance(incoming, dict) else ""
        return incoming if incoming_at > existing_at else existing
    # Neither row is a real faculty decision. Newly deployed owner-demo metadata
    # may refresh the presentation set, while the API still requires the
    # explicit full-demo environment gate before student visibility.
    return incoming


def _atomic_write_json(path: Path, payload: dict[str, object]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:20]
    temporary = path.with_name(f".overlay-{digest}-{os.getpid()}")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)
    return len(encoded)


def _sync_qbank_overlays(seed_root: Path, data_root: Path) -> tuple[int, int]:
    """Merge deployable overlays into the persistent volume.

    Drafts are server-storable review inputs, not student releases. Release
    rows are merged independently and real server-side faculty decisions win
    over unreviewed/demo seed rows. Both overlay documents must target the
    current immutable qbank checksum; stale inputs fail before mutation.
    """
    qbank_path = data_root / "student/qbank.json"
    if not qbank_path.is_file():
        return 0, 0
    current_qbank_sha = hashlib.sha256(qbank_path.read_bytes()).hexdigest()
    synced_files = 0
    synced_bytes = 0

    for relative in SYNCED_OVERLAY_FILES:
        source = seed_root / relative
        target = data_root / relative
        incoming = _load_json_object(source)
        if not incoming:
            continue
        incoming_sha = str(incoming.get("built_against_sha256") or "")
        if not incoming_sha or incoming_sha != current_qbank_sha:
            raise RuntimeError(f"stale qbank enrichment overlay in runtime seed: {relative}")

        existing = _load_json_object(target)
        existing_sha = str(existing.get("built_against_sha256") or "")
        if existing and existing_sha and existing_sha != current_qbank_sha:
            raise RuntimeError(f"persistent qbank enrichment overlay targets another qbank: {relative}")

        collection_key = "drafts" if relative.endswith("draft.json") else "releases"
        incoming_rows = incoming.get(collection_key)
        existing_rows = existing.get(collection_key)
        incoming_rows = incoming_rows if isinstance(incoming_rows, dict) else {}
        existing_rows = existing_rows if isinstance(existing_rows, dict) else {}

        merged = dict(existing)
        # Preserve schema/notice metadata from the newest deployable artifact.
        for key, value in incoming.items():
            if key != collection_key:
                merged[key] = value
        rows = dict(existing_rows)
        if collection_key == "drafts":
            rows.update(incoming_rows)
        else:
            for question_id, entry in incoming_rows.items():
                rows[question_id] = _release_preference(rows.get(question_id), entry)
        merged[collection_key] = rows
        merged["built_against_sha256"] = current_qbank_sha

        if merged != existing:
            synced_bytes += _atomic_write_json(target, merged)
            synced_files += 1
    return synced_files, synced_bytes


def verify_runtime(data_root: Path) -> dict[str, object]:
    missing = [relative for relative in REQUIRED_FILES if not (data_root / relative).is_file()]
    empty_globs = [pattern for pattern in REQUIRED_GLOBS if not any(data_root.glob(pattern))]
    if missing or empty_globs:
        details = []
        if missing:
            details.append("missing files: " + ", ".join(missing))
        if empty_globs:
            details.append("empty groups: " + ", ".join(empty_globs))
        raise RuntimeError("P:accine runtime data is incomplete; " + "; ".join(details))

    qbank_payload = json.loads((data_root / "student/qbank.json").read_text(encoding="utf-8"))
    questions = qbank_payload.get("questions") if isinstance(qbank_payload, dict) else None
    if not isinstance(questions, list) or not questions:
        raise RuntimeError("P:accine student qbank is empty or invalid")

    return {
        "schema": SEED_SCHEMA,
        "ready": True,
        "question_count": len(questions),
        "question_set_count": len(list(data_root.glob("studio/question_bank/*.question_set.json"))),
        "course_exam_count": len(list(data_root.glob("course_exams/extracted/*.json"))),
        "medlegal_case_count": len(list(data_root.glob("medlegal/cases/*.case.json"))),
    }


def seed_runtime(seed_root: Path, data_root: Path) -> dict[str, object]:
    data_root.mkdir(parents=True, exist_ok=True)
    copied_files, copied_bytes = _copy_missing_tree(seed_root, data_root)
    synced_overlays, synced_overlay_bytes = _sync_qbank_overlays(seed_root, data_root)
    for relative in MUTABLE_DIRECTORIES:
        (data_root / relative).mkdir(parents=True, exist_ok=True)
    marker = {
        "schema": SEED_SCHEMA,
        "seeded_at": datetime.now(timezone.utc).isoformat(),
        "copied_files": copied_files,
        "copied_bytes": copied_bytes,
        "synced_overlays": synced_overlays,
        "synced_overlay_bytes": synced_overlay_bytes,
    }
    marker_path = data_root / ".runtime_seed.json"
    marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    return marker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-root", type=Path, default=Path("runtime_seed"))
    parser.add_argument("--data-root", type=Path, default=Path("data_private"))
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seed_root = args.seed_root.resolve()
    data_root = args.data_root.resolve()
    marker: dict[str, object] = {"copied_files": 0, "copied_bytes": 0}
    if not args.verify_only:
        if seed_root.exists():
            marker = seed_runtime(seed_root, data_root)
        else:
            for relative in MUTABLE_DIRECTORIES:
                (data_root / relative).mkdir(parents=True, exist_ok=True)
    status = verify_runtime(data_root) if args.verify or args.verify_only else {"ready": None}
    print(
        json.dumps(
            {
                "event": "paccine_runtime_seed",
                "data_root": str(data_root),
                "copied_files": marker.get("copied_files", 0),
                "copied_mib": round(int(marker.get("copied_bytes", 0)) / 1024 / 1024, 2),
                "synced_overlays": marker.get("synced_overlays", 0),
                **status,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
