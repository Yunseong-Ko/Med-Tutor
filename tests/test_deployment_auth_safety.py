from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import api_server


def _deployment_environment(**overrides: str) -> dict[str, str]:
    environment = {
        "RAILWAY_PROJECT_ID": "project-id",
        "APP_ALLOWED_EMAIL": "presenter@example.com",
        "APP_AUTH_PASSWORD": "long-presentation-password",
        "APP_SESSION_SECRET": "s" * 32,
        "APP_ROSTER_SECRET": "roster-secret-for-tests-32-bytes!!",
        "APP_FACULTY_EMAILS": "presenter@example.com",
        "APP_COOKIE_SECURE": "1",
        "ANTHROPIC_API_KEY": "configured-outside-source-control",
    }
    environment.update(overrides)
    return environment


def _enable_test_gate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    allowed_email: str = "student@example.com",
    faculty_emails: frozenset[str] = frozenset(),
) -> None:
    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", allowed_email)
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", "correct-password")
    monkeypatch.setattr(api_server, "_FACULTY_EMAILS", faculty_emails)
    monkeypatch.setattr(api_server, "_SESSION_SECRET", "test-session-secret-" * 3)
    monkeypatch.setattr(api_server, "_COOKIE_SECURE", False)


def test_railway_boot_fails_closed_when_auth_secrets_are_missing():
    with pytest.raises(RuntimeError, match="deployment environment is incomplete"):
        api_server._enforce_deployment_environment(
            {
                "RAILWAY_PROJECT_ID": "project-id",
                "ANTHROPIC_API_KEY": "configured-outside-source-control",
            }
        )


def test_railway_boot_accepts_complete_server_owned_role_configuration():
    api_server._enforce_deployment_environment(_deployment_environment())


def test_login_body_cannot_grant_faculty_role_without_server_allowlist(monkeypatch):
    _enable_test_gate(monkeypatch)
    client = TestClient(api_server.app, follow_redirects=False)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "student@example.com",
            "password": "correct-password",
            "role": "faculty",
            "next": "/faculty-studio-v2/",
        },
    )

    assert response.status_code == 200
    assert response.json()["role"] == "student"
    assert response.json()["redirect_to"] == "/student/"
    token = client.cookies["paccine_session"].strip('"')
    claims = api_server._verify_session_token(token)
    assert claims and claims["role"] == "student"


def test_server_allowlisted_identity_can_receive_faculty_role(monkeypatch):
    _enable_test_gate(
        monkeypatch,
        allowed_email="faculty@example.com",
        faculty_emails=frozenset({"faculty@example.com"}),
    )
    client = TestClient(api_server.app, follow_redirects=False)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "faculty@example.com",
            "password": "correct-password",
            "role": "faculty",
        },
    )

    assert response.status_code == 200
    assert response.json()["role"] == "faculty"
    assert response.json()["redirect_to"] == "/faculty-studio-v2/"


def test_signed_student_session_cannot_open_faculty_html_or_api(monkeypatch):
    _enable_test_gate(monkeypatch)
    expires_at = int(time.time()) + 300
    token = api_server._sign_session_token(
        "student@example.com",
        "student",
        expires_at,
    )
    client = TestClient(api_server.app, follow_redirects=False)
    client.cookies.set("paccine_session", token)
    client.cookies.set("paccine_role", "faculty")

    html_response = client.get(
        "/faculty-studio-v2/",
        headers={"accept": "text/html"},
    )
    api_response = client.get("/api/faculty/qbank-enrichment/review-queue")
    root_response = client.get("/")

    assert html_response.status_code == 303
    assert html_response.headers["location"] == "/student/"
    assert api_response.status_code == 403
    assert root_response.headers["location"] == "/student/"
