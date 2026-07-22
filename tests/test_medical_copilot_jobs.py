from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app
from src.services import medical_copilot_jobs as jobs


@pytest.fixture(autouse=True)
def clean_jobs() -> None:
    jobs._JOBS.clear()
    jobs._FUTURES.clear()
    yield
    jobs._JOBS.clear()
    jobs._FUTURES.clear()


def request_payload() -> dict:
    return {
        "query": "심방세동의 핵심 진단 원리를 설명해줘",
        "mode": "concept",
        "history": [],
        "generate_answer": True,
    }


def fake_builder(query: str, **kwargs) -> dict:
    assert query == request_payload()["query"]
    assert kwargs["mode"] == "concept"
    return {
        "status": "ready",
        "answer_status": "grounded_learning_draft",
        "answer": {"answer_summary": "근거 기반 학습 답변", "sections": []},
        "blocked": False,
    }


def test_memory_only_job_hides_request_and_completes() -> None:
    public = jobs.create_medical_copilot_job(
        request_payload(), owner_id="student-a", auto_submit=False
    )
    assert public["status"] == "queued"
    assert public["server_persistence"] == "memory_only"
    assert "request" not in public
    assert request_payload()["query"] not in str(public)

    jobs._run_job(public["job_id"], builder=fake_builder)
    done = jobs.get_medical_copilot_job(public["job_id"], owner_id="student-a")
    assert done["status"] == "done"
    assert done["result"]["answer"]["answer_summary"] == "근거 기반 학습 답변"
    assert jobs._JOBS[public["job_id"]]["request"] is None


def test_job_is_isolated_by_student_identity() -> None:
    public = jobs.create_medical_copilot_job(
        request_payload(), owner_id="student-a", auto_submit=False
    )
    with pytest.raises(FileNotFoundError):
        jobs.get_medical_copilot_job(public["job_id"], owner_id="student-b")


def test_privacy_block_creates_no_recoverable_job() -> None:
    called = False

    def should_not_run(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    payload = request_payload()
    payload["query"] = "환자번호: AB-12345, 전화번호 010-1234-5678"
    public = jobs.create_medical_copilot_job(
        payload,
        owner_id="student-a",
        auto_submit=True,
        builder=should_not_run,
    )
    assert public["status"] == "done"
    assert public["stage"] == "privacy_blocked"
    assert public["job_id"] is None
    assert public["server_persistence"] == "none"
    assert public["result"]["safety"]["retrieval_started"] is False
    assert called is False
    assert jobs._JOBS == {}


def test_cancelled_queued_job_discards_result() -> None:
    public = jobs.create_medical_copilot_job(
        request_payload(), owner_id="student-a", auto_submit=False
    )
    cancelled = jobs.cancel_medical_copilot_job(
        public["job_id"], owner_id="student-a"
    )
    assert cancelled["status"] == "cancel_requested"
    jobs._run_job(public["job_id"], builder=fake_builder)
    final = jobs.get_medical_copilot_job(public["job_id"], owner_id="student-a")
    assert final["status"] == "cancelled"
    assert "result" not in final


def test_failed_job_keeps_memory_only_request_for_retry_window() -> None:
    def failing_builder(*_args, **_kwargs):
        raise TimeoutError("model timed out")

    public = jobs.create_medical_copilot_job(
        request_payload(), owner_id="student-a", auto_submit=False
    )
    jobs._run_job(public["job_id"], builder=failing_builder)
    failed = jobs.get_medical_copilot_job(public["job_id"], owner_id="student-a")
    assert failed["status"] == "failed"
    assert "model timed out" in failed["error"]
    assert "request" not in failed
    assert jobs._JOBS[public["job_id"]]["request"]["query"] == request_payload()["query"]


def test_api_exposes_create_read_cancel_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_create(payload, *, owner_id):
        captured["payload"] = payload
        captured["owner_id"] = owner_id
        return {"job_id": "mcj_20260719T000000Z_1234567890abcdef", "status": "queued"}

    monkeypatch.setattr(api_server, "create_medical_copilot_job", fake_create)
    monkeypatch.setattr(
        api_server,
        "get_medical_copilot_job",
        lambda job_id, *, owner_id: {"job_id": job_id, "status": "running", "owner_seen": bool(owner_id)},
    )
    monkeypatch.setattr(
        api_server,
        "cancel_medical_copilot_job",
        lambda job_id, *, owner_id: {"job_id": job_id, "status": "cancel_requested"},
    )
    monkeypatch.setattr(
        api_server,
        "retry_medical_copilot_job",
        lambda job_id, *, owner_id: {"job_id": job_id, "status": "queued"},
    )
    client = TestClient(app)
    job_id = "mcj_20260719T000000Z_1234567890abcdef"
    created = client.post(
        "/api/student/medical-copilot/jobs",
        json={**request_payload(), "generate_answer": "false"},
    )
    assert created.status_code == 200
    assert created.json()["job"]["job_id"] == job_id
    assert captured["payload"]["generate_answer"] is False
    assert captured["owner_id"]
    assert client.get(f"/api/student/medical-copilot/jobs/{job_id}").json()["status"] == "running"
    assert client.post(f"/api/student/medical-copilot/jobs/{job_id}/cancel").json()["status"] == "cancel_requested"
    assert client.post(f"/api/student/medical-copilot/jobs/{job_id}/retry").json()["status"] == "queued"
