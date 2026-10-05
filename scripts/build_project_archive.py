#!/usr/bin/env python3
"""Build a reproducible, content-free inventory of the Med-Tutor workspace.

The inventory records paths and filesystem metadata only. It deliberately does
not read or copy file contents, which keeps credentials and private educational
materials out of the archive report.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DATE = "20260713"

DEPENDENCY_ROOTS = {".venv", "venv"}
BUILD_ROOTS = {
    "build",
    "dist",
    "build_backup_20260210_185035",
    "build_backup_20260210_185610",
    "dist_backup_20260210_185035",
    "dist_backup_20260210_185610",
}
CACHE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".DS_Store",
}
GENERATED_MIRROR_PREFIXES = (
    "data_private/ontology/archive/ontology_vault_pre_cleanup_20260713/",
    "data_private/neo4j_import/data/",
    "data_private/ontology_vault/Axes/",
    "data_private/ontology_vault/Diseases/",
    "data_private/ontology_vault/Findings/",
    "data_private/ontology_vault/Taxonomy/",
    "data_private/ontology_vault/Typed Entities/",
)
SENSITIVE_PATHS = {
    ".cc-session.env",
    "Gemini_API_Key.md",
    "auth_users.json",
    "audit_log.jsonl",
    "questions.json",
    "exam_history.json",
    "user_settings.json",
    "streamlit.log",
    "test.pdf",
    "tmp_pdf_text.txt",
}
SENSITIVE_PREFIXES = ("data_private/", "users/", "outputs/", "release_assets/")


def git_paths(root: Path, *args: str) -> set[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return set()
    return {
        value.decode("utf-8", errors="surrogateescape")
        for value in result.stdout.split(b"\0")
        if value
    }


def classify(path: str) -> str:
    parts = Path(path).parts
    top = parts[0] if parts else "(root)"
    name = parts[-1] if parts else path

    if top in DEPENDENCY_ROOTS:
        return "dependency_environment"
    if top in BUILD_ROOTS or top.startswith("build_backup_") or top.startswith("dist_backup_"):
        return "build_or_backup"
    if any(part in CACHE_PARTS for part in parts):
        return "cache"
    root_attachment = len(parts) == 1 and (
        name.startswith("[") or Path(name).suffix.lower() in {".hwp", ".hwpx", ".xlsx", ".pptx", ".docx", ".pdf"}
    )
    if path in SENSITIVE_PATHS or path.startswith(SENSITIVE_PREFIXES) or root_attachment:
        if path.startswith("data_private/"):
            return "private_research_data"
        return "local_sensitive_state"
    if top == "frontend":
        return "frontend"
    if top == "src" or name in {"api_server.py", "app.py", "launcher.py"}:
        return "application_source"
    if top == "scripts":
        return "pipeline_script"
    if top == "tests":
        return "test"
    if top == "schemas":
        return "schema"
    if top == "docs" or path in {"README.md", "DEPLOYMENT_NOTES.md"}:
        return "documentation"
    if top in {"output", "outputs", "release_assets"}:
        return "generated_output"
    if top == "mobile_shell":
        return "mobile_shell"
    if name in {"Dockerfile", "Justfile", "pytest.ini", "requirements.txt", ".dockerignore", ".gitignore"}:
        return "configuration"
    if name.endswith((".spec", ".spec.backup_20260210_185035", ".spec.backup_20260210_185610")):
        return "packaging"
    return "other"


def is_sensitive(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1] if parts else path
    root_attachment = len(parts) == 1 and (
        name.startswith("[") or Path(name).suffix.lower() in {".hwp", ".hwpx", ".xlsx", ".pptx", ".docx", ".pdf"}
    )
    return path in SENSITIVE_PATHS or path.startswith(SENSITIVE_PREFIXES) or root_attachment


def is_curated(path: str, category: str) -> bool:
    parts = Path(path).parts
    top = parts[0] if parts else "(root)"
    if category in {"dependency_environment", "build_or_backup", "cache"}:
        return False
    if any(path.startswith(prefix) for prefix in GENERATED_MIRROR_PREFIXES):
        return False
    if top == ".git":
        return False
    return True


def iter_files(root: Path, archive_dir: Path):
    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        if current_path == archive_dir:
            dirnames[:] = []
            continue
        if current_path == root:
            dirnames[:] = sorted(name for name in dirnames if name != ".git")
        else:
            dirnames[:] = sorted(
                name for name in dirnames if (current_path / name) != archive_dir
            )
        filenames.sort()
        for filename in filenames:
            absolute = current_path / filename
            try:
                stat = absolute.lstat()
            except FileNotFoundError:
                continue
            yield absolute, stat


def format_bytes(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--date", default=DEFAULT_DATE)
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = root / "output" / f"project_archive_{args.date}"
    output_dir.mkdir(parents=True, exist_ok=True)

    tracked = git_paths(root, "ls-files", "-z")
    modified = git_paths(root, "diff", "--name-only", "-z") | git_paths(
        root, "diff", "--cached", "--name-only", "-z"
    )
    untracked = git_paths(root, "ls-files", "--others", "--exclude-standard", "-z")

    full_path = output_dir / f"PROJECT_FILE_INVENTORY_FULL_{args.date}.tsv.gz"
    curated_path = output_dir / f"PROJECT_FILE_INVENTORY_CURATED_{args.date}.tsv"
    summary_path = output_dir / f"PROJECT_DIRECTORY_SUMMARY_{args.date}.tsv"
    metadata_path = output_dir / f"PROJECT_ARCHIVE_METADATA_{args.date}.json"

    fields = [
        "path",
        "size_bytes",
        "modified_at",
        "extension",
        "top_level",
        "category",
        "version_state",
        "sensitive_or_private",
        "curated_inventory",
    ]
    category_counts: Counter[str] = Counter()
    category_bytes: Counter[str] = Counter()
    top_counts: Counter[str] = Counter()
    top_bytes: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    curated_count = 0
    total_count = 0
    total_bytes = 0
    largest: list[tuple[int, str, str]] = []

    with gzip.open(full_path, "wt", encoding="utf-8", newline="") as full_handle, curated_path.open(
        "w", encoding="utf-8", newline=""
    ) as curated_handle:
        full_writer = csv.DictWriter(full_handle, fieldnames=fields, delimiter="\t")
        curated_writer = csv.DictWriter(curated_handle, fieldnames=fields, delimiter="\t")
        full_writer.writeheader()
        curated_writer.writeheader()

        for absolute, stat in iter_files(root, output_dir):
            relative = absolute.relative_to(root).as_posix()
            category = classify(relative)
            if relative in modified:
                version_state = "tracked_modified"
            elif relative in tracked:
                version_state = "tracked_clean"
            elif relative in untracked:
                version_state = "untracked"
            else:
                version_state = "ignored_or_local"
            curated = is_curated(relative, category)
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            suffix = absolute.suffix.lower() or "(none)"
            top = Path(relative).parts[0] if len(Path(relative).parts) > 1 else "(root)"
            row = {
                "path": relative,
                "size_bytes": stat.st_size,
                "modified_at": modified_at,
                "extension": suffix,
                "top_level": top,
                "category": category,
                "version_state": version_state,
                "sensitive_or_private": "yes" if is_sensitive(relative) else "no",
                "curated_inventory": "yes" if curated else "no",
            }
            full_writer.writerow(row)
            if curated:
                curated_writer.writerow(row)
                curated_count += 1

            total_count += 1
            total_bytes += stat.st_size
            category_counts[category] += 1
            category_bytes[category] += stat.st_size
            top_counts[top] += 1
            top_bytes[top] += stat.st_size
            state_counts[version_state] += 1
            largest.append((stat.st_size, relative, category))

    summary_fields = ["scope", "name", "file_count", "size_bytes", "size_human"]
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields, delimiter="\t")
        writer.writeheader()
        for category in sorted(category_counts):
            writer.writerow(
                {
                    "scope": "category",
                    "name": category,
                    "file_count": category_counts[category],
                    "size_bytes": category_bytes[category],
                    "size_human": format_bytes(category_bytes[category]),
                }
            )
        for top in sorted(top_counts):
            writer.writerow(
                {
                    "scope": "top_level",
                    "name": top,
                    "file_count": top_counts[top],
                    "size_bytes": top_bytes[top],
                    "size_human": format_bytes(top_bytes[top]),
                }
            )

    largest.sort(reverse=True)
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(root),
        "inventory_boundary": (
            "All workspace files except .git internals and the archive output directory itself; "
            "no file contents were read or copied."
        ),
        "total_files": total_count,
        "total_bytes": total_bytes,
        "total_size_human": format_bytes(total_bytes),
        "curated_files": curated_count,
        "git_tracked_files": len(tracked),
        "version_state_counts": dict(sorted(state_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "category_bytes": dict(sorted(category_bytes.items())),
        "largest_files": [
            {"path": path, "size_bytes": size, "size_human": format_bytes(size), "category": category}
            for size, path, category in largest[:50]
        ],
        "sensitive_policy": "Sensitive/private paths are listed by path and metadata only. Values and contents are excluded.",
        "curated_exclusions": {
            "dependency_roots": sorted(DEPENDENCY_ROOTS),
            "build_roots": sorted(BUILD_ROOTS),
            "cache_parts": sorted(CACHE_PARTS),
            "generated_mirror_prefixes": list(GENERATED_MIRROR_PREFIXES),
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
