from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from scripts import build_kr_guideline_overlays as overlays
from scripts import ingest_kr_guideline_sources as ingest


ROOT = Path(__file__).resolve().parents[1]


def private_artifact(relative_path: str) -> Path:
    path = ROOT / relative_path
    if not path.exists():
        pytest.skip(f"private ontology artifact is not present: {relative_path}")
    return path


def minimal_source(*, source_id: str = "kr-cpg:test:one") -> dict:
    return {
        "source_id": source_id,
        "title": "테스트 진료지침",
        "issuing_body": "공식 테스트 학회",
        "publication_year": 2026,
        "jurisdiction": "KR",
        "document_type": "clinical_practice_guideline",
        "catalog_provider": "official_society",
        "catalog_record_id": "test-one",
        "official_landing_url": "https://www.kdca.go.kr/test",
        "latest_status": "verified_latest_on_official_source",
        "latest_checked_at": "2026-07-17",
        "priority": "P0",
        "specialties": ["infectious_disease"],
        "clinical_axes": ["diagnosis", "treatment"],
        "topic_concept_ids": ["pneumonia"],
        "development": {
            "start_date": None,
            "completion_date": None,
            "method": None,
            "multidisciplinary": None,
            "society_certification": None,
            "keywords": None,
            "abstract_sha256": None,
        },
        "license": {
            "status": "kogl_type_4",
            "redistribution_allowed": False,
            "commercial_reuse_allowed": False,
            "notes": "private integrity mirror",
        },
        "attachments": [],
        "needs_review": True,
        "medical_approval": False,
        "student_visible": False,
    }


def minimal_registry(source: dict) -> dict:
    return {
        "schema_version": "kr_guideline_source_registry.v1",
        "generated_at": "2026-07-17T00:00:00+00:00",
        "latest_checked_at": "2026-07-17",
        "registry_role": "source_inventory_not_medical_approval",
        "safety_boundary": {
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "generation_eligible": False,
            "automatic_claim_promotion": False,
        },
        "sources": [source],
    }


def test_source_schema_is_fail_closed() -> None:
    schema = json.loads((ROOT / "schemas" / "kr_guideline_source_registry.schema.json").read_text())
    payload = minimal_registry(minimal_source())
    assert list(Draft7Validator(schema).iter_errors(payload)) == []

    payload["sources"][0]["medical_approval"] = True
    errors = list(Draft7Validator(schema).iter_errors(payload))
    assert errors
    assert any("False was expected" in error.message for error in errors)


def test_download_rejects_non_https_without_network(tmp_path: Path) -> None:
    source = minimal_source()
    attachment = {
        "attachment_id": "kr-cpg:test:one:a1",
        "filename": "test.pdf",
        "source_url": "http://www.kdca.go.kr/test.pdf",
        "file_type": "pdf",
        "public_download": True,
        "download_status": "not_requested",
        "relative_path": None,
        "bytes": None,
        "sha256": None,
        "content_type": None,
        "pdf_pages": None,
        "pdf_encrypted": None,
        "pdf_text_chars": None,
        "error": None,
    }
    result = ingest.download_attachment(
        object(), source, attachment, output_dir=tmp_path, overwrite=False
    )
    assert result["download_status"] == "restricted"
    assert result["error"] == "non_https_source_url"
    assert list(tmp_path.rglob("*")) == []


