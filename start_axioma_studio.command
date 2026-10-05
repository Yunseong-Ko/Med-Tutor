#!/bin/bash
set -e

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PY_BIN="python"
else
  echo "Python 3가 설치되어 있지 않습니다."
  read -n 1 -s -r -p "아무 키나 누르면 종료합니다..."
  echo
  exit 1
fi

if [ ! -d ".venv" ]; then
  "$PY_BIN" -m venv .venv
fi

source .venv/bin/activate

if [ ! -f ".venv/.axioma_studio_installed" ]; then
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  touch .venv/.axioma_studio_installed
fi

python -m uvicorn api_server:app --host 127.0.0.1 --port 8000 --reload

