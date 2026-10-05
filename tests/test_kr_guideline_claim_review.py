from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app
from src.services import kr_guideline_claim_review as review


@pytest.fixture()
def review_root(tmp_path: Path) -> Path:
    guideline_root = tmp_path / "data_private" / "kr_guidelines"
    guideline_root.mkdir(parents=True)
    source_file = guideline_root / "source.pdf"
    source_file.write_bytes(b"review fixture")
    source_sha = review.hashlib.sha256(source_file.read_bytes()).hexdigest()
    (guideline_root / "claim_extraction_worklist.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": "task:asthma",
                        "source_id": "source:asthma",
                        "source_title": "천식 진료지침",
                        "priority": "P0",
                        "latest_status": "verified_latest_on_official_source",
                        "clinical_axis": "treatment",
                        "readiness": "ready_for_candidate_extraction",
                        "concept_candidates": ["asthma"],
                        "specialty_agent_ids": ["pulmonology"],
                        "source_files": [
                            {
                                "attachment_id": "source:asthma:main",
                                "role": "main",
                                "relative_path": str(source_file.relative_to(tmp_path)),
                                "sha256": source_sha,
                                "pdf_pages": 20,
                            }
                        ],
                    },
                    {
                        "task_id": "task:uncertain",
                        "source_id": "source:uncertain",
                        "source_title": "최신성 미확인 지침",
                        "priority": "P1",
                        "latest_status": "latest_uncertain",
                        "clinical_axis": "diagnosis",
                        "readiness": "currentness_review_required",
                        "concept_candidates": ["asthma"],
                        "specialty_agent_ids": ["pulmonology"],
                        "source_files": [
                            {
                                "attachment_id": "source:uncertain:main",
                                "role": "main",
                                "relative_path": str(source_file.relative_to(tmp_path)),
                                "sha256": source_sha,
                                "pdf_pages": 20,
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (guideline_root / "verified_latest_registry.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "source:asthma",
                        "latest_status": "verified_latest_on_official_source",
                        "official_landing_url": "https://example.org/asthma",
                    },
                    {
                        "source_id": "source:uncertain",
                        "latest_status": "latest_uncertain",
                        "official_landing_url": "https://example.org/uncertain",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (guideline_root / "claim_releases.json").write_text(
        json.dumps(
            {
                "schema_version": "kr_guideline_claim_releases.v1",
                "generated_at": "2026-07-18T00:00:00+00:00",
                "policy": {
                    "default_deny": True,
                    "invalidate_on_claim_hash_change": True,
                    "invalidate_on_source_snapshot_change": True,
                },
                "releases": [],
            }
        ),
        encoding="utf-8",
    )
    schema_target = tmp_path / "schemas" / "kr_guideline_claim_release.schema.json"
    schema_target.parent.mkdir(parents=True)
    schema_target.write_text(
        (review.DEFAULT_ROOT / review.RELEASE_SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return tmp_path


def _draft_payload(task_id: str = "task:asthma") -> dict:
    return {
        "task_id": task_id,
        "page": 7,
        "subject_concept_id": "asthma",
        "relation": "recommends",
        "object_text": "천식 치료는 환자의 증상과 위험도 평가에 따라 단계적으로 조정한다.",
        "population": "천식이 확인된 성인 환자",
        "locator_note": "권고문 3, 표 2 아래 첫 번째 문단",
        "effective_version": "2026",
        "created_by": "reviewer-a",
    }


def test_draft_is_fail_closed_until_human_release(review_root: Path) -> None:
    tasks = review.list_claim_review_tasks(root=review_root)
    assert tasks["summary"]["tasks"] == 2
    assert tasks["summary"]["released_claims"] == 0

    draft = review.create_claim_draft(_draft_payload(), root=review_root)
    assert draft["status"] == "draft"
    assert draft["medical_approval"] is False
    assert draft["student_visible"] is False
    assert review.list_valid_released_claims(surface="study_qa", root=review_root) == []

    with pytest.raises(ValueError, match="attestation"):
        review.decide_claim(
            draft["claim_id"],
            {"action": "release", "reviewer": "professor-a", "attestation": False},
            root=review_root,
        )


def test_release_hash_source_and_revoke_guards(review_root: Path) -> None:
    draft = review.create_claim_draft(_draft_payload(), root=review_root)
    due = (datetime.now(timezone.utc) + timedelta(days=180)).isoformat()
    decision = review.decide_claim(
        draft["claim_id"],
        {
            "action": "release",
            "reviewer": "professor-a",
            "attestation": True,
            "review_due_at": due,
            "surfaces": ["study_qa", "anki"],
        },
        root=review_root,
    )
    assert decision["release"]["status"] == "released"
    claims = review.list_valid_released_claims(
        surface="study_qa", concept_ids=["asthma"], root=review_root
    )
    assert [claim["claim_id"] for claim in claims] == [draft["claim_id"]]
    assert claims[0]["object_text"].startswith("천식 치료")

    records_path = review_root / review.REVIEW_RECORDS_RELATIVE_PATH
    records = json.loads(records_path.read_text(encoding="utf-8"))
    records["claims"][0]["object_text"] += " 변경"
    records_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    assert review.list_valid_released_claims(surface="study_qa", root=review_root) == []

    records["claims"][0]["object_text"] = draft["object_text"]
    records_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    source_path = review_root / "data_private" / "kr_guidelines" / "source.pdf"
    source_path.write_bytes(b"changed source")
    assert review.list_valid_released_claims(surface="anki", root=review_root) == []
    source_path.write_bytes(b"review fixture")

    review.decide_claim(
        draft["claim_id"],
        {
            "action": "revoke",
            "reviewer": "professor-a",
            "attestation": True,
            "reason": "원문 개정 확인 필요",
        },
        root=review_root,
    )
    assert review.list_valid_released_claims(surface="anki", root=review_root) == []


def test_currentness_review_task_cannot_be_released(review_root: Path) -> None:
    draft = review.create_claim_draft(_draft_payload("task:uncertain"), root=review_root)
    with pytest.raises(ValueError, match="최신성과 원문 준비"):
        review.decide_claim(
            draft["claim_id"],
            {
                "action": "release",
                "reviewer": "professor-a",
                "attestation": True,
                "review_due_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                "surfaces": ["study_qa"],
            },
            root=review_root,
        )


def test_faculty_api_and_anki_fsrs_are_release_gated(
    monkeypatch: pytest.MonkeyPatch, review_root: Path, tmp_path: Path
) -> None:
    monkeypatch.setattr(review, "DEFAULT_ROOT", review_root)
    monkeypatch.setattr(api_server, "STUDENT_CLAIM_FSRS_LOG_PATH", tmp_path / "claim_fsrs.jsonl")
    client = TestClient(app)
    client.cookies.set("paccine_role", "faculty")

    tasks = client.get("/api/faculty/guideline-claims/tasks?priority=P0")
    assert tasks.status_code == 200
    assert tasks.json()["total"] == 1
    source = client.get(
        "/api/faculty/guideline-claims/tasks/task%3Aasthma/source/source%3Aasthma%3Amain"
    )
    assert source.status_code == 200
    assert source.content == b"review fixture"

    created = client.post("/api/faculty/guideline-claims/drafts", json=_draft_payload())
    assert created.status_code == 200
    claim_id = created.json()["claim"]["claim_id"]
    assert client.get("/api/student/medical-copilot/review").json()["items"] == []

    released = client.post(
        f"/api/faculty/guideline-claims/{claim_id}/decision",
        json={
            "action": "release",
            "reviewer": "professor-a",
            "attestation": True,
            "review_due_at": (datetime.now(timezone.utc) + timedelta(days=180)).isoformat(),
            "surfaces": ["study_qa", "anki"],
        },
    )
    assert released.status_code == 200
    queue = client.get("/api/student/medical-copilot/review")
    assert queue.status_code == 200
    assert queue.json()["items"][0]["claim_id"] == claim_id

    event = {"rating": 3, "event_id": "fixed-event"}
    first = client.post(f"/api/student/medical-copilot/claims/{claim_id}/fsrs", json=event)
    second = client.post(f"/api/student/medical-copilot/claims/{claim_id}/fsrs", json=event)
    assert first.status_code == 200
    assert first.json()["status"] == "saved"
    assert second.json()["status"] == "already_saved"
