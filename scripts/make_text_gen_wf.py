#!/usr/bin/env python3
"""텍스트 문항 생성 워크플로 생성기 — **골든 스키마**(게이트 계약 내장) 방식.

이전 런의 교훈(피드백 문서 §1.4): 게이트가 요구하는 메타데이터 계약이 생성 프롬프트에
없어서 잘 만든 문항도 하드룰 전량 탈락 → enrich 2-pass로 우회해야 했다.
여기서는 계약을 **생성 스키마와 프롬프트에 직접 내장**해 1-pass로 통과시킨다.

내장하는 계약:
  - reasoning_hops ≥ 2, cognitive_level, cognitive_model.decision_cues/answer_concept
  - choice_explanations: 정답 why_correct + 오답 4개 why_attractive(오개념 명시)
  - self_check 22키 자기평가
  - harrison_sources[{source_id, chapter, printed_page}]
  - NBME 선지 규칙(정답이 최장/최단 금지, 길이비 0.8~1.2, 동질성, cover-the-options)
  - difficulty_tier(하/중/상) — 설문 피드백(난이도 3.52 최저·단서 과다) 대응.
    티어는 개념 인덱스로 **결정론 배정**(모델이 고르지 않음), 티어별 단서 예산을 프롬프트로 강제.
보안: 원본 시험 텍스트는 프롬프트에 일절 넣지 않는다 — 온톨로지 팩만 사용.
사용: python3 scripts/make_text_gen_wf.py --per-batch 4 --model opus
"""
import argparse
import json
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
SP = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/"
          "4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad")

# 난이도 티어 결정론 배정 사이클 — 개념 인덱스 % 10 으로 30% 하 / 50% 중 / 20% 상.
# 라운드로빈이라 어느 구간을 잘라도 비율이 유지된다. make_pnu_gen_wf.py도 재사용.
TIER_CYCLE = ("하", "중", "상", "중", "하", "중", "중", "상", "하", "중")

SELF_CHECK_KEYS = [
    "undifferentiated_no_specialty_leak", "reasoning_hops_ge_2_real_not_recognition",
    "single_best_positive_lead_in", "lead_in_choice_consistent", "exactly_5_choices",
    "no_negative_stem", "no_all_or_none", "no_absolute_term", "no_vague_term",
    "key_length_rank_2_to_4_not_longest_not_shortest", "key_len_ratio_0_8_to_1_2",
    "key_not_most_components", "urgency_adverb_not_key_only", "no_clang_cue",
    "no_duplicate_or_overlapping_choices", "is_clinical_vignette_not_low_cognitive",
    "covers_the_options_passes", "distractors_homogeneous_same_category_and_form",
    "every_distractor_from_differential_or_misconception", "no_distractor_precluded_by_stem",
    "evidence_within_inherited_only", "cognitive_level_label_matches_actual",
]

HEAD = """export const meta = {
  name: 'text-item-golden-gen',
  description: '텍스트 문항 생성 — 게이트 계약 내장 골든 스키마(1-pass 통과 목표)',
  phases: [{ title: 'Generate' }],
}
const BATCHES = """


