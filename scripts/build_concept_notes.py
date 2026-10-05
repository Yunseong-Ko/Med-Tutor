#!/usr/bin/env python3
"""질환별 노트를 concept_registry 필드에서 **결정론적으로** 조립(LLM 미사용·환각 0).

각 노트 항목은 정해진 규칙대로 registry의 최적 필드에서 긁어온다. 빈 필드는 지어내지
않고 '미작성(검토 필요)'로 둔다. 전 산출 needs_review.

항목→소스 규칙:
  분류/상위       ← taxonomy, is_a(MONDO)
  별칭            ← aliases
  병태생리        ← clinical_axes.pathophysiology.summary
  위험인자        ← clinical_axes.risk_factors / edges.predisposes
  주호소·단서     ← cognitive_model.chief_complaint/key_cues, edges.presents_with
  진단검사        ← edges.diagnosed_by
  감별진단        ← edges.differential_of
  치료            ← edges.treated_with + edges.indicated_for(구체 요법)
  금기            ← edges.contraindicated_for
  예후/역학       ← clinical_axes.prognosis/epidemiology.summary
  근거            ← evidence.harrison (Ch/page + AccessMedicine)
"""

import json
import sys
from pathlib import Path

REG = json.loads(Path("data_private/concept_registry.json").read_text(encoding="utf-8"))["concepts"]
MISSING = "— 미작성(검토 필요)"


def axis_summary(c, axis):
    v = (c.get("clinical_axes") or {}).get(axis)
    if isinstance(v, dict):
        s = v.get("summary")
        return s if s else None
    return v or None


def edge_ids(c, rel):
    return [e.get("id") for e in ((c.get("edges") or {}).get(rel) or []) if e.get("id")]


def as_list(v):
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    if v:
        return [str(v)]
    return []


def build_note(cid):
    c = REG[cid]
    tax = c.get("taxonomy") or {}
    harr = (c.get("evidence") or {}).get("harrison") or {}
    cm = c.get("cognitive_model") or {}
    note = {
        "disease_concept_id": cid,
        "aliases": c.get("aliases") or [],
        "분류": {"세부": tax.get("primary_category"), "상위": tax.get("top_category"),
                "MONDO": [p.get("label") for p in (tax.get("parents") or []) if p.get("label")]},
        "병태생리": axis_summary(c, "pathophysiology") or MISSING,
        "위험인자": as_list(axis_summary(c, "risk_factors")) or edge_ids(c, "predisposes") or [MISSING],
        "주호소": cm.get("chief_complaint") or [],
        "결정단서": cm.get("key_cues") or edge_ids(c, "presents_with") or [],
        "진단검사": edge_ids(c, "diagnosed_by") or [MISSING],
        "감별진단": edge_ids(c, "differential_of") or [MISSING],
        "치료": {"모달리티": edge_ids(c, "treated_with"),
                "구체요법": as_list((c.get("edges") or {}).get("indicated_for") and
                                  [e.get("id") for e in c["edges"]["indicated_for"]])},
        "금기": [e.get("id") for e in ((c.get("edges") or {}).get("contraindicated_for") or [])] or [MISSING],
        "예후": axis_summary(c, "prognosis") or MISSING,
        "역학": axis_summary(c, "epidemiology") or MISSING,
        "근거": (f"Harrison Ch.{harr.get('chapter')} — {harr.get('title')} (p.{harr.get('page')})"
                 if harr.get("chapter") else MISSING),
        "accessmedicine": harr.get("accessmedicine"),
        "_fill": {},   # 채움률 메타
        "needs_review": True,
        "source": "concept_registry_deterministic_v1",
    }
    # 채움률: 핵심 8항목 중 실제 채워진 수
    core = ["병태생리", "위험인자", "결정단서", "진단검사", "감별진단", "예후", "역학", "근거"]
    filled = sum(1 for k in core if note[k] not in (MISSING, [MISSING], [], None))
    note["_fill"] = {"filled": filled, "of": len(core)}
    return note


def render_md(note):
    n = note
    t = n["분류"]
    L = lambda xs: ", ".join(xs) if xs else MISSING
    return f"""### {n['aliases'][0] if n['aliases'] else n['disease_concept_id']}  ({n['disease_concept_id']})
별칭: {L(n['aliases'])}  ·  분류: {t.get('세부') or '-'} › {t.get('상위') or '-'}  ·  채움 {n['_fill']['filled']}/{n['_fill']['of']}

- **병태생리**: {n['병태생리']}
- **위험인자**: {L(n['위험인자'])}
- **주호소**: {L(n['주호소'])}
- **결정단서**: {L(n['결정단서'])}
- **진단검사**: {L(n['진단검사'])}
- **감별진단**: {L(n['감별진단'])}
- **치료**: 모달리티 {L(n['치료']['모달리티'])}
  · 구체요법: {L(n['치료']['구체요법'])}
- **금기**: {L(n['금기'])}
- **예후**: {n['예후']}   ·   **역학**: {n['역학']}
- **근거**: {n['근거']}
- ※ {MISSING} 항목은 레지스트리 미작성 — 창작 금지, 검토·보강 대상
"""


def main():
    ids = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not ids:
        ids = ["acute_myeloid_leukemia"]
    for cid in ids:
        if cid not in REG:
            print(f"[없음] {cid}")
            continue
        print(render_md(build_note(cid)))


if __name__ == "__main__":
    main()
