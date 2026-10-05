#!/usr/bin/env python3
"""entailment 검증 워크플로 판정 → 320문항 세트에 적용.

적용 내용:
  - harrison_sources.entailment_status: chapter_pointer → page_verified / partially_supported / unsupported
  - best_page가 있으면 printed_page를 그 페이지로 정밀화(원래 값은 cited_page_original에 보존)
  - explanation_fix / choice_expl_fixes 반영 (의학적 오류 교정만 — 워크플로 프롬프트 원칙)
  - 문항에 entailment_verdict 필드 기록(해설집·검수 화면 표시용)
사용: python3 scripts/apply_entailment_verdicts.py --wf-dir <transcript dir>
"""
import argparse
import json
from collections import Counter
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
STATUS = {"fully": "page_verified", "partially": "partially_supported", "not": "unsupported"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = []
    for line in (Path(args.wf_dir) / "journal.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        r = d.get("result")
        if isinstance(r, dict) and isinstance(r.get("rows"), list):
            rows += r["rows"]
    verdicts = {str(r.get("qid")): r for r in rows if r.get("qid")}
    print(f"판정 {len(verdicts)}건 수신")

    st = Counter()
    for k in range(1, 5):
        p = GEN / f"set_{k}.json"
        items = json.loads(p.read_text(encoding="utf-8"))
        for it in items:
            qid = f"AIGEN_{k}_{it['no']:03d}"
            v = verdicts.get(qid)
            if not v:
                continue
            st[v["verdict"]] += 1
            it["entailment_verdict"] = v["verdict"]
            if v.get("unsupported_points"):
                it["entailment_unsupported_points"] = v["unsupported_points"][:4]
            hs = it.get("harrison_sources") or []
            if hs:
                hs[0]["entailment_status"] = STATUS[v["verdict"]]
                bp = v.get("best_page")
                if isinstance(bp, int) and bp > 0 and bp != hs[0].get("printed_page"):
                    hs[0]["cited_page_original"] = hs[0].get("printed_page")
                    hs[0]["printed_page"] = bp
                    st["page_refined"] += 1
            fix = str(v.get("explanation_fix") or "").strip()
            if fix and len(fix) >= 150:
                it["explanation_before_fix"] = it.get("explanation")
                it["explanation"] = fix
                st["explanation_fixed"] += 1
            for n, t in (v.get("choice_expl_fixes") or {}).items():
                t = str(t or "").strip()
                ce = it.get("choice_explanations") or {}
                if t and n in ce and isinstance(ce[n], dict):
                    key = "why_correct" if str(it.get("answer")) == n else "why_attractive"
                    ce[n][key] = t
                    st["choice_expl_fixed"] += 1
        if not args.dry_run:
            p.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"판정 분포: fully {st['fully']} · partially {st['partially']} · not {st['not']}")
    print(f"교정: 해설 {st['explanation_fixed']} · 선지해설 {st['choice_expl_fixed']} · 페이지 정밀화 {st['page_refined']}")
    if args.dry_run:
        print("(dry-run — 미기록)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
