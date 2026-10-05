#!/usr/bin/env python3
"""Author review-gated clinical-axis batches through Claude Code CLI.

Privacy boundary
----------------
Only four fields can enter a model prompt: concept ``id``, Korean name ``ko``,
and the mapped Harrison ``chapter``/``title``.  This module does not import or
read question banks, question sets, stems, choices, source PDFs, or textbook
page text.

The script writes a standalone batch under ``clinical_axes_batches``.  It never
merges into ``clinical_axes_map.json``.  Every generated record must keep
``needs_review=true`` and pass the five-axis structural validator before it is
saved.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "data_private" / "curriculum"
DEFAULT_WORKLIST = CURRICULUM / "clinical_axes_worklist.json"
DEFAULT_CURRENT_MAP = CURRICULUM / "clinical_axes_map.json"
DEFAULT_OUTPUT_DIR = CURRICULUM / "clinical_axes_batches"
MIN_CLAUDE_VERSION = (2, 1, 205)
MIN_CLAUDE_VERSION_TEXT = ".".join(map(str, MIN_CLAUDE_VERSION))
MAX_CHUNK_SIZE = 5
ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
PRECISE_EPIDEMIOLOGY_PATTERN = re.compile(r"\d|%|‰")
HARRISON_REF_KEYS = ("chapter", "title", "page", "part")


AXIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "pathophysiology",
        "risk_factors",
        "prognosis",
        "treatment",
        "epidemiology",
        "uncertainty_notes",
        "needs_review",
    ],
    "properties": {
        "id": {"type": "string", "pattern": ID_PATTERN.pattern},
        "pathophysiology": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "key_steps"],
            "properties": {
                "summary": {"type": "string", "minLength": 1},
                "key_steps": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 8,
                    "items": {"type": "string", "minLength": 1},
                },
            },
        },
        "risk_factors": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {"type": "string", "minLength": 1},
        },
        "prognosis": {
            "type": "object",
            "additionalProperties": False,
            "required": ["factors", "staging_or_grading", "natural_history"],
            "properties": {
                "factors": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 10,
                    "items": {"type": "string", "minLength": 1},
                },
                "staging_or_grading": {"type": "string", "minLength": 1},
                "natural_history": {"type": "string", "minLength": 1},
            },
        },
        "treatment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["principles", "indicated_for", "contraindicated_for"],
            "properties": {
                "principles": {"type": "string", "minLength": 1},
                "indicated_for": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 12,
                    "items": {"type": "string", "minLength": 1},
                },
                "contraindicated_for": {
                    "type": "array",
                    "maxItems": 10,
                    "items": {"type": "string", "minLength": 1},
                },
            },
        },
        "epidemiology": {
            "type": "object",
            "additionalProperties": False,
            "required": ["age", "sex", "population", "frequency"],
            "properties": {
                key: {"type": "string", "minLength": 1, "pattern": r"^[^0-9%‰]*$"}
                for key in ("age", "sex", "population", "frequency")
            },
        },
        "uncertainty_notes": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "minLength": 1},
        },
        "needs_review": {"type": "boolean", "const": True},
    },
}


SYSTEM_PROMPT = """You author draft clinical ontology records for medical-faculty review.
You have no access to private exam questions or source documents. Use only the sanitized
concept identifiers and Harrison chapter/title pointers in the user message. A chapter
pointer scopes the topic; it is not proof that a specific claim is textually entailed.
Return only structured JSON matching the supplied schema. Never mark content approved."""


AUTHORING_RULES = (
    "Write exactly five axes: pathophysiology, risk_factors, prognosis, treatment, epidemiology.",
    "Keep every needs_review value true; this is an unapproved medical draft.",
    "Use concise textbook-level statements and record uncertainty instead of guessing.",
    "Epidemiology must be qualitative only: no digits, percentages, ratios, incidence, or prevalence numbers.",
    "Do not invent Harrison pages, quotations, external identifiers, citations, or guideline versions.",
    "Do not infer facts from a Korean name alone when the concept is ambiguous; state the uncertainty.",
    "Be concise: use 2-5 mechanism steps, 2-6 risk factors, 2-5 prognostic factors, 2-6 indicated interventions, and at most 4 contraindications.",
    "Avoid numeric drug doses and avoid repeating the same intervention in multiple wordings.",
    "Return one and only one record for every requested concept id; do not add other ids.",
)


class BatchError(RuntimeError):
    """A recoverable batch-authoring or validation error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BatchError(f"Expected a JSON object: {path}")
    return data


