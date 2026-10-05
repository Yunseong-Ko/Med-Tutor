#!/usr/bin/env python3
"""Build a non-destructive, private evidence-library view.

The canonical files stay in their existing locations because runtime code and
manifests already point to them.  This script creates Finder-friendly symlinks
plus a machine-readable inventory under ``data_private/evidence_library``.
Large or copyrighted inputs are never copied by this builder.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = ROOT / "data_private" / "evidence_library" / "current"
DEPRECATED_BUNDLE_LINKS = (
    "01_primary_teaching_materials/neuro_summaries_external",
    "06_secondary_validation/primekg_raw_nodes_external.csv",
    "06_secondary_validation/primekg_raw_edges_external.csv",
)
RAG_SOURCE_RECOVERY_ROOTS = (
    Path.home() / "Downloads" / "Database Ontology",
    Path.home() / "Downloads" / "Database",
)


LINK_SPECS: list[dict[str, Any]] = [
    {
        "bundle_path": "01_primary_textbooks/harrison_22e_split",
        "target": Path.home() / "Downloads" / "Harrison_22e_분할",
        "role": "licensed_textbook_source",
        "scope": "ontology_mapping_and_claim_candidate_retrieval",
        "rights": "private_licensed_do_not_redistribute",
        "medical_status": "source_not_claim_approval",
        "integrity_anchor": "data_private/harrison/22e/snapshot_manifest.json",
        "runtime_status": "ontology_offline_source_snapshot",
    },
    {
        "bundle_path": "01_primary_textbooks/harrison_part4_runtime.pdf",
        "target": ROOT / "data_private" / "textbook_grounding" / "harrison" / "11_PART 4 Oncology and Hematology.pdf",
        "role": "licensed_textbook_source",
        "scope": "active_harrison_part4_rag_source",
        "rights": "private_licensed_do_not_redistribute",
        "medical_status": "source_not_claim_approval",
        "integrity_anchor": "direct_sha256",
        "runtime_status": "active_rag_source",
    },
    {
        "bundle_path": "01_primary_textbooks/harrison_part13_neurology_external.pdf",
        "target": Path.home() / "Downloads" / "Database" / "20_PART 13 Neurologic Disorders.pdf",
        "role": "licensed_textbook_source",
        "scope": "active_neuro_special_senses_rag_source",
        "rights": "private_licensed_do_not_redistribute",
        "medical_status": "source_not_claim_approval",
        "integrity_anchor": "direct_sha256",
        "runtime_status": "active_rag_source",
    },
    {
        "bundle_path": "01_primary_teaching_materials/parsed_lectures",
        "target": ROOT / "data_private" / "lectures",
        "role": "parsed_lecture_authoring_sources",
        "scope": "sections_and_ontology_anchors",
        "rights": "private_course_material_no_redistribution",
        "medical_status": "authoring_provenance_not_medical_approval",
        "integrity_anchor": "per_file",
        "runtime_status": "offline_authoring_inputs",
    },
    {
        "bundle_path": "01_primary_exam_sources/pma_raw",
        "target": ROOT / "data_private" / "pma" / "raw",
        "role": "restricted_exam_sources",
        "scope": "question_structure_and_provenance",
        "rights": "institutional_exam_private_no_redistribution",
        "medical_status": "exam_content_not_independent_medical_evidence",
        "integrity_anchor": "per_file",
        "runtime_status": "offline_extraction_sources",
    },
    {
        "bundle_path": "01_primary_exam_sources/course_exam_uploads",
        "target": ROOT / "data_private" / "course_exams" / "uploads",
        "role": "restricted_exam_upload_sources",
        "scope": "question_extraction_provenance",
        "rights": "institutional_exam_private_no_redistribution",
        "medical_status": "exam_content_not_independent_medical_evidence",
        "integrity_anchor": "per_file",
        "runtime_status": "partial_raw_provenance_only",
    },
    {
        "bundle_path": "02_korean_guidelines/source_files_latest",
        "target": ROOT / "data_private" / "kr_guidelines" / "source_files" / "latest",
        "role": "official_guideline_source_files",
        "scope": "private_integrity_mirror",
        "rights": "mixed_society_copyright_private_no_redistribution",
        "medical_status": "all_sources_and_claims_require_review",
        "integrity_anchor": "data_private/kr_guidelines/verified_latest_registry.json",
        "runtime_status": "offline_staging_not_connected_to_api_generate",
    },
    {
        "bundle_path": "02_korean_guidelines/verified_latest_registry.json",
        "target": ROOT / "data_private" / "kr_guidelines" / "verified_latest_registry.json",
        "role": "source_version_registry",
        "scope": "currentness_rights_and_checksum_metadata",
        "rights": "private_metadata",
        "medical_status": "not_medical_approval",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "02_korean_guidelines/kams_registered_catalog.json",
        "target": ROOT / "data_private" / "kr_guidelines" / "catalog" / "kams_registered_catalog.json",
        "role": "source_catalog",
        "scope": "registered_guideline_inventory_not_latest_proof",
        "rights": "private_metadata",
        "medical_status": "not_medical_approval",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "02_korean_guidelines/claim_extraction_worklist.json",
        "target": ROOT / "data_private" / "kr_guidelines" / "claim_extraction_worklist.json",
        "role": "review_worklist",
        "scope": "candidate_extraction_tasks",
        "rights": "private_derived",
        "medical_status": "tasks_are_not_claims",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "02_korean_guidelines/specialty_agent_registry.json",
        "target": ROOT / "data_private" / "kr_guidelines" / "specialty_agent_registry.json",
        "role": "retrieval_routing_profiles",
        "scope": "one_runtime_with_specialty_profiles",
        "rights": "private_derived",
        "medical_status": "routing_is_not_medical_judgment",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "02_korean_guidelines/divergence_seed.json",
        "target": ROOT / "data_private" / "kr_guidelines" / "divergence_seed.json",
        "role": "cross_source_divergence_candidates",
        "scope": "review_only",
        "rights": "private_derived",
        "medical_status": "unapproved_review_candidates",
        "integrity_anchor": "direct_sha256",
        "optional": True,
    },
    {
        "bundle_path": "02_us_guidelines/source_files_latest",
        "target": ROOT / "data_private" / "us_guidelines" / "source_files" / "latest",
        "role": "selected_official_us_guideline_reference_files",
        "scope": "private_reference_snapshots_with_source_specific_rights",
        "rights": "mixed_government_and_restricted_metadata_only_sources",
        "medical_status": "comparison_sources_not_claim_approval",
        "integrity_anchor": "data_private/us_guidelines/verified_latest_registry.json",
        "runtime_status": "offline_fail_closed_not_connected_to_generation",
    },
    {
        "bundle_path": "02_us_guidelines/verified_latest_registry.json",
        "target": ROOT / "data_private" / "us_guidelines" / "verified_latest_registry.json",
        "role": "us_source_version_rights_registry",
        "scope": "selected_currentness_rights_checksum_and_localization_metadata",
        "rights": "private_metadata",
        "medical_status": "not_medical_approval",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "02_us_guidelines/official_watch_hubs.json",
        "target": ROOT / "data_private" / "us_guidelines" / "official_watch_hubs.json",
        "role": "official_currentness_watchlist",
        "scope": "recheck_before_currentness_claim",
        "rights": "private_metadata",
        "medical_status": "source_surveillance_not_claim_approval",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "02_us_guidelines/jurisdiction_policy.json",
        "target": ROOT / "data_private" / "us_guidelines" / "jurisdiction_policy.json",
        "role": "cross_jurisdiction_precedence_policy",
        "scope": "kr_primary_us_comparison_and_us_exam_modes",
        "rights": "private_derived",
        "medical_status": "routing_policy_not_medical_judgment",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "02_us_guidelines/core_summary.md",
        "target": ROOT / "docs" / "ontology" / "US_GUIDELINE_OVERLAY.md",
        "role": "human_readable_us_guideline_base_summary",
        "scope": "source_selection_currentness_rights_and_next_pilot",
        "rights": "project_authored_metadata_summary",
        "medical_status": "unapproved_source_scope_summary",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "02_guideline_agent_map/source_map.json",
        "target": ROOT / "data_private" / "guideline_map" / "source_map.json",
        "role": "jurisdiction_aware_guideline_source_map",
        "scope": "kr_us_agent_navigation_and_retrieval_routing",
        "rights": "private_derived_metadata",
        "medical_status": "source_navigation_not_medical_evidence",
        "integrity_anchor": "direct_sha256",
        "runtime_status": "faculty_route_preview_only",
    },
    {
        "bundle_path": "02_guideline_agent_map/atomic_claim_candidates.json",
        "target": ROOT / "data_private" / "guideline_map" / "atomic_claim_candidates.json",
        "role": "guideline_atomic_claim_review_candidates",
        "scope": "diabetes_dyslipidemia_amr_pilot_review_queue",
        "rights": "independent_paraphrases_private_review_only",
        "medical_status": "all_candidates_unapproved_and_runtime_ineligible",
        "integrity_anchor": "direct_sha256",
        "runtime_status": "faculty_review_preview_only",
    },
    {
        "bundle_path": "03_rag_indexes/harrison_part4",
        "target": ROOT / "data_private" / "rag" / "harrison_part4",
        "role": "derived_rag_index",
        "scope": "active_local_retrieval_index",
        "rights": "private_derived_from_licensed_source",
        "medical_status": "retrieval_result_not_medical_approval",
        "integrity_anchor": "index_internal_metadata",
        "runtime_status": "available_explicit_course_id",
    },
    {
        "bundle_path": "03_rag_indexes/hematology_oncology",
        "target": ROOT / "data_private" / "rag" / "hematology_oncology",
        "role": "derived_rag_index",
        "scope": "active_local_retrieval_index_with_external_source_path",
        "rights": "private_derived_from_licensed_source",
        "medical_status": "retrieval_result_not_medical_approval",
        "integrity_anchor": "index_internal_metadata",
        "runtime_status": "active_default_rag_index",
    },
    {
        "bundle_path": "03_rag_indexes/neuro_special_senses",
        "target": ROOT / "data_private" / "rag" / "neuro_special_senses",
        "role": "derived_rag_index",
        "scope": "active_local_retrieval_index_with_missing_source_audit",
        "rights": "private_mixed_sources",
        "medical_status": "retrieval_result_not_medical_approval",
        "integrity_anchor": "index_internal_metadata",
        "runtime_status": "active_index_with_six_stale_source_paths",
    },
    {
        "bundle_path": "04_ontology_claims/clinical_axes_authoring_map.json",
        "target": ROOT / "data_private" / "curriculum" / "clinical_axes_map.json",
        "role": "clinical_axis_authoring_input",
        "scope": "source_claim_candidates_before_materialization",
        "rights": "private_derived_authoring_data",
        "medical_status": "needs_human_review",
        "integrity_anchor": "direct_sha256",
        "runtime_status": "builder_input",
    },
    {
        "bundle_path": "04_ontology_claims/concept_registry.json",
        "target": ROOT / "data_private" / "concept_registry.json",
        "role": "canonical_concept_registry",
        "scope": "concept_resolution_and_graph_routing",
        "rights": "private_derived",
        "medical_status": "all_concepts_need_review",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "04_ontology_claims/distractor_bridges.json",
        "target": ROOT / "data_private" / "curriculum" / "distractor_bridges.json",
        "role": "distractor_candidate_bridges",
        "scope": "generation_grounding",
        "rights": "private_derived",
        "medical_status": "review_candidates",
        "integrity_anchor": "direct_sha256",
        "runtime_status": "active_generation_grounding",
    },
    {
        "bundle_path": "04_ontology_claims/typed_entity_registry.json",
        "target": ROOT / "data_private" / "curriculum" / "typed_entity_registry.json",
        "role": "typed_entity_registry",
        "scope": "generation_scope_control",
        "rights": "private_derived",
        "medical_status": "needs_review",
        "integrity_anchor": "direct_sha256",
        "runtime_status": "active_generation_grounding",
    },
    {
        "bundle_path": "04_ontology_claims/axis_registry.json",
        "target": ROOT / "data_private" / "curriculum" / "axis_registry.json",
        "role": "clinical_claim_candidate_registry",
        "scope": "ontology_grounding_candidates",
        "rights": "private_derived",
        "medical_status": "all_claims_draft_unreviewed",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "04_ontology_claims/item_evidence_packs.json",
        "target": ROOT / "data_private" / "curriculum" / "item_evidence_packs.json",
        "role": "item_evidence_candidates",
        "scope": "faculty_review_support",
        "rights": "private_derived",
        "medical_status": "not_student_released",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "04_ontology_claims/ontology_review_decisions.json",
        "target": ROOT / "data_private" / "curriculum" / "ontology_review_decisions.json",
        "role": "human_review_decisions",
        "scope": "approval_input",
        "rights": "private_review_data",
        "medical_status": "authoritative_only_when_explicitly_signed",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "04_ontology_claims/trust_kernel_releases.json",
        "target": ROOT / "data_private" / "curriculum" / "ontology_trust_kernel_releases.json",
        "role": "surface_release_registry",
        "scope": "student_and_analytics_fail_closed_gate",
        "rights": "private_release_metadata",
        "medical_status": "current_release_count_zero",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "04_ontology_claims/harrison22_concept_overlay.json",
        "target": ROOT / "data_private" / "harrison" / "22e" / "concept_harrison_overlay.json",
        "role": "concept_to_textbook_locator_overlay",
        "scope": "chapter_pointer_retrieval",
        "rights": "private_derived_from_licensed_source",
        "medical_status": "locator_not_entailment_approval",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "04_ontology_claims/harrison22_claim_support_overlay.json",
        "target": ROOT / "data_private" / "harrison" / "22e" / "validation" / "claim_support_overlay.json",
        "role": "claim_retrieval_candidate_overlay",
        "scope": "review_prioritization",
        "rights": "private_derived_from_licensed_source",
        "medical_status": "candidate_match_not_entailment_approval",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "04_ontology_claims/harrison22_review_worklist.json",
        "target": ROOT / "data_private" / "harrison" / "22e" / "validation" / "review_worklist.json",
        "role": "claim_review_worklist",
        "scope": "human_entailment_review",
        "rights": "private_derived_from_licensed_source",
        "medical_status": "unapproved_review_queue",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "05_question_evidence/manual_rag_evidence",
        "target": ROOT / "data_private" / "studio" / "rag_evidence",
        "role": "manually_curated_generation_evidence",
        "scope": "explicit_upload_or_faculty_draft_only",
        "rights": "private_derived_summary",
        "medical_status": "needs_review",
        "integrity_anchor": "per_file",
        "runtime_status": "used_only_when_explicitly_attached",
    },
    {
        "bundle_path": "05_question_evidence/evidence_jump",
        "target": ROOT / "data_private" / "course_exams" / "evidence_jump",
        "role": "question_to_evidence_jump_artifacts",
        "scope": "faculty_review_and_preview",
        "rights": "private_exam_and_evidence_metadata",
        "medical_status": "review_required",
        "integrity_anchor": "per_artifact_metadata",
    },
    {
        "bundle_path": "05_question_evidence/question_links.json",
        "target": ROOT / "data_private" / "ontology" / "question_links.json",
        "role": "question_to_concept_linkage",
        "scope": "question_grounding_and_review",
        "rights": "private_exam_derived",
        "medical_status": "needs_review",
        "integrity_anchor": "direct_sha256",
        "runtime_status": "active_question_linkage",
    },
    {
        "bundle_path": "05_question_evidence/media/course_exam_media",
        "target": ROOT / "data_private" / "course_exams" / "media",
        "role": "extracted_question_media",
        "scope": "image_question_grounding",
        "rights": "institutional_exam_private_no_redistribution",
        "medical_status": "image_labels_need_review",
        "integrity_anchor": "data_private/course_exams/media_labeling/manifest.json",
        "runtime_status": "active_media_api_assets",
    },
    {
        "bundle_path": "05_question_evidence/media/course_exam_labeling",
        "target": ROOT / "data_private" / "course_exams" / "media_labeling",
        "role": "image_labeling_candidates",
        "scope": "media_provenance_and_review",
        "rights": "private_derived",
        "medical_status": "approved_for_question_use_zero",
        "integrity_anchor": "data_private/course_exams/media_labeling/manifest.json",
        "runtime_status": "offline_review_and_media_lookup",
    },
    {
        "bundle_path": "05_question_evidence/media/studio_media_bank",
        "target": ROOT / "data_private" / "studio" / "media_bank",
        "role": "studio_generation_media",
        "scope": "explicit_image_selection",
        "rights": "private_mixed_sources",
        "medical_status": "requires_media_review",
        "integrity_anchor": "data_private/studio/media_bank/media_assets.json",
        "runtime_status": "active_when_selected",
    },
    {
        "bundle_path": "06_secondary_validation/primekg",
        "target": ROOT / "data_private" / "external_kg" / "primekg",
        "role": "external_kg_candidate_layer",
        "scope": "secondary_cross_validation_only",
        "rights": "mixed_upstream_terms_review_before_redistribution",
        "medical_status": "not_canonical_not_student_visible",
        "integrity_anchor": "data_private/external_kg/primekg/source_manifest.json",
    },
    {
        "bundle_path": "07_standardization/mondo_taxonomy_map.json",
        "target": ROOT / "data_private" / "curriculum" / "mondo_taxonomy_map.json",
        "role": "external_taxonomy_mapping",
        "scope": "concept_standardization",
        "rights": "derived_mapping",
        "medical_status": "xref_not_medical_approval",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "07_standardization/ontology_xref_map.json",
        "target": ROOT / "data_private" / "curriculum" / "ontology_xref_map.json",
        "role": "external_identifier_mapping",
        "scope": "concept_standardization",
        "rights": "derived_mapping",
        "medical_status": "xref_not_medical_approval",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "07_standardization/finding_hpo_enrichment.json",
        "target": ROOT / "data_private" / "curriculum" / "finding_hpo_enrichment.json",
        "role": "finding_standardization_candidates",
        "scope": "finding_to_hpo_review",
        "rights": "derived_mapping",
        "medical_status": "review_candidates",
        "integrity_anchor": "direct_sha256",
    },
    {
        "bundle_path": "08_reproducibility/ontology_manifest.json",
        "target": ROOT / "docs" / "Ontology_Manifest_20260717.json",
        "role": "reproducibility_manifest",
        "scope": "checksums_and_rebuild_contract",
        "rights": "private_path_metadata_do_not_publish_unredacted",
        "medical_status": "integrity_not_medical_approval",
        "integrity_anchor": "direct_sha256",
    },
]

ACTIVE_NEURO_SUMMARY_NAMES = (
    "[정리족]신경 및 특수감각기학 1차 정리족(1).pdf",
    "[정리족]신경 및 특수감각기학 1차 정리족(2).pdf",
    "[정리족]신경 및 특수감각기학 1차 정리족(3).pdf",
    "[정리족]신경 및 특수감각기학 2차 정리족(1).pdf",
    "[정리족]신경 및 특수감각기학 2차 정리족(2).pdf",
    "[정리족]신경 및 특수감각기학 2차 정리족(3).pdf",
)
for index, filename in enumerate(ACTIVE_NEURO_SUMMARY_NAMES, start=1):
    LINK_SPECS.append(
        {
            "bundle_path": f"01_primary_teaching_materials/neuro_rag_sources/{index:02d}_{filename}",
            "target": Path.home() / "Downloads" / "Database Ontology" / filename,
            "role": "private_course_summary_source",
            "scope": "current_neuro_rag_source_with_stale_index_path",
            "rights": "institutional_or_author_copyright_private_no_redistribution",
            "medical_status": "authoring_provenance_not_verified_medical_evidence",
            "integrity_anchor": "direct_sha256",
            "runtime_status": "source_found_but_index_path_needs_repair",
        }
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_summary(path: Path) -> dict[str, int]:
    files = 0
    total_bytes = 0
    for root, _, names in os.walk(path):
        for name in names:
            candidate = Path(root) / name
            try:
                stat = candidate.stat()
            except OSError:
                continue
            files += 1
            total_bytes += stat.st_size
    return {"file_count": files, "bytes": total_bytes}


def ensure_symlink(destination: Path, target: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve(strict=False) == target.resolve(strict=False):
            return
        destination.unlink()
    elif destination.exists():
        raise RuntimeError(f"Refusing to replace non-symlink bundle entry: {destination}")
    destination.symlink_to(target, target_is_directory=target.is_dir())


def remove_deprecated_links() -> None:
    for relative_path in DEPRECATED_BUNDLE_LINKS:
        candidate = BUNDLE_ROOT / relative_path
        if candidate.is_symlink():
            candidate.unlink()


def normalized_filename(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def recover_rag_source(source: Path) -> Path | None:
    wanted = normalized_filename(source.name)
    for root in RAG_SOURCE_RECOVERY_ROOTS:
        if not root.exists():
            continue
        for candidate in root.glob("*"):
            if candidate.is_file() and normalized_filename(candidate.name) == wanted:
                return candidate.resolve()
    return None


def inventory_link(spec: dict[str, Any]) -> dict[str, Any]:
    target = Path(spec["target"]).expanduser().resolve(strict=False)
    destination = BUNDLE_ROOT / spec["bundle_path"]
    exists = target.exists()
    if exists:
        ensure_symlink(destination, target)
    record = {
        key: value
        for key, value in spec.items()
        if key not in {"target", "optional"}
    }
    record.update(
        {
            "target_path": str(target),
            "exists": exists,
            "optional": bool(spec.get("optional", False)),
            "link_created": exists,
            "target_type": "directory" if target.is_dir() else "file" if target.is_file() else "missing",
        }
    )
    if target.is_file():
        size = target.stat().st_size
        record["bytes"] = size
        if size <= 128 * 1024 * 1024 or spec.get("integrity_anchor") == "direct_sha256":
            record["sha256"] = sha256_file(target)
    elif target.is_dir():
        record.update(directory_summary(target))
    return record


def audit_rag_sources() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index_path in sorted((ROOT / "data_private" / "rag").glob("*/rag_index.json")):
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        for document in payload.get("documents", []):
            source = Path(str(document.get("source_path") or "")).expanduser()
            exists = source.exists()
            row = {
                "index_path": str(index_path.relative_to(ROOT)),
                "course_id": payload.get("course_id"),
                "document_id": document.get("document_id"),
                "title": document.get("title"),
                "source_type": document.get("source_type"),
                "source_path": str(source),
                "source_exists": exists,
                "status": "available" if exists else "missing_source_for_existing_index",
            }
            if exists and source.is_file():
                row["bytes"] = source.stat().st_size
            elif not exists:
                recovery = recover_rag_source(source)
                if recovery is not None:
                    row["recovery_candidate_path"] = str(recovery)
                    row["recovery_candidate_bytes"] = recovery.stat().st_size
                    row["status"] = "stale_index_path_recovery_candidate_found"
            rows.append(row)
    return rows


def build_readme(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    return f"""# P:accine private evidence library

