#!/usr/bin/env python3
"""Ingest curated Korean guideline seeds into a private, auditable registry.

Only explicitly curated HTTPS URLs from official/publication hosts are fetched.
Downloaded files remain under ``data_private``.  A successful download proves
file integrity only; it never approves medical claims or enables generation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from jsonschema import Draft7Validator, FormatChecker
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "kr_guideline_source_registry.schema.json"
DEFAULT_SEED_DIR = ROOT / "data_private" / "kr_guidelines" / "seeds"
DEFAULT_OUTPUT = ROOT / "data_private" / "kr_guidelines" / "verified_latest_registry.json"
DEFAULT_FILES = ROOT / "data_private" / "kr_guidelines" / "source_files" / "latest"
MAX_BYTES = 250 * 1024 * 1024

# An allowlist is deliberate: a seed file is data, not permission to fetch an
# arbitrary URL.  Add a host only after checking that it is an official issuer,
# government repository, society journal, or the issuer's declared file host.
ALLOWED_HOSTS = {
    "accjournal.org",
    "www.accjournal.org",
    "aard.or.kr",
    "www.aard.or.kr",
    "cancer.go.kr",
    "www.cancer.go.kr",
    "cdn.medsoft.co.kr",
    "circulation.or.kr",
    "m.circulation.or.kr",
    "diabetes.or.kr",
    "www.diabetes.or.kr",
    "drive.google.com",
    "drive.usercontent.google.com",
    "e-enm.org",
    "www.e-enm.org",
    "ejgo.org",
    "www.ejgo.org",
    "guideline.or.kr",
    "www.guideline.or.kr",
    "k-hrs.org",
    "www.k-hrs.org",
    "kams.or.kr",
    "www.kams.or.kr",
    "kasid.org",
    "www.kasid.org",
    "eng.kasid.org",
    "kasl.org",
    "www.kasl.org",
    "kdca.go.kr",
    "www.kdca.go.kr",
    "kjim.org",
    "www.kjim.org",
    "koreamed.org",
    "synapse.koreamed.org",
    "koreanhypertension.org",
    "www.koreanhypertension.org",
    "kosso.or.kr",
    "general.kosso.or.kr",
    "ksmfm.or.kr",
    "www.ksmfm.or.kr",
    "ksmo.or.kr",
    "www.ksmo.or.kr",
    "ksn.or.kr",
    "www.ksn.or.kr",
    "lipid.or.kr",
    "www.lipid.or.kr",
    "lungkorea.org",
    "new.lungkorea.org",
    "nip.kdca.go.kr",
    "rheum.or.kr",
    "www.rheum.or.kr",
    "thyroid.kr",
    "www.thyroid.kr",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def validate_registry(payload: dict, *, label: str) -> None:
    schema = load_json(SCHEMA)
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        detail = "\n".join(
            f"{list(error.path)}: {error.message}" for error in errors[:30]
        )
        raise ValueError(f"{label}: schema validation failed ({len(errors)} errors)\n{detail}")


def load_seed_sources(seed_dir: Path) -> tuple[list[dict], list[dict]]:
    sources: dict[str, dict] = {}
    seed_files: list[dict] = []
    paths = sorted(seed_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"no JSON seed files found under {seed_dir}")
    for path in paths:
        payload = load_json(path)
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict) and isinstance(payload.get("sources"), list):
            validate_registry(payload, label=str(path))
            rows = payload["sources"]
        else:
            raise ValueError(f"{path}: expected a registry object or source list")
        seed_files.append(
            {
                "path": display_path(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_path(path),
                "sources": len(rows),
            }
        )
        for row in rows:
            source_id = row.get("source_id")
            if not source_id:
                raise ValueError(f"{path}: source without source_id")
            if source_id in sources and sources[source_id] != row:
                raise ValueError(f"conflicting duplicate source_id: {source_id}")
            sources[source_id] = row
    return [sources[key] for key in sorted(sources)], seed_files


def safe_component(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value[:140] or "source"


def extension_for(attachment: dict) -> str:
    filename = unquote(attachment.get("filename") or "")
    suffix = Path(filename).suffix.lower()
    if suffix and len(suffix) <= 10:
        return suffix
    file_type = re.sub(r"[^a-z0-9]+", "", str(attachment.get("file_type") or "").lower())
    return f".{file_type}" if file_type else ".bin"


def fetch_url_for(source_url: str) -> str:
    """Convert a public Google Drive view link to its official download host."""
    parsed = urlparse(source_url)
    if parsed.hostname == "drive.google.com":
        match = re.search(r"/file/d/([^/]+)", parsed.path)
        if match:
            file_id = match.group(1)
            return f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    return source_url


def magic_valid(path: Path, file_type: str) -> tuple[bool, str]:
    with path.open("rb") as handle:
        head = handle.read(16)
    normalized = file_type.lower().lstrip(".")
    if normalized == "pdf":
        return head.startswith(b"%PDF-"), head[:8].hex()
    if normalized in {"docx", "zip", "hwpx", "xlsx", "pptx"}:
        return head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"), head[:8].hex()
    if normalized in {"hwp", "doc", "xls", "ppt"}:
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        return head.startswith(ole), head[:8].hex()
    return len(head) > 0, head[:8].hex()


def inspect_pdf(path: Path) -> tuple[int | None, bool | None, int | None, str | None]:
    try:
        reader = PdfReader(path)
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            return len(reader.pages), True, 0, None
        text_chars = 0
        failed_pages = 0
        first_error = None
        for page in reader.pages:
            try:
                text_chars += len(page.extract_text() or "")
            except Exception as exc:  # valid PDF pages can contain unusual object graphs
                failed_pages += 1
                if first_error is None:
                    first_error = f"{type(exc).__name__}:{exc}"
        if failed_pages and shutil.which("pdftotext"):
            try:
                completed = subprocess.run(
                    ["pdftotext", "-enc", "UTF-8", str(path), "-"],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=240,
                )
                if completed.returncode == 0:
                    return len(reader.pages), False, len(completed.stdout.decode("utf-8", errors="replace")), None
                first_error = (
                    f"{first_error};pdftotext_exit={completed.returncode};"
                    f"stderr={completed.stderr.decode('utf-8', errors='replace')[:300]}"
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                first_error = f"{first_error};pdftotext={type(exc).__name__}:{exc}"
        error = f"text_extraction_partial:failed_pages={failed_pages};first_error={first_error}" if failed_pages else None
        return len(reader.pages), False, text_chars, error
    except Exception as exc:  # unreadable PDF container stays failed, not trusted
        return None, None, None, f"{type(exc).__name__}:{exc}"


def normalize_attachment(attachment: dict) -> dict:
    row = dict(attachment)
    row.setdefault("role", "main")
    row.setdefault("download_status", "not_requested")
    row.setdefault("relative_path", None)
    row.setdefault("bytes", None)
    row.setdefault("sha256", None)
    row.setdefault("content_type", None)
    row.setdefault("pdf_pages", None)
    row.setdefault("pdf_encrypted", None)
    row.setdefault("pdf_text_chars", None)
    row.setdefault("error", None)
    return row


def download_attachment(
    session: requests.Session,
    source: dict,
    attachment: dict,
    *,
    output_dir: Path,
    overwrite: bool,
    previous: dict | None = None,
) -> dict:
    row = normalize_attachment(attachment)
    url = row["source_url"]
    request_url = fetch_url_for(url)
    parsed = urlparse(request_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        row.update(download_status="restricted", error="non_https_source_url")
        return row
    if not row.get("public_download"):
        row.update(download_status="metadata_only", error="not_marked_public_download")
        return row
    if host not in ALLOWED_HOSTS:
        row.update(download_status="restricted", error=f"download_host_not_allowlisted:{host}")
        return row

    source_dir = output_dir / safe_component(source["source_id"])
    source_dir.mkdir(parents=True, exist_ok=True)
    ordinal = safe_component(row["attachment_id"].rsplit(":", 1)[-1])
    destination = source_dir / f"{ordinal}_{safe_component(row.get('role') or 'main')}{extension_for(row)}"
    temporary = destination.with_suffix(destination.suffix + ".part")

    previous_has_partial_text = str((previous or {}).get("error") or "").startswith(
        "pdf_text_inspection_partial:"
    )
    if (
        not overwrite
        and previous
        and previous.get("download_status") == "downloaded"
        and not previous_has_partial_text
    ):
        prior_path_value = previous.get("relative_path")
        prior_path = Path(prior_path_value) if prior_path_value else destination
        if not prior_path.is_absolute():
            prior_path = ROOT / prior_path
        if prior_path.exists() and previous.get("sha256") == sha256_path(prior_path):
            for key in (
                "download_status",
                "relative_path",
                "bytes",
                "sha256",
                "content_type",
                "pdf_pages",
                "pdf_encrypted",
                "pdf_text_chars",
                "error",
            ):
                row[key] = previous.get(key)
            return row
    content_type = None
    final_url = request_url
    http_status = None
    etag = None
    last_modified = None

    try:
        if overwrite or not destination.exists():
            with session.get(request_url, stream=True, timeout=(20, 180), allow_redirects=True) as response:
                http_status = response.status_code
                response.raise_for_status()
                final_url = response.url
                final_host = (urlparse(final_url).hostname or "").lower()
                if final_host not in ALLOWED_HOSTS:
                    raise ValueError(f"redirect_host_not_allowlisted:{final_host}")
                content_type = response.headers.get("content-type")
                etag = response.headers.get("etag")
                last_modified = response.headers.get("last-modified")
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
            valid, magic = magic_valid(temporary, row.get("file_type") or destination.suffix)
            if not valid:
                raise ValueError(f"file_signature_mismatch:{magic}")
            os.replace(temporary, destination)
        else:
            content_type = mimetypes.guess_type(destination.name)[0]

        valid, magic = magic_valid(destination, row.get("file_type") or destination.suffix)
        if not valid:
            raise ValueError(f"existing_file_signature_mismatch:{magic}")
        row.update(
            {
                "download_status": "downloaded",
                "relative_path": display_path(destination),
                "bytes": destination.stat().st_size,
                "sha256": sha256_path(destination),
                "content_type": content_type,
                "error": None,
            }
        )
        if str(row.get("file_type") or "").lower().lstrip(".") == "pdf":
            pages, encrypted, text_chars, pdf_error = inspect_pdf(destination)
            row.update(
                pdf_pages=pages,
                pdf_encrypted=encrypted,
                pdf_text_chars=text_chars,
            )
            if pdf_error and pages is None:
                row["download_status"] = "failed"
                row["error"] = f"pdf_inspection_failed:{pdf_error}"
            elif pdf_error:
                row["error"] = f"pdf_text_inspection_partial:{pdf_error}"
    except Exception as exc:
        if temporary.exists():
            temporary.unlink()
        row["download_status"] = "failed"
        row["error"] = f"{type(exc).__name__}:{exc}"

    # These fields are intentionally not persisted until the v2 schema.  Keep
    # them in the deterministic error text/log rather than weakening v1.
    if row["download_status"] == "failed" and http_status is not None:
        row["error"] = f"{row['error']};http_status={http_status};final_url={final_url}"
    del etag, last_modified
    return row


def build_summary(sources: list[dict]) -> dict:
    attachments = [attachment for source in sources for attachment in source["attachments"]]
    return {
        "sources": len(sources),
        "attachments": len(attachments),
        "priorities": dict(sorted(Counter(source.get("priority", "unset") for source in sources).items())),
        "latest_statuses": dict(sorted(Counter(source["latest_status"] for source in sources).items())),
        "specialties": dict(
            sorted(Counter(specialty for source in sources for specialty in source["specialties"]).items())
        ),
        "download_statuses": dict(sorted(Counter(row["download_status"] for row in attachments).items())),
        "downloaded_bytes": sum(row.get("bytes") or 0 for row in attachments if row["download_status"] == "downloaded"),
        "medical_approval": sum(bool(source["medical_approval"]) for source in sources),
        "student_visible": sum(bool(source["student_visible"]) for source in sources),
    }


def ingest(args: argparse.Namespace) -> dict:
    sources, seed_files = load_seed_sources(args.seed_dir)
    previous_attachments: dict[str, dict] = {}
    if args.output.exists():
        try:
            previous_registry = load_json(args.output)
            previous_attachments = {
                attachment["attachment_id"]: attachment
                for source in previous_registry.get("sources") or []
                for attachment in source.get("attachments") or []
            }
        except (OSError, ValueError, KeyError, TypeError):
            previous_attachments = {}
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Paccine-KR-Guideline-Registry/1.0 (private research mirror)",
            "Accept": "application/pdf,application/zip,application/octet-stream,*/*;q=0.5",
        }
    )
    if args.download:
        for index, source in enumerate(sources, start=1):
            source["attachments"] = [
                download_attachment(
                    session,
                    source,
                    attachment,
                    output_dir=args.files_dir,
                    overwrite=args.overwrite,
                    previous=previous_attachments.get(attachment.get("attachment_id")),
                )
                for attachment in source.get("attachments", [])
            ]
            if index % 10 == 0 or index == len(sources):
                print(f"guidelines {index}/{len(sources)}", flush=True)
    else:
        for source in sources:
            source["attachments"] = [normalize_attachment(row) for row in source.get("attachments", [])]

    summary = build_summary(sources)
    payload = {
        "schema_version": "kr_guideline_source_registry.v1",
        "generated_at": utc_now(),
        "latest_checked_at": date.today().isoformat(),
        "registry_role": "source_inventory_not_medical_approval",
        "catalog": {
            "scope": "curated_official_latest_priority_sources",
            "seed_files": seed_files,
            "completeness_note": (
                "Priority official sources verified by specialty; this is not a claim that every Korean "
                "guideline topic has been exhaustively covered."
            ),
            "download_policy": (
                "Private integrity mirror only; public access does not grant redistribution or commercial reuse."
            ),
        },
        "summary": summary,
        "safety_boundary": {
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "generation_eligible": False,
            "automatic_claim_promotion": False,
        },
        "sources": sources,
    }
    validate_registry(payload, label="merged verified registry")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    failures = defaultdict(list)
    for source in sources:
        for attachment in source["attachments"]:
            if attachment["download_status"] in {"failed", "restricted", "metadata_only"}:
                failures[attachment["download_status"]].append(
                    {
                        "source_id": source["source_id"],
                        "title": source["title"],
                        "attachment_id": attachment["attachment_id"],
                        "source_url": attachment["source_url"],
                        "error": attachment.get("error"),
                    }
                )
    review_path = args.output.with_name("download_review_queue.json")
    review_payload = {
        "schema_version": "kr_guideline_download_review.v1",
        "generated_at": utc_now(),
        "registry": display_path(args.output),
        "counts": {key: len(value) for key, value in sorted(failures.items())},
        "items": {key: value for key, value in sorted(failures.items())},
        "medical_approval": False,
    }
    review_path.write_text(json.dumps(review_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--files-dir", type=Path, default=DEFAULT_FILES)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    result = ingest(parse_args())
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
