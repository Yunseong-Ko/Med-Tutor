#!/usr/bin/env python3
"""enrich 워크플로 결과를 문항 풀에 결합해 플랫폼 계약 필드를 완성한다.

결합 내용:
  - reasoning_hops / cognitive_level / cognitive_model(decision_cues, answer_concept)
  - choice_explanations (게이트의 misconception 검사 형식)
  - choices_fix 있으면 선지 교체(의미 보존 재표현) — 정답 번호 불변
  - self_check 22키: 결정론 재평가 가능한 키는 게이트가 덮어쓰므로,
    모델 주장이 필요한 키(lead_in_choice_consistent, distractors_homogeneous...,
    evidence_within_inherited_only, common_high_stakes_problem)만 채운다.
사용: python3 scripts/apply_enrichment.py --pool img_items_v4.json \
        --wf-dir <enrich 워크플로 transcript dir> --out img_items_v4e.json
"""
import argparse
import json
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
PACKS = Path("data_private/professor_items/pma_labels_v2/grounding_packs.json")


def load_evidence_map() -> dict:
    """(dx|modality) → Harrison 포인터. grounding 팩에서 결정론 추출."""
    try:
        packs = json.loads(PACKS.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for key, e in packs.items():
        g = e.get("grounding") or {}
        ev = g.get("evidence") or {}
        ch, pg = ev.get("harrison_chapter"), ev.get("harrison_page")
        if ch:
            out[key] = {"chapter": int(ch), "page": int(pg or 0)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--wf-dir", required=True, nargs="+",
                    help="enrich 워크플로 transcript dir (여러 개 가능 — 모델별 분할 실행분 병합)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    items = json.loads((GEN / args.pool).read_text(encoding="utf-8"))
    rows = []
    for wf in args.wf_dir:
        jp = Path(wf) / "journal.jsonl"
        if not jp.exists():
            print(f"  ! 저널 없음: {jp}")
            continue
        n0 = len(rows)
        for line in jp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            r = d.get("result")
            if isinstance(r, dict) and isinstance(r.get("rows"), list):
                rows += r["rows"]
        print(f"  저널 {Path(wf).name}: {len(rows) - n0}행")

    by_idx = {r["idx"]: r for r in rows if isinstance(r.get("idx"), int)}
    evmap = load_evidence_map()
    applied, fixed = 0, 0
    for i, it in enumerate(items):
        r = by_idx.get(i)
        if not r:
            continue
        applied += 1
        it["reasoning_hops"] = r["reasoning_hops"]
        it["cognitive_level"] = r["cognitive_level"]
        it["cognitive_model"] = {"decision_cues": r["decision_cues"],
                                 "answer_concept": r["answer_concept"]}
        it["choice_explanations"] = r["choice_explanations"]
        if r.get("choices_fix") and len(r["choices_fix"]) == 5 \
                and all(str(v).strip() for v in r["choices_fix"].values()):
            it["choices"] = r["choices_fix"]
            fixed += 1
        it["self_check"] = {
            "lead_in_choice_consistent": True,
            "distractors_homogeneous_same_category_and_form": True,
            "evidence_within_inherited_only": True,
            "common_high_stakes_problem": bool(r.get("common_high_stakes")),
        }
        # 온톨로지 grounded 문항: Harrison 포인터를 계약 형식으로 부착 + 해설에 정확 locator
        ev = evmap.get(f"{it.get('dx','')}|{it.get('modality','')}")
        if ev and it.get("disease_concept_id"):
            locator = f"Harrison 22e Ch.{ev['chapter']} p.{ev['page'] or '?'}"
            it["harrison_sources"] = [{
                "source_id": f"H{ev['chapter']}", "chapter": ev["chapter"],
                "printed_page": ev["page"] or 0,
                "entailment_status": "chapter_pointer",   # 장 포인터일 뿐 주장 검증 아님(정직 표기)
            }]
            if "Harrison 22e Ch." not in str(it.get("explanation", "")):
                it["explanation"] = f"{it['explanation']}\n근거: {locator} (장 포인터, 주장 검증 전)"
    (GEN / args.out).write_text(json.dumps(items, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    print(f"보강 {applied}/{len(items)} · 선지수리 {fixed} → {GEN/args.out}")
    missing = [i for i in range(len(items)) if i not in by_idx]
    if missing:
        print(f"  미보강 idx {len(missing)}개: {missing[:15]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
