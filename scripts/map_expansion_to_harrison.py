#!/usr/bin/env python3
"""Map the curriculum-expansion registry nodes to Harrison 22e chapters/pages.

Reuses the exact TF-IDF matcher from build_harrison_mapping.py (same as the 215 seeds),
so pages come from the real Harrison TOC (04_Contents.pdf) — never fabricated. Low-score
or no-match nodes get harrison=null and confidence='none' (a human/next step maps those).

Output: data_private/curriculum/expansion_harrison_map.json  {id: harrison_ref|null, ...}
build_concept_registry.py applies this map to evidence.harrison (needs_review stays true).
"""
from __future__ import annotations
import json
from pathlib import Path

import build_harrison_mapping as H  # parse_toc, toks, build_idf, match_concept, resolve_curated, accessmed_url, CURATED

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data_private" / "concept_registry.json"
OUT = ROOT / "data_private" / "curriculum" / "expansion_harrison_map.json"
HARRISON22_CHAPTER_INDEX = ROOT / "data_private" / "harrison" / "22e" / "chapter_index.json"

GUIDELINE_CURATED_CHAPTERS = {
    "chronic_kidney_disease": 322,
    "chronic_obstructive_pulmonary_disease": 303,
    "intracerebral_hemorrhage": 439,
    "metabolic_dysfunction_associated_steatotic_liver_disease": 354,
    "obesity": 414,
    "dyslipidemia": 419,
    "diabetic_kidney_disease": 322,
    "hypertensive_kidney_disease": 322,
    "fabry_disease": 429,
    "community_acquired_pneumonia": 131,
    "hospital_acquired_pneumonia": 131,
    "mycoplasma_pneumonia": 131,
    "carbapenem_resistant_enterobacterales_infection": 166,
}
GUIDELINE_NO_HARRISON_CHAPTER = {
    "multiple_gestation",
    "acute_upper_respiratory_tract_infection",
}


def ref_from_chapter(c: dict, score, conf: str) -> dict:
    return {
        "chapter": c["chapter"], "title": c["title"], "page": c["page"],
        "part": c["part"], "pdf": c.get("pdf"),
        "match_score": score, "confidence": conf,
        "accessmedicine": H.accessmed_url(c["title"]),
        "status": "expansion_auto_mapped",
    }


def ref_from_harrison22_snapshot(c: dict) -> dict:
    return {
        "chapter": c["chapter"],
        "title": c["title"],
        "page": c["toc_printed_page"],
        "part": c.get("part"),
        "pdf": c.get("source_file"),
        "match_score": 99,
        "confidence": "curated",
        "accessmedicine": None,
        "status": "expansion_22e_snapshot_curated",
        "edition": "22e",
        "source_file": c.get("source_file"),
        "source_file_sha256": c.get("source_file_sha256"),
        "needs_review": True,
        "medical_approval": False,
    }


def main() -> None:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))["concepts"]
    exp_ids = [cid for cid, c in reg.items()
               if str(c.get("source", "")).startswith(("heme_onc", "korean_topic", "differential", "kr_guideline"))]

    # preserve any prior mappings (incl. LLM-mapped) — only (re)map nodes not yet mapped
    existing = {}
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8")).get("map", {})

    chapters = H.parse_toc()
    snapshot_chapters = {
        int(row["chapter"]): row
        for row in json.loads(HARRISON22_CHAPTER_INDEX.read_text(encoding="utf-8"))["chapters"]
    }
    chap_tokens = [set(H.toks(c["title"])) for c in chapters]
    idf, df = H.build_idf(chap_tokens)

    out = {}
    hit_high = hit_med = curated = nomatch = kept = 0
    for cid in exp_ids:
        if cid in GUIDELINE_NO_HARRISON_CHAPTER:
            out[cid] = None
            nomatch += 1
            continue
        if cid in GUIDELINE_CURATED_CHAPTERS:
            chapter_number = GUIDELINE_CURATED_CHAPTERS[cid]
            c = snapshot_chapters.get(chapter_number)
            if c:
                out[cid] = ref_from_harrison22_snapshot(c)
                curated += 1
                continue
        if existing.get(cid):            # already mapped (deterministic or LLM) → keep
            out[cid] = existing[cid]
            kept += 1
            continue
        # 1) curated hard-case keyword (reuse build_harrison_mapping's CURATED table)
        if cid in H.CURATED:
            c = H.resolve_curated(H.CURATED[cid], chapters)
            if c:
                out[cid] = ref_from_chapter(c, 99, "high")
                curated += 1
                continue
        # 2) TF-IDF match on the bare id (snake_case -> disease words)
        r = H.match_concept(cid, chapters, chap_tokens, idf, df)
        if r:
            c, score, conf = r
            out[cid] = ref_from_chapter(c, score, conf)
            if conf == "high":
                hit_high += 1
            else:
                hit_med += 1
            continue
        # 3) no confident chapter — never guess a page
        out[cid] = None
        nomatch += 1

    OUT.write_text(json.dumps({"total": len(out), "map": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    mapped = sum(1 for v in out.values() if v)
    print("── Expansion → Harrison mapping ──")
    print(f"expansion nodes:   {len(exp_ids)}  (kept prior {kept}, newly TF-IDF {hit_high+hit_med})")
    print(f"mapped total:      {mapped}/{len(exp_ids)} ({mapped/len(exp_ids)*100:.0f}%)")
    print(f"no confident match: {len(exp_ids)-mapped}  (harrison=null → LLM/human next)")
    print(f"chapters indexed:  {len(chapters)}  →  {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
