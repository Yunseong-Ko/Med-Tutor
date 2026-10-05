#!/usr/bin/env python3
"""Build deterministic cumulative task selection for media visual review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKLIST = (
    ROOT
    / "data_private"
    / "course_exams"
    / "media_labeling"
    / "media_label_review_worklist.jsonl"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data_private"
    / "course_exams"
    / "media_labeling"
    / "ai_visual_review_selection.json"
)
DEFAULT_SCHEMA = ROOT / "schemas" / "media_visual_review_selection.schema.json"

PHOTO_RICH_MODALITIES = {
    "clinical_photo",
    "photo",
    "fundus",
    "microscopy",
    "mammography",
    "fluoroscopy",
    "eeg",
    "blood_smear",
    "bone_marrow_microscopy",
    "endoscopy",
}

MODALITY_TIERS = (
    {"clinical_photo", "photo", "fundus"},
    {"microscopy", "blood_smear", "bone_marrow_microscopy"},
    {"mammography", "fluoroscopy", "eeg"},
    {"endoscopy"},
)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: object expected")
        rows.append(row)
    return rows


def modality_labels(task: dict[str, Any]) -> set[str]:
    return {
        str(item.get("label_text") or "").strip()
        for item in task.get("candidate_labels") or []
        if isinstance(item, dict)
        and item.get("kind") == "modality"
        and str(item.get("label_text") or "").strip()
    }


def modality_tier(task: dict[str, Any]) -> int:
    labels = modality_labels(task)
    return next(
        (index for index, values in enumerate(MODALITY_TIERS) if labels & values),
        len(MODALITY_TIERS),
    )


def build_selection(worklist_path: Path) -> dict[str, Any]:
    tasks = read_jsonl(worklist_path)
    round_1 = [
        task["task_id"]
        for task in tasks
        if task.get("pilot_group") == "hematology_oncology_first"
    ]
    round_2_tasks = [
        task
        for task in tasks
        if task.get("pilot_group") == "general_backlog"
        and modality_labels(task) & PHOTO_RICH_MODALITIES
    ]
    round_2_tasks.sort(
        key=lambda task: (
            modality_tier(task),
            0 if task.get("question_contexts") else 1,
            int(task.get("priority_score") or 0),
            task["task_id"],
        )
    )
    round_2 = [task["task_id"] for task in round_2_tasks]
    selected = round_1 + round_2
    if len(selected) != len(set(selected)):
        raise ValueError("selection contains duplicate task IDs")
    known = {task["task_id"] for task in tasks}
    if not set(selected) <= known:
        raise ValueError("selection contains unknown task IDs")

    return {
        "schema_version": "media_visual_review_selection.v1",
        "worklist": {
            "path": display_path(worklist_path),
            "sha256": sha256_file(worklist_path),
            "task_count": len(tasks),
        },
        "rounds": [
            {
                "round_id": "hematology_oncology_first",
                "description": "Hematology-oncology image-first pilot",
                "selection_rule": "pilot_group == hematology_oncology_first",
                "task_ids": round_1,
            },
            {
                "round_id": "photo_rich_modalities_second",
                "description": (
                    "Clinical photographs, fundus, microscopy, mammography, "
                    "fluoroscopy, EEG, blood smear, and endoscopy candidates"
                ),
                "selection_rule": (
                    "general_backlog with at least one candidate modality in "
                    + ", ".join(sorted(PHOTO_RICH_MODALITIES))
                ),
                "task_ids": round_2,
            },
        ],
        "selected_task_ids": selected,
        "summary": {
            "selected_task_count": len(selected),
            "round_task_counts": {
                "hematology_oncology_first": len(round_1),
                "photo_rich_modalities_second": len(round_2),
            },
            "remaining_unselected_task_count": len(tasks) - len(selected),
        },
    }


def render(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def run(args: argparse.Namespace) -> int:
    value = build_selection(args.worklist)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    jsonschema.validate(value, schema)
    payload = render(value)
    if args.check:
        ok = args.output.is_file() and args.output.read_bytes() == payload
        print(
            json.dumps(
                {
                    "selection_ok": ok,
                    "output": display_path(args.output),
                    "summary": value["summary"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(
        json.dumps(
            {
                "status": "written",
                "output": display_path(args.output),
                "summary": value["summary"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build cumulative media visual-review selection."
    )
    parser.add_argument("--worklist", type=Path, default=DEFAULT_WORKLIST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
