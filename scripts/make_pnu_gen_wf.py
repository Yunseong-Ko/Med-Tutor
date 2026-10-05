#!/usr/bin/env python3
"""PNU PMA 공식 체계 기반 문항 생성 워크플로 생성기.

골든 스키마(게이트 계약 내장)에 학교 체계를 얹는다:
  - 차수·출제과 선택 → dept_totals에서 쿼터 → 그 과의 CP 메뉴에 분배
    (CP행에 교실 기입값이 있으면 그대로, 없으면 개념 풀 크기 비례)
  - 각 문항은 CP의 **구체적성과**(평가목표 성과문)를 명시적 평가 목표로 받는다
  - 근거 인용은 evidence_routing의 과별 1차 교과서 표기를 따른다
사용: python3 scripts/make_pnu_gen_wf.py --round 1cha --dept 감염내과 [--model opus]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_text_gen_wf import HEAD, TIER_CYCLE, build_tail  # 골든 스키마·티어 사이클 재사용
from build_image_item_grounding import condense
from generation_grounding import build_generation_grounding

GEN = Path("data_private/professor_items/generated")
CUR = Path("data_private/curriculum")
SP = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/"
          "4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad")


def allocate(dept_rows: list, total: int, pools: dict) -> list:
    """과 쿼터를 CP들에 분배. 교실 기입값 우선, 잔여는 개념 풀 크기 비례."""
    plan = []
    fixed = sum(r["counts_round"] for r in dept_rows if r["counts_round"])
    rest = max(0, total - fixed)
    flex = [r for r in dept_rows if not r["counts_round"]
            and pools.get(str(r["cp_no"]), {}).get("concepts")]
    weight = sum(len(pools[str(r["cp_no"])]["concepts"]) for r in flex) or 1
    for r in dept_rows:
        n = r["counts_round"]
        if not n and r in flex:
            n = round(rest * len(pools[str(r["cp_no"])]["concepts"]) / weight)
        if n:
            plan.append({**r, "n_items": n})
    # 반올림 오차 보정
    diff = total - sum(p["n_items"] for p in plan)
    for p in sorted(plan, key=lambda x: -x["n_items"]):
        if diff == 0:
            break
        p["n_items"] += 1 if diff > 0 else -1
        diff += -1 if diff > 0 else 1
    return [p for p in plan if p["n_items"] > 0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", default="1cha", choices=["1cha", "2cha", "3cha", "4cha", "5cha"])
    ap.add_argument("--dept", required=True)
    ap.add_argument("--per-batch", type=int, default=3)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    bp = json.loads((CUR / "pnu_pma_blueprint.json").read_text(encoding="utf-8"))
    pools = json.loads((CUR / "pnu_cp_concept_pools.json").read_text(encoding="utf-8"))["pools"]
    routing = json.loads((CUR / "evidence_routing.json").read_text(encoding="utf-8"))

    total = (bp.get("dept_totals") or {}).get(args.dept, {}).get(args.round, 0)
    if not total:
        print(f"! {args.dept}의 {args.round} 쿼터가 0입니다")
        return 1
    dept_rows = [{"cp_no": q["cp_no"], "cp_name": q["cp_name"],
                  "counts_round": q["counts"].get(args.round, 0)}
                 for q in bp["quota"] if q["dept"] == args.dept]
    plan = allocate(dept_rows, total, pools)
    books = [routing["books"][b]["title"] for b in routing["routes"].get(args.dept, [])]

    exp_p = CUR / "pnu_expansion_concepts.json"
    expansion = (json.loads(exp_p.read_text(encoding="utf-8"))["concepts"]
                 if exp_p.exists() else {})
    # 아이디어⑤: 감별 결정 포인트 오버레이 (concept_id → {differential: cue})
    cue_p = CUR / "differential_edge_cues.json"
    diff_cues = (json.loads(cue_p.read_text(encoding="utf-8"))
                 if cue_p.exists() else {})
    book_titles = {b: v["title"] for b, v in routing["books"].items()}

    rows = []
    pack_cache = {}


    def inject_cues(cid: str, out: dict) -> dict:
        """아이디어⑤: 감별 결정 포인트를 distractor_pool에 부착 (모든 팩 경로 공용)."""
        cues = diff_cues.get(cid) or {}
        if not cues:
            return out
        dp = out.get("distractor_pool") or []
        for d in dp:
            cue = cues.get(str(d.get("label") or ""))
            if cue:
                d["decision_cue"] = cue
        for label, cue in cues.items():
            if not any(str(d.get("label")) == label for d in dp):
                dp.append({"label": label, "why": "differential", "decision_cue": cue})
        out["distractor_pool"] = dp[:8]
        return out

    def expansion_pack(cid: str) -> dict | None:
        """확장 개념 팩 — differential_of가 오답 풀, 근거는 라우팅된 교과서 장."""
        e = expansion.get(cid)
        if not e:
            return None
        ev = e.get("evidence") or {}
        return {
            "disease_concept_id": cid,
            "label": e.get("label_kr") or cid,
            "aliases": (e.get("aliases") or [])[:6],
            "assessment_domains": e.get("assessment_domains") or [],
            "cognitive_model": {"key_cues": (e.get("edges") or {}).get("presents_with", [])},
            "clinical_axes": {
                "tests": (e.get("edges") or {}).get("diagnosed_by", []),
                "first_line": (e.get("edges") or {}).get("treated_with", []),
            },
            "distractor_pool": [{"label": d, "why": "differential"}
                                for d in (e.get("edges") or {}).get("differential_of", [])],
            "evidence": ({"book": book_titles.get(ev.get("book_id"), ev.get("book_id")),
                          "chapter": ev.get("chapter")} if ev else {}),
            "needs_review": True,
        }

    def full_pack(cid: str, fallback_label: str) -> dict:
        """개념별 전체 grounding 팩(감별·오답풀·근거 포함). 실패 시 최소 팩."""
        if cid in pack_cache:
            return pack_cache[cid]
        ep = expansion_pack(cid)
        if ep:
            ep = inject_cues(cid, ep)
            pack_cache[cid] = ep
            return ep
        try:
            g = build_generation_grounding(topic=cid)
            pk = (g or {}).get("pack") or {}
            out = condense(pk) if pk.get("disease_concept_id") else None
        except Exception:
            out = None
        if not out:
            out = {"disease_concept_id": cid, "label": fallback_label}
        out = inject_cues(cid, out)
        pack_cache[cid] = out
        return out

    for p in plan:
        pool = pools.get(str(p["cp_no"])) or {}
        concepts = pool.get("concepts") or []
        if not concepts:
            print(f"  ! CP{p['cp_no']} {p['cp_name']}: 개념 풀 비어 있음 — 건너뜀 ({p['n_items']}문항 미배정)")
            continue
        for k in range(p["n_items"]):
            c = concepts[k % len(concepts)]
            rows.append({
                "concept_id": c["concept_id"],
                "department": args.dept,
                # 티어는 전체 생성행 인덱스 라운드로빈으로 결정론 배정(30/50/20)
                "difficulty_tier": TIER_CYCLE[len(rows) % len(TIER_CYCLE)],
                "cp_no": p["cp_no"], "cp_name": p["cp_name"],
                "outcome": (pool.get("specific_outcomes") or pool.get("core_outcomes") or "")[:400],
                "textbook": books[0] if books else "Harrison's Principles of Internal Medicine 22e",
                "pack": full_pack(c["concept_id"], c["term"]),
            })
    print(f"{args.dept} {args.round}: 쿼터 {total} · 계획 {sum(p['n_items'] for p in plan)} · 생성행 {len(rows)}")
    print("  CP 분배:", {f"CP{p['cp_no']}({p['cp_name'][:8]})": p["n_items"] for p in plan})

    batches = [rows[i:i + args.per_batch] for i in range(0, len(rows), args.per_batch)]
    tail = build_tail(args.model, args.effort)
    # 안전 분류기가 큰 출력 스키마를 차단한다("schema too large to classify").
    # self_check 22키 중 18개는 게이트가 결정론으로 재평가하므로 스키마에서 제거하고,
    # 모델 주장이 실제로 쓰이는 4개만 남긴다(게이트 evaluate_self_check가 나머지를 덮어씀).
    import re as _re
    small_sc = """const SELF_CHECK = {
  type: 'object', additionalProperties: false,
  properties: {
    lead_in_choice_consistent: { type: 'boolean' },
    distractors_homogeneous_same_category_and_form: { type: 'boolean' },
    evidence_within_inherited_only: { type: 'boolean' },
    cognitive_level_label_matches_actual: { type: 'boolean' },
  },
  required: ['lead_in_choice_consistent', 'distractors_homogeneous_same_category_and_form',
             'evidence_within_inherited_only', 'cognitive_level_label_matches_actual'],
}"""
    tail = _re.sub(r"const SELF_CHECK = \{.*?\n\}", small_sc, tail, count=1, flags=_re.S)
    tail = tail.replace(
        "'22개 키를 스스로 점검해 boolean으로 채운다. 거짓 보고하지 말고,',\n"
        "'만족하지 못했으면 **문항을 고쳐서** 만족시킨 뒤 true로 보고한다.',",
        "'4개 키를 정직하게 점검한다. 만족 못 했으면 **문항을 고쳐서** 만족시킨 뒤 true로 보고한다.',")
    # 출력 스키마에 CP 필드 추가 — 프롬프트에만 넣으면 산출물에서 유실된다
    tail = tail.replace(
        "    concept_id: { type: 'string' },",
        "    concept_id: { type: 'string' },\n"
        "    cp_no: { type: 'integer' },\n"
        "    cp_name: { type: 'string' },")
    tail = tail.replace(
        "required: ['concept_id', 'department',",
        "required: ['concept_id', 'cp_no', 'cp_name', 'department',")
    tail = tail.replace(
        "items:[...]} — 개념마다 정확히 1문항, concept_id·difficulty_tier 입력 그대로.",
        "items:[...]} — 개념마다 정확히 1문항, concept_id·difficulty_tier·cp_no·cp_name 입력 그대로.")
    # 골든 프롬프트에 학교 맥락 주입: CP·성과문·근거 교과서
    tail = tail.replace(
        "'## 개념 ' + b.length + '개 — 각 개념당 문항 1개',",
        "'## 개념 ' + b.length + '개 — 각 개념당 문항 1개 (부산의대 PMA CP 체계)',")
    tail = tail.replace(
        "b.map((e, i) => (i + 1) + '. concept_id=' + e.concept_id + ' | 분과=' + e.department\n"
        "  + ' | 난이도=' + e.difficulty_tier + NL +\n"
        "  '   온톨로지: ' + JSON.stringify(e.pack)).join(NL),",
        "b.map((e, i) => (i + 1) + '. concept_id=' + e.concept_id + ' | 출제과=' + e.department\n"
        "  + ' | CP' + e.cp_no + ' ' + e.cp_name + ' | 난이도=' + e.difficulty_tier + NL\n"
        "  + '   평가목표(구체적성과): ' + e.outcome + NL\n"
        "  + '   근거 교과서: ' + e.textbook + NL\n"
        "  + '   온톨로지: ' + JSON.stringify(e.pack)).join(NL),")
    # 티어 주입이 유실되면 단서 예산 규칙이 죽는다 — 문자열 치환 어긋남을 즉시 잡는다
    assert "e.difficulty_tier" in tail, "골든 프롬프트 난이도 티어 주입 실패 — make_text_gen_wf.py 변경 확인"
    tail = tail.replace(
        "'## 해설·근거',",
        "'## 해설·근거',\n"
        "'- 이 문항은 위 CP 평가목표의 성과문을 검증해야 한다 — 성과문 밖의 지엽 지식을 묻지 않는다.',\n"
        "'- 근거 인용은 지정된 근거 교과서 이름으로 한다 (예: \"근거: \" + '\n"
        "  + '\"Sabiston 21e 해당 장\").',")
    out = args.out or f"pnu_{args.dept}_{args.round}_wf.js"
    (SP / out).write_text(HEAD + json.dumps(batches, ensure_ascii=False) + tail, encoding="utf-8")
    print(f"[워크플로] {SP/out}  (배치 {len(batches)} · model={args.model})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