def candidate_record(item: dict[str, Any]) -> dict[str, Any] | None:
    """Return safe local metadata; page/part remain local and never enter prompts."""
    concept_id = str(item.get("id") or "").strip()
    ko = str(item.get("ko") or "").strip()
    harrison = item.get("harrison") if isinstance(item.get("harrison"), dict) else {}
    chapter = harrison.get("chapter")
    title = str(harrison.get("title") or "").strip()
    if not ID_PATTERN.fullmatch(concept_id) or not ko or chapter is None or not title:
        return None
    if isinstance(chapter, bool) or not isinstance(chapter, (int, str)):
        return None
    chapter_text = str(chapter).strip()
    if not chapter_text or len(chapter_text) > 24:
        return None
    return {
        "id": concept_id,
        "ko": ko,
        "harrison": {key: harrison.get(key) for key in HARRISON_REF_KEYS},
    }


def load_candidates(worklist_path: Path, current_map_path: Path) -> list[dict[str, Any]]:
    worklist = read_json(worklist_path)
    current = read_json(current_map_path)
    items = worklist.get("items")
    axes = current.get("axes")
    if not isinstance(items, list):
        raise BatchError(f"worklist.items must be an array: {worklist_path}")
    if not isinstance(axes, dict):
        raise BatchError(f"current map axes must be an object: {current_map_path}")

    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        clean = candidate_record(item)
        if not clean or clean["id"] in axes or clean["id"] in seen:
            continue
        seen.add(clean["id"])
        candidates.append(clean)
    return candidates


def parse_slice(value: str) -> slice:
    match = re.fullmatch(r"(\d*):(\d*)", value.strip())
    if not match:
        raise argparse.ArgumentTypeError("slice must use START:STOP, for example 0:12")
    start = int(match.group(1)) if match.group(1) else None
    stop = int(match.group(2)) if match.group(2) else None
    if start is not None and stop is not None and stop < start:
        raise argparse.ArgumentTypeError("slice STOP must be greater than or equal to START")
    return slice(start, stop)


def parse_id_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if not isinstance(payload, list) or not all(isinstance(value, str) for value in payload):
            raise BatchError("--ids-file JSON must be an array of concept-id strings")
        values = payload
    else:
        values = [line.strip() for line in text.splitlines() if line.strip()]
    invalid = [value for value in values if not ID_PATTERN.fullmatch(value)]
    if invalid:
        raise BatchError(f"--ids-file contains non-ID content: {invalid[:3]}")
    return values


def normalized_requested_ids(cli_values: Sequence[str], ids_file: Path | None) -> list[str]:
    values: list[str] = []
    for raw in cli_values:
        values.extend(part.strip() for part in raw.split(",") if part.strip())
    if ids_file:
        values.extend(parse_id_file(ids_file))
    invalid = [value for value in values if not ID_PATTERN.fullmatch(value)]
    if invalid:
        raise BatchError(f"Invalid concept id(s): {invalid[:5]}")
    return list(dict.fromkeys(values))


def select_candidates(
    candidates: Sequence[dict[str, Any]],
    *,
    requested_ids: Sequence[str] = (),
    selection_slice: slice | None = None,
) -> list[dict[str, Any]]:
    if requested_ids and selection_slice is not None:
        raise BatchError("Use either --ids/--ids-file or --slice, not both")
    by_id = {row["id"]: row for row in candidates}
    if requested_ids:
        missing = [concept_id for concept_id in requested_ids if concept_id not in by_id]
        if missing:
            raise BatchError(
                "Requested ids are not un-authored Harrison-grounded candidates: "
                + ", ".join(missing[:10])
            )
        return [by_id[concept_id] for concept_id in requested_ids]
    return list(candidates[selection_slice or slice(0, None)])


