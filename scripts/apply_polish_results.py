#!/usr/bin/env python3
"""해설 디벨롭 워크플로 결과 → 320문항 세트 적용.

- explanation·choice_explanations 교체(전문 반환 방식이라 그대로 대입)
- 근거 재지정: evidence_book/chapter → textbook_sources 교체, 낡은 harrison 근거 제거,
  entailment_verdict를 'rerouted'로 (✗ 배지 해제 — 이전 판정은 옛 근거에 대한 것)
- 안전핀: explanation이 원본의 60% 미만 길이로 줄면 적용 거부(내용 소실 방지)
"""
import argparse
import json
from collections import Counter
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
BOOK_TITLES_PATH = Path("data_private/curriculum/evidence_routing.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf-dir", required=True)
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
    polish = {str(r.get("qid")): r for r in rows if r.get("qid")}
    titles = {k: v["title"] for k, v in
              json.loads(BOOK_TITLES_PATH.read_text(encoding="utf-8"))["books"].items()}
    print(f"디벨롭 결과 {len(polish)}건")

    st = Counter()
    for k in range(1, 5):
        p = GEN / f"set_{k}.json"
        items = json.loads(p.read_text(encoding="utf-8"))
        for it in items:
            qid = f"AIGEN_{k}_{it['no']:03d}"
            r = polish.get(qid)
            if not r:
                st["결측"] += 1
                continue
            new_exp = str(r.get("explanation") or "").strip()
            old_exp = str(it.get("explanation") or "")
            if new_exp and len(new_exp) >= len(old_exp) * 0.6:
                if new_exp != old_exp:
                    st["해설수정"] += 1
                it["explanation"] = new_exp
            else:
                st["해설거부(축소)"] += 1
            ce = it.get("choice_explanations") or {}
            changed = False
            for n, txt in (r.get("choice_expl") or {}).items():
                txt = str(txt or "").strip()
                if not txt or n not in ce or not isinstance(ce[n], dict):
                    continue
                key = "why_correct" if str(it.get("answer")) == n else "why_attractive"
                if txt != str(ce[n].get(key) or ""):
                    ce[n][key] = txt
                    changed = True
            if changed:
                st["선지해설수정"] += 1
            eb, ec = r.get("evidence_book"), r.get("evidence_chapter")
            if eb and ec and eb in titles:
                it["textbook_sources"] = [{
                    "source_id": f"{eb}#{int(ec)}", "book_id": eb, "chapter": int(ec),
                    "entailment_status": "chapter_pointer",
                }]
                it.pop("harrison_sources", None)
                it["entailment_verdict"] = "rerouted"
                it.pop("entailment_unsupported_points", None)
                st["근거재지정"] += 1
        p.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(dict(st))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
