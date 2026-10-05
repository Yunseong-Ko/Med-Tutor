#!/usr/bin/env python3
"""Build or verify the Ontology track checksum manifest.

Only file metadata and aggregate registry statistics are emitted.  The script
does not print or transmit question text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
OUT = ROOT / "docs" / "Ontology_Manifest_20260717.json"
EXTERNAL_KG_DIR = DP / "external_kg" / "primekg"
KR_GUIDELINE_DIR = DP / "kr_guidelines"
US_GUIDELINE_DIR = DP / "us_guidelines"
GUIDELINE_MAP_DIR = DP / "guideline_map"

CORE_DATA = [
    DP / "harrison" / "concept_to_harrison.json",
    DP / "embedding" / "consolidated_qbank.json",
    DP / "concept_registry.json",
    DP / "embedding" / "qbank_relabeled.json",
]

ONTOLOGY_SCRIPTS = [
    "apply_clinical_axes_legacy_safety_fixes_20260712.py",
    "apply_clinical_axes_legacy_safety_fixes_batch2_20260712.py",
    "apply_clinical_axes_legacy_safety_fixes_batch3_20260712.py",
    "apply_clinical_axes_safety_fixes_20260712.py",
    "attach_clinical_axes_alternate_evidence_20260712.py",
    "apply_topic_recovery.py",
    "assemble_item_evidence_pack.py",
    "audit_clinical_axes_expansion.py",
    "audit_ontology_v1.py",
    "audit_harrison_mappings.py",
    "author_clinical_axes_batch.py",
    "build_bridge_layer.py",
    "build_axis_layer.py",
    "build_harrison22_snapshot.py",
    "build_clinical_axis_review_worklist.py",
    "build_concept_registry.py",
    "build_endpoint_types.py",
    "build_evidence_library.py",
    "build_external_kg_review_worklist.py",
    "build_finding_endpoint_review_worklist.py",
    "build_finding_layer.py",
    "build_guideline_agent_map.py",
    "build_kr_guideline_claim_worklist.py",
    "build_kr_guideline_overlays.py",
    "build_mondo_taxonomy.py",
    "build_ontology_hardening_worklist.py",
    "build_ontology_manifest.py",
    "rebuild_ontology_harrison22.py",
    "revalidate_ontology_harrison22.py",
    "build_primekg_heme_phenotype_pilot.py",
    "build_course_exam_media_label_worklist.py",
    "build_media_visual_review_selection.py",
    "build_question_links.py",
    "build_typed_entity_registry.py",
    "export_ontology_neo4j.py",
    "export_ontology_obsidian.py",
    "attach_hemeonc_ontology.py",
    "generation_grounding.py",
    "ingest_kr_guideline_sources.py",
    "ingest_us_guideline_sources.py",
    "map_expansion_to_harrison.py",
    "merge_clinical_axes_batches.py",
    "merge_clinical_axes_alternate_batches.py",
    "merge_clinical_axes_scope_splits.py",
    "merge_media_visual_review_candidates.py",
    "migrate_typed_entity_clinical_axes.py",
    "normalize_harrison22_mapping_provenance.py",
    "ontology_trust_kernel_gate.py",
    "process_mondo_xref.py",
    "question_blueprint.py",
    "recover_korean_topic_disease.py",
    "recover_typed_entity_quarantine_archive.py",
    "serve_ontology_graph.py",
    "sync_kr_guideline_catalog.py",
    "validate_clinical_axes_scope_splits.py",
]

SCHEMA_FILES = [
    ROOT / "schemas" / "axis_registry.schema.json",
    ROOT / "schemas" / "harrison_source_snapshot.schema.json",
    ROOT / "schemas" / "harrison22_claim_revalidation.schema.json",
    ROOT / "schemas" / "question_blueprint.schema.json",
    ROOT / "schemas" / "studio_concept.schema.json",
    ROOT / "schemas" / "course_exam_media_labeling.schema.json",
    ROOT / "schemas" / "media_visual_review_candidate.schema.json",
    ROOT / "schemas" / "media_visual_review_selection.schema.json",
    ROOT / "schemas" / "ontology_trust_kernel_release.schema.json",
    ROOT / "schemas" / "feedback_packet.schema.json",
    ROOT / "schemas" / "external_kg_snapshot_manifest.schema.json",
    ROOT / "schemas" / "external_kg_crosswalk.schema.json",
    ROOT / "schemas" / "external_kg_candidate_graph.schema.json",
    ROOT / "schemas" / "external_kg_validation_report.schema.json",
    ROOT / "schemas" / "external_kg_review_worklist.schema.json",
    ROOT / "schemas" / "external_kg_review_decisions.schema.json",
    ROOT / "schemas" / "kr_guideline_source_registry.schema.json",
    ROOT / "schemas" / "kr_guideline_ontology_overlay.schema.json",
    ROOT / "schemas" / "kr_guideline_agent_registry.schema.json",
    ROOT / "schemas" / "kr_guideline_claim_worklist.schema.json",
    ROOT / "schemas" / "us_guideline_source_registry.schema.json",
    ROOT / "schemas" / "guideline_agent_map.schema.json",
    ROOT / "schemas" / "guideline_atomic_claim_candidate.schema.json",
]

STAGE_XY_OUTPUTS = [
    DP / "curriculum" / "ontology_review_decisions.json",
    DP / "curriculum" / "ontology_hardening_worklist_20260712.json",
    DP / "curriculum" / "clinical_axis_review_worklist_20260712.json",
    DP / "curriculum" / "finding_endpoint_review_worklist_20260712.json",
]

CONSUMER_FILES = [
    ROOT / "api_server.py",
    ROOT / "frontend" / "ontology_graph_live.html",
    ROOT / "frontend" / "app.js",
    ROOT / "src" / "services" / "lecture_studio.py",
    ROOT / "src" / "services" / "ontology_feedback.py",
    ROOT / "src" / "services" / "external_kg_adapter.py",
    ROOT / "src" / "services" / "external_kg_review.py",
    ROOT / "src" / "services" / "guideline_agent_map.py",
    ROOT / "docs" / "Ontology_V1_Readiness_20260711.json",
]

DOCUMENTATION_FILES = [
    ROOT / "docs" / "Ontology_Codex_Handoff_20260711.md",
    ROOT / "docs" / "Ontology_Autonomous_Session_Log_20260711.md",
    ROOT / "docs" / "Codex_Handoff_RAG_Hardening_20260713.md",
    ROOT / "docs" / "Claude_Ontology_Feedback_RAG_UIUX_Handoff_20260712.md",
    ROOT / "docs" / "Lecture_Ontology_StudyGen_Plan_20260712.md",
    ROOT / "docs" / "Question_Media_Labeling_Pilot_20260712.md",
    ROOT / "docs" / "Question_Ontology_Review_DataLayer.md",
    ROOT / "docs" / "ontology" / "README.md",
    ROOT / "docs" / "ontology" / "STATUS.md",
    ROOT / "docs" / "ontology" / "FILE_INDEX.md",
    ROOT / "docs" / "ontology" / "CHANGELOG.md",
    ROOT / "docs" / "ontology" / "EXTERNAL_KG_SECONDARY_VALIDATION.md",
    ROOT / "docs" / "ontology" / "HARRISON_22E_REVALIDATION.md",
    ROOT / "docs" / "ontology" / "KR_GUIDELINE_OVERLAYS.md",
    ROOT / "docs" / "ontology" / "US_GUIDELINE_OVERLAY.md",
    ROOT / "docs" / "ontology" / "GUIDELINE_AGENT_MAP.md",
    ROOT / "docs" / "KMLE_Korean_Guideline_Sourcing_Design_20260716.md",
]

EXTENSION_DATA = [
    DP / "harrison" / "22e" / "snapshot_manifest.json",
    DP / "harrison" / "22e" / "chapter_index.json",
    DP / "harrison" / "22e" / "pages.jsonl",
    DP / "harrison" / "22e" / "concept_harrison_overlay.json",
    DP / "harrison" / "22e" / "baseline" / "current_ontology_manifest.json",
    DP / "harrison" / "22e" / "baseline" / "claim_identity_snapshot.json",
    DP / "harrison" / "22e" / "validation" / "claim_support_overlay.json",
    DP / "harrison" / "22e" / "validation" / "review_worklist.json",
    DP / "harrison" / "22e" / "validation" / "downstream_impact.json",
    DP / "harrison" / "22e" / "validation" / "summary.json",
    DP / "harrison" / "22e" / "rebuild_report.json",
    DP / "ontology" / "question_links.json",
    DP / "course_exams" / "media_labeling" / "manifest.json",
    DP / "course_exams" / "media_labeling" / "ai_visual_review_manifest.json",
    DP / "course_exams" / "media_labeling" / "ai_visual_review_selection.json",
    DP / "course_exams" / "media_labeling" / "ai_visual_review_candidates.jsonl",
    DP / "concept_notes" / "hemeonc_concept_notes.json",
    DP / "anki_exports" / "paccine_혈액종양_강의연습문항_20260712.manifest.json",
    DP / "anki_exports" / "paccine_혈액종양내과_Ontology해설_20260712.manifest.json",
    EXTERNAL_KG_DIR / "README.md",
    EXTERNAL_KG_DIR / "source_manifest.json",
    EXTERNAL_KG_DIR / "heme_onc_mondo_crosswalk.json",
    EXTERNAL_KG_DIR / "heme_onc_phenotype_candidate_graph.json",
    EXTERNAL_KG_DIR / "heme_onc_validation_report.json",
    EXTERNAL_KG_DIR / "review_worklist.json",
    EXTERNAL_KG_DIR / "review_decisions.json",
    EXTERNAL_KG_DIR / "heme_onc_full" / "README.md",
    EXTERNAL_KG_DIR / "heme_onc_full" / "source_manifest.json",
    EXTERNAL_KG_DIR / "heme_onc_full" / "heme_onc_scope_audit.json",
    EXTERNAL_KG_DIR / "heme_onc_full" / "heme_onc_mondo_crosswalk.json",
    EXTERNAL_KG_DIR / "heme_onc_full" / "heme_onc_phenotype_candidate_graph.json",
    EXTERNAL_KG_DIR / "heme_onc_full" / "heme_onc_validation_report.json",
    EXTERNAL_KG_DIR / "heme_onc_full" / "review_worklist.json",
    EXTERNAL_KG_DIR / "heme_onc_full" / "review_decisions.json",
    KR_GUIDELINE_DIR / "catalog" / "kams_registered_catalog.json",
    KR_GUIDELINE_DIR / "verified_latest_registry.json",
    KR_GUIDELINE_DIR / "download_review_queue.json",
    KR_GUIDELINE_DIR / "seeds" / "acute_respiratory_seed.json",
    KR_GUIDELINE_DIR / "seeds" / "internal_medicine_seed.json",
    KR_GUIDELINE_DIR / "seeds" / "specialty_seed.json",
    KR_GUIDELINE_DIR / "ontology_overlay.json",
    KR_GUIDELINE_DIR / "specialty_agent_registry.json",
    KR_GUIDELINE_DIR / "claim_extraction_worklist.json",
    US_GUIDELINE_DIR / "README.md",
    US_GUIDELINE_DIR / "seeds" / "core_sources.json",
    US_GUIDELINE_DIR / "verified_latest_registry.json",
    US_GUIDELINE_DIR / "download_review_queue.json",
    US_GUIDELINE_DIR / "official_watch_hubs.json",
    US_GUIDELINE_DIR / "jurisdiction_policy.json",
    GUIDELINE_MAP_DIR / "seeds" / "pilot_claim_candidates.json",
    GUIDELINE_MAP_DIR / "source_map.json",
    GUIDELINE_MAP_DIR / "atomic_claim_candidates.json",
    DP / "curriculum" / "kr_guideline_expansion_final.json",
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_record(path: Path) -> dict:
    raw = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def has_harrison(node: dict) -> bool:
    ref = (node.get("evidence") or {}).get("harrison")
    return bool(ref and ref.get("chapter") is not None and ref.get("page") is not None)


def build_external_kg_profile_summary(directory: Path, *, scope_audit: bool = False) -> dict:
    crosswalk = load_json(directory / "heme_onc_mondo_crosswalk.json")
    graph = load_json(directory / "heme_onc_phenotype_candidate_graph.json")
    validation = load_json(directory / "heme_onc_validation_report.json")
    worklist = load_json(directory / "review_worklist.json")
    decisions = load_json(directory / "review_decisions.json")
    mappings = crosswalk.get("mappings") or []
    edges = graph.get("edges") or []
    exact = [row for row in mappings if row.get("mapping_method") == "identifier_exact"]
    grouped = [row for row in mappings if row.get("mapping_method") == "group_member_candidate"]
    source_rows = sum(
        len((((edge.get("qualifiers") or {}).get("primekg_source_record") or {}).get("source_rows") or []))
        for edge in edges
    )
    external_new_polarity = Counter(
        polarity
        for item in validation.get("items") or []
        if item.get("classification") == "external_new_candidate"
        for polarity in (item.get("external_polarities") or ["unknown"])
    )
    required_gate = {
        "status": "human_review_required",
        "needs_review": True,
        "medical_approval": False,
        "student_visible": False,
        "analytics_eligible": False,
        "promotion_status": "not_promoted",
    }
    result = {
        "selected_concepts": len((graph.get("scope") or {}).get("local_concept_ids") or []),
        "crosswalk": {
            "mappings": len(mappings),
            "exact_ungrouped_mondo": len(exact),
            "exact_name_exact": sum(row.get("mapping_relation") == "exact_match" for row in exact),
            "exact_name_close": sum(row.get("mapping_relation") == "close_match" for row in exact),
            "grouped_excluded": len(grouped),
        },
        "candidate_graph": {
            "nodes": len(graph.get("nodes") or []),
            "edges": len(edges),
            "polarity": dict(sorted(Counter(row.get("polarity") or "unknown" for row in edges).items())),
            "matched_source_rows": source_rows,
            "reverse_or_duplicate_rows_collapsed": max(0, source_rows - len(edges)),
            "paccine_subject_edges": sum(
                str((edge.get("subject") or {}).get("curie") or "").startswith("PACCINE:")
                or (edge.get("subject") or {}).get("source_namespace") == "PACCINE"
                for edge in edges
            ),
        },
        "validation": {
            **(validation.get("stats") or {}),
            "external_new_polarity": dict(sorted(external_new_polarity.items())),
        },
        "human_review_worklist": {
            **(worklist.get("stats") or {}),
            "worklist_id": worklist.get("worklist_id"),
            "decision_count": len(decisions.get("decisions") or []),
            "all_items_fail_closed": all(
                (row.get("review_gate") or {}) == required_gate
                for row in worklist.get("items") or []
            ),
        },
    }
    if scope_audit:
        result["scope_audit"] = load_json(directory / "heme_onc_scope_audit.json").get("stats") or {}
    return result


def build_external_kg_summary() -> dict:
    """Summarize the review-only external KG layer without importing raw snapshots."""
    source_manifest = load_json(EXTERNAL_KG_DIR / "source_manifest.json")
    crosswalk = load_json(EXTERNAL_KG_DIR / "heme_onc_mondo_crosswalk.json")
    graph = load_json(EXTERNAL_KG_DIR / "heme_onc_phenotype_candidate_graph.json")
    validation = load_json(EXTERNAL_KG_DIR / "heme_onc_validation_report.json")

    mappings = crosswalk.get("mappings") or []
    edges = graph.get("edges") or []
    items = validation.get("items") or []
    exact_mappings = [row for row in mappings if row.get("mapping_method") == "identifier_exact"]
    grouped_mappings = [row for row in mappings if row.get("mapping_method") == "group_member_candidate"]
    polarity_counts = Counter(row.get("polarity") or "unknown" for row in edges)
    external_new_polarities = Counter(
        polarity
        for item in items
        if item.get("classification") == "external_new_candidate"
        for polarity in (item.get("external_polarities") or ["unknown"])
    )
    matched_source_rows = sum(
        len((((edge.get("qualifiers") or {}).get("primekg_source_record") or {}).get("source_rows") or []))
        for edge in edges
    )
    paccine_subjects = sum(
        str((edge.get("subject") or {}).get("curie") or "").startswith("PACCINE:")
        or (edge.get("subject") or {}).get("source_namespace") == "PACCINE"
        for edge in edges
    )
    required_review = {
        "status": "external_candidate",
        "needs_review": True,
        "medical_approval": False,
        "student_visible": False,
        "analytics_eligible": False,
        "promotion_status": "not_promoted",
    }
    all_edges_fail_closed = all(
        all((edge.get("review") or {}).get(key) == value for key, value in required_review.items())
        for edge in edges
    )
    official_snapshots = {
        row["dataset_name"]: {
            "bytes": (row.get("artifact") or {}).get("byte_size"),
            "sha256": (row.get("artifact") or {}).get("content_sha256"),
            "source_url": row.get("source_url"),
            "redistribution_status": (row.get("license") or {}).get("redistribution_status"),
        }
        for row in (source_manifest.get("snapshots") or [])
        if row.get("dataset_name") in {"PrimeKG nodes.csv", "PrimeKG edges.csv"}
    }
    profile_summaries = {
        "core20": build_external_kg_profile_summary(EXTERNAL_KG_DIR),
        "heme_onc_full": build_external_kg_profile_summary(
            EXTERNAL_KG_DIR / "heme_onc_full", scope_audit=True
        ),
    }

    return {
        "role": "secondary_validation_candidate_only",
        "provider": "primekg",
        "dataset_version": (graph.get("snapshot") or {}).get("dataset_version"),
        "source_manifest_id": source_manifest.get("manifest_id"),
        "official_snapshot_checksums": official_snapshots,
        "official_checksum_verification_required_by_default": True,
        "raw_snapshots_in_repository": False,
        "profiles": profile_summaries,
        "selected_concepts": len((graph.get("scope") or {}).get("local_concept_ids") or []),
        "crosswalk": {
            "mappings": len(mappings),
            "exact_ungrouped_mondo": len(exact_mappings),
            "exact_name_exact": sum(row.get("mapping_relation") == "exact_match" for row in exact_mappings),
            "exact_name_close": sum(row.get("mapping_relation") == "close_match" for row in exact_mappings),
            "grouped_excluded": len(grouped_mappings),
        },
        "candidate_graph": {
            "nodes": len(graph.get("nodes") or []),
            "edges": len(edges),
            "polarity": dict(sorted(polarity_counts.items())),
            "matched_source_rows": matched_source_rows,
            "reverse_or_duplicate_rows_collapsed": max(0, matched_source_rows - len(edges)),
            "paccine_subject_edges": paccine_subjects,
        },
        "validation": {
            **(validation.get("stats") or {}),
            "external_new_polarity": dict(sorted(external_new_polarities.items())),
            "absence_is_not_contradiction": bool(
                (validation.get("interpretation_policy") or {}).get("absence_is_not_contradiction")
            ),
        },
        "safety": {
            **required_review,
            "all_candidate_edges_fail_closed": all_edges_fail_closed,
            "grouped_mapping_is_not_evaluable": True,
            "negated_edges_are_not_positive_findings": True,
        },
    }


def build_kr_guideline_summary() -> dict:
    """Summarize the private Korean-guideline routing layer without hashing source PDFs.

    The verified registry is itself checksummed by this manifest and contains the
    per-attachment size/SHA-256 records.  Reading hundreds of megabytes of private
    source documents again here would add cost without adding a distinct trust
    guarantee, so the raw attachment files are intentionally not manifest entries.
    """
    catalog = load_json(KR_GUIDELINE_DIR / "catalog" / "kams_registered_catalog.json")
    registry = load_json(KR_GUIDELINE_DIR / "verified_latest_registry.json")
    download_queue = load_json(KR_GUIDELINE_DIR / "download_review_queue.json")
    overlay = load_json(KR_GUIDELINE_DIR / "ontology_overlay.json")
    agents = load_json(KR_GUIDELINE_DIR / "specialty_agent_registry.json")
    worklist = load_json(KR_GUIDELINE_DIR / "claim_extraction_worklist.json")
    expansion = load_json(DP / "curriculum" / "kr_guideline_expansion_final.json")
    concepts = load_json(DP / "concept_registry.json").get("concepts") or {}

    sources = registry.get("sources") or []
    attachments = [
        attachment
        for source in sources
        for attachment in (source.get("attachments") or [])
    ]
    downloaded = [row for row in attachments if row.get("download_status") == "downloaded"]
    additions = expansion.get("additions") or []
    addition_ids = [row.get("disease_concept_id") for row in additions if row.get("disease_concept_id")]
    added_nodes = [concepts[cid] for cid in addition_ids if cid in concepts]
    source_links = overlay.get("source_links") or []
    route_profiles = agents.get("agents") or []
    tasks = worklist.get("tasks") or []

    return {
        "role": "official_source_inventory_and_review_routing_not_medical_approval",
        "as_of": registry.get("latest_checked_at"),
        "kams_registered_catalog": {
            "records": (catalog.get("summary") or {}).get("sources"),
            "attachments": (catalog.get("summary") or {}).get("attachments"),
            "catalog_presence_is_latest_proof": False,
            "registry_role": catalog.get("registry_role"),
        },
        "curated_official_sources": {
            "sources": len(sources),
            "attachments": len(attachments),
            "priorities": (registry.get("summary") or {}).get("priorities") or {},
            "latest_statuses": (registry.get("summary") or {}).get("latest_statuses") or {},
            "download_statuses": (registry.get("summary") or {}).get("download_statuses") or {},
            "downloaded_bytes": (registry.get("summary") or {}).get("downloaded_bytes"),
            "download_review_queue": download_queue.get("counts") or {},
            "completeness_claim": "curated_priority_sources_not_exhaustive_all_korean_guidelines",
        },
        "attachment_integrity": {
            "downloaded": len(downloaded),
            "downloaded_with_registered_sha256": sum(bool(row.get("sha256")) for row in downloaded),
            "downloaded_with_registered_size": sum(row.get("bytes") is not None for row in downloaded),
            "all_downloaded_have_registered_sha256": bool(downloaded)
            and all(bool(row.get("sha256")) for row in downloaded),
            "raw_source_files_enumerated_in_manifest": False,
            "integrity_model": "checksummed_registry_with_embedded_per_attachment_sha256",
        },
        "ontology_topic_overlay": {
            **(overlay.get("summary") or {}),
            "role": overlay.get("overlay_role"),
            "all_links_review_only": all(
                row.get("needs_review") is True
                and row.get("medical_approval") is False
                and row.get("canonical_registry_mutated") is False
                for row in source_links
            ),
        },
        "specialty_retrieval_profiles": {
            **(agents.get("summary") or {}),
            "role": agents.get("routing_role"),
            "one_shared_runtime_not_separate_models": True,
            "all_profiles_fail_closed": all(
                row.get("student_retrieval_enabled") is False
                and row.get("generation_retrieval_enabled") is False
                for row in route_profiles
            ),
        },
        "claim_extraction_worklist": {
            **(worklist.get("summary") or {}),
            "role": worklist.get("worklist_role"),
            "tasks_are_claims": False,
            "all_tasks_fail_closed": all(
                row.get("needs_review") is True
                and row.get("medical_approval") is False
                and row.get("student_visible") is False
                and row.get("generation_eligible") is False
                for row in tasks
            ),
        },
        "guideline_topic_expansion": {
            **(expansion.get("summary") or {}),
            "canonical_registry_nodes_present": len(added_nodes),
            "harrison22_chapter_pointers": sum(has_harrison(row) for row in added_nodes),
            "guideline_only_without_harrison_chapter": sum(not has_harrison(row) for row in added_nodes),
            "alias_updates": len(expansion.get("alias_updates") or []),
            "all_added_nodes_need_review": bool(added_nodes)
            and all(row.get("needs_review") is True for row in added_nodes),
        },
        "safety": {
            "all_sources_fail_closed": all(
                row.get("needs_review") is True
                and row.get("medical_approval") is False
                and row.get("student_visible") is False
                for row in sources
            ),
            "medical_approval": 0,
            "student_visible": 0,
            "generation_eligible": 0,
            "automatic_claim_promotion": False,
        },
    }


def build_us_guideline_summary() -> dict:
    """Summarize the U.S. comparison layer without re-enumerating private PDFs."""
    registry = load_json(US_GUIDELINE_DIR / "verified_latest_registry.json")
    download_queue = load_json(US_GUIDELINE_DIR / "download_review_queue.json")
    watch_hubs = load_json(US_GUIDELINE_DIR / "official_watch_hubs.json")
    jurisdiction = load_json(US_GUIDELINE_DIR / "jurisdiction_policy.json")
    registry_jurisdiction = registry.get("jurisdiction_policy") or {}
    sources = registry.get("sources") or []
    attachments = [
        attachment
        for source in sources
        for attachment in (source.get("attachments") or [])
    ]
    downloaded = [row for row in attachments if row.get("download_status") == "downloaded"]

    return {
        "role": registry.get("registry_role"),
        "as_of": registry.get("latest_checked_at"),
        "curated_official_sources": {
            **(registry.get("summary") or {}),
            "download_review_queue": download_queue.get("counts") or {},
            "completeness_claim": "curated_core_sources_not_exhaustive_all_us_guidelines",
        },
        "attachment_integrity": {
            "downloaded": len(downloaded),
            "downloaded_with_registered_sha256": sum(bool(row.get("sha256")) for row in downloaded),
            "downloaded_with_registered_size": sum(row.get("bytes") is not None for row in downloaded),
            "downloaded_with_pdf_page_check": sum(row.get("pdf_pages") is not None for row in downloaded),
            "all_downloaded_have_registered_sha256": bool(downloaded)
            and all(bool(row.get("sha256")) for row in downloaded),
            "raw_source_files_enumerated_in_manifest": False,
            "integrity_model": "checksummed_registry_with_embedded_per_attachment_sha256",
        },
        "jurisdiction": {
            "primary_for_korean_care": registry_jurisdiction.get("primary_for_korean_care"),
            "silent_merge_allowed": (jurisdiction.get("conflict_policy") or {}).get(
                "silent_merge_allowed"
            ),
            "modes": sorted((jurisdiction.get("modes") or {}).keys()),
        },
        "watch_hubs": {
            "count": len(watch_hubs.get("hubs") or []),
            "source_of_truth": "official_issuer_pages",
        },
        "safety": {
            "all_sources_fail_closed": bool(sources)
            and all(
                row.get("needs_review") is True
                and row.get("medical_approval") is False
                and row.get("student_visible") is False
                and row.get("generation_eligible") is False
                and (row.get("rights") or {}).get("runtime_ingest_allowed") is False
                for row in sources
            ),
            "medical_approval": 0,
            "student_visible": 0,
            "generation_eligible": 0,
            "runtime_ingest_enabled": 0,
            "automatic_claim_promotion": False,
        },
    }


def build_guideline_agent_map_summary() -> dict:
    source_map = load_json(GUIDELINE_MAP_DIR / "source_map.json")
    claims = load_json(GUIDELINE_MAP_DIR / "atomic_claim_candidates.json")
    sources = source_map.get("sources") or []
    candidates = claims.get("candidates") or []
    return {
        "role": source_map.get("map_role"),
        "generated_at": source_map.get("generated_at"),
        "source_map": source_map.get("summary") or {},
        "atomic_claim_pilot": claims.get("summary") or {},
        "routing_modes": sorted((source_map.get("routing_modes") or {}).keys()),
        "safety": {
            "all_sources_review_only": bool(sources)
            and all(
                (item.get("review_state") or {}).get("medical_approval") is False
                and (item.get("review_state") or {}).get("student_visible") is False
                and (item.get("review_state") or {}).get("generation_eligible") is False
                for item in sources
            ),
            "all_candidates_runtime_ineligible": bool(candidates)
            and all(
                (item.get("review_state") or {}).get("runtime_answer_eligible") is False
                and (item.get("review_state") or {}).get("medical_approval") is False
                for item in candidates
            ),
            "source_text_stored": (claims.get("summary") or {}).get("source_text_stored"),
            "silent_cross_jurisdiction_merge": False,
            "canonical_ontology_mutations": 0,
        },
    }


def build_summary() -> dict:
    registry = load_json(DP / "concept_registry.json")
    concepts = registry["concepts"]
    seed_ids = {cid for cid, node in concepts.items() if node.get("source") == "concept_to_harrison_seed"}
    expansion_ids = set(concepts) - seed_ids

    edge_counts = Counter()
    for node in concepts.values():
        for edge_type, values in (node.get("edges") or {}).items():
            if isinstance(values, list):
                edge_counts[edge_type] += len(values)

    worklist = load_json(DP / "curriculum" / "clinical_axes_worklist.json").get("items", [])
    axes = load_json(DP / "curriculum" / "clinical_axes_map.json").get("axes", {})
    grounded_worklist_ids = {
        item["id"] for item in worklist
        if item.get("harrison") and item["harrison"].get("chapter") is not None
        and item["harrison"].get("page") is not None
    }

    relabeled = load_json(DP / "embedding" / "qbank_relabeled.json")
    questions = relabeled.get("items", relabeled.get("questions", relabeled if isinstance(relabeled, list) else []))
    covered = sum(bool(row.get("disease_concept_id")) for row in questions)
    packs = load_json(DP / "curriculum" / "item_evidence_packs.json").get("packs", [])
    batch_axes = set()
    new_batch_axes = set()
    for path in sorted((DP / "curriculum" / "clinical_axes_batches").glob("*.json")):
        ids = set(load_json(path).get("axes", {}))
        batch_axes.update(ids)
        if "batch_001_" not in path.name:
            new_batch_axes.update(ids)
    axis_registry = load_json(DP / "curriculum" / "axis_registry.json")
    axis_stats = axis_registry.get("stats") or {}
    hardening_summary = load_json(
        DP / "curriculum" / "ontology_hardening_worklist_20260712.json"
    ).get("summary", {})
    claim_review_summary = load_json(
        DP / "curriculum" / "clinical_axis_review_worklist_20260712.json"
    ).get("summary", {})
    finding_endpoint_summary = load_json(
        DP / "curriculum" / "finding_endpoint_review_worklist_20260712.json"
    ).get("summary", {})
    readiness = load_json(ROOT / "docs" / "Ontology_V1_Readiness_20260711.json")
    student_policy_probes = readiness.get("student_approved_policy_probes") or []
    axis_claims_total = int(axis_stats.get("nodes") or 0) + int(axis_stats.get("relationships") or 0)
    approved_axis_claims = int(axis_stats.get("medical_approval_claims") or 0)
    unverified_axis_claims = sum(
        int(count or 0)
        for status, count in (axis_stats.get("claim_entailment_statuses") or {}).items()
        if status != "verified"
    )
    clinical_audit_path = DP / "curriculum" / "clinical_axes_audits" / "clinical_axes_map_20260712.audit.json"
    clinical_audit = load_json(clinical_audit_path).get("summary", {}) if clinical_audit_path.exists() else {}
    typed_registry_path = DP / "curriculum" / "typed_entity_registry.json"
    typed_registry = load_json(typed_registry_path) if typed_registry_path.exists() else {"entities": {}, "_meta": {}}
    typed_entities = typed_registry.get("entities") or {}
    active_disease_ids = {
        cid
        for cid, row in concepts.items()
        if cid not in typed_entities and row.get("node_type") in {"disease", "neoplasm", "syndrome"}
    }
    classification_ids = {
        cid for cid, row in concepts.items() if cid not in typed_entities and row.get("node_type") == "category"
    }
    alternate_grounded_axes = {cid for cid, row in axes.items() if row.get("evidence_refs")}
    active_grounded_worklist_ids = grounded_worklist_ids - set(typed_entities)
    question_links_path = DP / "ontology" / "question_links.json"
    question_links_summary = (
        load_json(question_links_path).get("meta") or {}
        if question_links_path.exists()
        else {}
    )
    media_manifest_path = DP / "course_exams" / "media_labeling" / "manifest.json"
    media_summary = (
        load_json(media_manifest_path).get("summary") or {}
        if media_manifest_path.exists()
        else {}
    )
    visual_manifest_path = DP / "course_exams" / "media_labeling" / "ai_visual_review_manifest.json"
    visual_media_summary = (
        load_json(visual_manifest_path).get("summary") or {}
        if visual_manifest_path.exists()
        else {}
    )

    return {
        "concepts": len(concepts),
        "disease_export_concepts": len(active_disease_ids),
        "classification_nodes": len(classification_ids),
        "typed_entities": len(typed_entities),
        "typed_entity_types": (typed_registry.get("_meta") or {}).get("counts_by_entity_type", {}),
        "seed": len(seed_ids),
        "expansion_effective": len(expansion_ids),
        "harrison_mapped_seed": sum(has_harrison(concepts[cid]) for cid in seed_ids),
        "harrison_mapped_expansion": sum(has_harrison(concepts[cid]) for cid in expansion_ids),
        "harrison_mapped_total": sum(has_harrison(node) for node in concepts.values()),
        "mondo_xref": registry["_meta"].get("mondo_xref_count"),
        "mondo_taxonomy": registry["_meta"].get("mondo_taxonomy_count"),
        "clinical_axes": len(axes),
        "clinical_axes_worklist_total": len(worklist),
        "clinical_axes_worklist_harrison_grounded": len(grounded_worklist_ids),
        "clinical_axes_worklist_active_harrison_grounded": len(active_grounded_worklist_ids),
        "clinical_axes_harrison_grounded": len(set(axes) & grounded_worklist_ids),
        "clinical_axes_alternate_source_grounded": len(alternate_grounded_axes),
        "clinical_axes_source_grounded_total": len((set(axes) & grounded_worklist_ids) | alternate_grounded_axes),
        "clinical_axes_grounded_remaining": len(active_grounded_worklist_ids - set(axes)),
        "clinical_axes_without_harrison_after_audit": len(set(axes) - grounded_worklist_ids),
        "clinical_axes_batch_authored": len(batch_axes),
        "clinical_axes_new_batch_20260712": len(new_batch_axes),
        "clinical_axes_merged_quality_blockers": clinical_audit.get("blocking_issues"),
        "clinical_axes_review_warnings": clinical_audit.get("warnings"),
        "scope_split_concepts": (registry.get("_meta") or {}).get("clinical_scope_split", {}).get("added", 0),
        "axis_registry_schema_version": axis_registry.get("schema_version"),
        "axis_layer_nodes": axis_stats.get("nodes"),
        "axis_layer_relationships": axis_stats.get("relationships"),
        "axis_layer_diseases_covered": axis_stats.get("diseases_covered"),
        "axis_layer_types": axis_stats.get("types", {}),
        "axis_claim_review": {
            "claims_total": axis_claims_total,
            "claims_medically_approved": approved_axis_claims,
            "claims_without_verified_entailment": unverified_axis_claims,
            "review_decisions_applied": int(axis_stats.get("review_decisions_applied") or 0),
            "all_claims_unapproved": axis_claims_total > 0 and approved_axis_claims == 0,
            "student_approved_probe_count": len(student_policy_probes),
            "student_approved_fail_closed": bool(student_policy_probes)
            and all(bool(row.get("safe_fail_closed")) for row in student_policy_probes),
            "student_approved_packs_exposed": sum(bool(row.get("pack_exposed")) for row in student_policy_probes),
        },
        "hardening_worklists": {
            "ontology": {
                "active_disease_like_concepts": hardening_summary.get("active_disease_like_concepts"),
                "generation_groundable_concepts": hardening_summary.get("generation_groundable_concepts"),
                "axis_missing_all": hardening_summary.get("axis_missing_all"),
                "axis_missing_generation_groundable": hardening_summary.get("axis_missing_generation_groundable"),
                "evidence_missing_generation_groundable": hardening_summary.get("evidence_missing_generation_groundable"),
                "distractor_pool_lt_4": hardening_summary.get("distractor_pool_lt_4"),
                "distractor_pool_zero": hardening_summary.get("distractor_pool_zero"),
                "clinical_axis_review_warnings": hardening_summary.get("clinical_axis_review_warnings"),
                "unresolved_endpoint_ids": hardening_summary.get("unresolved_endpoint_ids"),
            },
            "clinical_axis_review": {
                "review_items": claim_review_summary.get("review_items"),
                "claims": claim_review_summary.get("claims"),
                "claims_mapped_to_axis": claim_review_summary.get("claims_mapped_to_axis"),
                "claims_without_materialized_axis": claim_review_summary.get("claims_without_materialized_axis"),
                "priorities": claim_review_summary.get("priorities") or {},
                "pending_decisions": claim_review_summary.get("pending_decisions"),
            },
            "finding_endpoint_review": finding_endpoint_summary,
        },
        "item_evidence_packs": len(packs),
        "isa_edges": registry["_meta"].get("isa_edge_count"),
        "p2_edge_nodes": registry["_meta"].get("p2_edges_applied"),
        "qbank_coverage": {"covered": covered, "total": len(questions)},
        "question_links": question_links_summary,
        "media_labeling": media_summary,
        "media_visual_review": visual_media_summary,
        "external_kg_secondary_validation": build_external_kg_summary(),
        "kr_guideline_review_routing": build_kr_guideline_summary(),
        "us_guideline_comparison_sources": build_us_guideline_summary(),
        "guideline_agent_map": build_guideline_agent_map_summary(),
        "all_needs_review": all(node.get("needs_review") is True for node in concepts.values()),
        "edge_counts": dict(sorted(edge_counts.items())),
    }


def current_payload() -> dict:
    curriculum = sorted((DP / "curriculum").rglob("*.json"))
    lecture_anchors = sorted((DP / "lectures").glob("*/ontology_anchor.json"))
    script_paths = [ROOT / "scripts" / name for name in ONTOLOGY_SCRIPTS]
    data_paths = list(dict.fromkeys(CORE_DATA + curriculum + EXTENSION_DATA + lecture_anchors))
    missing = [
        path
        for path in CORE_DATA + EXTENSION_DATA + script_paths + SCHEMA_FILES + STAGE_XY_OUTPUTS + CONSUMER_FILES + DOCUMENTATION_FILES
        if not path.exists()
    ]
    if missing:
        raise SystemExit("Missing manifest inputs: " + ", ".join(str(p) for p in missing))
    return {
        "data_inputs_outputs": [
            file_record(path)
            for path in data_paths
        ],
        "scripts": [file_record(path) for path in script_paths],
        "schema_files": [file_record(path) for path in SCHEMA_FILES],
        "consumer_files": [file_record(path) for path in CONSUMER_FILES],
        "documentation_files": [file_record(path) for path in DOCUMENTATION_FILES],
        "registry_summary": build_summary(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify the existing manifest without rewriting it")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    output_path = args.output.expanduser().resolve()
    current = current_payload()

    if args.check:
        existing = load_json(output_path)
        errors = []
        for key in (
            "data_inputs_outputs",
            "scripts",
            "schema_files",
            "consumer_files",
            "documentation_files",
            "registry_summary",
        ):
            if existing.get(key) != current.get(key):
                errors.append(key)
        if errors:
            raise SystemExit("Manifest mismatch: " + ", ".join(errors))
        print(
            "manifest_ok files="
            f"{len(current['data_inputs_outputs']) + len(current['scripts']) + len(current['schema_files']) + len(current['consumer_files']) + len(current['documentation_files'])} "
            f"harrison={current['registry_summary']['harrison_mapped_total']}"
        )
        return

    payload = {
        "_meta": {
            "manifest_version": "3.3.0",
            "generated": datetime.now(timezone.utc).isoformat(),
            "purpose": "Ontology 트랙 재현/복원 검증 manifest (data_private는 git-ignored). checksum으로 산출물 무결성 확인.",
            "rebuild": [
                "python3 scripts/sync_kr_guideline_catalog.py --with-details --download-year-min 2025  # catalog presence alone does not prove latest status",
                "python3 scripts/ingest_kr_guideline_sources.py --download  # private integrity mirror; not redistribution or medical approval",
                "python3 scripts/ingest_us_guideline_sources.py --download  # only rights-conditioned private snapshots; all runtime use remains disabled",
                "python3 scripts/build_guideline_agent_map.py  # source navigation + review-only atomic claim pilot; no runtime medical release",
                "python3 scripts/rebuild_ontology_harrison22.py  # licensed 22e PDFs remain private/local",
                "python3 scripts/audit_harrison_mappings.py --apply",
                "python3 scripts/apply_clinical_axes_safety_fixes_20260712.py --apply",
                "python3 scripts/merge_clinical_axes_batches.py --apply",
                "python3 scripts/apply_clinical_axes_legacy_safety_fixes_20260712.py --apply",
                "python3 scripts/apply_clinical_axes_legacy_safety_fixes_batch2_20260712.py --apply",
                "python3 scripts/apply_clinical_axes_legacy_safety_fixes_batch3_20260712.py --apply",
                "python3 scripts/merge_clinical_axes_alternate_batches.py --apply",
                "python3 scripts/attach_clinical_axes_alternate_evidence_20260712.py --apply",
                "python3 scripts/merge_clinical_axes_scope_splits.py --apply",
                "python3 scripts/build_concept_registry.py",
                "python3 scripts/map_expansion_to_harrison.py",
                "python3 scripts/build_concept_registry.py  # apply curated 22e pointers while preserving needs_review",
                "python3 scripts/build_kr_guideline_overlays.py",
                "python3 scripts/build_kr_guideline_claim_worklist.py",
                "python3 scripts/build_evidence_library.py  # non-destructive private symlink view; no source copies",
                "python3 scripts/apply_topic_recovery.py",
                "python3 scripts/build_typed_entity_registry.py",
                "python3 scripts/migrate_typed_entity_clinical_axes.py --apply",
                "python3 scripts/build_typed_entity_registry.py",
                "python3 scripts/audit_clinical_axes_expansion.py data_private/curriculum/clinical_axes_map.json --strict --output data_private/curriculum/clinical_axes_audits/clinical_axes_map_20260712.audit.json",
                "python3 scripts/build_axis_layer.py",
                "python3 scripts/build_clinical_axis_review_worklist.py",
                "python3 scripts/build_finding_endpoint_review_worklist.py",
                "python3 scripts/build_ontology_hardening_worklist.py",
                "python3 scripts/audit_ontology_v1.py",
                "python3 scripts/build_primekg_heme_phenotype_pilot.py --nodes /private/tmp/primekg_nodes_original.csv --edges /private/tmp/primekg_edges.csv  # official bytes+MD5 verified by default; raw 394MB snapshot is not copied into the repository",
                "python3 scripts/build_primekg_heme_phenotype_pilot.py --profile heme-onc-full --nodes /private/tmp/primekg_nodes_original.csv --edges /private/tmp/primekg_edges.csv",
                "python3 scripts/build_external_kg_review_worklist.py",
                "python3 scripts/build_external_kg_review_worklist.py --validation-report data_private/external_kg/primekg/heme_onc_full/heme_onc_validation_report.json --candidate-graph data_private/external_kg/primekg/heme_onc_full/heme_onc_phenotype_candidate_graph.json --crosswalk data_private/external_kg/primekg/heme_onc_full/heme_onc_mondo_crosswalk.json --output data_private/external_kg/primekg/heme_onc_full/review_worklist.json --decisions-output data_private/external_kg/primekg/heme_onc_full/review_decisions.json --scope-id heme_onc_full",
            ],
            "stage_xy_outputs": [str(path.relative_to(ROOT)) for path in STAGE_XY_OUTPUTS],
            "extension_outputs": [str(path.relative_to(ROOT)) for path in EXTENSION_DATA],
            "runtime_schemas": [str(path.relative_to(ROOT)) for path in SCHEMA_FILES],
            "verify": "python3 scripts/build_ontology_manifest.py --check",
            "note": (
                "ontology_review_decisions.json은 사람 검토 입력이며 기본값은 비어 있다. "
                f"축·관계 {current['registry_summary']['axis_claim_review']['claims_total']:,} claim은 현재 모두 미승인이고 student_approved 정책은 fail-closed다. "
                "Harrison 22e retrieval candidate는 자동 entailment·의학 승인이 아니다. "
                "finding/endpoint worklist의 분류는 검토 후보일 뿐 자동 표준화·의학승인이 아니다. "
                "PrimeKG는 2차 교차검증용 external candidate 층으로만 사용하며, 부재는 모순이 아니고 "
                "grouped MONDO는 비교 불가다. core20/full 검토 큐와 사람 decision overlay도 별도 curated "
                "promotion gate 전에는 canonical 병합·문항 생성·학생 노출·analytics에 사용하지 않는다. "
                "국내 가이드라인은 우선순위 공식 소스 inventory와 review-routing layer이며 전체 국내 지침을 "
                "망라했다는 뜻이 아니다. KAMS 등록 여부만으로 최신판을 확정하지 않고, 원문 파일은 manifest에 "
                "중복 열거하지 않으며 checksum된 source registry 안의 첨부별 SHA-256으로 무결성을 고정한다. "
                "가이드라인 topic 연결·전문의 route·claim extraction task는 모두 검토 후보이며 실제 claim, "
                "의학 승인, 학생 노출 또는 문항 생성 권한이 아니다. "
                "미국 가이드라인은 KR clinical·US exam·연구 비교를 분리한 보조 source inventory다. "
                "대한민국 진료의 primary source가 아니며 국내외 권고를 자동 병합하지 않는다. 권리가 확인되지 "
                "않은 13개 attachment는 metadata-only이고, 저장된 3개 private snapshot도 runtime RAG·TDM·모델 "
                "학습·학생 공개·문항 생성에는 사용하지 않는다."
                " Guideline Agent Map은 KR·US source navigation용이며 medical evidence가 아니다. 당뇨·"
                "이상지질혈증·AMR 36개 atomic claim 후보는 독립 paraphrase review queue이고 사람 release 전에는 "
                "Q&A·Anki·학생 피드백·문항 생성에 사용할 수 없다."
            ),
        },
        **current,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "manifest_written files="
        f"{len(current['data_inputs_outputs']) + len(current['scripts']) + len(current['schema_files']) + len(current['consumer_files']) + len(current['documentation_files'])} "
        f"harrison={current['registry_summary']['harrison_mapped_total']}"
    )


if __name__ == "__main__":
    main()
