from fastapi.testclient import TestClient

from api_server import app


def test_medlegal_cases_endpoint_lists_seed_cases():
    client = TestClient(app)

    response = client.get("/api/medlegal/cases")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["cases"]) >= 3
    assert "ed_discharge" in {case["required_note_type"] for case in payload["cases"]}
    assert all(isinstance(case["fictional_case"], bool) for case in payload["cases"])


def test_medlegal_case_detail_includes_sources_and_cpx_expansion():
    client = TestClient(app)

    response = client.get("/api/medlegal/cases/case_bad_news_consent_001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["track"] == "cpx_medlegal"
    assert payload["sources"]
    assert "CPX" in payload["expansion_path"]


def test_medlegal_submission_flags_missing_items_and_privacy_scope():
    client = TestClient(app)

    response = client.post(
        "/api/medlegal/cases/case_ed_discharge_headache_001/submit",
        json={"note_text": "환자 증상 호전되어 퇴원함. 단순 두통으로 판단함."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["privacy"]["uses_real_patient_data"] is False
    assert payload["feedback"]["missing_items"]
    assert payload["feedback"]["risky_phrases"]
    assert "Educational feedback only" in payload["feedback"]["disclaimer"]


def test_medlegal_rich_submission_scores_higher_than_sparse_note():
    client = TestClient(app)
    sparse = client.post(
        "/api/medlegal/cases/case_informed_refusal_ct_001/submit",
        json={"note_text": "환자가 검사 거부함. 본인 책임 설명."},
    ).json()
    rich = client.post(
        "/api/medlegal/cases/case_informed_refusal_ct_001/submit",
        json={
            "learner_role": "clerkship_student",
            "note_text": (
                "흉통으로 내원하여 심전도 재평가, 혈액검사, 영상검사 및 관찰을 권유하였다. "
                "검사를 시행하지 않을 경우 심근경색 진단 지연, 악화, 사망 등 중대한 위험이 "
                "있을 수 있음을 설명하였다. 환자는 비용과 시간을 이유로 거부하였고, 설명 내용을 "
                "이해한다고 진술하였다. 의사결정 판단능력은 보존되어 보였으며 보호자에게도 "
                "같이 설명하였다. 대안으로 빠른 외래 추적과 증상 악화 시 즉시 응급실 재내원, "
                "흉통 지속/호흡곤란/실신 발생 시 119 연락을 안내하였다."
            ),
        },
    ).json()

    assert rich["feedback"]["overall_score"] > sparse["feedback"]["overall_score"]
    assert rich["feedback"]["missing_items"] == []
