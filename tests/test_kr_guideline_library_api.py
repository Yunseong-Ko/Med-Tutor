from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

import src.services.kr_guideline_library as guideline_library
from api_server import app
from src.services.kr_guideline_library import (
    build_guideline_evidence_packet,
    build_guideline_study_assistant,
    get_guideline_library_status,
    search_guideline_library,
)


def _source(
    *,
    source_id: str,
    title: str,
    latest_status: str,
    relative_path: str,
    publication_year: int = 2026,
) -> dict:
    return {
        "source_id": source_id,
        "title": title,
        "issuing_body": "대한테스트학회",
        "publication_year": publication_year,
        "jurisdiction": "KR",
        "document_type": "clinical_practice_guideline",
        "catalog_provider": "official_society",
        "catalog_record_id": source_id.rsplit(":", 1)[-1],
        "official_landing_url": f"https://example.org/{source_id.rsplit(':', 1)[-1]}",
        "latest_status": latest_status,
        "latest_evidence": "internal reviewer prose must not be returned",
        "latest_checked_at": "2026-07-18",
        "priority": "P0",
        "version": {
            "display_version": str(publication_year),
            "printed_publication_year": publication_year,
            "operational_release": f"{publication_year}-01-02",
            "last_corrected_at": None,
            "version_conflict": False,
            "currency_review_due": latest_status != "verified_latest_on_official_source",
            "notes": "internal version review note must not be returned",
        },
        "specialties": ["pulmonology"],
        "clinical_axes": ["diagnosis", "treatment", "follow_up"],
        "topic_concept_ids": [],
        "development": {"keywords": "asthma airway inhaled treatment"},
        "attachments": [
            {
                "attachment_id": f"{source_id}:main",
                "filename": "asthma_guideline.pdf",
                "file_type": "pdf",
                "role": "main",
                "download_status": "downloaded",
                "relative_path": relative_path,
                "bytes": None,
                "sha256": "a" * 64,
                "pdf_pages": 2,
                "pdf_text_chars": 200,
            }
        ],
        "needs_review": True,
        "medical_approval": False,
        "student_visible": False,
    }