기준 시각: **{manifest['generated_at']}**

이 폴더는 현재 Ontology·RAG·문항 근거에 쓰이는 파일을 한곳에서 보는
**바로가기형 라이브러리**다. 원본은 기존 위치에 그대로 있으며, 이 폴더의
항목은 대부분 symbolic link다. 따라서 코드 경로를 깨뜨리거나 대용량·저작권
자료를 중복 복사하지 않는다.

## 현재 상태

- 정리된 연결: **{summary['linked_entries']}개**
- 선택적 또는 누락 항목: **{summary['missing_entries']}개**
- RAG가 참조하는 원본: **{summary['rag_source_documents']}개**
- 그중 인덱스에 옛 경로가 남은 원본: **{summary['rag_missing_source_documents']}개**
- 새 위치에서 복구 후보를 찾은 원본: **{summary['rag_recovery_candidate_documents']}개**
- 이 폴더가 새로 복사한 원문: **0개**

## 폴더 의미

1. `01_primary_textbooks` — Harrison 등 비공개 교과서 원문
2. `01_primary_teaching_materials` — 강의 parsing 자료와 정리족 원문
3. `01_primary_exam_sources` — 재배포 금지 기출 원문과 업로드
4. `02_korean_guidelines` — 공식 국내 가이드라인 원문·판본 registry·작업표
5. `02_us_guidelines` — 선별 미국 지침의 판본·권리·비교 정책과 허용된 private snapshot
6. `02_guideline_agent_map` — KR·US 공통 source map과 미승인 atomic claim 파일럿
7. `03_rag_indexes` — 현재 로컬 검색 인덱스
8. `04_ontology_claims` — authoring map, concept, claim 후보, release gate
9. `05_question_evidence` — evidence jump·수동 근거·문항/이미지 연결
10. `06_secondary_validation` — PrimeKG manifest와 파생 교차검증 후보층
11. `07_standardization` — MONDO·HPO·외부 ID 정규화 자료
12. `08_reproducibility` — checksum·재빌드 manifest

