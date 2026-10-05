#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${PACCINE_HOST:-0.0.0.0}"
PORT="${PACCINE_PORT:-8000}"
LOG_DIR="$ROOT/logs"

mkdir -p "$LOG_DIR"
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PY_BIN="python"
else
  echo "Python 3 is required." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  "$PY_BIN" -m venv .venv
fi

source .venv/bin/activate

if [ ! -f ".venv/.paccine_server_installed" ]; then
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  touch .venv/.paccine_server_installed
fi

export AXIOMA_REQUIRE_SUPABASE="${AXIOMA_REQUIRE_SUPABASE:-0}"
export PYTHONUNBUFFERED=1

echo "Starting P:accine server at http://$HOST:$PORT"
exec python -m uvicorn api_server:app \
  --host "$HOST" \
  --port "$PORT" \
  --proxy-headers \
  --forwarded-allow-ips="*"
