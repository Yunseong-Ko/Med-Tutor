from scripts.validate_full_demo_env import (
    deployment_guard_required,
    validate_environment,
)


def test_local_environment_does_not_require_deployment_secrets():
    assert validate_environment({}) == []


def test_full_demo_requires_login_ai_and_secure_cookie():
    errors = validate_environment({"PACCINE_REQUIRE_FULL_DEMO": "1"})

    assert any("missing login variables" in error for error in errors)
    assert any("missing AI provider key" in error for error in errors)
    assert any("APP_COOKIE_SECURE" in error for error in errors)


def test_full_demo_accepts_complete_anthropic_configuration():
    environment = {
        "PACCINE_REQUIRE_FULL_DEMO": "1",
        "APP_ALLOWED_EMAIL": "presenter@example.com",
        "APP_AUTH_PASSWORD": "long-demo-password",
        "APP_SESSION_SECRET": "x" * 32,
        "APP_ROSTER_SECRET": "roster-secret-for-tests-32-bytes!!",
        "APP_FACULTY_EMAILS": "presenter@example.com",
        "APP_COOKIE_SECURE": "1",
        "ANTHROPIC_API_KEY": "configured-outside-source-control",
    }

    assert validate_environment(environment) == []


def test_railway_environment_requires_guard_without_opt_in_flag():
    environment = {
        "RAILWAY_PROJECT_ID": "project-id",
        "RAILWAY_SERVICE_ID": "service-id",
    }

    assert deployment_guard_required(environment) is True
    errors = validate_environment(environment)
    assert any("missing login variables" in error for error in errors)


def test_single_account_faculty_email_must_be_server_allowlisted():
    environment = {
        "PACCINE_REQUIRE_FULL_DEMO": "1",
        "APP_ALLOWED_EMAIL": "presenter@example.com",
        "APP_AUTH_PASSWORD": "long-demo-password",
        "APP_SESSION_SECRET": "x" * 32,
        "APP_ROSTER_SECRET": "roster-secret-for-tests-32-bytes!!",
        "APP_FACULTY_EMAILS": "someone-else@example.com",
        "APP_COOKIE_SECURE": "1",
        "ANTHROPIC_API_KEY": "configured-outside-source-control",
    }

    errors = validate_environment(environment)
    assert any("APP_ALLOWED_EMAIL must be listed" in error for error in errors)


def test_missing_roster_secret_is_reported_for_deployments():
    environment = {
        "PACCINE_REQUIRE_FULL_DEMO": "1",
        "APP_ALLOWED_EMAIL": "presenter@example.com",
        "APP_AUTH_PASSWORD": "safe-presentation-password",
        "APP_SESSION_SECRET": "x" * 32,
        "APP_FACULTY_EMAILS": "presenter@example.com",
        "ANTHROPIC_API_KEY": "key",
        "APP_COOKIE_SECURE": "1",
    }
    errors = validate_environment(environment)
    assert any("APP_ROSTER_SECRET" in error for error in errors), errors
    environment["APP_ROSTER_SECRET"] = "short"
    assert any("APP_ROSTER_SECRET must contain at least 16" in error for error in validate_environment(environment))
    environment["APP_ROSTER_SECRET"] = "roster-secret-for-tests-32-bytes!!"
    assert validate_environment(environment) == []
