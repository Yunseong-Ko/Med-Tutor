#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Enables agent-to-agent coordination features when available in Claude Code.
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-1}"

exec claude --name pma-question-pipeline "$@"
