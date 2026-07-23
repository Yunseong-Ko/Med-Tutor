#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${PACCINE_APP_ROOT:-/app}"
DATA_ROOT="${PACCINE_DATA_ROOT:-${APP_ROOT}/data_private}"
SEED_ROOT="${PACCINE_RUNTIME_SEED_ROOT:-${APP_ROOT}/runtime_seed}"

cd "${APP_ROOT}"

python scripts/validate_full_demo_env.py

python scripts/seed_runtime_data.py \
  --seed-root "${SEED_ROOT}" \
  --data-root "${DATA_ROOT}" \
  --verify

exec uvicorn api_server:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
