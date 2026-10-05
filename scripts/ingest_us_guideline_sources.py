#!/usr/bin/env python3
"""Build a private, fail-closed registry for selected U.S. guideline sources.

The seed list is deliberately small and curated.  Society/journal material is
metadata-only unless the source's rights statement explicitly permits a local
private snapshot.  No downloaded file or summary is automatically available to
RAG, question generation, students, or clinical decision support.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from jsonschema import Draft7Validator, FormatChecker
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "us_guideline_source_registry.schema.json"
DEFAULT_SEED = ROOT / "data_private" / "us_guidelines" / "seeds" / "core_sources.json"
DEFAULT_OUTPUT = ROOT / "data_private" / "us_guidelines" / "verified_latest_registry.json"
DEFAULT_FILES = ROOT / "data_private" / "us_guidelines" / "source_files" / "latest"
MAX_BYTES = 80 * 1024 * 1024

# Only hosts whose official reuse policy was reviewed may be mirrored.  Other
# official sources can still exist in the registry as metadata-only records.
DOWNLOAD_HOST_ALLOWLIST = {
    "cdc.gov",
    "www.cdc.gov",
    "uspreventiveservicestaskforce.org",
    "www.uspreventiveservicestaskforce.org",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned[:140] or "source"


def validate_registry(payload: dict, *, label: str) -> None:
    validator = Draft7Validator(load_json(SCHEMA), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        detail = "\n".join(f"{list(error.path)}: {error.message}" for error in errors[:40])
        raise ValueError(f"{label}: schema validation failed ({len(errors)} errors)\n{detail}")


def normalize_attachment(row: dict) -> dict:
    attachment = dict(row)
    attachment.setdefault("download_status", "not_requested")
    attachment.setdefault("relative_path", None)
    attachment.setdefault("bytes", None)
    attachment.setdefault("sha256", None)
    attachment.setdefault("content_type", None)
    attachment.setdefault("pdf_pages", None)
    attachment.setdefault("pdf_text_chars", None)
    attachment.setdefault("error", None)
    return attachment


def inspect_pdf(path: Path) -> tuple[int | None, int | None, str | None]:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            return len(reader.pages), 0, "encrypted_pdf"
        text_chars = 0
        for page in reader.pages:
            text_chars += len(page.extract_text() or "")
        return len(reader.pages), text_chars, None
    except Exception as exc:
        return None, None, f"{type(exc).__name__}:{exc}"


def download_attachment(
    session: requests.Session,
    source: dict,
    attachment: dict,
    *,
    files_dir: Path,
    overwrite: bool,
) -> dict:
    row = normalize_attachment(attachment)
    rights = source["rights"]
    if not row["public_download"] or not row["private_snapshot_authorized"]:
        row.update(download_status="metadata_only", error="source_or_rights_policy_metadata_only")
        return row
    if rights.get("local_private_snapshot_allowed") is not True:
        row.update(download_status="restricted", error="local_private_snapshot_not_authorized")
        return row

    parsed = urlparse(row["source_url"])
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        row.update(download_status="restricted", error="non_https_source_url")
        return row
    if host not in DOWNLOAD_HOST_ALLOWLIST:
        row.update(download_status="restricted", error=f"download_host_not_allowlisted:{host}")
        return row

    source_dir = files_dir / safe_component(source["source_id"])
    source_dir.mkdir(parents=True, exist_ok=True)
    destination = source_dir / safe_component(row["filename"])
    temporary = destination.with_suffix(destination.suffix + ".part")

    try:
        if overwrite or not destination.exists():
            with session.get(row["source_url"], stream=True, timeout=(20, 180), allow_redirects=True) as response:
                response.raise_for_status()
                final_host = (urlparse(response.url).hostname or "").lower()
                if final_host not in DOWNLOAD_HOST_ALLOWLIST:
                    raise ValueError(f"redirect_host_not_allowlisted:{final_host}")
                announced = response.headers.get("content-length")
                if announced and int(announced) > MAX_BYTES:
                    raise ValueError(f"content_too_large:{announced}")
                written = 0
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > MAX_BYTES:
                            raise ValueError(f"content_too_large:{written}")
                        handle.write(chunk)
                if row["file_type"] == "pdf" and not temporary.read_bytes()[:5] == b"%PDF-":
                    raise ValueError("file_signature_mismatch:not_pdf")
                os.replace(temporary, destination)

        row.update(
            download_status="downloaded",
            relative_path=display_path(destination),
            bytes=destination.stat().st_size,
            sha256=sha256_path(destination),
            content_type="application/pdf" if row["file_type"] == "pdf" else None,
            error=None,
        )
        if row["file_type"] == "pdf":
            pages, text_chars, error = inspect_pdf(destination)
            row.update(pdf_pages=pages, pdf_text_chars=text_chars)
            if error:
                row.update(download_status="failed", error=f"pdf_inspection_failed:{error}")
    except Exception as exc:
        if temporary.exists():
            temporary.unlink()
        row.update(download_status="failed", error=f"{type(exc).__name__}:{exc}")
    return row


def build_summary(sources: list[dict]) -> dict:
    attachments = [item for source in sources for item in source["attachments"]]
    return {
        "sources": len(sources),
        "attachments": len(attachments),
        "issuing_bodies": dict(sorted(Counter(source["issuing_body"] for source in sources).items())),
        "priorities": dict(sorted(Counter(source["priority"] for source in sources).items())),
        "latest_statuses": dict(sorted(Counter(source["latest_status"] for source in sources).items())),
        "download_statuses": dict(sorted(Counter(item["download_status"] for item in attachments).items())),
        "downloaded_bytes": sum(item.get("bytes") or 0 for item in attachments if item["download_status"] == "downloaded"),
        "runtime_ingest_allowed_sources": sum(bool(source["rights"]["runtime_ingest_allowed"]) for source in sources),
        "medical_approval": sum(bool(source["medical_approval"]) for source in sources),
        "student_visible": sum(bool(source["student_visible"]) for source in sources),
        "generation_eligible": sum(bool(source["generation_eligible"]) for source in sources),
    }


def ingest(args: argparse.Namespace) -> dict:
    seed = load_json(args.seed)
    sources = seed.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"{args.seed}: expected non-empty sources list")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Paccine-US-Guideline-Registry/1.0 (private research inventory)",
            "Accept": "application/pdf,*/*;q=0.5",
        }
    )
    for source in sources:
        source["attachments"] = [
            download_attachment(
                session,
                source,
                attachment,
                files_dir=args.files_dir,
                overwrite=args.overwrite,
            )
            if args.download
            else normalize_attachment(attachment)
            for attachment in source.get("attachments", [])
        ]

    payload = {
        "schema_version": "us_guideline_source_registry.v1",
        "generated_at": utc_now(),
        "latest_checked_at": seed.get("latest_checked_at") or date.today().isoformat(),
        "registry_role": "source_inventory_and_comparison_overlay_not_medical_approval",
        "jurisdiction_policy": {
            "primary_for_korean_care": False,
            "permitted_roles": ["gap_fill", "kr_us_comparison", "us_exam_mode", "research_review"],
            "silent_merge_allowed": False,
        },
        "catalog": {
            "scope": "selected_high_value_official_us_sources_not_exhaustive",
            "seed": display_path(args.seed),
            "seed_sha256": sha256_path(args.seed),
            "selection_note": seed.get("selection_note"),
            "rights_policy": (
                "Public web access is not permission for AI indexing, redistribution, derivative products, "
                "or commercial reuse. Metadata-only is the default."
            ),
        },
        "summary": build_summary(sources),
        "safety_boundary": {
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "generation_eligible": False,
            "runtime_ingest_enabled": False,
            "automatic_claim_promotion": False,
        },
        "sources": sources,
    }
    validate_registry(payload, label="U.S. guideline registry")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    failures: dict[str, list[dict]] = defaultdict(list)
    for source in sources:
        for attachment in source["attachments"]:
            if attachment["download_status"] != "downloaded":
                failures[attachment["download_status"]].append(
                    {
                        "source_id": source["source_id"],
                        "attachment_id": attachment["attachment_id"],
                        "source_url": attachment["source_url"],
                        "error": attachment.get("error"),
                    }
                )
    review = {
        "schema_version": "us_guideline_download_review.v1",
        "generated_at": utc_now(),
        "registry": display_path(args.output),
        "counts": {key: len(value) for key, value in sorted(failures.items())},
        "items": {key: value for key, value in sorted(failures.items())},
        "medical_approval": False,
        "runtime_ingest_enabled": False,
    }
    args.output.with_name("download_review_queue.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def check(args: argparse.Namespace) -> None:
    payload = load_json(args.output)
    validate_registry(payload, label="existing U.S. guideline registry")
    errors: list[str] = []
    for source in payload["sources"]:
        for attachment in source["attachments"]:
            if attachment["download_status"] != "downloaded":
                continue
            path = ROOT / attachment["relative_path"]
            if not path.exists():
                errors.append(f"missing:{attachment['attachment_id']}")
            elif sha256_path(path) != attachment["sha256"]:
                errors.append(f"sha256_mismatch:{attachment['attachment_id']}")
            if source["rights"]["runtime_ingest_allowed"] is not False:
                errors.append(f"runtime_rights_open:{source['source_id']}")
    if payload["safety_boundary"]["runtime_ingest_enabled"] is not False:
        errors.append("runtime_ingest_enabled")
    if errors:
        raise SystemExit("us_guideline_check_failed\n" + "\n".join(errors))
    print(
        f"us_guideline_registry_ok sources={len(payload['sources'])} "
        f"downloaded={payload['summary']['download_statuses'].get('downloaded', 0)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--files-dir", type=Path, default=DEFAULT_FILES)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.check:
        check(arguments)
    else:
        result = ingest(arguments)
        print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
