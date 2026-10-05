#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HANDOFF_DIR="$ROOT/.claude/handoffs/pma-$(date +%Y%m%d-%H%M%S)"
PERMISSION_MODE="${CLAUDE_PERMISSION_MODE:-acceptEdits}"

mkdir -p "$HANDOFF_DIR"
cd "$ROOT"

export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-1}"

run_agent() {
  local agent="$1"
  local out="$2"
  local prompt="$3"

  echo
  echo "==> Running $agent"
  echo "    output: $out"

  claude -p \
    --agent "$agent" \
    --name "$agent" \
    --permission-mode "$PERMISSION_MODE" \
    --append-system-prompt "Keep raw PMA question text private. Do not paste full raw PMA questions into handoff notes. Refer to question_id, file paths, counts, and parser issues instead." \
    "$prompt" | tee "$out"
}

PM_OUT="$HANDOFF_DIR/01_pm_ticket.md"
DATA_OUT="$HANDOFF_DIR/02_data_engineer.md"
QA_OUT="$HANDOFF_DIR/03_qa_integrator.md"
MED_OUT="$HANDOFF_DIR/04_medical_reviewer.md"
SUMMARY_OUT="$HANDOFF_DIR/README.md"

PM_PROMPT=$(cat <<'PROMPT'
PMA PDF -> question-level JSON pipeline의 첫 번째 최소 구현 티켓을 작성해줘.

목표:
- data_private/pma/raw/*.pdf에서 텍스트를 추출
- 문항 번호 기준으로 분리
- stem, choices, raw_text, has_image, source_exam, period, question_number 생성
- 정답이 없으면 answer=null
- 결과는 data_private/pma/extracted/*.json
- 샘플 5문항만 구조 확인 가능하게 출력하는 옵션 또는 명령 제공

구현하지 말고 pma-data-engineer에게 전달할 티켓만 작성해줘.
민감한 PMA 원문은 출력하지 말고, 경로/필드/완료 기준 중심으로 작성해줘.
PROMPT
)

run_agent "pma-pm-architect" "$PM_OUT" "$PM_PROMPT"

DATA_PROMPT=$(cat <<PROMPT
아래 PM 티켓만 구현해줘.

$(cat "$PM_OUT")

수정 범위:
- scripts/ 안의 PMA 추출/검수 보조 스크립트
- 필요하면 최소 문서
- 필요하면 .gitignore 보완

주의:
- raw PDF와 추출 JSON/CSV는 data_private/ 아래에만 둘 것
- git status에 data_private/ 내용이 뜨지 않게 할 것
- 정답은 출처에 명시적으로 있더라도 이번 1차 파이프라인에서는 answer=null 유지
- 애매한 문항은 needs_review=true
- 완료 후 실행 명령과 샘플 5문항 확인 방법을 남길 것
PROMPT
)

run_agent "pma-data-engineer" "$DATA_OUT" "$DATA_PROMPT"

QA_PROMPT=$(cat <<PROMPT
현재 변경사항을 검토하고 PMA 추출 파이프라인을 검증해줘.

이전 산출물:
PM ticket:
$(cat "$PM_OUT")

Data engineer handoff:
$(cat "$DATA_OUT")

확인:
- data_private/가 gitignore에 포함되어 있는지
- raw PDF나 추출 JSON/CSV가 git status에 뜨지 않는지
- parser 실행이 성공하는지
- 샘플 5문항 JSON 필드가 완전한지
- needs_review와 has_image 플래그가 보수적으로 설정되는지
- 기존 앱 동작을 건드리는 불필요한 변경이 없는지

필요하면 최소 수정만 해줘.
민감한 PMA 원문은 출력하지 말고 question_id, 개수, 파일 경로, 문제 유형의 오류만 요약해줘.
PROMPT
)

run_agent "pma-qa-integrator" "$QA_OUT" "$QA_PROMPT"

MED_PROMPT=$(cat <<PROMPT
data_private/pma/extracted의 샘플 5문항을 보고 문항 분리 품질을 리뷰해줘.

이전 산출물:
PM ticket:
$(cat "$PM_OUT")

Data engineer handoff:
$(cat "$DATA_OUT")

QA handoff:
$(cat "$QA_OUT")

확인:
- stem과 choices가 자연스럽게 분리되었는지
- 이미지 의존 문항이 has_image=true로 표시되어야 하는지
- answer를 추정하지 않고 null로 둔 것이 적절한지
- 향후 라벨링에 필요한 course, unit, concepts, question_type 후보가 무엇인지
- 교수 검수 큐로 넘겨야 할 위험 케이스가 무엇인지

코드는 수정하지 말고 리뷰 결과와 라벨링 가이드 제안만 작성해줘.
민감한 PMA 원문은 출력하지 말고 question_id와 구조적 이슈 중심으로 요약해줘.
PROMPT
)

run_agent "pma-medical-reviewer" "$MED_OUT" "$MED_PROMPT"

cat > "$SUMMARY_OUT" <<EOF
# PMA Claude Agent Chain Handoff

Created: $(date)
Permission mode: $PERMISSION_MODE

## Outputs

- PM ticket: $PM_OUT
- Data engineer: $DATA_OUT
- QA integrator: $QA_OUT
- Medical reviewer: $MED_OUT

## Next step

Review the four handoff files, then ask Codex to inspect changed code and run the final checks.
EOF

echo
echo "Done."
echo "Handoff directory:"
echo "$HANDOFF_DIR"
echo
echo "Open summary:"
echo "$SUMMARY_OUT"
