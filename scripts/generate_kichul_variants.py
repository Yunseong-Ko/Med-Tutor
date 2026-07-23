"""기출 변형(모드 A) 생성 프롬프트/스키마 빌더.

검증된 기출 문항(부모)을 앵커로 PMA형 변형 문항을 만든다. 부모가 의학적으로
검증돼 있으므로 환각 리스크가 낮고, 부모의 concept_tags를 상속해 약점-타겟
출제(모드 C)로 자연 확장된다.

프라이버시: 부모 문항은 data_private 원문이므로 기본은 prompt-only(외부 전송 없음).
실제 생성은 승인된 제공자 경로(Claude Code 계정 in-session)로만 수행한다.

사용:
    python3 scripts/generate_kichul_variants.py <exam.json> --q 5 \
        --types numeric,distractor,vignette --provider prompt-only \
        --out data_private/course_exams/variants/PMA_..._Q005_variants.prompt.txt
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.generate_lecture_questions import GENERATION_SYSTEM_PROMPT
    from scripts.generation_grounding import append_grounding_context, build_generation_grounding
except ModuleNotFoundError:  # direct script execution
    from generate_lecture_questions import GENERATION_SYSTEM_PROMPT
    from generation_grounding import append_grounding_context, build_generation_grounding

VARIANT_TYPES = {
    "numeric": "수치 변형 — 나이·성별·검사수치 등 표면 정보만 바꾸고 개념·감별점·정답논리는 동일하게 유지.",
    "distractor": "선지 재구성 — 같은 문두, 오답 선지를 같은 감별축에서 새로 구성(정답 개념 동일).",
    "vignette": "증례 재작성 — 같은 진단/치료를 제시하는 새 임상 시나리오로 문두 전면 재작성.",
    "difficulty_up": "난이도 상향 — 결정적 단서를 줄이거나 유사 감별을 추가.",
    "difficulty_down": "난이도 하향 — 결정적 단서를 명시해 난이도를 낮춤.",
}

LABELING_RULES = """\
[라벨링·작성 규칙 — 운영 포맷 동일]
- 정답은 정확한 임상 사실로 1개만. 추정 금지, 메타문장 금지("정답이라서 맞다" 류 금지).
- 오답 선지 해설은 ① 개념 → ② 왜 헷갈리는지 → ③ 감별점 순으로 학습가치 있게.
- 한국어 + 영어 용어 병기.
- labels(course_name·major_category·topic·subtopic·assessment_domain·question_type·concept_tags)는 부모에서 상속하되 변형에 맞게 조정.
- key_info(important_clues·summary·core_explanation), answer_rationale, choice_explanations(선지별 rationale·is_correct), key_learning_points, anki_cards(cloze) 포함.
- 이미지 의존이면 media.has_image_or_data_reference=true + needs_review=true.
- 모든 변형: parent_question_id, generation_mode="kichul_variant", variant_type, evidence_tier="parent_verified", review_status="draft", needs_review=true.
"""

OUTPUT_SCHEMA_HINT = """\
[출력: 변형 문항 JSON 배열] 각 원소는 운영 questions[] 레코드 + 다음 필드:
  parent_question_id, generation_mode="kichul_variant", variant_type,
  evidence_refs:[{"citation":"기출 변형: <parent_id>"}], evidence_tier:"parent_verified",
  review_status:"draft", needs_review:true, gen_ready:false,
  item_type:"A", reveal_specialty:false, reasoning_hops:2,
  cognitive_model, choice_explanations(각 오답 misconception·why_attractive), self_check(22항목)
