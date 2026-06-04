# P:accine local automation shortcuts.
# Install just if desired: brew install just

set shell := ["zsh", "-cu"]

default:
    just --list

status:
    git status --short

dev-studio:
    python -m uvicorn api_server:app --host 127.0.0.1 --port 8000 --reload

dev-streamlit:
    AXIOMA_REQUIRE_SUPABASE=0 streamlit run app.py

check:
    node --check frontend/app.js
    git diff --check

test:
    python -m pytest

learning-doc:
    sed -n '1,120p' docs/Paccine_Learning_Analytics_Master_Prompt_20260604.md

