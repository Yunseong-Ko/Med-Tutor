#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="${1:-pma-personas}"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required for the 4-pane persona launcher."
  echo "Install with: brew install tmux"
  exit 1
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Attaching existing tmux session: $SESSION"
  exec tmux attach-session -t "$SESSION"
fi

CLAUDE_ENV='export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-1}"'

run_claude() {
  local agent="$1"
  local name="$2"
  local title="$3"
  printf 'cd %q && %s && printf "\\033]2;%s\\033\\\\" && claude --agent %q --name %q' \
    "$ROOT" "$CLAUDE_ENV" "$title" "$agent" "$name"
}

tmux new-session -d -s "$SESSION" -n "PMA"
tmux send-keys -t "$SESSION":0.0 "$(run_claude pma-pm-architect pma-pm 'PMA PM Architect')" C-m

# Four side-by-side vertical columns, left to right:
# PM Architect / Data Engineer / QA Integrator / Medical Reviewer.
tmux split-window -h -t "$SESSION":0.0
tmux send-keys -t "$SESSION":0.1 "$(run_claude pma-data-engineer pma-data 'PMA Data Engineer')" C-m

tmux split-window -h -t "$SESSION":0.1
tmux send-keys -t "$SESSION":0.2 "$(run_claude pma-qa-integrator pma-qa 'PMA QA Integrator')" C-m

tmux split-window -h -t "$SESSION":0.2
tmux send-keys -t "$SESSION":0.3 "$(run_claude pma-medical-reviewer pma-medical 'PMA Medical Reviewer')" C-m

tmux select-layout -t "$SESSION":0 even-horizontal
tmux select-pane -t "$SESSION":0.0

cat <<EOF
Started tmux session: $SESSION

Panes:
  0: pma-pm-architect
  1: pma-data-engineer
  2: pma-qa-integrator
  3: pma-medical-reviewer

Useful tmux keys:
  Ctrl-b + arrow keys  Move between panes
  Ctrl-b + z           Zoom/unzoom current pane
  Ctrl-b + d           Detach without stopping sessions

EOF

exec tmux attach-session -t "$SESSION"
