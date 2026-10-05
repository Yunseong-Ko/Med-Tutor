#!/usr/bin/env python3
"""텍스트 문항 생성 워크플로 저널 → 문항 풀 + 계약 필드 정규화.

골든 스키마 생성물은 게이트 계약을 이미 갖고 있으므로, 여기서는
게이트가 읽는 필드 이름으로 옮겨 담고 결정론 수리만 한다:
  - harrison_chapter/page → harrison_sources[{source_id, chapter, printed_page}]
  - explanation 내 Harrison locator 보정
  - lead-in 질문 종결 확인
출력: generated/<out>.json
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
AXIS_LEADIN = {"진단": "가장 가능성 있는 진단은?",
               "검사": "진단을 위하여 다음에 시행할 검사는?",
               "치료": "가장 적절한 치료는?"}
LEADIN_TAIL = re.compile(r"\?\s*$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf-dir", required=True, nargs="+")
    ap.add_argument("--out", default="text_items.json")
    args = ap.parse_args()

    # 확장 개념의 교과서 근거(다권 체계) — harrison이 없는 개념에 부착
    exp_p = Path("data_private/curriculum/pnu_expansion_concepts.json")
    routing_p = Path("data_private/curriculum/evidence_routing.json")
    expansion, book_titles = {}, {}
    if exp_p.exists():
        expansion = json.loads(exp_p.read_text(encoding="utf-8"))["concepts"]
    if routing_p.exists():
        book_titles = {k: v["title"] for k, v in
                       json.loads(routing_p.read_text(encoding="utf-8"))["books"].items()}

    raw, batches = [], 0
    for wf in args.wf_dir:
        jp = Path(wf) / "journal.jsonl"
        if not jp.exists():
            print(f"  ! 저널 없음: {jp}")
            continue
        for line in jp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            r = d.get("result")
            if isinstance(r, dict) and isinstance(r.get("items"), list):
                batches += 1
                raw += r["items"]

    st, keep, seen = Counter(), [], set()
    for it in raw:
        st["raw"] += 1
        ch = it.get("choices") or {}
        if sorted(ch) != ["1", "2", "3", "4", "5"] or any(not str(ch[k]).strip() for k in ch):
            st["drop:선지불완전"] += 1
            continue
        if not isinstance(it.get("answer"), int) or not 1 <= it["answer"] <= 5:
            st["drop:정답범위"] += 1
            continue
        stem = re.sub(r"\s+", " ", str(it.get("stem", ""))).strip()
        if len(stem) < 60:
            st["drop:문두짧음"] += 1
            continue
        if not LEADIN_TAIL.search(stem):
            stem = f"{stem} {AXIS_LEADIN.get(it.get('axis',''), '가장 적절한 것은?')}"
            st["fix:leadin"] += 1
        key = re.sub(r"\s+", "", stem)
        if key in seen:
            st["drop:문두중복"] += 1
            continue
        seen.add(key)

        it["stem"] = stem
        it["concept"] = it.get("concept_id", "")
        it["disease_concept_id"] = it.get("concept_id", "")
        it["subject"] = it.get("department", "")
        it["topic"] = it.get("concept_id", "")
        it.setdefault("lab_box", "")
        # Harrison 포인터를 게이트가 읽는 계약 형식으로
        chn, pg = it.pop("harrison_chapter", None), it.pop("harrison_page", None)
        if chn:
            it["harrison_sources"] = [{
                "source_id": f"H{int(chn)}", "chapter": int(chn),
                "printed_page": int(pg or 0), "entailment_status": "chapter_pointer",
            }]
            loc = f"Harrison 22e Ch.{int(chn)} p.{int(pg or 0) or '?'}"
            if "Harrison 22e Ch." not in str(it.get("explanation", "")):
                it["explanation"] = f"{it['explanation']}\n근거: {loc} (장 포인터, 주장 검증 전)"
                st["fix:locator"] += 1
        # 확장 개념: 과별 교과서 장 포인터를 계약 형식으로 부착
        if not it.get("harrison_sources"):
            e = expansion.get(str(it.get("concept_id") or ""))
            ev = (e or {}).get("evidence") or {}
            if ev.get("book_id") and ev.get("chapter"):
                bid, chn = ev["book_id"], int(ev["chapter"])
                it["textbook_sources"] = [{
                    "source_id": f"{bid}#{chn}", "book_id": bid, "chapter": chn,
                    "entailment_status": "chapter_pointer",
                }]
                title = book_titles.get(bid, bid)
                if "Ch." not in str(it.get("explanation", ""))[-120:]:
                    it["explanation"] = (f"{it['explanation']}\n근거: {title} "
                                         f"Ch.{chn} (장 포인터, 주장 검증 전)")
                    st["fix:textbook_locator"] += 1

        # rule 18이 읽는 키는 self_check 안에 있어야 한다
        sc = it.get("self_check") if isinstance(it.get("self_check"), dict) else {}
        sc["common_high_stakes_problem"] = bool(it.get("common_high_stakes_problem"))
        it["self_check"] = sc
        it["source"] = "ontology_text_item"
        keep.append(it)
        st["kept"] += 1

    (GEN / args.out).write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    ans = Counter(it["answer"] for it in keep)
    longest = sum(1 for it in keep
                  if max(it["choices"], key=lambda k: len(it["choices"][k])) == str(it["answer"]))
    print(f"배치 {batches} · 문항 {st['raw']} → 채택 {st['kept']}")
    print("  처리:", {k: v for k, v in sorted(st.items()) if ":" in k})
    print(f"  축: {dict(Counter(it.get('axis') for it in keep))}")
    print(f"  분과: {len(set(it.get('subject') for it in keep))}종 · 고유개념 {len({it['concept'] for it in keep})}")
    print(f"  정답 분포: {dict(sorted(ans.items()))} · 정답=최장선지 "
          f"{longest}/{len(keep)} ({longest*100//max(1,len(keep))}%)")
    print(f"[출력] {GEN/args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
