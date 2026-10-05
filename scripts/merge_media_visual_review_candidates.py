#!/usr/bin/env python3
"""Normalize and merge AI-assisted visual labeling batches.

The merged output remains a human-review-required candidate layer. This script
cannot approve medical semantics, rights, deidentification, question use, or
student visibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
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
DEFAULT_BATCH_DIR = (
    ROOT
    / "data_private"
    / "course_exams"
    / "media_labeling"
    / "ai_review_batches"
)
DEFAULT_SELECTION = (
    ROOT
    / "data_private"
    / "course_exams"
    / "media_labeling"
    / "ai_visual_review_selection.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data_private"
    / "course_exams"
    / "media_labeling"
    / "ai_visual_review_candidates.jsonl"
)
DEFAULT_MANIFEST = (
    ROOT
    / "data_private"
    / "course_exams"
    / "media_labeling"
    / "ai_visual_review_manifest.json"
)
DEFAULT_SCHEMA = ROOT / "schemas" / "media_visual_review_candidate.schema.json"
DEFAULT_FINDING_REGISTRY = (
    ROOT / "data_private" / "curriculum" / "finding_registry.json"
)

SCHEMA_VERSION = "media_visual_review_candidate.v1"
RECORD_TYPE = "media_visual_review_candidate"

READABILITY = {"readable", "limited", "unreadable"}
ALIGNMENT = {"supported", "uncertain", "conflict", "unlinked"}
LEAK_RISK = {"low", "medium", "high", "unknown"}
DEIDENTIFICATION_RISK = {"none_observed", "possible", "present", "unknown"}
BASIS = {
    "visual_only",
    "question_only",
    "visual_and_question",
    "embedded_annotation",
}


def stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def digest_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def display_path(path: Path) -> str:
    """Return a reproducible project-relative path when possible."""
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: object expected")
        rows.append(value)
    return rows


def read_finding_ids(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    findings = data.get("findings") if isinstance(data, dict) else []
    if not isinstance(findings, list):
        return set()
    return {
        str(item.get("finding_id"))
        for item in findings
        if isinstance(item, dict)
        if item.get("finding_id")
    }


def normalize_text_list(value: Any) -> list[str]:
    source = value if isinstance(value, list) else []
    result: list[str] = []
    for item in source:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def normalize_label_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    key = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE).strip("_")
    if not key:
        raise ValueError(f"label cannot form normalized key: {value!r}")
    return key


def normalize_light_candidates(
    value: Any,
    *,
    default_status: str,
    target_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    source = value if isinstance(value, list) else []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(source):
        if not isinstance(item, dict):
            raise ValueError(f"candidate index {index}: object expected")
        label = str(item.get("label_text") or "").strip()
        if not label:
            raise ValueError(f"candidate index {index}: label_text required")
        normalized_key = normalize_label_key(label)
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"candidate {label}: numeric confidence required") from exc
        if not 0 <= confidence <= 1:
            raise ValueError(f"candidate {label}: confidence outside 0..1")
        basis = str(item.get("basis") or "").strip()
        if basis not in BASIS:
            raise ValueError(f"candidate {label}: invalid basis {basis}")
        # A label inferred only from the question is context, not visual proof.
        # This prevents a disease named in the answer from being silently
        # promoted to something the image itself depicts.
        status = (
            "question_context_candidate"
            if basis == "question_only"
            else default_status
        )
        target_id = item.get("target_id")
        if target_id is None and target_ids is not None:
            if label in target_ids:
                target_id = label
            elif normalized_key in target_ids:
                target_id = normalized_key
        candidate = {
            "label_text": label,
            "normalized_key": normalized_key,
            "target_id": str(target_id) if target_id else None,
            "status": status,
            "confidence": round(confidence, 3),
            "basis": basis,
        }
        if candidate not in result:
            result.append(candidate)
    return sorted(
        result,
        key=lambda item: (
            item["label_text"],
            item["normalized_key"],
            item.get("target_id") or "",
            item["basis"],
        ),
    )


def question_candidates(
    task: dict[str, Any],
    *,
    kind: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in task.get("candidate_labels") or []:
        if not isinstance(item, dict) or item.get("kind") != kind:
            continue
        label = str(item.get("label_text") or "").strip()
        if not label:
            continue
        candidate = {
            "label_text": label,
            "normalized_key": normalize_label_key(label),
            "target_id": item.get("target_id"),
            "status": "question_context_candidate",
            "confidence": round(float(item.get("confidence") or 0), 3),
            "basis": "question_only",
        }
        if candidate not in result:
            result.append(candidate)
    return sorted(
        result,
        key=lambda item: (
            item["label_text"],
            item["normalized_key"],
            item.get("target_id") or "",
        ),
    )


def resolve_source_image(task: dict[str, Any]) -> Path:
    raw_path = Path(task["media_occurrence"]["file"]["path"])
    return raw_path if raw_path.is_absolute() else ROOT / raw_path


def verify_source_image(task: dict[str, Any]) -> Path:
    task_id = task["task_id"]
    image_path = resolve_source_image(task)
    if not image_path.is_file():
        raise ValueError(f"{task_id}: source image missing: {image_path}")
    expected = task["media_occurrence"]["media_object_id"].removeprefix(
        "mediaobj_"
    )
    actual = file_sha256(image_path)
    if actual != expected:
        raise ValueError(
            f"{task_id}: image SHA-256 mismatch: expected={expected} actual={actual}"
        )
    return image_path


def build_record(
    *,
    decision: dict[str, Any],
    task: dict[str, Any],
    batch_name: str,
    finding_ids: set[str],
) -> dict[str, Any]:
    task_id = task["task_id"]
    verify_source_image(task)
    occurrence = task["media_occurrence"]
    media_object_id = occurrence["media_object_id"]
    image_sha256 = media_object_id.removeprefix("mediaobj_")
    task_sha256 = digest_json(task)
    seed = {
        "task_id": task_id,
        "batch_name": batch_name,
        "decision": decision,
        "task_sha256": task_sha256,
    }
    review_id = "mvisual_" + digest_json(seed)[:24]

    readability = str(decision.get("image_readability") or "").strip()
    alignment_status = str(decision.get("alignment_status") or "").strip()
    leak_risk = str(decision.get("answer_leak_risk") or "").strip()
    deidentification_risk = str(
        decision.get("deidentification_risk_observed") or "unknown"
    ).strip()
    if readability not in READABILITY:
        raise ValueError(f"{task_id}: invalid image_readability {readability}")
    if alignment_status not in ALIGNMENT:
        raise ValueError(f"{task_id}: invalid alignment_status {alignment_status}")
    if leak_risk not in LEAK_RISK:
        raise ValueError(f"{task_id}: invalid answer_leak_risk {leak_risk}")
    if deidentification_risk not in DEIDENTIFICATION_RISK:
        raise ValueError(
            f"{task_id}: invalid deidentification_risk_observed "
            f"{deidentification_risk}"
        )
    try:
        visual_confidence = float(decision.get("visual_confidence"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{task_id}: visual_confidence required") from exc
    if not 0 <= visual_confidence <= 1:
        raise ValueError(f"{task_id}: visual_confidence outside 0..1")

    question_ids = sorted(
        {
            str(context.get("question", {}).get("question_id") or "").strip()
            for context in task.get("question_contexts") or []
            if str(context.get("question", {}).get("question_id") or "").strip()
        }
    )
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_TYPE,
        "visual_review_id": review_id,
        "task_id": task_id,
        "occurrence_id": occurrence["occurrence_id"],
        "media_object_id": media_object_id,
        "reviewer": {
            "type": "ai_assisted_candidate_reviewer",
            "agent_id": batch_name,
            "review_method": "image_plus_original_question_context",
        },
        "source": {
            "worklist_task_sha256": task_sha256,
            "image_sha256": image_sha256,
            "image_path": occurrence["file"]["path"],
            "question_ids": question_ids,
        },
        "visual_assessment": {
            "image_readability": readability,
            "visual_description": str(decision.get("visual_description") or "").strip(),
            "modality_candidates": normalize_light_candidates(
                decision.get("modality_labels"),
                default_status="visually_supported_candidate",
            ),
            "specimen_candidates": normalize_light_candidates(
                decision.get("specimen_labels"),
                default_status="visually_supported_candidate",
            ),
            "depicted_finding_candidates": normalize_light_candidates(
                decision.get("finding_labels"),
                default_status="visually_supported_candidate",
                target_ids=finding_ids,
            ),
            "visible_annotations": normalize_text_list(
                decision.get("visible_annotations")
            ),
            "embedded_text": normalize_text_list(decision.get("embedded_text")),
            "visual_confidence": round(visual_confidence, 3),
        },
        "question_alignment": {
            "status": alignment_status,
            "associated_concept_candidates": question_candidates(
                task,
                kind="concept",
            ),
            "assessment_axis_candidates": question_candidates(
                task,
                kind="axis",
            ),
            "answer_leak_risk": leak_risk,
            "notes": str(decision.get("alignment_notes") or "").strip(),
        },
        "safety": {
            "rights_status": "unknown",
            "deidentification_status": "unknown",
            "deidentification_risk_observed": deidentification_risk,
            "rights_review_required": True,
            "deidentification_review_required": True,
            "medical_approval": False,
            "approved_for_question_use": False,
            "student_visible": False,
        },
        "review_status": "human_review_required",
    }
    return record


def build_outputs(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tasks = read_jsonl(args.worklist)
    tasks_by_id = {task["task_id"]: task for task in tasks}
    selection_meta: dict[str, Any]
    round_task_ids: dict[str, list[str]]
    if args.selection is not None:
        selection_value = json.loads(args.selection.read_text(encoding="utf-8"))
        selected_ids = selection_value.get("selected_task_ids")
        if not isinstance(selected_ids, list) or not selected_ids:
            raise ValueError(f"{args.selection}: selected_task_ids required")
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError(f"{args.selection}: duplicate selected task ID")
        unknown_selected = sorted(set(selected_ids) - set(tasks_by_id))
        if unknown_selected:
            raise ValueError(
                f"{args.selection}: unknown task IDs: {unknown_selected[:5]}"
            )
        expected_worklist_sha = (
            selection_value.get("worklist", {}).get("sha256")
            if isinstance(selection_value.get("worklist"), dict)
            else None
        )
        actual_worklist_sha = file_sha256(args.worklist)
        if expected_worklist_sha != actual_worklist_sha:
            raise ValueError(
                f"{args.selection}: worklist SHA-256 mismatch"
            )
        round_task_ids = {
            str(item.get("round_id") or "").strip(): list(item.get("task_ids") or [])
            for item in selection_value.get("rounds") or []
            if isinstance(item, dict) and str(item.get("round_id") or "").strip()
        }
        flattened_round_ids = [
            task_id
            for task_ids in round_task_ids.values()
            for task_id in task_ids
        ]
        if (
            len(flattened_round_ids) != len(set(flattened_round_ids))
            or set(flattened_round_ids) != set(selected_ids)
        ):
            raise ValueError(
                f"{args.selection}: round task IDs must uniquely cover selection"
            )
        selected = {task_id: tasks_by_id[task_id] for task_id in selected_ids}
        selection_meta = {
            "path": display_path(args.selection),
            "sha256": file_sha256(args.selection),
            "rounds": [
                {
                    "round_id": item.get("round_id"),
                    "task_count": len(item.get("task_ids") or []),
                }
                for item in selection_value.get("rounds") or []
                if isinstance(item, dict)
            ],
        }
    else:
        selected = {
            task["task_id"]: task
            for task in tasks
            if task.get("pilot_group") == "hematology_oncology_first"
        }
        selection_meta = {
            "path": None,
            "sha256": None,
            "rounds": [
                {
                    "round_id": "hematology_oncology_first",
                    "task_count": len(selected),
                }
            ],
        }
        round_task_ids = {
            "hematology_oncology_first": list(selected),
        }
    finding_ids = read_finding_ids(args.finding_registry)
    batch_paths = sorted(args.batch_dir.glob("batch_*.json"))
    if not batch_paths:
        raise ValueError(f"No batch files found under {args.batch_dir}")

    decisions_by_task: dict[str, tuple[dict[str, Any], str]] = {}
    batch_inputs: list[dict[str, Any]] = []
    for batch_path in batch_paths:
        values = json.loads(batch_path.read_text(encoding="utf-8"))
        if not isinstance(values, list):
            raise ValueError(f"{batch_path}: JSON array expected")
        batch_inputs.append(
            {
                "path": display_path(batch_path),
                "sha256": file_sha256(batch_path),
                "decision_count": len(values),
            }
        )
        for decision in values:
            if not isinstance(decision, dict):
                raise ValueError(f"{batch_path}: decision object expected")
            task_id = str(decision.get("task_id") or "").strip()
            if task_id not in selected:
                raise ValueError(f"{batch_path}: unknown/unselected task_id {task_id}")
            if task_id in decisions_by_task:
                raise ValueError(f"duplicate decision for {task_id}")
            decisions_by_task[task_id] = (decision, batch_path.stem)

    missing = sorted(set(selected) - set(decisions_by_task))
    if missing and not args.allow_incomplete:
        raise ValueError(
            f"Missing {len(missing)} selected decisions; first={missing[:5]}"
        )

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for task_id in sorted(decisions_by_task):
        decision, batch_name = decisions_by_task[task_id]
        record = build_record(
            decision=decision,
            task=selected[task_id],
            batch_name=batch_name,
            finding_ids=finding_ids,
        )
        jsonschema.validate(record, schema)
        records.append(record)

    readability = Counter(
        record["visual_assessment"]["image_readability"]
        for record in records
    )
    alignment = Counter(
        record["question_alignment"]["status"]
        for record in records
    )
    leak_risk = Counter(
        record["question_alignment"]["answer_leak_risk"]
        for record in records
    )
    deidentification_risk = Counter(
        record["safety"]["deidentification_risk_observed"]
        for record in records
    )
    modality = Counter(
        candidate["normalized_key"]
        for record in records
        for candidate in record["visual_assessment"]["modality_candidates"]
    )
    finding = Counter(
        candidate["normalized_key"]
        for record in records
        for candidate in record["visual_assessment"]["depicted_finding_candidates"]
    )
    all_visual_candidates = [
        candidate
        for record in records
        for key in (
            "modality_candidates",
            "specimen_candidates",
            "depicted_finding_candidates",
        )
        for candidate in record["visual_assessment"][key]
    ]
    finding_candidates = [
        candidate
        for record in records
        for candidate in record["visual_assessment"][
            "depicted_finding_candidates"
        ]
    ]
    unique_media_objects = {
        record["media_object_id"]
        for record in records
    }
    record_ids = {record["task_id"] for record in records}
    round_summary = {
        round_id: {
            "selected_task_count": len(task_ids),
            "record_count": sum(task_id in record_ids for task_id in task_ids),
            "missing_task_count": sum(
                task_id not in record_ids for task_id in task_ids
            ),
        }
        for round_id, task_ids in round_task_ids.items()
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "review_method": "image_plus_original_question_context",
        "selection": selection_meta,
        "round_summary": round_summary,
        "worklist": {
            "path": display_path(args.worklist),
            "sha256": file_sha256(args.worklist),
            "selected_task_count": len(selected),
        },
        "batch_inputs": batch_inputs,
        "review_queues": {
            "conflict_task_ids": sorted(
                record["task_id"]
                for record in records
                if record["question_alignment"]["status"] == "conflict"
            ),
            "uncertain_task_ids": sorted(
                record["task_id"]
                for record in records
                if record["question_alignment"]["status"] == "uncertain"
            ),
            "unlinked_task_ids": sorted(
                record["task_id"]
                for record in records
                if record["question_alignment"]["status"] == "unlinked"
            ),
            "high_answer_leak_task_ids": sorted(
                record["task_id"]
                for record in records
                if record["question_alignment"]["answer_leak_risk"] == "high"
            ),
            "limited_readability_task_ids": sorted(
                record["task_id"]
                for record in records
                if record["visual_assessment"]["image_readability"]
                == "limited"
            ),
            "deidentification_risk_task_ids": sorted(
                record["task_id"]
                for record in records
                if record["safety"]["deidentification_risk_observed"]
                in {"possible", "present"}
            ),
        },
        "summary": {
            "record_count": len(records),
            "unique_media_object_count": len(unique_media_objects),
            "duplicate_media_object_occurrence_count": (
                len(records) - len(unique_media_objects)
            ),
            "image_integrity_verified_count": len(records),
            "selected_task_count": len(selected),
            "missing_task_count": len(missing),
            "duplicate_task_count": 0,
            "readability": dict(sorted(readability.items())),
            "alignment": dict(sorted(alignment.items())),
            "answer_leak_risk": dict(sorted(leak_risk.items())),
            "deidentification_risk_observed": dict(
                sorted(deidentification_risk.items())
            ),
            "top_modalities": modality.most_common(20),
            "top_findings": finding.most_common(30),
            "visual_candidate_count": len(all_visual_candidates),
            "visually_supported_candidate_count": sum(
                candidate["status"] == "visually_supported_candidate"
                for candidate in all_visual_candidates
            ),
            "question_context_candidate_in_visual_fields_count": sum(
                candidate["status"] == "question_context_candidate"
                for candidate in all_visual_candidates
            ),
            "finding_candidate_count": len(finding_candidates),
            "finding_registry_resolved_count": sum(
                bool(candidate["target_id"])
                for candidate in finding_candidates
            ),
            "finding_registry_unresolved_count": sum(
                not candidate["target_id"]
                for candidate in finding_candidates
            ),
            "medical_approval_count": 0,
            "approved_for_question_use_count": 0,
            "student_visible_count": 0,
        },
        "missing_task_ids": missing,
    }
    return records, manifest


def records_bytes(records: list[dict[str, Any]]) -> bytes:
    return (
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in records
        )
        + ("\n" if records else "")
    ).encode("utf-8")


def manifest_bytes(
    manifest: dict[str, Any],
    records_payload: bytes,
    output_path: Path = DEFAULT_OUTPUT,
) -> bytes:
    value = dict(manifest)
    value["output"] = {
        "path": display_path(output_path),
        "sha256": hashlib.sha256(records_payload).hexdigest(),
        "size_bytes": len(records_payload),
        "row_count": records_payload.count(b"\n"),
    }
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def run(args: argparse.Namespace) -> int:
    records, manifest = build_outputs(args)
    payload = records_bytes(records)
    manifest_payload = manifest_bytes(manifest, payload, args.output)

    if args.check:
        changed: list[str] = []
        for path, expected in (
            (args.output, payload),
            (args.manifest, manifest_payload),
        ):
            if not path.exists() or path.read_bytes() != expected:
                changed.append(str(path))
        if changed:
            print(
                json.dumps(
                    {
                        "visual_review_ok": False,
                        "changed_or_missing": changed,
                        "summary": manifest["summary"],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "visual_review_ok": True,
                    "summary": manifest["summary"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    args.manifest.write_bytes(manifest_payload)
    print(
        json.dumps(
            {
                "status": "written",
                "output": display_path(args.output),
                "manifest": display_path(args.manifest),
                "summary": manifest["summary"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge AI-assisted visual review batches into safe candidates."
    )
    parser.add_argument("--worklist", type=Path, default=DEFAULT_WORKLIST)
    parser.add_argument(
        "--selection",
        type=Path,
        default=DEFAULT_SELECTION,
        help="Cumulative selection manifest; pass an empty value only via API tests.",
    )
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--finding-registry", type=Path, default=DEFAULT_FINDING_REGISTRY)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