def build_tail(model: str, effort: str) -> str:
    sc_props = ",\n        ".join(f"'{k}': {{ type: 'boolean' }}" for k in SELF_CHECK_KEYS)
    sc_req = ", ".join(f"'{k}'" for k in SELF_CHECK_KEYS)
    ce_props = ",\n            ".join(
        f"'{i}': {{ type: 'object', additionalProperties: false, "
        f"properties: {{ why_attractive: {{ type: 'string' }}, why_correct: {{ type: 'string' }} }} }}"
        for i in range(1, 6))
    return r"""
const SELF_CHECK = {
  type: 'object', additionalProperties: false,
  properties: {
        __SC_PROPS__
  },
  required: [__SC_REQ__],
}
const ITEM = {
  type: 'object', additionalProperties: false,
  properties: {
    concept_id: { type: 'string' },
    department: { type: 'string' },
    axis: { type: 'string', enum: ['진단', '검사', '치료'] },
    difficulty_tier: { type: 'string', enum: ['하', '중', '상'] },
    stem: { type: 'string' },
    lab_box: { type: 'string' },
    choices: {
      type: 'object', additionalProperties: false,
      properties: {
        '1': { type: 'string' }, '2': { type: 'string' }, '3': { type: 'string' },
        '4': { type: 'string' }, '5': { type: 'string' },
      },
      required: ['1', '2', '3', '4', '5'],
    },
    answer: { type: 'integer', minimum: 1, maximum: 5 },
    explanation: { type: 'string' },
    reasoning_hops: { type: 'integer', minimum: 2, maximum: 5 },
    cognitive_level: { type: 'string', enum: ['해석', '문제해결'] },
    cognitive_model: {
      type: 'object', additionalProperties: false,
      properties: {
        decision_cues: { type: 'array', items: { type: 'string' }, minItems: 2, maxItems: 6 },
        answer_concept: { type: 'string' },
      },
      required: ['decision_cues', 'answer_concept'],
    },
    choice_explanations: {
      type: 'object', additionalProperties: false,
      properties: {
            __CE_PROPS__
      },
      required: ['1', '2', '3', '4', '5'],
    },
    evidence_spec: {
      type: 'object', additionalProperties: false,
      properties: {
        answer_claim: { type: 'string' },
        distractor_claims: {
          type: 'object', additionalProperties: false,
          properties: { '1': {type:'string'}, '2': {type:'string'}, '3': {type:'string'},
                        '4': {type:'string'}, '5': {type:'string'} },
        },
      },
      required: ['answer_claim'],
    },
    harrison_chapter: { type: 'integer' },
    harrison_page: { type: 'integer' },
    common_high_stakes_problem: { type: 'boolean' },
    self_check: SELF_CHECK,
  },
  required: ['concept_id', 'department', 'axis', 'difficulty_tier', 'stem', 'choices', 'answer', 'explanation',
             'reasoning_hops', 'cognitive_level', 'cognitive_model', 'choice_explanations', 'evidence_spec',
             'common_high_stakes_problem', 'self_check'],
}
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { batch_id: { type: 'string' }, items: { type: 'array', items: ITEM } },
  required: ['batch_id', 'items'],
}
const NL = String.fromCharCode(10)
function prompt(b, bi) {
  return [
'너는 의사국가시험 수준 A형 문항 출제 전문가다. 아래 **온톨로지 팩만** 근거로 임상증례 문항을 만든다.',
'원본 기출 문항은 제공되지 않으며, 어떤 기출 문장도 재현해서는 안 된다.',
'',
'## 개념 ' + b.length + '개 — 각 개념당 문항 1개',
b.map((e, i) => (i + 1) + '. concept_id=' + e.concept_id + ' | 분과=' + e.department
  + ' | 난이도=' + e.difficulty_tier + NL +
  '   온톨로지: ' + JSON.stringify(e.pack)).join(NL),
'',
'## 문항 규격 (A형)',
'- stem = 임상증례 vignette. "NN세 남자/여자가 ~로 병원에 왔다."로 시작.',
'  병력 → 진찰소견 → 활력징후 → 검사결과 순. 수치는 참고치와 함께.',
'  마지막은 lead-in 질문 1문장: 진단축="가장 가능성 있는 진단은?",',
'  검사축="진단을 위하여 다음에 시행할 검사는?", 치료축="가장 적절한 치료는?"',
'- 선지 5개, 동일 범주·동일 문법형식(진단명끼리/검사명끼리/치료명끼리).',
'- **오답은 전부 온톨로지 팩의 distractor_pool 또는 감별진단에서** 가져온다. 지어내지 않는다.',
'- 분과명·진단명을 stem에 노출하지 않는다(미분화 원칙).',
'- 의학 용어는 표준 한글 용어로 쓰고 **처음 등장할 때 영문을 병기**한다',
'  — 예: 심근경색(myocardial infarction). 잘 쓰지 않는 순우리말 용어를 만들지 않는다.',
'',
'## 난이도 티어 · 단서 예산 (스펙 줄의 난이도= 값을 그대로 따른다 — 임의 변경 금지)',
'- 하: 결정 단서(decision cue)를 모두 문두에 포함해도 된다.',
'- 중: 핵심 단서만 남긴다 — 감별 배제용 부가 단서는 최대 1개.',
'  정답을 직접 지시하는 소견을 나열하지 않는다.',
'- 상: 정답 추론에 **필수인 최소 단서만** 남긴다.',
'  오답 중 최소 1개는 판별 단서 1개 차이의 근접 감별로 구성한다.',
'',
'## 반드시 지킬 선지 규칙 (자동 게이트가 검사한다 — 위반 시 전량 탈락)',
'- 정답이 가장 길거나 가장 짧으면 안 된다. 길이 순위 2~4위에 두고,',
'  정답 길이 / 오답 평균 길이 = 0.8~1.2 범위를 맞춘다.',
'- 정답에만 수식어를 많이 붙이지 않는다(구성요소 최다 금지).',
'- "즉시", "반드시", "항상", "절대" 같은 부사를 정답에만 쓰지 않는다.',
'- "모두", "위 항목 없음", "적절하지 않은 것은" 금지. 부정형 문두 금지.',
'- stem을 가리고 선지만 봐도 무엇을 묻는지 알 수 있어야 한다(cover-the-options).',
'- 선지끼리 의미가 겹치거나 stem 정보로 이미 배제되는 선지를 넣지 않는다.',
'- 오답은 문두 단서가 명시적으로 배제하지 **않는** 근접 감별에서 고른다',
'  — 한눈에 배제되는 오답은 난이도를 떨어뜨린다.',
'',
'## 추론 깊이',
'- reasoning_hops ≥ 2: 단서 인지만으로 풀리면 안 되고, 최소 2단계 추론이 필요해야 한다.',
'  (예: 소견 → 병태생리 판단 → 그에 맞는 처치 선택)',
'- cognitive_level은 해석 또는 문제해결. 단순 암기 문항 금지.',
'',
'## evidence spec (문항을 쓰기 전에 먼저 정한다)',
'- answer_claim: 정답을 정당화하는 핵심 주장 1문장 — 온톨로지 팩의 내용으로 방어 가능해야 한다.',
'- distractor_claims: 오답 번호별로 "왜 틀렸는지"의 근거 주장 1문장.',
'  팩에 decision_cue(감별 결정 포인트)가 있으면 **그 문구를 근거로 인용**하라.',
'- 문항·해설은 이 spec을 벗어나는 주장을 새로 만들지 않는다.',
'',
'## 해설·근거',
'- explanation: 결정타 단서 → 기전 → 오답 감별 → 핵심 정리 순, 300자 이상.',
'  온톨로지 팩의 evidence에 harrison chapter/page가 있으면 explanation 끝에',
'  "근거: Harrison 22e Ch.NN p.MM" 형식으로 붙이고 harrison_chapter/page 필드에도 넣는다.',
'- choice_explanations: 정답은 why_correct, 오답 4개는 why_attractive에',
'  "어떤 오개념·유사소견 때문에 끌리는지"를 구체적으로 쓴다.',
'- common_high_stakes_problem: 흔하거나, 드물어도 놓치면 위중한 문제면 true.',
'',
'## self_check',
'22개 키를 스스로 점검해 boolean으로 채운다. 거짓 보고하지 말고,',
'만족하지 못했으면 **문항을 고쳐서** 만족시킨 뒤 true로 보고한다.',
'',
'## 출력',
'{batch_id:"t' + bi + '", items:[...]} — 개념마다 정확히 1문항, concept_id·difficulty_tier 입력 그대로.',
  ].join(NL)
}
phase('Generate')
const results = await pipeline(
  BATCHES.map((b, i) => ({ b, i })),
  (x) => agent(prompt(x.b, x.i), { label: 'gen:t' + String(x.i).padStart(2, '0'),
    phase: 'Generate', schema: SCHEMA, model: '__MODEL__', effort: '__EFFORT__' }),
)
const items = results.filter(Boolean).flatMap(r => r.items || [])
log('생성 문항 ' + items.length)
return { batches: BATCHES.length, total: items.length }
""".replace("__SC_PROPS__", sc_props).replace("__SC_REQ__", sc_req) \
   .replace("__CE_PROPS__", ce_props).replace("__MODEL__", model).replace("__EFFORT__", effort)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-batch", type=int, default=4)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--out", default="textgen_wf.js")
    ap.add_argument("--packs", default="text_grounding_packs.json")
    args = ap.parse_args()

    packs = json.loads((GEN / args.packs).read_text(encoding="utf-8"))
    # 티어는 개념 인덱스 라운드로빈으로 결정론 배정 — 모델이 고르지 않는다.
    rows = [{"concept_id": cid, "department": p.get("department", ""),
             "difficulty_tier": TIER_CYCLE[i % len(TIER_CYCLE)], "pack": p}
            for i, (cid, p) in enumerate(packs.items())]
    batches = [rows[i:i + args.per_batch] for i in range(0, len(rows), args.per_batch)]
    (SP / args.out).write_text(
        HEAD + json.dumps(batches, ensure_ascii=False) + build_tail(args.model, args.effort),
        encoding="utf-8")
    tiers = {t: sum(1 for r in rows if r["difficulty_tier"] == t) for t in ("하", "중", "상")}
    print(f"개념 {len(rows)} · 배치 {len(batches)} · 티어 {tiers} · model={args.model} → {SP/args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
