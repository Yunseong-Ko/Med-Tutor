#!/usr/bin/env python3
"""Correct legacy 21e labels/URLs after confirming the source is Harrison 22e.

The original mapping metadata was copied into several derived JSON artifacts
(lecture anchors, cards, question packs, and concept notes).  Canonical mapping
objects receive full snapshot provenance below; derived artifacts receive only
the mechanical edition/link correction.  Keys prefixed with ``legacy_`` are
left untouched so the audit trail remains available.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
SNAPSHOT = DP / "harrison" / "22e"
SEED = DP / "harrison" / "concept_to_harrison.json"
EXPANSION = DP / "curriculum" / "expansion_harrison_map.json"
BOOK_ID = "3541"
LEGACY_BOOK_ID = "3095"


def corrected_url(value: object) -> str | None:
    if not value:
        return None
    parsed = urlparse(str(value))
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["book"] = [BOOK_ID]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def normalize_derived_value(value: object, *, key: str = "") -> tuple[object, int]:
    """Recursively correct copied 21e labels and AccessMedicine book IDs."""
    if key.startswith("legacy_"):
        return value, 0
    if isinstance(value, dict):
        changed = 0
        normalized: dict = {}
        for child_key, child_value in value.items():
            new_value, child_changed = normalize_derived_value(child_value, key=str(child_key))
            normalized[child_key] = new_value
            changed += child_changed
        return normalized, changed
    if isinstance(value, list):
        changed = 0
        normalized_list = []
        for child_value in value:
            new_value, child_changed = normalize_derived_value(child_value, key=key)
            normalized_list.append(new_value)
            changed += child_changed
        return normalized_list, changed
    if key == "bookid" and str(value) == LEGACY_BOOK_ID:
        return (int(BOOK_ID) if isinstance(value, int) else BOOK_ID), 1
    if isinstance(value, str):
        normalized_text = value.replace("local Harrison 21e", "local Harrison 22e")
        normalized_text = normalized_text.replace("Harrison 21e", "Harrison 22e")
        normalized_text = normalized_text.replace(f"book={LEGACY_BOOK_ID}", f"book={BOOK_ID}")
        normalized_text = normalized_text.replace(f"bookid={LEGACY_BOOK_ID}", f"bookid={BOOK_ID}")
        normalized_text = normalized_text.replace(f"/book/{LEGACY_BOOK_ID}", f"/book/{BOOK_ID}")
        return normalized_text, int(normalized_text != value)
    return value, 0


def normalize_derived_artifacts() -> tuple[int, int]:
    """Update copied provenance in private derived JSON without approving claims."""
    files_updated = 0
    values_updated = 0
    for path in sorted(DP.rglob("*.json")):
        if SNAPSHOT in path.parents or path in {SEED, EXPANSION}:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        normalized, changed = normalize_derived_value(payload)
        if not changed:
            continue
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        files_updated += 1
        values_updated += changed
    return files_updated, values_updated


def normalize_reference(ref: dict, chapter_index: dict[int, dict], snapshot_id: str) -> dict:
    row = dict(ref)
    for key, value in list(row.items()):
        if isinstance(value, str) and "Harrison 21e" in value and key != "legacy_accessmedicine":
            row[key] = value.replace("Harrison 21e", "Harrison 22e")
    chapter = ref.get("chapter")
    if chapter is None:
        row["edition"] = "22e"
        row["source_id"] = snapshot_id
        row["needs_review"] = True
        return row
    source = chapter_index.get(int(chapter))
    if not source:
        raise ValueError(f"mapped chapter absent from Harrison 22e snapshot: {chapter}")
    if ref.get("page") != source.get("toc_printed_page"):
        raise ValueError(
            f"printed page mismatch for Ch.{chapter}: {ref.get('page')} != {source.get('toc_printed_page')}"
        )
    legacy_url = row.get("accessmedicine")
    if legacy_url and "book=3095" in str(legacy_url):
        row["legacy_accessmedicine"] = legacy_url
    row["accessmedicine"] = corrected_url(legacy_url)
    row["edition"] = "22e"
    row["source_id"] = snapshot_id
    row["source_file"] = source.get("source_file")
    row["source_file_sha256"] = source.get("source_file_sha256")
    row["needs_review"] = True
    return row


def normalize() -> dict:
    manifest = json.loads((SNAPSHOT / "snapshot_manifest.json").read_text(encoding="utf-8"))
    chapters = json.loads((SNAPSHOT / "chapter_index.json").read_text(encoding="utf-8"))["chapters"]
    chapter_index = {int(row["chapter"]): row for row in chapters}
    snapshot_id = manifest["snapshot_id"]

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    old_source = seed.get("source")
    seed["legacy_source_label"] = old_source
    seed["source"] = "Harrison 22e TOC; legacy edition label corrected 2026-07-17"
    seed["edition"] = "22e"
    seed["bookid"] = BOOK_ID
    seed["source_snapshot_id"] = snapshot_id
    seed["concept_to_harrison"] = {
        cid: normalize_reference(ref, chapter_index, snapshot_id)
        for cid, ref in sorted((seed.get("concept_to_harrison") or {}).items())
    }
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    expansion = json.loads(EXPANSION.read_text(encoding="utf-8"))
    expansion["source"] = "Harrison 22e TOC; provenance corrected 2026-07-17"
    expansion["edition"] = "22e"
    expansion["bookid"] = BOOK_ID
    expansion["source_snapshot_id"] = snapshot_id
    expansion["map"] = {
        cid: (normalize_reference(ref, chapter_index, snapshot_id) if ref else None)
        for cid, ref in sorted((expansion.get("map") or {}).items())
    }
    EXPANSION.write_text(
        json.dumps(expansion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    derived_files_updated, derived_values_updated = normalize_derived_artifacts()
    result = {
        "snapshot_id": snapshot_id,
        "seed_mappings": len(seed["concept_to_harrison"]),
        "expansion_mappings": sum(bool(ref) for ref in expansion["map"].values()),
        "edition": "22e",
        "bookid": BOOK_ID,
        "derived_files_updated": derived_files_updated,
        "derived_values_updated": derived_values_updated,
        "medical_approval": False,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


if __name__ == "__main__":
    normalize()
