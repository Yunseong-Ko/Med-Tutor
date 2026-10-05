#!/usr/bin/env python3
"""S2 — 강의 섹션을 concept_registry(598)에 앵커. 강의가 다루는 disease_concept_id 식별.

각 강의의 제목+섹션제목+본문을 registry alias와 대조해 개념별 히트수 집계 → 랭킹.
'개념별 통합 카드' 단위 결정을 위해, 강의가 커버하는 개념 목록을 뽑는다.
출력: data_private/lectures/<lecture_id>/ontology_anchor.json
"""

import json
import re
import glob
import unicodedata
from pathlib import Path

REG = json.loads(Path("data_private/concept_registry.json").read_text(encoding="utf-8"))["concepts"]
DISEASE_NODES = {"disorder", "neoplasm", "disease", "syndrome", "infection"}


def norm(s):
    return unicodedata.normalize("NFC", re.sub(r"\s+", "", str(s or ""))).lower()


ALIAS_INDEX = []  # (matcher, cid, alias, is_ko)  matcher: 한글=normed substring, 영문=compiled \b regex
for cid, c in REG.items():
    if (c.get("node_type") or "") not in DISEASE_NODES:
        continue
    for a in [cid.replace("_", " ")] + list(c.get("aliases") or []):
        is_ko = bool(re.search(r"[가-힣]", a))
        if is_ko:
            na = norm(a)
            if len(na) >= 3:
                ALIAS_INDEX.append(("ko", na, cid, a, len(na)))
        else:
            # 영문: 5자 이상 단어경계 매칭(짧은 substring 오탐 방지)
            aw = a.strip().lower()
            if len(aw) >= 5:
                ALIAS_INDEX.append(("en", re.compile(r"\b" + re.escape(aw) + r"\b"), cid, a, len(aw)))


def anchor(rec):
    ko_title = norm(rec.get("source_name")) + "".join(norm(s.get("title")) for s in rec.get("sections", []))
    ko_body = "".join(norm(s.get("text")) for s in rec.get("sections", []))
    en_title = (unicodedata.normalize("NFC", str(rec.get("source_name") or "")) + " "
                + " ".join(str(s.get("title") or "") for s in rec.get("sections", []))).lower()
    en_body = " ".join(str(s.get("text") or "") for s in rec.get("sections", [])).lower()
    hits = {}
    for kind, matcher, cid, alias, ln in ALIAS_INDEX:
        if kind == "ko":
            t, b = ko_title.count(matcher), ko_body.count(matcher)
        else:
            t, b = len(matcher.findall(en_title)), len(matcher.findall(en_body))
        score = t * 3 + b
        if score:
            prev = hits.get(cid, (0, ""))
            hits[cid] = (prev[0] + score, alias if len(alias) > len(prev[1]) else prev[1])
    ranked = sorted(hits.items(), key=lambda kv: -kv[1][0])
    concepts = []
    for cid, (score, alias) in ranked:
        c = REG[cid]
        ev = (c.get("evidence") or {}).get("harrison")
        ko = next((a for a in (c.get("aliases") or []) if re.search(r"[가-힣]", a)), cid.replace("_", " "))
        concepts.append({
            "disease_concept_id": cid, "label": ko, "score": score, "matched_alias": alias,
            "harrison": ev,
            "differentials": [e.get("id") for e in ((c.get("edges") or {}).get("differential_of") or []) if e.get("id")][:6],
            "treated_with": [e.get("id") for e in ((c.get("edges") or {}).get("treated_with") or []) if e.get("id")][:5],
        })
    return concepts


def main():
    for f in sorted(glob.glob("data_private/lectures/*/sections.json")):
        rec = json.loads(Path(f).read_text(encoding="utf-8"))
        concepts = anchor(rec)
        primary = [c for c in concepts if c["score"] >= 3][:8]
        out = {"lecture_id": rec["lecture_id"], "source_name": rec["source_name"],
               "primary_concepts": primary, "all_hits": len(concepts), "needs_review": True}
        Path(f).with_name("ontology_anchor.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"● {rec['source_name'][:40]}")
        for c in primary:
            h = c["harrison"]
            print(f"   {c['disease_concept_id']:32s} score={c['score']:3d}  Harrison={h.get('chapter') if h else '-'}  감별={c['differentials'][:3]}")


if __name__ == "__main__":
    main()
