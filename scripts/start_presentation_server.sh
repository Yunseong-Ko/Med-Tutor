#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${PACCINE_PRESENTATION_ENV_FILE:-$ROOT/ops/presentation.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing presentation environment file: $ENV_FILE" >&2
  echo "Copy ops/presentation.env.example to ops/presentation.env and fill the secrets." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PY_BIN="${PACCINE_PYTHON:-python3}"

for required in APP_ALLOWED_EMAIL APP_AUTH_PASSWORD APP_SESSION_SECRET APP_FACULTY_EMAILS; do
  if [ -z "${!required:-}" ] || [ "${!required}" = "CHANGE_ME" ]; then
    echo "$required must be configured in $ENV_FILE" >&2
    exit 1
  fi
done

if ! "$PY_BIN" "$ROOT/scripts/validate_full_demo_env.py"; then
  echo "Presentation environment safety check failed." >&2
  exit 1
fi

HOST="${PACCINE_PRESENTATION_HOST:-127.0.0.1}"
PORT="${PACCINE_PRESENTATION_PORT:-8010}"

cd "$ROOT"
echo "Starting login-protected P:accine presentation server on $HOST:$PORT"
exec "$PY_BIN" -m uvicorn api_server:app \
  --host "$HOST" \
  --port "$PORT" \
  --proxy-headers \
  --forwarded-allow-ips="*"
