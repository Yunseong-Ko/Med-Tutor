#!/usr/bin/env python3
"""Validate source/rule registries and build the curated item-writing RAG index."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_REGISTRY = ROOT / "data_private/item_writing/source_registry.json"
DEFAULT_RULE_REGISTRY = ROOT / "data_private/item_writing/rule_registry.json"
DEFAULT_OUTPUT = ROOT / "data_private/rag/item_writing/rag_index.json"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_registries(source_registry: dict[str, Any], rule_registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sources = source_registry.get("sources") if isinstance(source_registry.get("sources"), list) else []
    source_ids = {str(source.get("source_id")) for source in sources if isinstance(source, dict)}
    if len(source_ids) != len(sources):
        errors.append("duplicate_or_missing_source_id")

    for source in sources:
        path = Path(str(source.get("path") or "")).expanduser()
        if not path.exists():
            errors.append(f"missing_source:{source.get('source_id')}")
            continue
        if path.stat().st_size != int(source.get("bytes") or -1):
            errors.append(f"size_mismatch:{source.get('source_id')}")
        if _sha256(path) != str(source.get("sha256") or ""):
            errors.append(f"sha256_mismatch:{source.get('source_id')}")

    rules = rule_registry.get("rules") if isinstance(rule_registry.get("rules"), list) else []
    rule_ids = {str(rule.get("rule_id")) for rule in rules if isinstance(rule, dict)}
    if len(rule_ids) != len(rules):
        errors.append("duplicate_or_missing_rule_id")
    for rule in rules:
        for ref in rule.get("source_refs") or []:
            if str(ref.get("source_id") or "") not in source_ids:
                errors.append(f"unknown_source_ref:{rule.get('rule_id')}:{ref.get('source_id')}")
    routing = rule_registry.get("retrieval_routing") or {}
    for rule_id in routing.get("always_include_rule_ids") or []:
        if str(rule_id) not in rule_ids:
            errors.append(f"unknown_always_include_rule:{rule_id}")
    return errors


def build_index(source_registry: dict[str, Any], rule_registry: dict[str, Any]) -> dict[str, Any]:
    source_meta = {
        str(source["source_id"]): {
            "title": source.get("title"),
            "publisher": source.get("publisher"),
            "date_or_version": source.get("date_or_version"),
            "role": source.get("role"),
            "generation_visibility": source.get("generation_visibility"),
            "sha256": source.get("sha256"),
        }
        for source in source_registry.get("sources") or []
    }
    prompt_rules = []
    post_exam_rules = []
    for rule in rule_registry.get("rules") or []:
        compact = {
            "rule_id": rule.get("rule_id"),
            "title": rule.get("title"),
            "statement_ko": rule.get("statement_ko"),
            "stage": rule.get("stage"),
            "severity": rule.get("severity"),
            "exam_profiles": rule.get("exam_profiles") or [],
            "assessment_tasks": rule.get("assessment_tasks") or [],
            "tags": rule.get("tags") or [],
            "source_refs": rule.get("source_refs") or [],
            "prompt": bool((rule.get("runtime") or {}).get("prompt", False)),
            "validator": (rule.get("runtime") or {}).get("validator"),
            "fail_action": (rule.get("runtime") or {}).get("fail_action"),
        }
        if compact["prompt"]:
            prompt_rules.append(compact)
        else:
            post_exam_rules.append(compact)
    return {
        "schema_version": "paccine.item_writing_rag_index.v1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "safety": {
            "contains_raw_source_text": False,
            "contains_sample_item_text": False,
            "generation_payload": "curated_atomic_rules_only",
        },
        "profiles": rule_registry.get("profiles") or {},
        "conflict_resolutions": rule_registry.get("conflict_resolutions") or [],
        "retrieval_routing": rule_registry.get("retrieval_routing") or {},
        "sources": source_meta,
        "rules": prompt_rules,
        "post_exam_rules": post_exam_rules,
        "counts": {
            "sources": len(source_meta),
            "generation_rules": len(prompt_rules),
            "post_exam_rules": len(post_exam_rules),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE_REGISTRY)
    parser.add_argument("--rule-registry", type=Path, default=DEFAULT_RULE_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Validate only; do not write the index")
    args = parser.parse_args()

    sources = _read_json(args.source_registry)
    rules = _read_json(args.rule_registry)
    errors = validate_registries(sources, rules)
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    index = build_index(sources, rules)
    if not args.check:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(args.output)
    print(json.dumps(index["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
