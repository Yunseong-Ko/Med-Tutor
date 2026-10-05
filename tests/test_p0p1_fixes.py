from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import api_server
from scripts import generation_grounding
from src.services import medical_copilot
from src.services import qbank_enrichment


def _clear_qbank_caches() -> None:
    qbank_enrichment._load_snapshot.cache_clear()
    qbank_enrichment._sha256_snapshot.cache_clear()


def test_signed_session_binds_role_and_plain_cookie_cannot_escalate(monkeypatch):
    monkeypatch.setattr(api_server, "_SESSION_SECRET", "acceptance-test-secret")
    expires_at = int(time.time()) + 300
    token = api_server._sign_session_token("student@example.com", "student", expires_at)

    assert api_server._verify_session_token(token) == {
        "email": "student@example.com",
        "role": "student",
        "expires_at": expires_at,
    }
    assert api_server._verify_session_token(token.replace(":student:", ":faculty:")) is None

    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", "student@example.com")
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", "correct-password")
    monkeypatch.setattr(api_server, "_COOKIE_SECURE", False)
    client = TestClient(api_server.app)
    login = client.post(
        "/api/auth/login",
        json={
            "email": "student@example.com",
            "password": "correct-password",
            "role": "student",
        },
    )
    assert login.status_code == 200
    client.cookies.delete("paccine_role")
    client.cookies.set("paccine_role", "faculty")

    denied = client.get("/api/faculty/qbank-enrichment/review-queue")
    assert denied.status_code == 403


def test_all_declared_faculty_write_routes_have_dependency_gate():
    expected_paths = {
        "/api/faculty/item-intents/recommendations",
        "/api/faculty/guideline-claims/drafts",
        "/api/faculty/guideline-claims/{claim_id}/decision",
        "/api/faculty/qbank-enrichment/{question_id}/review",
        "/api/evidence/review",
        "/api/course-exams/import",
        "/api/course-exams/{exam_id}/review-set",
        "/api/media",
        "/api/media/{asset_id}",
        "/api/notebooklm/import",
        "/api/question-sets/{set_id}/export/anki",
        "/api/question-sets/{set_id}/export/cbt-hwp",
        "/api/question-sets/{set_id}/export/cbt-docx",
        "/api/question-sets/{set_id}/questions/{question_id}",
        "/api/question-sets/{set_id}/questions/{question_id}/approve",
        "/api/question-sets/{set_id}/questions/{question_id}/reject",
        "/api/generate-from-topic",
        "/api/faculty/item-intents/generation-jobs",
    }
    routes = {
        route.path: route
        for route in api_server.app.routes
        if hasattr(route, "dependant")
    }

    assert expected_paths <= routes.keys()
    for path in expected_paths:
        dependency_calls = {
            dependency.call
            for dependency in routes[path].dependant.dependencies
        }
        assert api_server._require_faculty_reviewer in dependency_calls, path


