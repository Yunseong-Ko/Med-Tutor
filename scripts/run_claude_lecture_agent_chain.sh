#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HANDOFF_DIR="$ROOT/.claude/handoffs/lecture-$(date +%Y%m%d-%H%M%S)"
PERMISSION_MODE="${CLAUDE_PERMISSION_MODE:-acceptEdits}"

mkdir -p "$HANDOFF_DIR"
cd "$ROOT"

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
    --append-system-prompt "Keep raw lecture/PMA source text private. Do not paste full raw source text into handoff notes. Use file paths, counts, schema fields, and short structural summaries instead." \
    "$prompt" | tee "$out"
}

PM_OUT="$HANDOFF_DIR/01_pm_ticket.md"
DATA_OUT="$HANDOFF_DIR/02_data_engineer.md"
QA_OUT="$HANDOFF_DIR/03_qa_integrator.md"
EVIDENCE_OUT="$HANDOFF_DIR/04_evidence_reviewer.md"
SUMMARY_OUT="$HANDOFF_DIR/README.md"

PM_PROMPT=$(cat <<'PROMPT'
현재 Codex가 만든 lecture -> PMA-style question draft 파이프라인을 검토하고, 첫 데모 준비를 위한 가장 작은 다음 구현 티켓을 작성해줘.

목표:
- 예시 강의록을 넣으면 텍스트 추출과 PMA식 문항 생성 프롬프트가 안정적으로 만들어질 것
- API 키가 있으면 PMA식 5지선다 JSON 초안까지 생성될 것
- 해설은 풀이/정답/오답 포인트/출제 포인트 구조일 것
- AMBOSS/UpToDate/NEJM/PubMed/가이드라인은 승인된 로컬 evidence pack으로만 보조 근거화할 것
- data_private/ 밖으로 원문/생성 원문이 새지 않을 것

검토 대상:
- scripts/generate_lecture_questions.py
- schemas/lecture_question.schema.json
- docs/pma_pipeline/Lecture_Question_Generation_First_Target.md
- app.py의 객관식 생성 프롬프트와 normalize_mcq_item 관련 변경

구현하지 말고 lecture-data-engineer가 바로 수행할 티켓만 작성해줘.
PROMPT
)

run_agent "lecture-pm-architect" "$PM_OUT" "$PM_PROMPT"

DATA_PROMPT=$(cat <<PROMPT
아래 PM 티켓만 구현해줘.

$(cat "$PM_OUT")

범위:
- scripts/generate_lecture_questions.py
- schemas/lecture_question.schema.json
- docs/pma_pipeline/Lecture_Question_Generation_First_Target.md
- 필요 시 app.py의 매우 작은 호환성 수정
- 필요 시 최소 테스트 또는 self-check 스크립트

주의:
- raw lecture/PMA/evidence 파일과 모델 출력은 data_private/ 아래에만 둘 것
- 외부 자료 scraping 금지
- 교수 검수 전 의료 정답성을 확정한다고 표현하지 말 것
- 완료 후 실행 명령, 변경 파일, 남은 리스크를 남겨줘
PROMPT
)

run_agent "lecture-data-engineer" "$DATA_OUT" "$DATA_PROMPT"

QA_PROMPT=$(cat <<PROMPT
현재 변경사항을 검토하고 lecture question pipeline을 검증해줘.

이전 산출물:
PM ticket:
$(cat "$PM_OUT")

Data engineer handoff:
$(cat "$DATA_OUT")

확인:
- data_private/가 gitignore에 포함되어 있고 git status에 원문/생성물이 뜨지 않는지
- scripts/generate_lecture_questions.py가 py_compile 되는지
- prompt-only 모드가 예시 문서로 실행되는지
- lecture_question.schema.json이 representative normalized question을 통과하는지
- AXIOMA_REQUIRE_SUPABASE=0으로 Streamlit AppTest 예외가 없는지
- app.py 변경이 불필요하게 넓지 않은지

필요하면 최소 수정만 해줘. 검증 명령과 결과를 정리해줘.
PROMPT
)

run_agent "lecture-qa-integrator" "$QA_OUT" "$QA_PROMPT"

EVIDENCE_PROMPT=$(cat <<PROMPT
lecture -> PMA-style question pipeline을 의학교육/근거자료 관점에서 리뷰해줘.

이전 산출물:
PM ticket:
$(cat "$PM_OUT")

Data engineer handoff:
$(cat "$DATA_OUT")

QA handoff:
$(cat "$QA_OUT")

확인:
- PMA 풀이 스타일이 충분히 반영되었는지
- AMBOSS/UpToDate/NEJM/PubMed/가이드라인 활용 정책이 안전한지
- evidence_refs/evidence_tier 구조가 향후 RAG/DB화에 충분한지
- 예시 강의록 업로드 데모 전에 필요한 사용자 입력/자료가 무엇인지
- 환자/학생/저작권/최신 진료지침 관련 리스크가 무엇인지

코드는 수정하지 말고 리뷰와 다음 권장 티켓만 작성해줘.
PROMPT
)

run_agent "lecture-evidence-reviewer" "$EVIDENCE_OUT" "$EVIDENCE_PROMPT"

cat > "$SUMMARY_OUT" <<EOF
# Lecture Claude Agent Chain Handoff

Created: $(date)
Permission mode: $PERMISSION_MODE

## Outputs

- PM ticket: $PM_OUT
- Data engineer: $DATA_OUT
- QA integrator: $QA_OUT
- Evidence reviewer: $EVIDENCE_OUT

## Next step

Ask Codex to inspect the changed files and decide whether to run the app or integrate the pipeline into the Streamlit UI.
EOF

echo
echo "Done."
echo "Handoff directory:"
echo "$HANDOFF_DIR"
echo
echo "Open summary:"
echo "$SUMMARY_OUT"
