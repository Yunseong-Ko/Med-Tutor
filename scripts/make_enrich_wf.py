#!/usr/bin/env python3
"""게이트 통과 실패 원인(플랫폼 메타데이터 계약 미충족)을 채우는 enrich 워크플로 생성기.

플랫폼 계약(item_quality_check 하드룰 20종이 요구):
  - reasoning_hops(≥2), cognitive_level, cognitive_model.decision_cues/answer_concept
  - choice_explanations: 오답 4개 전부 why_attractive(오개념) + 정답 why_correct
  - self_check 22키 자기평가
  - 구조 결함(정답 최장/최단, 길이비 0.8~1.2 이탈)은 **의미 보존 재표현**으로 수정 허용
사용: python3 scripts/make_enrich_wf.py --pool img_items_v4.json --out enrich_v4_wf.js
"""
import argparse
import json
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
SP = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad")

HEAD = """export const meta = {
  name: 'item-metadata-enrich',
  description: '플랫폼 품질계약 메타데이터 보강(선지별 해설·추론단계·self-check) + 구조결함 수리',
  phases: [{ title: 'Enrich' }],
}
const BATCHES = """

TAIL = r"""
const OUT = {
  type: 'object', additionalProperties: false,
  properties: {
    idx: { type: 'integer' },
    reasoning_hops: { type: 'integer', minimum: 1, maximum: 5 },
    cognitive_level: { type: 'string', enum: ['암기', '해석', '문제해결'] },
    decision_cues: { type: 'array', items: { type: 'string' }, minItems: 2, maxItems: 6 },
    answer_concept: { type: 'string' },
    choice_explanations: {
      type: 'object', additionalProperties: false,
      properties: {
        '1': { type: 'object', additionalProperties: false, properties: { why_attractive: { type: 'string' }, why_correct: { type: 'string' } } },
        '2': { type: 'object', additionalProperties: false, properties: { why_attractive: { type: 'string' }, why_correct: { type: 'string' } } },
        '3': { type: 'object', additionalProperties: false, properties: { why_attractive: { type: 'string' }, why_correct: { type: 'string' } } },
        '4': { type: 'object', additionalProperties: false, properties: { why_attractive: { type: 'string' }, why_correct: { type: 'string' } } },
        '5': { type: 'object', additionalProperties: false, properties: { why_attractive: { type: 'string' }, why_correct: { type: 'string' } } },
      },
      required: ['1', '2', '3', '4', '5'],
    },
    choices_fix: {
      type: 'object', additionalProperties: false,
      properties: { '1': { type: 'string' }, '2': { type: 'string' }, '3': { type: 'string' }, '4': { type: 'string' }, '5': { type: 'string' } },
    },
    common_high_stakes: { type: 'boolean' },
    self_check_notes: { type: 'string' },
  },
  required: ['idx', 'reasoning_hops', 'cognitive_level', 'decision_cues', 'answer_concept', 'choice_explanations', 'common_high_stakes'],
}
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { batch_id: { type: 'string' }, rows: { type: 'array', items: OUT } },
  required: ['batch_id', 'rows'],
}
const NL = String.fromCharCode(10)

function itemBlock(it, i) {
  const ch = it.choices
  return [
    '### 문항 idx=' + it.idx + ' (정답 ' + it.answer + '번' + (it.flaws && it.flaws.length ? ' · 구조결함: ' + it.flaws.join(',') : '') + ')',
    '문두: ' + it.stem,
    '선지: 1)' + ch['1'] + ' 2)' + ch['2'] + ' 3)' + ch['3'] + ' 4)' + ch['4'] + ' 5)' + ch['5'],
    '진단개념: ' + it.dx + (it.distractor_pool && it.distractor_pool.length ? ' · 온톨로지 오답풀: ' + it.distractor_pool.join(', ') : ''),
  ].join(NL)
}

function prompt(b, bi) {
  return [
'너는 의사국가시험 문항 검토위원이다. 각 문항에 품질 메타데이터를 부여하고, 표시된 구조결함만 수리하라.',
'',
'## 문항 ' + b.length + '개',
b.map(itemBlock).join(NL + NL),
'',
'## 각 문항에 대해 산출',
'1. reasoning_hops: 정답까지 필요한 실제 추론 단계 수(자료해석→진단→행동선택이면 3). 인식만으로 풀리면 1로 정직하게.',
'2. cognitive_level: 암기/해석/문제해결 중 실제 수준.',
'3. decision_cues: 문두에서 정답을 결정하는 단서 2~6개(짧게).',
'4. answer_concept: 정답의 행동/판단 개념 한 줄.',
'5. choice_explanations: 5개 선지 전부 —',
'   정답 선지: why_correct(왜 정답인지 1~2문장).',
'   오답 선지: why_attractive(**학생이 왜 고르게 되는지 — 어떤 오개념/함정인지** 1~2문장). 4개 오답 전부 필수.',
'   온톨로지 오답풀이 주어진 문항은 그 감별 관계를 반영하라.',
'6. common_high_stakes: 이 문제가 "흔하거나, 놓치면 위중한" 임상문제인가(국시 출제기준). 정직하게.',
'7. choices_fix (구조결함 표시된 문항만): 정답이 최장/최단이거나 길이비 이탈이면, **의미·개념 완전 보존** 하에',
'   선지 표현만 다듬어 길이 균형을 맞춘 5개 선지 전체를 제출. 결함 없으면 생략.',
'',
'## 출력',
'{batch_id:"e' + bi + '", rows:[...]} — 문항마다 1행, idx 그대로.',
  ].join(NL)
}

phase('Enrich')
const results = await pipeline(
  BATCHES.map((b, i) => ({ b, i })),
  (x) => agent(prompt(x.b, x.i), { label: 'enrich:b' + String(x.i).padStart(2, '0'), phase: 'Enrich', schema: SCHEMA, model: 'fable', effort: 'medium' }),
)
const ok = results.filter(Boolean)
const rows = ok.flatMap(r => r.rows || [])
log('메타데이터 보강: ' + rows.length + '행')
return { count: rows.length }
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-batch", type=int, default=6)
    ap.add_argument("--only", help="처리할 idx 목록 JSON 파일 (미완료분 재시도용)")
    ap.add_argument("--model", default="fable", help="agent model (fable/opus/sonnet)")
    args = ap.parse_args()

    items = json.loads((GEN / args.pool).read_text(encoding="utf-8"))
    only = None
    if args.only:
        only = set(json.loads(Path(args.only).read_text(encoding="utf-8")))
    rows = []
    for i, it in enumerate(items):
        if only is not None and i not in only:
            continue
        q = it.get("item_quality") or {}
        flaws = [f for f in (q.get("flaws") or [])
                 if f in ("longest_is_key", "shortest_is_key", "key_length_rank",
                          "most_components_is_key", "urgency_adverb_only_in_key")]
        rows.append({
            "idx": i, "stem": it["stem"], "choices": it["choices"],
            "answer": it["answer"], "dx": it.get("dx") or it.get("concept", ""),
            "distractor_pool": it.get("distractor_sources") or [],
            "flaws": flaws,
        })
    batches = [rows[i:i + args.per_batch] for i in range(0, len(rows), args.per_batch)]
    tail = TAIL.replace("model: 'fable'", f"model: '{args.model}'")
    (SP / args.out).write_text(HEAD + json.dumps(batches, ensure_ascii=False) + tail,
                               encoding="utf-8")
    print(f"문항 {len(rows)} · 배치 {len(batches)} → {SP/args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