@pytest.fixture()
def guideline_root(tmp_path: Path) -> Path:
    pdf_relative = Path("data_private/kr_guidelines/source_files/latest/asthma/main.pdf")
    pdf_path = tmp_path / pdf_relative
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    first = document.new_page()
    first.insert_text((72, 72), "Asthma diagnosis requires variable expiratory airflow limitation.")
    second = document.new_page()
    second.insert_text((72, 72), "Asthma treatment and follow-up require assessment of control and risk.")
    document.save(pdf_path)
    document.close()

    sources = [
        _source(
            source_id="kr-cpg:test:asthma-current",
            title="2026 Asthma Clinical Practice Guideline",
            latest_status="verified_latest_on_official_source",
            relative_path=pdf_relative.as_posix(),
        ),
        _source(
            source_id="kr-cpg:test:asthma-uncertain",
            title="2021 Asthma Legacy Guideline",
            latest_status="latest_uncertain",
            relative_path=pdf_relative.as_posix(),
            publication_year=2021,
        ),
    ]
    registry = {
        "schema_version": "kr_guideline_source_registry.v1",
        "generated_at": "2026-07-18T00:00:00+00:00",
        "latest_checked_at": "2026-07-18",
        "sources": sources,
    }
    overlay = {
        "concept_index": {},
        "candidate_concept_index": {
            "asthma": [
                "kr-cpg:test:asthma-current",
                "kr-cpg:test:asthma-uncertain",
            ]
        },
    }
    concepts = {
        "concepts": {
            "asthma": {
                "disease_concept_id": "asthma",
                "aliases": ["천식"],
                "evidence": {"harrison": {"title": "Asthma"}},
                "needs_review": True,
            }
        }
    }
    for relative, payload in (
        (guideline_library.REGISTRY_RELATIVE_PATH, registry),
        (guideline_library.OVERLAY_RELATIVE_PATH, overlay),
        (guideline_library.CONCEPT_REGISTRY_RELATIVE_PATH, concepts),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_library_status_and_search_preserve_fail_closed_metadata(guideline_root: Path) -> None:
    status = get_guideline_library_status(root=guideline_root)
    assert status["counts"]["sources"] == 2
    assert status["counts"]["verified_current_sources"] == 1
    assert status["counts"]["approved_claims_connected"] == 0
    assert status["safety"]["student_claim_release_available"] is False

    result = search_guideline_library(
        "천식",
        concept_id="asthma",
        current_only=True,
        root=guideline_root,
    )
    assert result["total"] == 1
    source = result["results"][0]
    assert source["source_id"] == "kr-cpg:test:asthma-current"
    assert source["currentness"] == {
        "status": "verified_latest_on_official_source",
        "verified_current": True,
        "checked_at": "2026-07-18",
    }
    assert source["version"]["display_version"] == "2026"
    assert source["attachments"][0]["filename"] == "asthma_guideline.pdf"
    assert source["release"]["student_claim_release_available"] is False
    serialized = json.dumps(source, ensure_ascii=False)
    assert "relative_path" not in serialized
    assert "file_locator" not in serialized
    assert str(guideline_root) not in serialized
    assert "internal reviewer prose" not in serialized
    assert "internal version review note" not in serialized


def test_internal_evidence_packet_labels_excerpts_as_unapproved(guideline_root: Path) -> None:
    packet = build_guideline_evidence_packet(
        "asthma treatment",
        concept_id="asthma",
        include_passages=True,
        root=guideline_root,
    )
    assert packet["status"] == "evidence_packet_ready"
    assert packet["passages"]
    passage = packet["passages"][0]
    assert passage["pdf_page"] == 2
    assert passage["page_locator_status"] == "pdf_page_only_printed_page_not_resolved"
    assert passage["evidence_status"] == "unreviewed_source_excerpt_not_medical_claim"
    assert passage["student_claim_release"] is False
    assert packet["claim_boundary"]["approved_claims_included"] == 0
    serialized = json.dumps(packet, ensure_ascii=False)
    assert str(guideline_root) not in serialized
    assert "relative_path" not in serialized
    assert "file_locator" not in serialized


def test_assistant_returns_deterministic_workspace_without_clinical_answer(
    guideline_root: Path,
) -> None:
    response = build_guideline_study_assistant(
        "천식 치료와 추적 관찰을 어떻게 공부할까?",
        mode="case_presentation",
        concept_id="asthma",
        include_passages=False,
        root=guideline_root,
    )
    assert response["answer_status"] == "retrieval_only_approved_claims_unavailable"
    assert response["grounding_state"] == "guideline_metadata_only"
    assert "treatment" in response["detected_intents"]
    assert "follow_up" in response["detected_intents"]
    assert response["detected_concepts"][0]["concept_id"] == "asthma"
    assert response["workspace_template"]["template_type"] == "supervised_case_presentation"
    assert response["safety"]["diagnosis_generated"] is False
    assert response["safety"]["treatment_recommendation_generated"] is False
    assert "answer" not in response


def test_case_privacy_preflight_blocks_before_retrieval(guideline_root: Path) -> None:
    response = build_guideline_study_assistant(
        "천식 케이스 발표",
        mode="case_presentation",
        case_text="환자명: 홍길동, 전화번호 010-1234-5678",
        root=guideline_root,
    )
    assert response["status"] == "privacy_blocked"
    assert response["answer_status"] == "blocked_direct_identifiers"
    assert response["grounding_state"] == "retrieval_not_started"
    assert response["privacy_status"]["accepted"] is False
    assert response["privacy_status"]["persisted"] is False
    assert response["evidence_packet"] is None
    assert "홍길동" not in json.dumps(response, ensure_ascii=False)
    assert "010-1234-5678" not in json.dumps(response, ensure_ascii=False)


def test_deidentified_case_text_can_route_without_being_echoed(guideline_root: Path) -> None:
    response = build_guideline_study_assistant(
        "케이스 발표 준비",
        mode="case_presentation",
        case_text="반복되는 천명 때문에 천식을 고려한 성인 사례",
        include_passages=False,
        root=guideline_root,
    )
    assert response["detected_concepts"][0]["concept_id"] == "asthma"
    assert response["evidence_packet"]["sources"][0]["source_id"] == "kr-cpg:test:asthma-current"
    serialized = json.dumps(response, ensure_ascii=False)
    assert "반복되는 천명 때문에" not in serialized


def test_student_api_contract_is_metadata_only(monkeypatch: pytest.MonkeyPatch, guideline_root: Path) -> None:
    monkeypatch.setattr(guideline_library, "DEFAULT_ROOT", guideline_root)
    client = TestClient(app)

    library_response = client.get(
        "/api/student/guidelines",
        params={"q": "천식", "concept_id": "asthma", "currentness": "verified_current"},
    )
    assert library_response.status_code == 200
    library_payload = library_response.json()
    assert set(("summary", "filters", "results")) <= library_payload.keys()
    assert library_payload["summary"]["approved_claims_connected"] == 0
    assert len(library_payload["results"]) == 1
    assert library_payload["offset"] == 0
    assert library_payload["limit"] == 20
    assert library_payload["total"] == 1
    assert library_payload["pagination"]["has_more"] is False

    assistant_response = client.post(
        "/api/student/clinical-assistant",
        json={
            "mode": "case_presentation",
            "query": "천식 치료와 추적 관찰",
            "concept_id": "asthma",
            "case_text": "성인 환자, 반복되는 호흡곤란과 천명",
            "include_passages": True,
        },
    )
    assert assistant_response.status_code == 200
    payload = assistant_response.json()
    assert payload["answer_status"] == "retrieval_only_approved_claims_unavailable"
    assert payload["grounding_state"] == "guideline_metadata_only"
    assert payload["blocked"] is True
    assert payload["guidelines"]
    assert payload["evidence"] == []
    assert payload["privacy_status"]["status"] == "clear"
    assert payload["detected_concepts"][0]["concept_id"] == "asthma"
    assert payload["workspace_template"]["template_type"] == "supervised_case_presentation"
    assert payload["case_presentation"]["template_type"] == "supervised_case_presentation"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "relative_path" not in serialized
    assert "file_locator" not in serialized
    assert "asthma_guideline.pdf" not in serialized
    assert "a" * 64 not in serialized
    assert "sha256" not in serialized
    assert "filename" not in serialized
    assert str(guideline_root) not in serialized


def test_student_api_rejects_identifiers_without_echo(
    monkeypatch: pytest.MonkeyPatch, guideline_root: Path
) -> None:
    monkeypatch.setattr(guideline_library, "DEFAULT_ROOT", guideline_root)
    response = TestClient(app).post(
        "/api/student/clinical-assistant",
        json={
            "mode": "case_presentation",
            "query": "천식 케이스 발표",
            "case_text": "환자번호: AB-12345, 이메일 student@example.com",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "privacy_blocked"
    assert payload["blocked"] is True
    assert payload["privacy_status"]["accepted"] is False
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "AB-12345" not in serialized
    assert "student@example.com" not in serialized
