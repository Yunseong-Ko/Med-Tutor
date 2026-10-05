#!/usr/bin/env python3
"""질환 노트 생성용 태스크 준비 — concept_registry 근거를 개념별 task 파일로 묶는다.

각 태스크 = 노트 에이전트(docs/Concept_Note_Agent_Spec.md)가 읽을 온톨로지 grounding.
사용: python3 prep_concept_note_tasks.py [--specialty 혈액종양 | --ids a,b,c]
출력: scratchpad/concept_notes/task_<cid>.json
"""

import json
import re
import sys
from pathlib import Path

REG = json.loads(Path("data_private/concept_registry.json").read_text(encoding="utf-8"))["concepts"]
OUT = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad/concept_notes")


def axis(c, name):
    v = (c.get("clinical_axes") or {}).get(name)
    if isinstance(v, dict):
        return v.get("summary")
    return v


def edge(c, rel):
    return [e.get("id") for e in ((c.get("edges") or {}).get(rel) or []) if e.get("id")]


def edge_text(c, rel):
    # indicated_for/contraindicated_for는 문자열 요법이 담김
    return [e.get("id") for e in ((c.get("edges") or {}).get(rel) or []) if e.get("id")]


def bundle(cid):
    c = REG[cid]
    cm = c.get("cognitive_model") or {}
    tax = c.get("taxonomy") or {}
    h = (c.get("evidence") or {}).get("harrison") or {}
    ko = next((a for a in (c.get("aliases") or []) if re.search(r"[가-힣]", a)), cid.replace("_", " "))
    return {
        "disease_concept_id": cid,
        "label": ko,
        "aliases": c.get("aliases") or [],
        "taxonomy": {"primary": tax.get("primary_category"), "top": tax.get("top_category"),
                     "parents": [p.get("label") for p in (tax.get("parents") or []) if p.get("label")]},
        "pathophysiology": axis(c, "pathophysiology"),
        "risk_factors": axis(c, "risk_factors"),
        "prognosis": axis(c, "prognosis"),
        "epidemiology": axis(c, "epidemiology"),
        "chief_complaint": cm.get("chief_complaint") or [],
        "key_cues": cm.get("key_cues") or [],
        "differential_of": edge(c, "differential_of"),
        "due_to": edge(c, "due_to"),
        "predisposes": edge(c, "predisposes"),
        "presents_with": edge(c, "presents_with"),
        "diagnosed_by": edge(c, "diagnosed_by"),
        "treated_with": edge(c, "treated_with"),
        "indicated_for": edge_text(c, "indicated_for"),
        "contraindicated_for": edge_text(c, "contraindicated_for"),
        "harrison": {"chapter": h.get("chapter"), "title": h.get("title"),
                     "page": h.get("page"), "accessmedicine": h.get("accessmedicine")} if h.get("chapter") else None,
    }


def main():
    args = sys.argv[1:]
    ids = []
    if "--ids" in args:
        ids = args[args.index("--ids") + 1].split(",")
    else:
        spec = args[args.index("--specialty") + 1] if "--specialty" in args else "혈액종양"
        ids = [cid for cid, c in REG.items() if c.get("specialty") == spec]
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for cid in ids:
        if cid not in REG:
            continue
        (OUT / f"task_{cid}.json").write_text(
            json.dumps(bundle(cid), ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    print(f"{n}개 개념 태스크 저장 → {OUT}")
    print("개념:", ", ".join(ids[:12]) + (" …" if len(ids) > 12 else ""))


if __name__ == "__main__":
    main()
