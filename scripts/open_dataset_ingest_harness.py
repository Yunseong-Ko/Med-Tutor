#!/usr/bin/env python3
"""Create P:accine media asset drafts from an open dataset manifest.

This harness is intentionally conservative:
- It never crawls arbitrary pages.
- It skips providers that require manual access, such as most Grand Challenge archives.
- It downloads only direct URLs explicitly listed in the manifest when --download is passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


REQUIRED_DATASET_FIELDS = {
    "dataset_id",
    "name",
    "provider",
    "source_url",
    "license",
    "requires_manual_access",
    "download_policy",
    "entries",
}

REQUIRED_ENTRY_FIELDS = {
    "entry_id",
    "source_url",
    "asset_type",
    "modality",
    "body_system",
    "finding_labels",
}

MANUAL_PROVIDERS = {"grand_challenge"}
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_slug(value: str, field_name: str) -> None:
    if not SLUG_PATTERN.match(value):
        raise ValueError(f"{field_name} must match {SLUG_PATTERN.pattern}: {value}")


def _validate_manifest(manifest: dict[str, Any]) -> None:
    for field in ["manifest_version", "manifest_slug", "datasets"]:
        if field not in manifest:
            raise ValueError(f"Missing top-level field: {field}")

    _ensure_slug(str(manifest["manifest_slug"]), "manifest_slug")

    datasets = manifest["datasets"]
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("datasets must be a non-empty list")

    for dataset in datasets:
        missing = REQUIRED_DATASET_FIELDS - set(dataset)
        if missing:
            raise ValueError(f"Dataset is missing fields {sorted(missing)}")
        _ensure_slug(str(dataset["dataset_id"]), "dataset_id")
        if not isinstance(dataset["entries"], list):
            raise ValueError(f"{dataset['dataset_id']}.entries must be a list")

        for entry in dataset["entries"]:
            missing_entry = REQUIRED_ENTRY_FIELDS - set(entry)
            if missing_entry:
                raise ValueError(
                    f"{dataset['dataset_id']} entry is missing fields {sorted(missing_entry)}"
                )
            if not isinstance(entry["finding_labels"], list):
                raise ValueError(f"{entry['entry_id']}.finding_labels must be a list")


def _safe_filename(entry: dict[str, Any], url: str) -> str:
    explicit = entry.get("file_name")
    if explicit:
        return Path(str(explicit)).name

    parsed_name = Path(urlparse(url).path).name
    if parsed_name:
        return parsed_name

    return f"{entry['entry_id']}.bin"


def _download_direct_url(url: str, target_path: Path, max_file_mb: float) -> str:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = int(max_file_mb * 1024 * 1024)
    digest = hashlib.sha256()
    downloaded = 0
    request = Request(url, headers={"User-Agent": "PaccineDatasetHarness/0.1"})

    with urlopen(request, timeout=30) as response, target_path.open("wb") as f:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            downloaded += len(chunk)
            if downloaded > max_bytes:
                raise ValueError(
                    f"Download exceeds max_file_mb={max_file_mb}: {url}"
                )
            digest.update(chunk)
            f.write(chunk)

    return digest.hexdigest()


def _make_asset_id(dataset_id: str, entry_id: str) -> str:
    raw = f"{dataset_id}:{entry_id}".encode("utf-8")
    suffix = hashlib.sha1(raw).hexdigest()[:10]
    return f"asset_{dataset_id}_{entry_id}_{suffix}"


def _entry_to_asset(
    *,
    dataset: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    download: bool,
    max_file_mb: float,
) -> dict[str, Any]:
    provider = str(dataset["provider"])
    requires_manual_access = bool(dataset["requires_manual_access"]) or provider in MANUAL_PROVIDERS
    direct_url = entry.get("direct_download_url")
    ingestion_status = "metadata_only"
    file_path = None
    file_hash = None

    if requires_manual_access:
        ingestion_status = "manual_access_required"
    elif download:
        if not direct_url:
            ingestion_status = "skipped_no_direct_download_url"
        elif dataset["download_policy"] not in {"direct_urls_only"}:
            ingestion_status = "skipped_policy_not_direct_url"
        else:
            filename = _safe_filename(entry, str(direct_url))
            target_path = output_dir / "files" / str(dataset["dataset_id"]) / filename
            file_hash = _download_direct_url(str(direct_url), target_path, max_file_mb)
            file_path = str(target_path)
            ingestion_status = "downloaded"
    elif direct_url:
        ingestion_status = "not_downloaded_direct_url_available"

    return {
        "asset_id": _make_asset_id(str(dataset["dataset_id"]), str(entry["entry_id"])),
        "source_dataset": dataset["name"],
        "source_dataset_id": dataset["dataset_id"],
        "source_provider": provider,
        "source_url": entry["source_url"],
        "direct_download_url": direct_url,
        "license": dataset["license"],
        "license_url": dataset.get("license_url"),
        "terms_url": dataset.get("terms_url"),
        "citation": dataset.get("citation"),
        "usage_scope": dataset.get("usage_scope"),
        "asset_type": entry["asset_type"],
        "modality": entry["modality"],
        "body_system": entry["body_system"],
        "anatomy": entry.get("anatomy"),
        "diagnosis": entry.get("diagnosis"),
        "finding_labels": entry["finding_labels"],
        "caption": entry.get("caption"),
        "split": entry.get("split"),
        "deidentified": bool(entry.get("deidentified", False)),
        "approved_for_question_use": False,
        "review_status": "needs_review",
        "needs_manual_access": requires_manual_access,
        "ingestion_status": ingestion_status,
        "file_path": file_path,
        "file_hash": file_hash,
        "metadata": entry.get("metadata", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def build_draft(
    manifest: dict[str, Any],
    *,
    base_output_dir: Path,
    download: bool,
    max_file_mb: float,
) -> tuple[Path, list[dict[str, Any]]]:
    manifest_slug = str(manifest["manifest_slug"])
    output_dir = base_output_dir / manifest_slug
    draft_assets: list[dict[str, Any]] = []

    for dataset in manifest["datasets"]:
        for entry in dataset["entries"]:
            draft_assets.append(
                _entry_to_asset(
                    dataset=dataset,
                    entry=entry,
                    output_dir=output_dir,
                    download=download,
                    max_file_mb=max_file_mb,
                )
            )

    return output_dir / "media_assets.draft.json", draft_assets


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build P:accine media asset drafts from an open dataset manifest."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data_private/open_datasets"),
        help="Base output directory for draft metadata and optional files.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download only explicit direct_download_url values that do not require manual access.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print summary without writing output files.",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=25,
        help="Maximum size per downloaded file when --download is used.",
    )
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    _validate_manifest(manifest)

    draft_path, draft_assets = build_draft(
        manifest,
        base_output_dir=args.output_dir,
        download=args.download,
        max_file_mb=args.max_file_mb,
    )

    summary: dict[str, int] = {}
    for asset in draft_assets:
        status = str(asset["ingestion_status"])
        summary[status] = summary.get(status, 0) + 1

    if not args.dry_run:
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        with draft_path.open("w", encoding="utf-8") as f:
            json.dump(draft_assets, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "manifest": str(args.manifest),
        "draft_path": str(draft_path),
        "written": not args.dry_run,
        "asset_count": len(draft_assets),
        "status_counts": summary,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"open_dataset_ingest_harness error: {exc}", file=sys.stderr)
        raise SystemExit(1)
