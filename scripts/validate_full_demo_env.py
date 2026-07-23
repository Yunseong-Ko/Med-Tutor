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
)
AI_KEY_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
)


def validate_environment(environment: dict[str, str]) -> list[str]:
    if environment.get("PACCINE_REQUIRE_FULL_DEMO", "").strip() != "1":
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