def chunks(values: Sequence[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(values), size):
        yield list(values[index : index + size])


def response_schema(chunk_size: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["axes"],
        "properties": {
            "axes": {
                "type": "array",
                "minItems": 1,
                "maxItems": chunk_size,
                "items": AXIS_SCHEMA,
            }
        },
    }


def build_prompt(records: Sequence[dict[str, Any]]) -> str:
    """Build a prompt after reducing local references to the four-field boundary."""
    safe: list[dict[str, Any]] = []
    for record in records:
        if set(record) != {"id", "ko", "harrison"}:
            raise BatchError("Internal privacy guard rejected an unsanitized record")
        harrison = record.get("harrison")
        if not isinstance(harrison, dict) or set(harrison) != set(HARRISON_REF_KEYS):
            raise BatchError("Internal privacy guard rejected Harrison metadata")
        safe.append(
            {
                "id": record["id"],
                "ko": record["ko"],
                "harrison": {
                    "chapter": harrison["chapter"],
                    "title": harrison["title"],
                },
            }
        )
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(AUTHORING_RULES, 1))
    inputs = json.dumps(safe, ensure_ascii=False, indent=2)
    return f"""Create clinical-axis drafts for the sanitized concepts below.

Rules:
{rules}

Sanitized inputs (the complete available input):
{inputs}
"""


