#!/usr/bin/env python3
"""Fail closed when a full P:accine demo is started without its secrets.

The local development server remains unchanged. Railway sets
``PACCINE_REQUIRE_FULL_DEMO=1`` so a deployment cannot accidentally expose
private educational data without login protection or silently lose its AI
features because a provider key was omitted.
"""

from __future__ import annotations

import os
import sys


AUTH_VARIABLES = (
    "APP_ALLOWED_EMAIL",
    "APP_AUTH_PASSWORD",
    "APP_SESSION_SECRET",
    "APP_FACULTY_EMAILS",
    # 가입 승인 계정(교수 검토 콘솔 F2)·로스터 계정의 초기 비밀번호 파생 키. 없으면 승인은 되지만 학생 로그인이 영구 불가.
    "APP_ROSTER_SECRET",
)
AI_KEY_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
)


TRUE_VALUES = {"1", "true", "yes", "on"}
PRODUCTION_VALUES = {"prod", "production"}
RAILWAY_MARKERS = (
    "RAILWAY_PROJECT_ID",
    "RAILWAY_SERVICE_ID",
    "RAILWAY_ENVIRONMENT_ID",
    "RAILWAY_DEPLOYMENT_ID",
)


def deployment_guard_required(environment: dict[str, str]) -> bool:
    """Return whether missing deployment secrets must stop the process."""

    full_demo = environment.get("PACCINE_REQUIRE_FULL_DEMO", "").strip().lower()
    environment_name = (
        environment.get("ENV")
        or environment.get("ENVIRONMENT")
        or environment.get("APP_ENV")
        or environment.get("RAILWAY_ENVIRONMENT_NAME")
        or ""
    ).strip().lower()
    return bool(
        full_demo in TRUE_VALUES
        or environment_name in PRODUCTION_VALUES
        or any(environment.get(name, "").strip() for name in RAILWAY_MARKERS)
    )


def validate_environment(environment: dict[str, str]) -> list[str]:
    if not deployment_guard_required(environment):
        return []

    errors: list[str] = []
    missing_auth = [name for name in AUTH_VARIABLES if not environment.get(name, "").strip()]
    if missing_auth:
        errors.append("missing login variables: " + ", ".join(missing_auth))

    password = environment.get("APP_AUTH_PASSWORD", "")
    if password and len(password) < 12:
        errors.append("APP_AUTH_PASSWORD must contain at least 12 characters")

    session_secret = environment.get("APP_SESSION_SECRET", "")
    if session_secret and len(session_secret) < 32:
        errors.append("APP_SESSION_SECRET must contain at least 32 characters")

    roster_secret = environment.get("APP_ROSTER_SECRET", "")
    if roster_secret and len(roster_secret) < 16:
        errors.append("APP_ROSTER_SECRET must contain at least 16 characters")

    allowed_email = environment.get("APP_ALLOWED_EMAIL", "").strip().lower()
    faculty_emails = {
        value.strip().lower()
        for value in environment.get("APP_FACULTY_EMAILS", "").split(",")
        if value.strip()
    }
    if allowed_email and faculty_emails and allowed_email not in faculty_emails:
        errors.append(
            "APP_ALLOWED_EMAIL must be listed in APP_FACULTY_EMAILS "
            "for the single-account faculty demo"
        )

    if not any(environment.get(name, "").strip() for name in AI_KEY_VARIABLES):
        errors.append("missing AI provider key: set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY")

    if environment.get("APP_COOKIE_SECURE", "").strip() != "1":
        errors.append("APP_COOKIE_SECURE must be 1 for the external HTTPS demo")

    return errors


def main() -> int:
    errors = validate_environment(dict(os.environ))
    if errors:
        print("P:accine full-demo environment check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("P:accine full-demo environment check passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