## 반드시 지킬 경계

- Harrison 및 학회 가이드라인 원문은 private이며 재배포하지 않는다.
- `latest` 또는 checksum 검증은 의학적 승인과 다르다.
- Ontology claim, Harrison 후보, PrimeKG 관계는 현재 학생 공개 근거가 아니다.
- 국내 가이드라인 폴더는 아직 `/api/generate`의 자동 RAG에 연결되지 않았다.
- 미국 지침은 국내 진료의 primary source가 아니며 권리·의학 검토 전 원문 RAG에 연결하지 않는다.
- 공통 guideline map은 Agent의 출처 탐색용이다. 36개 atomic claim 후보는 교수자 검토 큐에서만 보이며 답변·문항 생성에는 사용하지 않는다.
- PrimeKG raw CSV는 임시 경로·재배포 불확실성 때문에 이 허브에서 제외했다.
- `manifest.json`의 `runtime_source_audit`에서 `source_exists=false`인 문서는
  인덱스에 옛 경로가 남은 상태다. `recovery_candidate_path`에서 실제 파일을
  찾았더라도 재색인 전까지 기존 source jump는 깨져 있을 수 있다.
- 이 폴더 안의 link를 지워도 원본은 삭제되지 않지만, 원본을 지우면 link가 깨진다.

