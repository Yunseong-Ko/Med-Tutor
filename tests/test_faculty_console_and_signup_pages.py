"""교수 검토 콘솔(/faculty-review-console/) · 공개 가입 페이지(/signup) 라우팅 — 2026-09-06.

클로드 디자인 시안(design_handoff/received_faculty_student_ops_20260905) 구현분의 서버 측 접점만 검사한다:
콘솔은 교수 세션 전용(_path_requires_faculty), 가입 페이지는 게이트 밖 공개(_AUTH_PUBLIC_PATHS), 둘 다 no-cache.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import api_server


NO_CACHE = "no-cache, no-store, must-revalidate"


def _enable_gate(monkeypatch):
    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", "presenter@example.com")
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", "safe-presentation-password")
    monkeypatch.setattr(api_server, "_FACULTY_EMAILS", frozenset({"presenter@example.com"}))
    monkeypatch.setattr(api_server, "_ROSTER_EMAILS", frozenset())
    monkeypatch.setattr(api_server, "_ROSTER_SECRET", "")
    monkeypatch.setattr(api_server, "_SESSION_SECRET", "test-session-secret-" * 3)
    monkeypatch.setattr(api_server, "_COOKIE_SECURE", False)
    assert api_server._auth_gate_enabled()


def test_console_shell_serves_isolated_entrypoint_for_faculty_role():
    client = TestClient(api_server.app)
    client.cookies.set("paccine_role", "faculty")
    for path in ("/faculty-review-console", "/faculty-review-console/", "/faculty-review-console/index.html"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == NO_CACHE
        assert "교수 검토 콘솔" in response.text
        assert "/faculty-review-console/console.js" in response.text
    # 정적 자산(콘솔 JS/CSS)은 StaticFiles 마운트로 서빙된다
    assert client.get("/faculty-review-console/console.js").status_code == 200
    assert client.get("/faculty-review-console/console.css").status_code == 200


def test_console_requires_faculty_session_when_gate_is_enabled(monkeypatch):
    _enable_gate(monkeypatch)
    anonymous = TestClient(api_server.app, follow_redirects=False)
    blocked = anonymous.get("/faculty-review-console/", headers={"accept": "text/html"})
    assert blocked.status_code in (302, 303, 307)
    assert blocked.headers["location"].startswith("/login")

    faculty = TestClient(api_server.app)
    login = faculty.post("/api/auth/login", json={"email": "presenter@example.com", "password": "safe-presentation-password", "role": "faculty"})
    assert login.status_code == 200 and login.json()["role"] == "faculty"
    assert faculty.get("/faculty-review-console/").status_code == 200
    # 같은 계정을 학생 세션으로 열면 학생 화면으로 돌려보낸다(교수 전용 경로)
    student = TestClient(api_server.app, follow_redirects=False)
    assert student.post("/api/auth/login", json={"email": "presenter@example.com", "password": "safe-presentation-password", "role": "student"}).status_code == 200
    redirected = student.get("/faculty-review-console/", headers={"accept": "text/html"})
    assert redirected.status_code == 303 and redirected.headers["location"] == "/student/"
    assert student.get("/api/faculty/adjudication/summary").status_code == 403


def test_signup_page_is_public_and_links_from_login(monkeypatch):
    _enable_gate(monkeypatch)
    anonymous = TestClient(api_server.app, follow_redirects=False)
    page = anonymous.get("/signup", headers={"accept": "text/html"})
    assert page.status_code == 200
    assert page.headers["cache-control"] == NO_CACHE
    assert "가입 신청" in page.text and "/api/auth/signup" in page.text
    # 외부 정적 자산 의존 없음(게이트 밖에서도 완전 렌더)
    assert 'rel="stylesheet"' not in page.text and "<script src=" not in page.text
    login = anonymous.get("/login")
    assert 'href="/signup"' in login.text
    # 다른 학생 정적 경로는 여전히 게이트에 막힌다
    assert anonymous.get("/student/", headers={"accept": "text/html"}).status_code in (302, 303, 307)


def test_faculty_studio_nav_links_to_console():
    client = TestClient(api_server.app)
    client.cookies.set("paccine_role", "faculty")
    studio = client.get("/faculty-studio-v2/")
    assert studio.status_code == 200 and 'href="/faculty-review-console/"' in studio.text
    # 기본 착지 셸(v3)은 모바일에서 nav 를 숨기므로 메뉴 토글이 있어야 콘솔 링크에 닿는다
    assert 'id="nav-menu-button"' in studio.text and 'id="faculty-nav"' in studio.text
    # 스튜디오 서브페이지 7개(v2)도 전부 링크를 가진다 — 서버는 v3 셸만 서빙하므로 파일을 직접 읽는다
    pages = sorted((api_server.FRONTEND_DIR / "faculty-studio-v2").glob("*.html"))
    assert len(pages) >= 7
    missing = [page.name for page in pages if 'href="/faculty-review-console/"' not in page.read_text(encoding="utf-8")]
    assert not missing, missing


def test_console_shell_has_logout_and_no_global_live_region():
    client = TestClient(api_server.app)
    client.cookies.set("paccine_role", "faculty")
    html = client.get("/faculty-review-console/").text
    assert 'id="frc-logout"' in html
    assert '<main id="frc-app" class="frc-main">' in html          # 전체 재렌더 영역은 aria-live 가 아니어야 한다
    js = (api_server.FRONTEND_DIR / "faculty-review-console" / "console.js").read_text(encoding="utf-8")
    assert '"/api/auth/logout"' in js
    assert 'event.key === "Enter" && (event.metaKey || event.ctrlKey)' in js   # 메모창 일반 Enter 로는 승인되지 않는다