def test_concurrent_faculty_reviews_do_not_lose_updates(tmp_path, monkeypatch):
    qbank_path = tmp_path / "qbank.json"
    draft_path = tmp_path / "qbank_enrichment.draft.json"
    releases_path = tmp_path / "qbank_enrichment.releases.json"
    qbank_path.write_text('{"questions":[]}', encoding="utf-8")
    qbank_sha = hashlib.sha256(qbank_path.read_bytes()).hexdigest()
    question_ids = [f"Q{index:03d}" for index in range(20)]
    draft_path.write_text(
        json.dumps(
            {
                "built_against_sha256": qbank_sha,
                "drafts": {
                    question_id: {
                        "release_eligible": True,
                        "explanation": f"{question_id} 해설",
                    }
                    for question_id in question_ids
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    releases_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(qbank_enrichment, "QBANK_PATH", qbank_path)
    monkeypatch.setattr(qbank_enrichment, "DRAFT_PATH", draft_path)
    monkeypatch.setattr(qbank_enrichment, "RELEASES_PATH", releases_path)
    _clear_qbank_caches()

    def approve(question_id: str) -> None:
        qbank_enrichment.record_faculty_review(
            question_id,
            decision="approve",
            reviewer_id="faculty:acceptance@example.com",
            reviewed_at="2026-07-24T12:00:00+09:00",
            medical_approval=True,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(approve, question_ids))

    payload = json.loads(releases_path.read_text(encoding="utf-8"))
    assert set(payload["releases"]) == set(question_ids)
    assert all(row["medical_approval"] is True for row in payload["releases"].values())
    _clear_qbank_caches()


def test_generate_error_masks_private_inputs_and_exception_details(
    tmp_path,
    monkeypatch,
    capsys,
):
    private_topic = "환자이름-홍길동-비밀주제"
    private_filename = "홍길동_민감한_강의자료.pdf"
    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", "")
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", "")
    monkeypatch.setattr(
        api_server,
        "save_upload_bytes",
        lambda *_args, **_kwargs: tmp_path / "opaque-upload.txt",
    )

    def fail_generation(*_args, **_kwargs):
        raise RuntimeError("/Users/private/patient/홍길동/raw.pdf")

    monkeypatch.setattr(api_server, "generate_studio_questions", fail_generation)
    client = TestClient(api_server.app)
    client.cookies.set("paccine_role", "faculty")
    response = client.post("/api/generate", data={"topic": private_topic})
    captured = capsys.readouterr().out

    assert response.status_code == 500
    assert response.json()["detail"] == "문항 생성 중 내부 오류가 발생했습니다."
    assert private_topic not in captured
    assert "홍길동" not in captured
    assert "/Users/private" not in captured
    assert "RuntimeError" in captured
    assert private_filename not in api_server._private_generation_input_label(
        private_filename,
        "",
    )


def test_default_entailment_shadow_reuses_model_without_becoming_blocking(monkeypatch):
    captured = {}

    def fake_compose(prompt, context):
        captured["prompt"] = prompt
        captured["context"] = context
        return {"claims": [], "blocks_answer": False}

    monkeypatch.setattr(medical_copilot, "_compose_with_model", fake_compose)
    result = medical_copilot._default_entailment_judge(
        "검증 프롬프트",
        {"provider": {"name": "test"}},
    )

    assert result["blocks_answer"] is False
    assert captured["context"]["response_kind"] == "entailment_shadow"
    assert captured["context"]["answer_scope"]["max_output_tokens"] == 3000


def test_sync_medical_copilot_api_injects_entailment_shadow(monkeypatch):
    captured = {}

    def fake_builder(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", "")
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", "")
    monkeypatch.setattr(api_server, "build_medical_copilot_response", fake_builder)
    response = TestClient(api_server.app).post(
        "/api/student/medical-copilot",
        json={"query": "CML의 기전은?"},
    )

    assert response.status_code == 200
    assert captured["entailment_judge"] is api_server._default_entailment_judge


def test_unspecified_jurisdiction_gets_deterministic_international_notice():
    query = "고혈압의 1차 약제와 목표 혈압은?"
    policy = medical_copilot.classify_guideline_question(query)
    response = medical_copilot.build_medical_copilot_response(
        query,
        generate_answer=False,
    )

    assert policy["requires_released_claim"] is False
    assert policy["answer_jurisdiction_label"] == "international_reference"
    assert response["jurisdiction_notice"]["jurisdiction"] == "international_reference"
    assert response["guideline_boundary"]["current_guideline_claim_pending"] is False


def test_explicit_korean_detail_still_requires_released_claim():
    policy = medical_copilot.classify_guideline_question(
        "대한민국 최신 고혈압 가이드라인의 1차 약제와 목표 혈압은?"
    )

    assert policy["answer_jurisdiction_label"] == "korean"
    assert policy["requires_released_claim"] is True


def test_local_connected_media_requires_matching_sha256(tmp_path, monkeypatch):
    exam_dir = tmp_path / "exam-a"
    exam_dir.mkdir()
    media_path = exam_dir / "image.png"
    media_path.write_bytes(b"verified-image-bytes")
    checksum = hashlib.sha256(media_path.read_bytes()).hexdigest()
    monkeypatch.setattr(api_server, "COURSE_EXAM_MEDIA_DIR", tmp_path)
    question = {
        "id": "Q1",
        "stem": "다음 사진을 보고 답하시오.",
        "stimulus": "<사진>",
        "choices": [],
    }
    valid_release = {
        "connected_media": [
            {
                "url": "/api/course-exams/media/exam-a/image.png",
                "checksum": checksum,
            }
        ]
    }
    forged_release = {
        "connected_media": [
            {
                "url": "/api/course-exams/media/exam-a/image.png",
                "checksum": "0" * 64,
            }
        ]
    }

    assert api_server.qbank_question_practice_readiness(
        question,
        valid_release,
    )["practice_ready"] is True
    assert api_server.public_qbank_question(question, valid_release)["imgs"]
    assert api_server.qbank_question_practice_readiness(
        question,
        forged_release,
    )["practice_ready"] is False
    assert api_server.public_qbank_question(question, forged_release)["imgs"] == []


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"url": "https://example.org/image.png", "checksum": "manifest-sha"}, True),
        ({"url": "https://example.org/image.png"}, False),
    ],
)
def test_remote_connected_media_requires_manifest_checksum(item, expected):
    assert api_server.connected_qbank_media_is_verified(item) is expected


def test_unknown_axis_ids_are_excluded_when_registry_exists(tmp_path, monkeypatch):
    registry_path = tmp_path / "axis_registry.json"
    registry_path.write_text(
        json.dumps({"nodes": [{"axis_id": "a:diagnosis:valid"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_server, "ONTOLOGY_AXIS_REGISTRY_PATH", registry_path)

    def event(axis_id: str, is_correct: bool) -> dict:
        return {
            "ontology_snapshot_status": "resolved_from_stored_question",
            "ontology_snapshot": {
                "analytics_eligible": True,
                "disease_concept_id": "cml",
                "target_axis_type": "diagnosis",
                "target_axis_ids": [axis_id],
            },
            "is_correct": is_correct,
            "time_ms": 1000,
        }

    rows = api_server.aggregate_student_ontology_weakness(
        [
            event("a:diagnosis:valid", True),
            event("a:diagnosis:forged", False),
        ]
    )

    assert len(rows) == 1
    assert rows[0]["axis_id"] == "a:diagnosis:valid"
    assert rows[0]["attempt_count"] == 1


def test_numeric_dose_tagging_ignores_labs_and_forces_review_without_anchor():
    assert generation_grounding._numeric_safety_review_reasons(
        {"stem": "혈색소 8.5 g/dL, 혈소판 20,000/μL"},
        has_harrison_anchor=False,
    ) == []

    reasons = generation_grounding._numeric_safety_review_reasons(
        {"explanation": "아스피린 300 mg을 투여한다."},
        has_harrison_anchor=False,
    )
    assert reasons == [
        "numeric_dose_requires_human_review",
        "numeric_dose_without_harrison_anchor",
    ]

    grounded = generation_grounding.apply_grounding_trace(
        {
            "stem": "급성 치료로 약제 10 mg을 투여한다.",
            "review_reasons": [],
        },
        {
            "review_policy": "faculty_draft",
            "pack": None,
            "blocked": False,
            "block_reasons": [],
        },
    )
    assert grounded["needs_review"] is True
    assert "numeric_dose_requires_human_review" in grounded["review_reasons"]
    assert "numeric_dose_without_harrison_anchor" in grounded["review_reasons"]