세부 경로·checksum·권리·검토 상태는 `manifest.json`을 기준으로 확인한다.
"""


def write_inventory_files(manifest: dict[str, Any]) -> None:
    inventory_root = BUNDLE_ROOT / "00_inventory"
    inventory_root.mkdir(parents=True, exist_ok=True)
    fields = (
        "bundle_path",
        "role",
        "scope",
        "runtime_status",
        "target_type",
        "exists",
        "bytes",
        "file_count",
        "rights",
        "medical_status",
        "integrity_anchor",
        "target_path",
    )
    with (inventory_root / "inventory.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in manifest["entries"]:
            writer.writerow(row)
    (inventory_root / "runtime_source_audit.json").write_text(
        json.dumps(manifest["runtime_source_audit"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (inventory_root / "known_gaps.json").write_text(
        json.dumps(manifest["known_gaps"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build() -> dict[str, Any]:
    BUNDLE_ROOT.mkdir(parents=True, exist_ok=True)
    remove_deprecated_links()
    entries = [inventory_link(spec) for spec in LINK_SPECS]
    rag_sources = audit_rag_sources()
    manifest = {
        "schema_version": "paccine_evidence_library.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "library_role": "non_destructive_private_evidence_view",
        "root": str(BUNDLE_ROOT),
        "policy": {
            "copies_source_files": False,
            "uses_symbolic_links": True,
            "medical_approval_inferred": False,
            "student_visibility_inferred": False,
            "safe_to_redistribute": False,
        },
        "summary": {
            "entries": len(entries),
            "linked_entries": sum(bool(row["link_created"]) for row in entries),
            "missing_entries": sum(not bool(row["exists"]) for row in entries),
            "rag_source_documents": len(rag_sources),
            "rag_missing_source_documents": sum(not row["source_exists"] for row in rag_sources),
            "rag_recovery_candidate_documents": sum(bool(row.get("recovery_candidate_path")) for row in rag_sources),
        },
        "entries": entries,
        "runtime_source_audit": rag_sources,
        "known_gaps": [
            {
                "gap_id": "neuro_rag_stale_source_paths",
                "status": "recovery_candidates_found_reindex_required",
                "count": sum(not row["source_exists"] for row in rag_sources),
                "impact": "retrieval index remains usable, but recorded source-path jumps are stale",
            },
            {
                "gap_id": "kr_guidelines_not_connected_to_generation_runtime",
                "status": "offline_staging",
                "impact": "guideline files are inventoried but /api/generate does not automatically retrieve them",
            },
            {
                "gap_id": "us_guidelines_comparison_layer_not_released",
                "status": "offline_fail_closed",
                "impact": "selected U.S. sources are versioned and rights-classified, but no U.S. claim is medically approved or available to generation",
            },
            {
                "gap_id": "ncbi_local_corpus_absent",
                "status": "not_implemented",
                "impact": "external URLs are not equivalent to a versioned local evidence snapshot",
            },
            {
                "gap_id": "standard_vocab_raw_snapshot_absent",
                "status": "derived_maps_only",
                "impact": "MONDO/HPO maps exist without a pinned upstream raw snapshot and license manifest",
            },
            {
                "gap_id": "course_exam_raw_provenance_incomplete",
                "status": "partial_raw_sources",
                "impact": "derived exam corpus is broader than the raw uploads currently retained locally",
            },
        ],
    }
    (BUNDLE_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (BUNDLE_ROOT / "README.md").write_text(build_readme(manifest), encoding="utf-8")
    write_inventory_files(manifest)
    print(json.dumps(manifest["summary"], ensure_ascii=False, sort_keys=True))
    return manifest


def check() -> None:
    manifest_path = BUNDLE_ROOT / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("evidence_library_missing: run without --check first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for row in manifest.get("entries", []):
        bundle_path = BUNDLE_ROOT / str(row["bundle_path"])
        target = Path(str(row["target_path"]))
        if row.get("link_created") and not bundle_path.is_symlink():
            errors.append(f"not_a_symlink:{row['bundle_path']}")
        if row.get("exists") and not target.exists():
            errors.append(f"target_now_missing:{row['bundle_path']}")
        if target.is_file() and row.get("sha256"):
            actual = sha256_file(target)
            if actual != row["sha256"]:
                errors.append(f"sha256_mismatch:{row['bundle_path']}")
    for relative_path in DEPRECATED_BUNDLE_LINKS:
        if (BUNDLE_ROOT / relative_path).is_symlink():
            errors.append(f"deprecated_link_present:{relative_path}")
    if manifest.get("policy", {}).get("copies_source_files") is not False:
        errors.append("copy_policy_not_fail_closed")
    if errors:
        raise SystemExit("evidence_library_check_failed\n" + "\n".join(errors))
    missing_runtime = sum(
        not bool(row.get("source_exists"))
        for row in manifest.get("runtime_source_audit", [])
    )
    recovered = sum(
        bool(row.get("recovery_candidate_path"))
        for row in manifest.get("runtime_source_audit", [])
    )
    print(
        f"evidence_library_ok entries={len(manifest.get('entries', []))} "
        f"runtime_missing={missing_runtime} recovery_candidates={recovered}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the existing evidence-library links and checksums")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.check:
        check()
    else:
        build()
