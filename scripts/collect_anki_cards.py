#!/usr/bin/env python3
"""Anki 워크플로 저널 → 문항별 카드 수집 + 결정론 검증.

검증(로컬):
  - cloze 구문 {{cN::…}} 존재 — 없으면 인출 강제가 안 되므로 폐기
  - 부등호/HTML 잔존 검사 (과거 '{{c1::<80}}fL'이 태그로 파싱돼 깨진 전례)
  - 자명·다답형 휴리스틱 플래그(설계원칙 3·6원칙)
  - 문항당 카드 수, 중복 text
출력: generated/anki_cards.json  {qid: [ {text, extra, concept, system, tags} ]}
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
CLOZE = re.compile(r"\{\{c\d+::.+?\}\}")
ANGLE = re.compile(r"<[^>]{0,40}>")
VAGUE = re.compile(r"설명하시오|무엇인가\?$|옳은 것은|맞는 것은|O/X|참/거짓")
LISTY = re.compile(r"(,\s*){3,}|[①-⑤]|\d\)\s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf-dir", required=True, nargs="+")
    ap.add_argument("--out", default="anki_cards.json")
    args = ap.parse_args()

    rows = []
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
            if isinstance(r, dict) and isinstance(r.get("rows"), list):
                rows += r["rows"]

    # 문항 메타(태그·개념 보완용)
    meta = {}
    for k in range(1, 5):
        p = GEN / f"set_{k}.json"
        if p.exists():
            for it in json.loads(p.read_text(encoding="utf-8")):
                meta[f"AIGEN_{k}_{it['no']:03d}"] = it

    out, st, seen_text = {}, Counter(), set()
    for row in rows:
        qid = str(row.get("qid") or "")
        m = meta.get(qid) or {}
        kept = []
        for c in row.get("cards") or []:
            st["raw"] += 1
            text = re.sub(r"\s+", " ", str(c.get("text") or "")).strip()
            if not CLOZE.search(text):
                st["drop:cloze없음"] += 1
                continue
            if ANGLE.search(text) or ANGLE.search(str(c.get("extra") or "")):
                st["drop:부등호/태그"] += 1
                continue
            nk = re.sub(r"\s+", "", text)
            if nk in seen_text:
                st["drop:중복"] += 1
                continue
            seen_text.add(nk)
            flags = []
            if VAGUE.search(text):
                flags.append("모호형")
            if LISTY.search(text):
                flags.append("나열형")
            if flags:
                st["flag:" + "/".join(flags)] += 1
            kept.append({
                "text": text,
                "extra": re.sub(r"\s+", " ", str(c.get("extra") or "")).strip(),
                "concept": str(c.get("concept") or m.get("concept") or ""),
                "system": str(c.get("system") or m.get("subject") or ""),
                "tags": [t for t in (
                    f"AIGEN::{m.get('subject','')}".replace(" ", "_"),
                    f"axis::{m.get('axis','')}",
                    str(m.get("disease_concept_id") or ""),
                ) if t and not t.endswith("::")],
                "source_qid": qid,
                "needs_review": bool(flags),
                "quality_flags": flags,
            })
            st["kept"] += 1
        if kept:
            out[qid] = kept

    (GEN / args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    per = Counter(len(v) for v in out.values())
    print(f"문항 {len(out)}/320 · 카드 {st['raw']} → 채택 {st['kept']}")
    print("  폐기:", {k[5:]: v for k, v in sorted(st.items()) if k.startswith("drop:")})
    print("  검토플래그:", {k[5:]: v for k, v in sorted(st.items()) if k.startswith("flag:")})
    print(f"  문항당 카드 수 분포: {dict(sorted(per.items()))}")
    print(f"[출력] {GEN/args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