def parse_version(text: str) -> tuple[int, int, int]:
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", text)
    if not match:
        raise BatchError(f"Could not parse Claude CLI version: {text.strip()!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def claude_version(claude_bin: str) -> tuple[tuple[int, int, int], str]:
    completed = subprocess.run(
        [claude_bin, "--version"],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    text = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        raise BatchError(f"Claude CLI version check failed: {text[:300]}")
    return parse_version(text), text


def extract_structured_output(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BatchError(f"Claude CLI returned non-JSON output: {exc}") from exc
    if not isinstance(payload, dict):
        raise BatchError("Claude CLI JSON envelope must be an object")

    structured = payload.get("structured_output")
    if isinstance(structured, dict):
        return structured
    result = payload.get("result")
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            decoded = json.loads(result)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            return decoded
    if isinstance(payload.get("axes"), list):
        return payload
    raise BatchError("Claude CLI JSON envelope contains no structured_output object")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any, *, minimum: int = 0, maximum: int) -> bool:
    return (
        isinstance(value, list)
        and minimum <= len(value) <= maximum
        and all(_nonempty_string(item) for item in value)
    )


def validate_axis(axis: Any, expected_id: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(axis, dict):
        return ["record must be an object"]
    required = set(AXIS_SCHEMA["required"])
    extra = set(axis) - required
    missing = required - set(axis)
    if missing:
        errors.append("missing fields: " + ", ".join(sorted(missing)))
    if extra:
        errors.append("unexpected fields: " + ", ".join(sorted(extra)))
    if axis.get("id") != expected_id:
        errors.append(f"id must equal {expected_id!r}")
    if axis.get("needs_review") is not True:
        errors.append("needs_review must be true")

    path = axis.get("pathophysiology")
    if not isinstance(path, dict) or set(path) != {"summary", "key_steps"}:
        errors.append("pathophysiology must contain only summary and key_steps")
    elif not _nonempty_string(path.get("summary")) or not _string_list(
        path.get("key_steps"), minimum=2, maximum=8
    ):
        errors.append("pathophysiology summary/key_steps are incomplete")

    if not _string_list(axis.get("risk_factors"), minimum=1, maximum=12):
        errors.append("risk_factors must contain 1-12 non-empty strings")

    prognosis = axis.get("prognosis")
    prognosis_keys = {"factors", "staging_or_grading", "natural_history"}
    if not isinstance(prognosis, dict) or set(prognosis) != prognosis_keys:
        errors.append("prognosis has an invalid shape")
    elif (
        not _string_list(prognosis.get("factors"), minimum=1, maximum=10)
        or not _nonempty_string(prognosis.get("staging_or_grading"))
        or not _nonempty_string(prognosis.get("natural_history"))
    ):
        errors.append("prognosis fields are incomplete")

    treatment = axis.get("treatment")
    treatment_keys = {"principles", "indicated_for", "contraindicated_for"}
    if not isinstance(treatment, dict) or set(treatment) != treatment_keys:
        errors.append("treatment has an invalid shape")
    elif (
        not _nonempty_string(treatment.get("principles"))
        or not _string_list(treatment.get("indicated_for"), minimum=1, maximum=12)
        or not _string_list(treatment.get("contraindicated_for"), maximum=10)
    ):
        errors.append("treatment fields are incomplete")

    epidemiology = axis.get("epidemiology")
    epidemiology_keys = {"age", "sex", "population", "frequency"}
    if not isinstance(epidemiology, dict) or set(epidemiology) != epidemiology_keys:
        errors.append("epidemiology has an invalid shape")
    else:
        for key in sorted(epidemiology_keys):
            value = epidemiology.get(key)
            if not _nonempty_string(value):
                errors.append(f"epidemiology.{key} must be a non-empty string")
            elif PRECISE_EPIDEMIOLOGY_PATTERN.search(value):
                errors.append(f"epidemiology.{key} must be qualitative (no digits/percentages)")

    if not _string_list(axis.get("uncertainty_notes"), maximum=8):
        errors.append("uncertainty_notes must be an array of up to 8 non-empty strings")
    return errors


def validate_response(
    payload: dict[str, Any], expected_ids: Sequence[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    rows = payload.get("axes")
    if not isinstance(rows, list):
        return {}, ["structured output axes must be an array"]
    expected = set(expected_ids)
    valid: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, row in enumerate(rows):
        concept_id = row.get("id") if isinstance(row, dict) else None
        if not isinstance(concept_id, str) or concept_id not in expected:
            errors.append(f"axes[{index}] has an unexpected id")
            continue
        if concept_id in valid:
            errors.append(f"duplicate axis record: {concept_id}")
            continue
        row_errors = validate_axis(row, concept_id)
        if row_errors:
            errors.extend(f"{concept_id}: {message}" for message in row_errors)
            continue
        valid[concept_id] = row
    for concept_id in expected_ids:
        if concept_id not in valid:
            errors.append(f"missing valid axis record: {concept_id}")
    return valid, errors


def invoke_claude(
    records: Sequence[dict[str, Any]],
    *,
    claude_bin: str,
    model: str,
    timeout_seconds: int,
    max_budget_usd: float | None,
) -> dict[str, Any]:
    schema = json.dumps(response_schema(len(records)), ensure_ascii=False, separators=(",", ":"))
    command = [
        claude_bin,
        "-p",
        "--model",
        model,
        "--effort",
        "low",
        "--output-format",
        "json",
        "--json-schema",
        schema,
        "--system-prompt",
        SYSTEM_PROMPT,
        "--tools",
        "",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--no-chrome",
        "--strict-mcp-config",
        "--setting-sources",
        "",
    ]
    if max_budget_usd is not None:
        command.extend(["--max-budget-usd", str(max_budget_usd)])
    prompt = build_prompt(records)
    with tempfile.TemporaryDirectory(prefix="paccine-axes-") as temporary_cwd:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            cwd=temporary_cwd,
            timeout=timeout_seconds,
            check=False,
            env=os.environ.copy(),
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown Claude CLI error").strip()
        raise BatchError(f"Claude CLI exited {completed.returncode}: {detail[:800]}")
    return extract_structured_output(completed.stdout)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def new_payload(
    selected: Sequence[dict[str, Any]], args: argparse.Namespace, cli_version_text: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "_meta": {
            "authoring_method": "Claude Code CLI structured JSON",
            "claude_cli_required": MIN_CLAUDE_VERSION_TEXT,
            "claude_cli_version": cli_version_text,
            "model": args.model,
            "privacy": (
                "Only concept id, Korean name, and Harrison chapter/title metadata were sent; "
                "no question text or source-document text was read or transmitted."
            ),
            "worklist": str(args.worklist),
            "current_map": str(args.current_map),
            "batch_size": len(selected),
            "chunk_size": args.chunk_size,
            "needs_review": True,
            "rules": list(AUTHORING_RULES),
            "created_at": utc_now(),
        },
        "axes": {},
        "harrison_refs": {
            row["id"]: {key: row["harrison"].get(key) for key in HARRISON_REF_KEYS}
            for row in selected
        },
        "_progress": {
            "selected_ids": [row["id"] for row in selected],
            "completed_ids": [],
            "failures": [],
            "attempts": 0,
            "updated_at": utc_now(),
        },
    }


def update_progress(payload: dict[str, Any]) -> None:
    axes = payload.get("axes") if isinstance(payload.get("axes"), dict) else {}
    progress = payload.setdefault("_progress", {})
    selected = progress.get("selected_ids") if isinstance(progress.get("selected_ids"), list) else []
    progress["completed_ids"] = [concept_id for concept_id in selected if concept_id in axes]
    progress["updated_at"] = utc_now()


def resume_payload(path: Path, selected: Sequence[dict[str, Any]]) -> dict[str, Any]:
    payload = read_json(path)
    axes = payload.get("axes")
    progress = payload.get("_progress")
    if not isinstance(axes, dict) or not isinstance(progress, dict):
        raise BatchError("Resume file is missing axes/_progress objects")
    selected_ids = [row["id"] for row in selected]
    if progress.get("selected_ids") != selected_ids:
        raise BatchError("Resume selection differs from the batch's saved selected_ids")
    for concept_id, axis in axes.items():
        errors = validate_axis(axis, concept_id)
        if errors:
            raise BatchError(f"Resume file contains invalid saved axis {concept_id}: {errors[0]}")
    update_progress(payload)
    return payload


def run(args: argparse.Namespace) -> int:
    candidates = load_candidates(args.worklist, args.current_map)
    requested = normalized_requested_ids(args.ids, args.ids_file)

    saved_selection: list[str] = []
    if args.resume and args.output.exists() and not requested and args.selection_slice is None:
        existing = read_json(args.output)
        progress = existing.get("_progress") or {}
        if isinstance(progress.get("selected_ids"), list):
            saved_selection = [str(value) for value in progress["selected_ids"]]
            requested = saved_selection

    selected = select_candidates(
        candidates,
        requested_ids=requested,
        selection_slice=args.selection_slice,
    )
    if not selected:
        raise BatchError("Selection is empty; all requested concepts may already be authored")
    if len(selected) > args.max_concepts:
        raise BatchError(
            f"Selection has {len(selected)} concepts; use --slice/--ids or raise --max-concepts "
            f"(current cap {args.max_concepts})"
        )

    cli_path = shutil.which(args.claude_bin) if not Path(args.claude_bin).is_file() else args.claude_bin
    version_tuple: tuple[int, int, int] | None = None
    version_text = "not checked (dry-run)"
    if cli_path:
        try:
            version_tuple, version_text = claude_version(str(cli_path))
        except BatchError:
            if not args.dry_run:
                raise
    elif not args.dry_run:
        raise BatchError(f"Claude CLI not found: {args.claude_bin}")

    if args.dry_run:
        summary = {
            "mode": "dry-run",
            "available_unwritten_harrison_grounded": len(candidates),
            "selected_count": len(selected),
            "selected_ids": [row["id"] for row in selected],
            "chunk_size": args.chunk_size,
            "chunks": (len(selected) + args.chunk_size - 1) // args.chunk_size,
            "claude_cli_detected": version_text,
            "claude_cli_required": MIN_CLAUDE_VERSION_TEXT,
            "claude_binary": str(cli_path or args.claude_bin),
            "model": args.model,
            "effort": "low",
            "would_write": str(args.output),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.prompt_preview:
            for index, group in enumerate(chunks(selected, args.chunk_size), 1):
                print(f"\n--- sanitized prompt chunk {index} ---")
                print(build_prompt(group))
        return 0

    if version_tuple is None or version_tuple < MIN_CLAUDE_VERSION:
        raise BatchError(
            f"Claude Code CLI {MIN_CLAUDE_VERSION_TEXT}+ is required; detected {version_text}. "
            "Update the Desktop/CLI installation before authoring."
        )
    if args.output.exists() and not args.resume:
        raise BatchError(f"Output already exists; pass --resume or choose another --output: {args.output}")

    payload = resume_payload(args.output, selected) if args.resume and args.output.exists() else new_payload(
        selected, args, version_text
    )
    if args.resume:
        payload.setdefault("_meta", {})["chunk_size"] = args.chunk_size
        payload["_meta"]["rules"] = list(AUTHORING_RULES)
        payload["_meta"]["resumed_at"] = utc_now()
    atomic_write_json(args.output, payload)
    completed = set(payload["axes"])
    remaining = [row for row in selected if row["id"] not in completed]

    for chunk_number, initial_group in enumerate(chunks(remaining, args.chunk_size), 1):
        pending = list(initial_group)
        for attempt in range(1, args.retries + 2):
            if not pending:
                break
            payload["_progress"]["attempts"] = int(payload["_progress"].get("attempts") or 0) + 1
            pending_ids = [row["id"] for row in pending]
            try:
                response = invoke_claude(
                    pending,
                    claude_bin=str(cli_path),
                    model=args.model,
                    timeout_seconds=args.timeout,
                    max_budget_usd=args.max_budget_usd,
                )
                valid, validation_errors = validate_response(response, pending_ids)
                payload["axes"].update(valid)
                pending = [row for row in pending if row["id"] not in valid]
                if validation_errors:
                    payload["_progress"]["failures"].append(
                        {
                            "chunk": chunk_number,
                            "attempt": attempt,
                            "ids": pending_ids,
                            "error": "; ".join(validation_errors)[:1200],
                        }
                    )
            except (BatchError, subprocess.TimeoutExpired) as exc:
                payload["_progress"]["failures"].append(
                    {
                        "chunk": chunk_number,
                        "attempt": attempt,
                        "ids": pending_ids,
                        "error": str(exc)[:1200],
                    }
                )
            update_progress(payload)
            atomic_write_json(args.output, payload)
            if pending and attempt <= args.retries:
                time.sleep(args.retry_delay)

        if pending and args.fail_fast:
            break

    update_progress(payload)
    atomic_write_json(args.output, payload)
    selected_ids = payload["_progress"]["selected_ids"]
    incomplete = [concept_id for concept_id in selected_ids if concept_id not in payload["axes"]]
    print(
        json.dumps(
            {
                "output": str(args.output),
                "selected": len(selected_ids),
                "completed": len(payload["axes"]),
                "incomplete_ids": incomplete,
                "needs_review": True,
            },
            ensure_ascii=False,
        )
    )
    return 2 if incomplete else 0


def default_output() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_OUTPUT_DIR / f"claude_axes_{timestamp}.json"


def default_claude_binary() -> str:
    """Prefer the version-pinned binary bundled by Claude Desktop."""
    desktop = (
        Path.home()
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude-code"
        / MIN_CLAUDE_VERSION_TEXT
        / "claude.app"
        / "Contents"
        / "MacOS"
        / "claude"
    )
    if desktop.is_file():
        return str(desktop)
    installed = shutil.which("claude")
    return installed or "claude"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Author a standalone, review-gated clinical-axis batch via Claude Code CLI."
    )
    parser.add_argument("--worklist", type=Path, default=DEFAULT_WORKLIST)
    parser.add_argument("--current-map", type=Path, default=DEFAULT_CURRENT_MAP)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--slice", dest="selection_slice", type=parse_slice, default=None)
    parser.add_argument(
        "--ids",
        action="append",
        default=[],
        metavar="ID[,ID...]",
        help="Select explicit concept ids; repeat or use comma-separated ids.",
    )
    parser.add_argument("--ids-file", type=Path, default=None)
    parser.add_argument("--chunk-size", type=int, default=3)
    parser.add_argument("--max-concepts", type=int, default=30)
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--claude-bin", default=default_claude_binary())
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument("--max-budget-usd", type=float, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prompt-preview", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.chunk_size <= MAX_CHUNK_SIZE:
        parser.error(f"--chunk-size must be between 1 and {MAX_CHUNK_SIZE}")
    if args.max_concepts < 1:
        parser.error("--max-concepts must be positive")
    if args.timeout < 1 or args.retries < 0 or args.retry_delay < 0:
        parser.error("timeout/retries/retry-delay values are invalid")
    if args.prompt_preview and not args.dry_run:
        parser.error("--prompt-preview is only available with --dry-run")
    if args.resume and args.output is None:
        parser.error("--resume requires an explicit --output path")
    args.worklist = args.worklist.resolve()
    args.current_map = args.current_map.resolve()
    args.output = args.output.resolve() if args.output else default_output().resolve()
    args.ids_file = args.ids_file.resolve() if args.ids_file else None
    try:
        return run(args)
    except (BatchError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
