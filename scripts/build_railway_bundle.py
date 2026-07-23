#!/usr/bin/env python3
"""Build the small, allow-listed source bundle uploaded to Railway.

This deliberately does not archive the whole working tree. The repository
contains private source drops, backups, generated exports, and several GB of
derived data that are not required by the live demo.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


APP_PATHS = (
    ".dockerignore",
    "Dockerfile",
    "railway.json",
    "requirements.txt",
    # Publish only the current role-separated surfaces. The repository keeps
    # older design iterations for audit/portfolio history, but Railway must not
    # expose them through StaticFiles.
    "frontend/tokens.css",
    "frontend/student-v3",
    "frontend/faculty-studio-v3",
    "frontend/cpx-osce",
    "frontend/faculty-studio-v2/archive.html",
    "frontend/faculty-studio-v2/evidence-media.html",
    "frontend/faculty-studio-v2/faculty-studio.css",
    "frontend/faculty-studio-v2/faculty-workspace.js",
    "frontend/faculty-studio-v2/guideline-claims.css",
    "frontend/faculty-studio-v2/guideline-claims.html",
    "frontend/faculty-studio-v2/guideline-claims.js",
    "frontend/faculty-studio-v2/import.html",
    "frontend/faculty-studio-v2/review.html",
    "frontend/faculty-studio-v2/sources.html",
    "frontend/faculty-studio-v2/workspace.css",
    "src",
    "scripts",
    "schemas",
    "assets",
    "docs/Ontology_V1_Readiness_20260711.json",
)

DATA_PATHS = (
    "concept_registry.json",
    "curriculum/axis_registry.json",
    "curriculum/distractor_bridges.json",
    "curriculum/typed_entity_registry.json",
    "curriculum/ontology_review_decisions.json",
    "curriculum/ontology_hardening_worklist_20260712.json",
    "curriculum/clinical_axis_review_worklist_20260712.json",
    "curriculum/finding_endpoint_review_worklist_20260712.json",
    "curriculum/registry_index.json",
    "curriculum/ontology_query_map.json",
    "curriculum/ontology_trust_kernel_releases.json",
    "student/qbank.json",
    # Enrichment overlays are deployable review data. Drafts stay in the
    # faculty queue; student visibility is decided by the API's explicit
    # faculty-approval or bounded full-demo release gates.
    "student/qbank_enrichment.draft.json",
    "student/qbank_enrichment.releases.json",
    "concept_notes/hemeonc_concept_notes.json",
    "ontology/question_links.json",
    "harrison/22e/pages.jsonl",
    "harrison/22e/chapter_index.json",
    "harrison/22e/snapshot_manifest.json",
    "harrison/22e/concept_harrison_overlay.json",
    "kr_guidelines/catalog",
    "kr_guidelines/seeds",
    "us_guidelines",
    "guideline_map",
    "rag",
    "external_kg",
    "studio/student_releases.json",
    "studio/question_bank",
    "studio/review_sets",
    "studio/media_bank",
    "course_exams/markdown",
    "course_exams/previews",
    # Preserve all media used by the canonical student qbank plus representative
    # Hematology/Oncology and PMA exam sets. Other extracted exam JSON remains
    # available for review, while its media can be uploaded later to the volume.
    "course_exams/media/COURSE_2_20251103_NEURO_SPECIAL_SENSES_2차",
    "course_exams/media/COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험",
    "course_exams/media/COURSE_2_20260306_HEMATOLOGY_ONCOLOGY_1차",
    "course_exams/media/COURSE_2_20260317_HEMATOLOGY_ONCOLOGY_2차",
    "course_exams/media/PMA_202306_G3_B군_1교시",
    "course_exams/media/PMA_202306_G3_B군_2교시",
    "course_exams/media/PMA_202511_G3_B군_1교시",
    "course_exams/media/PMA_202511_G3_B군_2교시",
    "course_exams/media/SYNTH_GENERATED",
    "course_exams/evidence_jump",
    "course_exams/media_labeling",
    "medlegal/cases",
    "medlegal/demo",
)

DATA_GLOBS = (
    "kr_guidelines/*.json",
    "course_exams/extracted/*.json",
)


def _copy(source: Path, destination: Path) -> tuple[int, int]:
    if not source.exists():
        return 0, 0
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
        files = [path for path in destination.rglob("*") if path.is_file()]
        return len(files), sum(path.stat().st_size for path in files)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return 1, destination.stat().st_size


def build_bundle(project_root: Path, destination: Path) -> dict[str, object]:
    project_root = project_root.resolve()
    destination = destination.resolve()
    if destination == project_root or project_root in destination.parents:
        raise ValueError("bundle destination must be outside the project working tree")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    copied_files = 0
    copied_bytes = 0
    for relative in APP_PATHS:
        files, size = _copy(project_root / relative, destination / relative)
        copied_files += files
        copied_bytes += size

    for source in sorted(project_root.glob("*.py")):
        files, size = _copy(source, destination / source.name)
        copied_files += files
        copied_bytes += size

    for relative in DATA_PATHS:
        source = project_root / "data_private" / relative
        files, size = _copy(source, destination / "data_private" / relative)
        copied_files += files
        copied_bytes += size

    for pattern in DATA_GLOBS:
        for source in sorted((project_root / "data_private").glob(pattern)):
            relative = source.relative_to(project_root / "data_private")
            files, size = _copy(source, destination / "data_private" / relative)
            copied_files += files
            copied_bytes += size

    manifest = {
        "schema": "paccine.railway_bundle.v1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": str(project_root),
        "destination": str(destination),
        "file_count": copied_files,
        "size_mib": round(copied_bytes / 1024 / 1024, 2),
    }
    (destination / "railway_bundle_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--destination", type=Path, default=Path("/tmp/paccine-railway-bundle"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(build_bundle(args.project_root, args.destination), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
