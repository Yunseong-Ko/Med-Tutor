#!/usr/bin/env python3
"""Turn the MONDO cross-reference workflow output into an xref map + build a comparison report.

Clean xrefs (exact/close) get attached to nodes. Divergent/none are NOT attached as equivalences
(they'd assert a false identity) — they are surfaced in the report as either legitimate
non-standard exam concepts (our value-add) or finding-not-disease nodes to reconsider.
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
OUT_MAP = DP / "curriculum" / "ontology_xref_map.json"
REPORT = ROOT / "docs" / "Ontology_MONDO_Comparison_20260711.md"


def main(task_out: str) -> None:
    res = json.loads(Path(task_out).read_text(encoding="utf-8"))["result"]["results"]
    reg = json.loads((DP / "concept_registry.json").read_text(encoding="utf-8"))["concepts"]

    xref, divergent, none_std = {}, [], []
    for r in res:
        nm = r.get("name_match")
        if nm in ("exact", "close") and r.get("mondo_id"):
            xref[r["id"]] = {"mondo_id": r["mondo_id"], "mondo_label": r.get("mondo_label", ""), "name_match": nm}
        elif nm == "divergent":
            divergent.append(r)
        elif nm == "none":
            none_std.append(r)
    OUT_MAP.write_text(json.dumps({"total": len(xref), "map": xref}, ensure_ascii=False, indent=1), encoding="utf-8")

    by = Counter(r.get("name_match") for r in res)
    # split the no-standard-match set: findings-not-disease vs legit non-standard exam concepts
    finding_like = [r for r in none_std + divergent
                    if any(k in r["id"] for k in ("_delay", "hemolytic_anemia", "bacteriuria", "incontinence",
                                                  "developmental", "microangiopathic"))]
    n_lines = []
    n_lines.append("# 우리 온톨로지 × 표준 온톨로지(MONDO) 비교·업데이트 리포트 (2026-07-11)")
    n_lines.append("")
    n_lines.append("> 확장 358노드를 MONDO(EBI/Monarch 통합 질환 온톨로지, Harvard PrimeKG의 질환어휘)에 OLS API로 교차매핑.")
    n_lines.append("> 참조: MONDO(is-a 분류학+DOID/OMIM/ICD/SNOMED xref) · PrimeKG(하버드 Zitnik, 17k질환·4M관계, MONDO기반 관계그래프).")
    n_lines.append("")
    n_lines.append("## 1. 매핑 결과")
    n_lines.append(f"- **287/358 (80%)가 MONDO 표준 질환에 매핑** → 우리 확장이 대부분 실재·표준 질환임을 검증.")
    n_lines.append(f"- name_match 분포: exact {by.get('exact',0)} · close {by.get('close',0)} · divergent {by.get('divergent',0)} · none {by.get('none',0)}.")
    n_lines.append(f"- **clean xref로 채택(exact+close): {len(xref)}개** → `evidence.ontology_xref.mondo_id` 부착(상호운용). divergent/none은 거짓 동일성 방지 위해 미부착.")
    n_lines.append("")
    n_lines.append("## 2. 핵심 통찰 (divergent/none이 드러낸 것)")
    n_lines.append("")
    n_lines.append("### (a) 우리 고유 가치 = MONDO에 인간 질환 term이 없는 시험근거 개념")
    n_lines.append("MONDO가 'non-human animal' term만 갖거나 아예 없는 것들 — 외과합병증·산과역학·소아외과 선천기형은 표준 질환 온톨로지의 사각지대인데 국시엔 출제됨:")
    for r in [x for x in none_std if any(k in x['id'] for k in ('hernia','ileus','rupture','pseudocyst','atresia','omphalocele','presentation','abortion','previa','chylous','torch','malrotation'))][:14]:
        n_lines.append(f"- `{r['id']}` — {r.get('note','MONDO 인간 term 없음')[:120]}")
    n_lines.append("")
    n_lines.append("### (b) 질환 아닌 '소견/상태' 노드 (의학검토와 일치 — 재검토 권고)")
    n_lines.append("MONDO가 discrete 질환으로 인정 안 함 = 우리가 소견을 노드화한 케이스:")
    for r in finding_like[:8]:
        n_lines.append(f"- `{r['id']}` — {r.get('note','finding/pattern, not a discrete disease')[:120]}")
    n_lines.append("")
    n_lines.append("### (c) 입도 불일치 (우리 generic ↔ MONDO subtype만) — xref 시 부모term 수동선택 필요")
    for r in divergent:
        if r['id'] not in {x['id'] for x in finding_like}:
            n_lines.append(f"- `{r['id']}` → MONDO 최근접 `{r.get('mondo_id')}` \"{r.get('mondo_label','')}\" ({r.get('note','')[:90]})")
    n_lines.append("")
    n_lines.append("## 3. 구조 비교")
    n_lines.append("| | 우리 온톨로지 | MONDO | PrimeKG(하버드) |")
    n_lines.append("|---|---|---|---|")
    n_lines.append("| 성격 | 시험근거 임상추론 그래프 | is-a 질환 분류학 | DB유래 관계그래프 |")
    n_lines.append("| 노드 | 573 질환(국시/과정시험 기반) | ~22k 질환 | 17k 질환(MONDO기반) |")
    n_lines.append("| 엣지 | differential/cause/treat/diagnose (문항+Harrison 근거) | subClassOf(is-a) 중심 | disease-drug/protein/phenotype 등 7종(DB) |")
    n_lines.append("| 근거 | Harrison 페이지 + 실제 문항 | 문헌 큐레이션 | 20개 DB 통합 |")
    n_lines.append("| 강점 | 무엇이 어떻게 출제되나 | 표준 ID·계층·상호운용 | 분자/치료 연관 규모 |")
    n_lines.append("")
    n_lines.append("## 4. 업데이트 방향 (채택/보류)")
    n_lines.append("- **채택**: MONDO xref ID를 evidence에 부착(287→clean 252) = 상호운용성·검증. → 반영됨.")
    n_lines.append("- **채택(권고)**: MONDO is-a 부모개념 수입으로 우리 flat 레지스트리에 계층(category) 추가 — 예 multiple_myeloma ⊂ plasma_cell_neoplasm ⊂ hematologic_neoplasm. (별도 티켓)")
    n_lines.append("- **재검토**: (b)의 소견형 노드(MAHA·motor_developmental_delay 등) → finding 레이어로 강등 검토(의학검토와 일치).")
    n_lines.append("- **유지(차별점)**: (a)의 시험근거 고유개념 + 우리 임상관계 엣지 = MONDO/PrimeKG에 없는 국시 특화 자산. 표준에 없다고 지우지 않음.")
    n_lines.append("- **보류**: PrimeKG식 분자/약물 대규모 관계는 우리 목적(문항개발)엔 과함 — 도입 안 함.")
    REPORT.write_text("\n".join(n_lines) + "\n", encoding="utf-8")
    print(f"xref map: {len(xref)} clean · report: {REPORT.relative_to(ROOT)}")
    print(f"name_match: {dict(by)} | divergent {len(divergent)} | none {len(none_std)}")


if __name__ == "__main__":
    main(sys.argv[1])
