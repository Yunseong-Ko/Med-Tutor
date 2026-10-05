#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${PACCINE_PRESENTATION_ENV_FILE:-$ROOT/ops/presentation.env}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

HOST="${PACCINE_PRESENTATION_HOST:-127.0.0.1}"
PORT="${PACCINE_PRESENTATION_PORT:-8010}"
ORIGIN="http://$HOST:$PORT"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is required. Install it with: brew install cloudflared" >&2
  exit 1
fi

if ! curl -fsS "$ORIGIN/api/health" >/dev/null; then
  echo "Presentation server is not ready at $ORIGIN" >&2
  echo "Start scripts/start_presentation_server.sh first." >&2
  exit 1
fi

echo "Creating an HTTPS presentation address for $ORIGIN"
echo "Keep this process running. The temporary URL changes whenever it restarts."
exec cloudflared tunnel \
  --no-autoupdate \
  --protocol http2 \
  --url "$ORIGIN"