정답키(answer)는 변형의 임상적 사실에 따라 정확히 설정하고, choice_explanations의 is_correct와 일치시킬 것.
"""


def check_gitignore() -> None:
    try:
        r = subprocess.run(["git", "check-ignore", "data_private"], capture_output=True, text=True)
        if r.returncode != 0:
            print("경고: data_private가 git에 무시되지 않습니다. 진행 전 .gitignore 확인.", file=sys.stderr)
    except Exception:
        pass


def load_parent(exam_path: Path, qnum: int) -> tuple[dict[str, Any], dict[str, Any]]:
    data = json.loads(exam_path.read_text(encoding="utf-8"))
    exam = data.get("exam") or {}
    for q in data.get("questions") or []:
        if q.get("question_number") == qnum:
            return exam, q
    raise SystemExit(f"문항 {qnum}을(를) 찾을 수 없습니다: {exam_path}")


def parent_brief(q: dict[str, Any]) -> str:
    return json.dumps(
        {
            "question_id": q.get("question_id"),
            "stem": q.get("stem"),
            "choices": q.get("choices"),
            "answer": q.get("answer"),
            "labels": q.get("labels"),
            "key_info": q.get("key_info"),
            "answer_rationale": q.get("answer_rationale"),
            "choice_explanations": q.get("choice_explanations"),
        },
        ensure_ascii=False,
        indent=2,
    )


def build_prompt(
    exam: dict[str, Any],
    parent: dict[str, Any],
    types: list[str],
    n_each: int,
    *,
    reveal_specialty: bool = False,
    reasoning_hops: int = 2,
) -> str:
    type_lines = "\n".join(f"- {t}: {VARIANT_TYPES.get(t, t)}" for t in types)
    labels = parent.get("labels") if isinstance(parent.get("labels"), dict) else {}
    concept_id = parent.get("disease_concept_id") or labels.get("disease_concept_id")
    if isinstance(concept_id, list):
        concept_id = concept_id[0] if concept_id else ""
    grounding_topic = str(concept_id or labels.get("topic") or labels.get("subtopic") or "").strip()
    grounding = build_generation_grounding(grounding_topic)
    prompt = f"""당신은 PMA(임상의학종합평가) 문항 출제자입니다. 아래 '검증된 기출 부모 문항'을 앵커로
요청된 변형 유형별로 각 {n_each}개씩 변형 문항을 생성하세요.

[배포 시스템 프롬프트]
{GENERATION_SYSTEM_PROMPT}

[기본 생성 파라미터]
- item_type: A
- reveal_specialty: {str(bool(reveal_specialty)).lower()}
- reasoning_hops: {max(1, min(3, int(reasoning_hops)))}

[부모 문항 — 의학적으로 검증됨]
시험: {exam.get('exam_title') or exam.get('course_name')}
{parent_brief(parent)}

[요청 변형 유형]
{type_lines}

{LABELING_RULES}
{OUTPUT_SCHEMA_HINT}

변형은 부모의 핵심 개념·감별점을 보존하되 표면을 충분히 바꿔 단순 암기로 풀리지 않게 하세요.
부모와 정답 위치(번호)가 기계적으로 같아지지 않도록 선지 순서를 적절히 섞으세요.
"""
    return append_grounding_context(prompt, grounding)


def main() -> int:
    ap = argparse.ArgumentParser(description="기출 변형(모드 A) 생성 프롬프트 빌더")
    ap.add_argument("exam_json")
    ap.add_argument("--q", type=int, required=True, help="부모 문항 번호")
    ap.add_argument("--types", default="numeric,distractor,vignette")
    ap.add_argument("--n-each", type=int, default=1)
    ap.add_argument("--provider", default="prompt-only", choices=["prompt-only"],
                    help="기본 prompt-only(외부 전송 없음). 실제 생성은 in-session 승인 제공자로 수행.")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    check_gitignore()
    types = [t.strip() for t in a.types.split(",") if t.strip()]
    bad = [t for t in types if t not in VARIANT_TYPES]
    if bad:
        raise SystemExit(f"알 수 없는 변형 유형: {bad}. 가능: {list(VARIANT_TYPES)}")

    exam, parent = load_parent(Path(a.exam_json), a.q)
    prompt = build_prompt(exam, parent, types, a.n_each)

    out = Path(a.out) if a.out else Path("data_private/course_exams/variants") / f"{parent.get('question_id','parent')}_variants.prompt.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")
    print(json.dumps({
        "mode": "prompt_only",
        "parent": parent.get("question_id"),
        "variant_types": types,
        "n_each": a.n_each,
        "prompt_file": str(out),
        "next": "이 프롬프트를 승인된 제공자(Claude Code 계정)로 생성 → 검토 큐(needs_review=true) → 승인 → cbt_docx_export",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
