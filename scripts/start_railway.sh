#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${PACCINE_APP_ROOT:-/app}"
DATA_ROOT="${PACCINE_DATA_ROOT:-${APP_ROOT}/data_private}"
SEED_ROOT="${PACCINE_RUNTIME_SEED_ROOT:-${APP_ROOT}/runtime_seed}"

cd "${APP_ROOT}"

# API 모듈(api_server·signup_requests·faculty_adjudication·trust_badges)은 ${APP_ROOT}/data_private 고정 경로를 읽는다.
# 시더만 다른 곳을 채우면 콘솔·가입 승인·학생 문항이 '사라진' 것처럼 보이고 교수 결정이 볼륨 밖에 써지므로 즉시 중단한다.
if [ "${DATA_ROOT%/}" != "${APP_ROOT%/}/data_private" ]; then
  echo "PACCINE_DATA_ROOT must be ${APP_ROOT}/data_private (got ${DATA_ROOT}); app modules read a fixed path." >&2
  exit 1
fi

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
