from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import api_server


app = api_server.app


def test_login_exposes_separate_student_and_faculty_workspaces():
    client = TestClient(app)

    response = client.get("/login")

    assert response.status_code == 200
    assert "학생 학습" in response.text
    assert "교수 스튜디오" in response.text
    assert "P:accine 로그인" in response.text


def test_login_response_chooses_latest_role_surface_when_gate_is_disabled():
    client = TestClient(app)

    student = client.post("/api/auth/login", json={"role": "student"})
    faculty = client.post("/api/auth/login", json={"role": "faculty"})

    assert student.json()["redirect_to"] == "/student/"
    assert faculty.json()["redirect_to"] == "/faculty-studio-v2/"


def test_root_uses_role_cookie_and_legacy_ui_routes_redirect():
    client = TestClient(app, follow_redirects=False)

    assert client.get("/").headers["location"] == "/student/"
    client.cookies.set("paccine_role", "faculty")
    assert client.get("/").headers["location"] == "/faculty-studio-v2/"
    assert client.get("/faculty-studio-v2/legacy").headers["location"] == "/faculty-studio-v2/"
    assert client.get("/faculty-studio-v2/index.html").headers["location"] == "/faculty-studio-v2/"
    assert client.get("/student-v2/").headers["location"] == "/student/"
    assert client.get("/student/index.html").headers["location"] == "/student/"


def test_current_role_shells_do_not_reuse_stale_html():
    client = TestClient(app)

    student = client.get("/student/")
    faculty = client.get("/faculty-studio-v2/")
    reader = client.get("/student/reader.html")

    assert student.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert faculty.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert reader.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert 'data-logout' in student.text
    assert 'id="logout-button"' in faculty.text


def test_login_next_path_is_preserved_without_allowing_external_redirects():
    client = TestClient(app)

    internal = client.post(
        "/api/auth/login",
        json={"role": "student", "next": "/student/reader.html?ids=q1"},
    )
    external = client.post(
        "/api/auth/login",
        json={"role": "faculty", "next": "//example.com/steal"},
    )

    assert internal.json()["redirect_to"] == "/student/reader.html?ids=q1"
    assert external.json()["redirect_to"] == "/faculty-studio-v2/"


def test_enabled_gate_preserves_requested_surface_and_sets_role(monkeypatch):
    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", "presenter@example.com")
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", "safe-presentation-password")
    monkeypatch.setattr(
        api_server,
        "_FACULTY_EMAILS",
        frozenset({"presenter@example.com"}),
    )
    monkeypatch.setattr(api_server, "_COOKIE_SECURE", False)
    client = TestClient(app, follow_redirects=False)

    protected = client.get("/faculty-studio-v2/review.html", headers={"accept": "text/html"})
    parsed = urlparse(protected.headers["location"])
    assert parsed.path == "/login"
    assert parse_qs(parsed.query)["next"] == ["/faculty-studio-v2/review.html"]

    login = client.post(
        "/api/auth/login",
        json={
            "email": "presenter@example.com",
            "password": "safe-presentation-password",
            "role": "faculty",
            "next": "/faculty-studio-v2/review.html",
        },
    )
    assert login.status_code == 200
    assert login.json()["redirect_to"] == "/faculty-studio-v2/review.html"
    assert login.json()["role"] == "faculty"
    assert client.cookies.get("paccine_role") == "faculty"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["ok"] is True
    assert client.cookies.get("paccine_session") is None
    assert client.cookies.get("paccine_role") is None

    protected_again = client.get("/faculty-studio-v2/", headers={"accept": "text/html"})
    assert protected_again.status_code == 307
    assert protected_again.headers["location"].startswith("/login?next=")
