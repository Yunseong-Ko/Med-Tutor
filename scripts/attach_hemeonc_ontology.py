#!/usr/bin/env python3
"""Step 1 — 혈액종양내과 문항에 concept_registry(598) 온톨로지 근거를 결정론적으로 부착.

각 문항의 subtopic/topic/concept_tags/stem을 registry의 한글·영문 alias와 대조해
disease_concept_id를 부여하고, 매칭 개념의 Harrison ref + 타입드 엣지(감별/치료/진단)를
`ontology_grounding` 블록으로 부착한다. 매칭 실패(기초개념 문항)는 null로 남긴다.
LLM 미사용·환각 0. 원본 필드는 건드리지 않는다(해설 재작성은 Step 2).

출력: 원본 JSON에 각 question["ontology_grounding"] 추가 (백업 후 in-place).
"""

import json
import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

REG = json.loads(Path("data_private/concept_registry.json").read_text(encoding="utf-8"))["concepts"]
COURSE_FILES = [
    "data_private/course_exams/extracted/COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험.json",
    "data_private/course_exams/extracted/COURSE_2_20260306_HEMATOLOGY_ONCOLOGY_1차.json",
    "data_private/course_exams/extracted/COURSE_2_20260317_HEMATOLOGY_ONCOLOGY_2차.json",
]
# CLI 인자로 파일 지정 가능(--files a.json b.json). PMA 혈액종양(G3 B군) 등 재사용.
_argv = [a for a in sys.argv[1:] if not a.startswith("--")]
if "--files" in sys.argv:
    i = sys.argv.index("--files")
    FILES = [a for a in sys.argv[i + 1:] if not a.startswith("--")]
else:
    FILES = COURSE_FILES
DISEASE_NODES = {"disorder", "neoplasm", "disease", "syndrome", "infection"}

# ---- alias index: normalized alias -> list of (concept_id, alias, is_disease, len) ----
def norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()

ALIAS_INDEX = []  # (norm_alias, concept_id, is_disease, raw_len, is_korean)
for cid, c in REG.items():
    is_disease = (c.get("node_type") or "") in DISEASE_NODES
    names = [cid.replace("_", " ")] + list(c.get("aliases") or [])
    for a in names:
        na = norm(a)
        if len(na) < 2:
            continue
        is_ko = bool(re.search(r"[가-힣]", a))
        # English aliases: require length >=4 to avoid noise; abbreviations (AML) only if uppercase>=3
        if not is_ko and len(na) < 4 and not (a.isupper() and len(a) >= 3):
            continue
        ALIAS_INDEX.append((na, cid, is_disease, len(na), is_ko))
# longest, disease-first
ALIAS_INDEX.sort(key=lambda x: (x[2], x[3]), reverse=True)


def match_concept(q: dict) -> dict | None:
    labels = q.get("labels") or {}
    subtopic = labels.get("subtopic") or ""
    topic = labels.get("topic") or ""
    ctags = labels.get("concept_tags") or []
    stem = str(q.get("stem") or "")[:220]
    # search field priority: subtopic (most specific) > topic > concept_tags > stem
    hay_specific = norm(subtopic) + "|" + norm(topic)
    hay_tags = "|".join(norm(t) for t in ctags)
    hay_stem = norm(stem)

    # 1) concept_tags exact-ish: a tag equals a concept id or a disease alias
    for t in ctags:
        nt = norm(t)
        for na, cid, is_dis, ln, is_ko in ALIAS_INDEX:
            if is_dis and na == nt:
                return {"cid": cid, "method": "concept_tag_exact"}
    # 2) subtopic/topic contains a disease alias (longest disease alias first)
    for na, cid, is_dis, ln, is_ko in ALIAS_INDEX:
        if not is_dis:
            continue
        if is_ko and ln >= 3 and na in hay_specific:
            return {"cid": cid, "method": "subtopic_alias"}
        if (not is_ko) and ln >= 4 and na in hay_specific:
            return {"cid": cid, "method": "subtopic_alias_en"}
    # 3) stem contains a distinctive disease alias (ko >=4 to be safe)
    for na, cid, is_dis, ln, is_ko in ALIAS_INDEX:
        if not is_dis:
            continue
        if is_ko and ln >= 4 and na in hay_stem:
            return {"cid": cid, "method": "stem_alias"}
    return None


def grounding_for(cid: str) -> dict:
    c = REG[cid]
    ev = c.get("evidence") or {}
    harrison = ev.get("harrison")
    edges = c.get("edges") or {}
    def edge_ids(rel):
        return [e.get("id") for e in (edges.get(rel) or []) if e.get("id")]
    ko_label = next((a for a in (c.get("aliases") or []) if re.search(r"[가-힣]", a)), cid.replace("_", " "))
    return {
        "disease_concept_id": cid,
        "label": ko_label,
        "node_type": c.get("node_type"),
        "harrison": harrison,   # {chapter,title,page,accessmedicine,...} or None
        "differentials": edge_ids("differential_of"),   # → 오답/감별 근거
        "treated_with": edge_ids("treated_with"),
        "diagnosed_by": edge_ids("diagnosed_by"),
        "presents_with": edge_ids("presents_with"),
        "assessment_domains": c.get("assessment_domains") or [],
        "needs_review": True,
        "grounding_source": "concept_registry_v598_deterministic",
    }


def main():
    commit = "--commit" in sys.argv
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    grand = {"total": 0, "matched": 0, "by_method": {}, "concepts": {}}
    for fp in FILES:
        p = Path(fp)
        d = json.loads(p.read_text(encoding="utf-8"))
        qs = d.get("questions", [])
        m = 0
        for q in qs:
            grand["total"] += 1
            res = match_concept(q)
            if res:
                g = grounding_for(res["cid"])
                g["match_method"] = res["method"]
                q["ontology_grounding"] = g
                m += 1
                grand["matched"] += 1
                grand["by_method"][res["method"]] = grand["by_method"].get(res["method"], 0) + 1
                grand["concepts"][res["cid"]] = grand["concepts"].get(res["cid"], 0) + 1
            else:
                q["ontology_grounding"] = None
        print(f"{p.name[:52]:52s} matched {m}/{len(qs)}")
        if commit:
            bak = p.with_suffix(f".json.bak_ontology_{stamp}")
            shutil.copy(p, bak)
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {grand['matched']}/{grand['total']} 매칭 ({100*grand['matched']/max(1,grand['total']):.0f}%)")
    print("방법별:", grand["by_method"])
    top = sorted(grand["concepts"].items(), key=lambda x: -x[1])[:12]
    print("상위 개념:", top)
    if not commit:
        print("\n(dry-run — 부착만 계산. 실제 저장은 --commit)")


if __name__ == "__main__":
    main()
