#!/usr/bin/env python3
"""문항별 Anki cloze 카드 생성 워크플로 생성기.

설계 근거: docs/Anki_Deck_Design_Principles_20260716.md 의 카드 10원칙을
프롬프트에 직접 내장한다(최소화·구체성·트리거·개별화·쌍방향성 등).

입력은 **문항의 해설·정답개념·온톨로지 태그**뿐이다. 원본 기출 텍스트는 관여하지 않는다.
카드 스키마는 기존 파이프라인과 동일: {text, extra, concept, system} + tags.
사용: python3 scripts/make_anki_wf.py --per-batch 6 --model opus
"""
import argparse
import json
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
SP = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/"
          "4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad")

HEAD = """export const meta = {
  name: 'item-anki-cards',
  description: '문항별 Anki cloze 카드 생성 (카드 10원칙 내장)',
  phases: [{ title: 'Cards' }],
}
const BATCHES = """


def build_tail(model: str, effort: str) -> str:
    return r"""
const CARD = {
  type: 'object', additionalProperties: false,
  properties: {
    text: { type: 'string' },
    extra: { type: 'string' },
    concept: { type: 'string' },
    system: { type: 'string' },
  },
  required: ['text', 'extra', 'concept', 'system'],
}
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    batch_id: { type: 'string' },
    rows: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          qid: { type: 'string' },
          cards: { type: 'array', items: CARD, minItems: 2, maxItems: 3 },
        },
        required: ['qid', 'cards'],
      },
    },
  },
  required: ['batch_id', 'rows'],
}
const NL = String.fromCharCode(10)
function prompt(b, bi) {
  return [
'너는 의대생용 Anki 카드 저자다. 아래 각 문항의 **핵심 학습점**을 cloze 카드로 만든다.',
'문항을 그대로 옮기지 말고, 그 문항이 가르치려는 사실만 뽑아 독립적으로 성립하는 카드로 만든다.',
'',
'## 문항 ' + b.length + '개 — 각 2~3장',
b.map((e, i) => (i + 1) + '. qid=' + e.qid + ' | 개념=' + e.concept + ' | 분과=' + e.system + NL +
  '   평가축: ' + e.axis + ' | 정답: ' + e.answer_text + NL +
  '   정답개념: ' + e.answer_concept + NL +
  '   결정단서: ' + (e.cues || []).join(' / ') + NL +
  '   해설: ' + e.explanation).join(NL),
'',
'## 카드 10원칙 (반드시 준수)',
'1. **Cloze 강제**: text에 {{c1::…}} 형식 빈칸을 최소 1개. 앞면-뒷면 나열식 금지.',
'2. **최소화**: 자명한 사실(“백혈구는 혈액세포이다”)은 카드로 만들지 않는다.',
'3. **구체성**: 답이 하나로 수렴해야 한다. “설명하시오”, O/X, “옳은 것은?” 금지.',
'4. **트리거**: 앞면 단서만으로 답 후보가 좁혀져야 한다. “이 질환은?” 같은 무단서 금지.',
'5. **최적화**: 불필요한 수식어 제거. 한 문장 40자 내외를 목표.',
'6. **개별화**: 서로 독립적으로 틀릴 수 있는 사실은 각각 다른 카드로 분리.',
'   (전해질 4가지를 한 카드에 나열하지 말 것)',
'7. **쌍방향성**: 시험에서 반대로도 묻는 사실이면 역방향 카드를 형제로 추가.',
'   (“t(9;22) → CML”과 “CML의 염색체 → t(9;22)”)',
'',
'## 필드',
'- text: cloze 문장. {{c1::…}} {{c2::…}} 사용. **HTML 태그·부등호(<, >) 쓰지 말 것**',
'  (부등호가 필요하면 “미만/초과”로 풀어 쓴다 — 렌더링이 깨진다).',
'- extra: 보조 설명 1~2문장(기전·감별 포인트). 없으면 빈 문자열이 아니라 짧게라도 채운다.',
'- concept: 이 카드가 다루는 개념명(한글).',
'- system: 분과명(주어진 값 그대로).',
'',
'## 출력',
'{batch_id:"a' + bi + '", rows:[{qid, cards:[...]}]} — 문항마다 정확히 1행, qid 그대로.',
  ].join(NL)
}
phase('Cards')
const results = await pipeline(
  BATCHES.map((b, i) => ({ b, i })),
  (x) => agent(prompt(x.b, x.i), { label: 'anki:a' + String(x.i).padStart(2, '0'),
    phase: 'Cards', schema: SCHEMA, model: '__MODEL__', effort: '__EFFORT__' }),
)
const rows = results.filter(Boolean).flatMap(r => r.rows || [])
log('카드 생성 문항 ' + rows.length)
return { items: rows.length, cards: rows.reduce((s, r) => s + (r.cards || []).length, 0) }
""".replace("__MODEL__", model).replace("__EFFORT__", effort)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-batch", type=int, default=6)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--out", default="anki_wf.js")
    args = ap.parse_args()

    rows = []
    for k in range(1, 5):
        p = GEN / f"set_{k}.json"
        if not p.exists():
            continue
        for it in json.loads(p.read_text(encoding="utf-8")):
            cm = it.get("cognitive_model") or {}
            ans = str(it.get("answer") or "")
            rows.append({
                "qid": f"AIGEN_{k}_{it['no']:03d}",
                "concept": str(it.get("concept") or ""),
                "system": str(it.get("subject") or ""),
                "axis": str(it.get("axis") or ""),
                "answer_text": str((it.get("choices") or {}).get(ans, ""))[:120],
                "answer_concept": str(cm.get("answer_concept") or "")[:120],
                "cues": [str(c)[:60] for c in (cm.get("decision_cues") or [])[:4]],
                "explanation": str(it.get("explanation") or "")[:900],
            })
    batches = [rows[i:i + args.per_batch] for i in range(0, len(rows), args.per_batch)]
    (SP / args.out).write_text(
        HEAD + json.dumps(batches, ensure_ascii=False) + build_tail(args.model, args.effort),
        encoding="utf-8")
    print(f"문항 {len(rows)} · 배치 {len(batches)} · model={args.model} → {SP/args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
