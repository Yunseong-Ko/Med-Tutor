#!/usr/bin/env python3
"""Korean-topic disease-id recovery — Step 3 (the biggest coverage lever).

The deterministic English concept_tags join only reaches ~19.5% because 81% of items
carry a Korean disease name in topic/subtopic that the English key never matches.

This script does the ZERO-RISK part deterministically:
  1. Build a registry index (id, node_type, harrison English title, aliases) for the 275 seeds.
  2. Recover disease_concept_id where a registry node's KOREAN alias (Hangul, len>=3) or its
     English id/title tokens appear in the item's topic/subtopic.
  3. Emit the still-unmatched work-list for the LLM semantic-recovery batch.

No fabrication: only assigns an id that is a real registry key. Everything stays in data_private/.
Outputs:
  data_private/curriculum/registry_index.json      (for the LLM batch to match against)
  data_private/curriculum/recovery_deterministic.json  (items recovered here)
  data_private/curriculum/recovery_worklist.json   (still-unmatched -> LLM batch)
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
REGISTRY = DP / "concept_registry.json"
RELABELED = DP / "embedding" / "qbank_relabeled.json"
QBANK = DP / "embedding" / "consolidated_qbank.json"
CUR = DP / "curriculum"

OUT_INDEX = CUR / "registry_index.json"
OUT_DET = CUR / "recovery_deterministic.json"
OUT_WORK = CUR / "recovery_worklist.json"

HANGUL = re.compile(r"[가-힣]")


def norm_ko(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def norm_en(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def build_index(reg: dict) -> list:
    idx = []
    for cid, c in reg["concepts"].items():
        h = (c.get("evidence") or {}).get("harrison") or {}
        idx.append({
            "id": cid,
            "node_type": c.get("node_type"),
            "title": h.get("title"),                     # English disease title (may be None for expansion)
            "aliases": c.get("aliases", []),
            "source": c.get("source"),
        })
    return idx


def main() -> None:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    index = build_index(reg)
    CUR.mkdir(parents=True, exist_ok=True)
    OUT_INDEX.write_text(json.dumps({"total": len(index), "concepts": index}, ensure_ascii=False, indent=1), encoding="utf-8")

    # Korean alias -> id  (Hangul aliases, length >= 3 to avoid noisy short matches)
    ko_alias = []
    for c in index:
        for al in c["aliases"]:
            a = norm_ko(al)
            if HANGUL.search(a) and len(a) >= 3:
                ko_alias.append((a, c["id"]))
    # English id/title tokens -> id (multiword phrases only, to avoid single-word false hits)
    en_phrase = []
    for c in index:
        cand = set()
        tid = norm_en(c["id"].replace("_", " "))
        if len(tid.split()) >= 2:
            cand.add(tid)
        if c["title"]:
            t = norm_en(c["title"])
            if len(t.split()) >= 2:
                cand.add(t)
        for ph in cand:
            en_phrase.append((ph, c["id"]))

    relabeled = json.loads(RELABELED.read_text(encoding="utf-8"))["items"]
    qb = {it["id"]: it for it in json.loads(QBANK.read_text(encoding="utf-8"))["items"]}

    recovered, worklist = [], []
    for r in relabeled:
        if r["disease_concept_id"]:
            continue  # already matched by the English concept_tags join
        it = qb.get(r["id"], {})
        topic = it.get("topic") or ""
        subtopic = it.get("subtopic") or ""
        major = it.get("major_category") or ""
        ko_hay = norm_ko(topic + " " + subtopic + " " + major)
        en_hay = norm_en(topic + " " + subtopic + " " + major)
        hits = []
        for a, cid in ko_alias:
            if a in ko_hay and cid not in hits:
                hits.append(cid)
        for ph, cid in en_phrase:
            if ph and ph in en_hay and cid not in hits:
                hits.append(cid)
        if hits:
            recovered.append({
                "id": r["id"], "question_number": r.get("question_number"),
                "major_category": major, "topic": topic, "subtopic": subtopic,
                "disease_concept_id": hits[:3], "basis": "deterministic_alias_title_match",
            })
        else:
            has_stem = bool(it.get("stem")) and not it.get("stem_is_reconstructed", False)
            worklist.append({
                "id": r["id"], "question_number": r.get("question_number"),
                "major_category": major, "topic": topic, "subtopic": subtopic,
                "has_real_stem": has_stem,
            })

    OUT_DET.write_text(json.dumps({"total": len(recovered), "items": recovered}, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_WORK.write_text(json.dumps({"total": len(worklist), "items": worklist}, ensure_ascii=False, indent=1), encoding="utf-8")

    already = sum(1 for r in relabeled if r["disease_concept_id"])
    total = len(relabeled)
    print("── Korean-topic recovery (deterministic pass) ──")
    print(f"registry index:      {OUT_INDEX.relative_to(ROOT)}  ({len(index)} concepts)")
    print(f"already matched:     {already}/{total} ({already/total*100:.1f}%)  [English concept_tags join]")
    print(f"deterministic recov: +{len(recovered)}  (Korean alias / English title match)")
    print(f"floor after det:     {already+len(recovered)}/{total} ({(already+len(recovered))/total*100:.1f}%)")
    print(f"LLM work-list:       {len(worklist)}  -> {OUT_WORK.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