def test_file_signature_checks_are_type_specific(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.7\nnot-a-complete-pdf")
    assert ingest.magic_valid(pdf, "pdf")[0] is True
    assert ingest.magic_valid(pdf, "docx")[0] is False

    docx = tmp_path / "sample.docx"
    docx.write_bytes(b"PK\x03\x04placeholder")
    assert ingest.magic_valid(docx, "docx")[0] is True


def test_title_rules_only_create_review_candidates() -> None:
    candidates = overlays.candidate_matches(
        "2025 만성콩팥병 진료지침", {"pneumonia", "chronic_hypertension"}
    )
    assert candidates == [
        {
            "concept_id": "chronic_kidney_disease",
            "matched_term": "만성콩팥",
            "resolved_in_registry": False,
            "mapping_status": "review_candidate_not_attached",
        }
    ]


def test_overlay_and_specialty_routes_remain_review_only(tmp_path: Path) -> None:
    source_path = tmp_path / "sources.json"
    concept_path = tmp_path / "concepts.json"
    source_path.write_text(json.dumps(minimal_registry(minimal_source())), encoding="utf-8")
    concept_path.write_text(json.dumps({"concepts": {"pneumonia": {}}}), encoding="utf-8")

    ontology = overlays.build_ontology_overlay(source_path, concept_path)
    agents = overlays.build_agent_registry(source_path)

    assert ontology["concept_index"] == {"pneumonia": ["kr-cpg:test:one"]}
    assert ontology["summary"]["canonical_registry_mutations"] == 0
    assert agents["summary"]["agents"] == 1
    assert agents["agents"][0]["agent_id"] == "kr-specialist:infectious_disease"
    assert agents["agents"][0]["review_retrieval_enabled"] is True
    assert agents["agents"][0]["student_retrieval_enabled"] is False
    assert agents["agents"][0]["generation_retrieval_enabled"] is False


def test_current_private_guideline_snapshot_is_integral_and_fail_closed() -> None:
    artifact_schemas = {
        "data_private/kr_guidelines/verified_latest_registry.json": (
            "schemas/kr_guideline_source_registry.schema.json"
        ),
        "data_private/kr_guidelines/ontology_overlay.json": (
            "schemas/kr_guideline_ontology_overlay.schema.json"
        ),
        "data_private/kr_guidelines/specialty_agent_registry.json": (
            "schemas/kr_guideline_agent_registry.schema.json"
        ),
        "data_private/kr_guidelines/claim_extraction_worklist.json": (
            "schemas/kr_guideline_claim_worklist.schema.json"
        ),
    }
    artifacts = {}
    for artifact_name, schema_name in artifact_schemas.items():
        artifact = json.loads(private_artifact(artifact_name).read_text())
        schema = json.loads((ROOT / schema_name).read_text())
        assert list(Draft7Validator(schema).iter_errors(artifact)) == []
        artifacts[artifact_name] = artifact

    registry = artifacts[
        "data_private/kr_guidelines/verified_latest_registry.json"
    ]
    attachments = [
        attachment
        for source in registry["sources"]
        for attachment in source.get("attachments", [])
    ]
    downloaded = [
        attachment
        for attachment in attachments
        if attachment["download_status"] == "downloaded"
    ]

    assert len(registry["sources"]) == 65
    assert len(attachments) == 68
    assert len(downloaded) == 67
    assert sum(item["download_status"] == "metadata_only" for item in attachments) == 1
    assert all(source["needs_review"] is True for source in registry["sources"])
    assert all(source["medical_approval"] is False for source in registry["sources"])
    assert all(source["student_visible"] is False for source in registry["sources"])

    downloaded_bytes = 0
    for attachment in downloaded:
        source_file = private_artifact(attachment["relative_path"])
        downloaded_bytes += source_file.stat().st_size
        assert source_file.stat().st_size == attachment["bytes"]
        assert hashlib.sha256(source_file.read_bytes()).hexdigest() == attachment["sha256"]
    assert downloaded_bytes == 485_617_470

    ontology = artifacts["data_private/kr_guidelines/ontology_overlay.json"]
    agents = artifacts["data_private/kr_guidelines/specialty_agent_registry.json"]
    worklist = artifacts[
        "data_private/kr_guidelines/claim_extraction_worklist.json"
    ]
    assert ontology["summary"]["title_rule_review_candidates"] == 69
    assert ontology["summary"]["unresolved_concept_candidate_ids"] == 0
    assert agents["summary"]["agents"] == 24
    assert agents["summary"]["student_enabled_agents"] == 0
    assert agents["summary"]["generation_enabled_agents"] == 0
    assert worklist["summary"]["tasks"] == 505
    assert worklist["summary"]["readiness"] == {
        "currentness_review_required": 93,
        "ready_for_candidate_extraction": 401,
        "source_file_unavailable": 11,
    }
    assert worklist["summary"]["automatic_medical_approvals"] == 0
    assert all(task["needs_review"] is True for task in worklist["tasks"])
    assert all(task["medical_approval"] is False for task in worklist["tasks"])
    assert all(task["student_visible"] is False for task in worklist["tasks"])
    assert all(task["generation_eligible"] is False for task in worklist["tasks"])


def test_current_guideline_expansion_is_review_only_and_endpoints_are_normalized() -> None:
    expansion = json.loads(
        private_artifact(
            "data_private/curriculum/kr_guideline_expansion_final.json"
        ).read_text()
    )
    concept_registry = json.loads(
        private_artifact("data_private/concept_registry.json").read_text()
    )["concepts"]
    source_registry = json.loads(
        private_artifact(
            "data_private/kr_guidelines/verified_latest_registry.json"
        ).read_text()
    )
    harrison_overlay = json.loads(
        private_artifact(
            "data_private/harrison/22e/concept_harrison_overlay.json"
        ).read_text()
    )["concepts"]

    additions = expansion["additions"]
    concept_ids = {addition["disease_concept_id"] for addition in additions}
    source_ids = {source["source_id"] for source in source_registry["sources"]}
    assert len(concept_ids) == 14
    assert concept_ids <= concept_registry.keys()
    assert all(
        source_ref in source_ids
        for addition in additions
        for source_ref in addition.get("source_refs", [])
    )
    assert all(concept_registry[concept_id]["needs_review"] is True for concept_id in concept_ids)
    assert all(
        concept_registry[concept_id].get("medical_approval") is not True
        for concept_id in concept_ids
    )
    assert all(
        concept_registry[concept_id].get("gen_ready") is not True
        for concept_id in concept_ids
    )
    assert sum(
        harrison_overlay[concept_id]["mapping_status"] == "exact_22e_pointer"
        for concept_id in concept_ids
    ) == 12
    assert sum(
        harrison_overlay[concept_id]["mapping_status"] == "no_chapter_mapping"
        for concept_id in concept_ids
    ) == 2
    assert all(
        harrison_overlay[concept_id]["medical_approval"] is False
        for concept_id in concept_ids
    )

    linked_new_endpoints = [
        edge
        for concept in concept_registry.values()
        for edges in (concept.get("edges") or {}).values()
        if isinstance(edges, list)
        for edge in edges
        if isinstance(edge, dict) and edge.get("id") in concept_ids
    ]
    assert linked_new_endpoints
    assert all(edge.get("in_registry") is True for edge in linked_new_endpoints)
