#!/usr/bin/env python3
"""PB/BM 혈액검사 스터디노트 × concept_registry(598) 교차검증 — 소스 패치 (idempotent).

정합성 버그(A)와 혈액형태학/검사 커버리지 공백(B)에서 도출된 편집을 결정론 빌드의
*소스* 파일에 적용한다. 출력(concept_registry.json / finding_registry.json)은 이후
빌드 스크립트가 재생성한다. 모두 needs_review=true, 환각 금지(실제 HPO 조회분만).

편집 대상 소스:
  curriculum/p2_nodes.json              A1 HS presents_with, A2 megaloblastic 재분류, 신규 5노드 엣지
  curriculum/finding_hpo_worklist.json  A1 spherocyte.presented_by, B2 신규 소견 9종
  curriculum/finding_hpo_enrichment.json B2 신규 소견 HPO xref(실측) + body_system
  curriculum/endpoint_types.json        B2 신규 소견 finding 타이핑(엣지 라우팅 정합)

재실행 안전(idempotent): 이미 반영된 편집은 건너뛴다.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
P2 = DP / "curriculum" / "p2_nodes.json"
WORK = DP / "curriculum" / "finding_hpo_worklist.json"
ENRICH = DP / "curriculum" / "finding_hpo_enrichment.json"
EPTYPES = DP / "curriculum" / "endpoint_types.json"

HPO_SEARCH = "https://www.ebi.ac.uk/ols4/api/search?q={q}&ontology=hp&rows=3"

# ── B2: 신규 RBC 형태 소견 (presented_by는 의학적으로 검증, registry 여부와 무관) ──
# hpo_id는 EBI OLS4 실측 결과만 채운다 (basophilic_stippling/cabot_ring/teardrop/rouleaux = HPO 부재 -> null).
NEW_FINDINGS = [
    {"id": "target_cell", "q": "target cell",
     "presented_by": ["thalassemia", "hemoglobin_c_disease", "liver_disease", "sickle_cell_disease", "asplenia"],
     "hpo_id": "HP:0034280", "hpo_label": "Target cells"},
    {"id": "rouleaux", "q": "rouleaux",
     "presented_by": ["multiple_myeloma", "waldenstrom_macroglobulinemia", "chronic_inflammation"],
     "hpo_id": None, "hpo_label": ""},
    {"id": "sickle_cell", "q": "sickle cell",
     "presented_by": ["sickle_cell_disease"],
     "hpo_id": "HP:0030058", "hpo_label": "Sickled erythrocytes"},
    {"id": "teardrop_cell", "q": "teardrop cell",
     "presented_by": ["primary_myelofibrosis", "myelophthisic_anemia", "thalassemia"],
     "hpo_id": None, "hpo_label": ""},
    {"id": "howell_jolly_body", "q": "Howell-Jolly body",
     "presented_by": ["asplenia", "post_splenectomy", "sickle_cell_disease", "megaloblastic_anemia"],
     "hpo_id": "HP:0032550", "hpo_label": "Howell-Jolly bodies"},
    {"id": "pappenheimer_body", "q": "Pappenheimer body",
     "presented_by": ["sideroblastic_anemia", "post_splenectomy", "sickle_cell_disease"],
     "hpo_id": "HP:0020081", "hpo_label": "Pappenheimer bodies"},
    {"id": "basophilic_stippling", "q": "basophilic stippling",
     "presented_by": ["lead_poisoning", "thalassemia", "sideroblastic_anemia", "megaloblastic_anemia"],
     "hpo_id": None, "hpo_label": ""},
    {"id": "heinz_body", "q": "Heinz body",
     "presented_by": ["g6pd_deficiency", "thalassemia", "unstable_hemoglobin_disease"],
     "hpo_id": "HP:0020082", "hpo_label": "Heinz bodies"},
    {"id": "cabot_ring", "q": "Cabot ring",
     "presented_by": ["megaloblastic_anemia", "lead_poisoning", "myelodysplastic_syndrome"],
     "hpo_id": None, "hpo_label": ""},
]
FINDING_BODY_SYSTEM = "blood_hematologic"

# 신규 소견 + 항체 소견은 endpoint 라우팅상 'finding'으로 타이핑돼야 diagnosed_by -> presents_with 로 간다.
NEW_FINDING_TYPES = {f["id"]: "finding" for f in NEW_FINDINGS}
NEW_FINDING_TYPES["cold_igm_autoantibody"] = "finding"  # warm_igg_autoantibody(=finding)와 대칭

# ── p2_nodes: 신규/보강 노드 (edges 만 채운 draft, cognitive_model 미저작) ──
def edge(_id, in_reg):
    return {"id": _id, "in_registry": in_reg}

NEW_P2_NODES = [
    {"node_id": "non_megaloblastic_macrocytosis", "node_type": "syndrome", "needs_review": True,
     "edges": {
         "differential_of": [edge("megaloblastic_anemia", True)],
         "caused_by": [edge("alcohol_use_disorder", True), edge("liver_disease", False), edge("hypothyroidism", True)],
         "treated_with": [],
         "diagnosed_by": [edge("mcv", False), edge("peripheral_blood_smear", False), edge("reticulocyte_count", False)],
     }},
    {"node_id": "sickle_cell_disease", "node_type": "disease", "needs_review": True,
     "edges": {
         "differential_of": [edge("thalassemia", True), edge("hemoglobin_c_disease", False)],
         "caused_by": [],
         "treated_with": [edge("hydroxyurea", False)],
         "diagnosed_by": [edge("hemoglobin_electrophoresis", False), edge("peripheral_blood_smear", False),
                          edge("sickle_cell", False), edge("target_cell", False), edge("howell_jolly_body", False)],
     }},
    {"node_id": "lead_poisoning", "node_type": "disease", "needs_review": True,
     "edges": {
         "differential_of": [edge("iron_deficiency_anemia", True)],
         "caused_by": [edge("lead_exposure", False)],
         "treated_with": [edge("chelation_therapy", False)],
         "diagnosed_by": [edge("blood_lead_level", False), edge("peripheral_blood_smear", False),
                          edge("basophilic_stippling", False)],
     }},
    {"node_id": "cold_agglutinin_disease", "node_type": "disease", "needs_review": True,
     "edges": {
         "differential_of": [edge("autoimmune_hemolytic_anemia", True)],
         "caused_by": [edge("cold_igm_autoantibody", False), edge("mycoplasma_pneumoniae_infection", False)],
         "treated_with": [edge("rituximab", False)],
         "diagnosed_by": [edge("direct_coombs_test", False), edge("cold_agglutinin_titer", False)],
     }},
    # g6pd_deficiency: 이미 registry 개념(wave4). p2 엣지만 보강(중복 아님).
    {"node_id": "g6pd_deficiency", "node_type": "disease", "needs_review": True,
     "edges": {
         "differential_of": [edge("hereditary_spherocytosis", True), edge("autoimmune_hemolytic_anemia", True)],
         "caused_by": [edge("oxidative_stress", False)],
         "treated_with": [],
         "diagnosed_by": [edge("g6pd_enzyme_assay", False), edge("peripheral_blood_smear", False),
                          edge("heinz_body", False)],
     }},
]

MEGALO_REMOVE_CAUSES = {"alcohol_use_disorder", "liver_disease"}  # A2: 비거대적혈모구성 대구성 원인 -> 이관


def patch_p2():
    d = json.loads(P2.read_text(encoding="utf-8"))
    nodes = d.get("nodes", d) if isinstance(d, dict) else d
    idx = {n.get("node_id"): n for n in nodes}
    log = []

    # A1: hereditary_spherocytosis 가 spherocyte 를 presents_with 하도록 (diagnosed_by 에 추가 -> 타이핑 시 presents_with)
    hs = idx.get("hereditary_spherocytosis")
    if hs is not None:
        db = hs.setdefault("edges", {}).setdefault("diagnosed_by", [])
        if not any(e.get("id") == "spherocyte" for e in db):
            db.append(edge("spherocyte", False))
            log.append("A1 hereditary_spherocytosis.diagnosed_by += spherocyte")

    # A2: megaloblastic_anemia.caused_by 에서 비거대적혈모구성 원인 제거 + non_megaloblastic_macrocytosis 를 상호 감별로
    mg = idx.get("megaloblastic_anemia")
    if mg is not None:
        cb = mg.setdefault("edges", {}).setdefault("caused_by", [])
        removed = [e.get("id") for e in cb if e.get("id") in MEGALO_REMOVE_CAUSES]
        if removed:
            mg["edges"]["caused_by"] = [e for e in cb if e.get("id") not in MEGALO_REMOVE_CAUSES]
            log.append(f"A2 megaloblastic_anemia.caused_by -= {removed}")
        df = mg["edges"].setdefault("differential_of", [])
        if not any(e.get("id") == "non_megaloblastic_macrocytosis" for e in df):
            df.append(edge("non_megaloblastic_macrocytosis", True))
            log.append("A2 megaloblastic_anemia.differential_of += non_megaloblastic_macrocytosis")

    # 신규/보강 노드 추가
    for n in NEW_P2_NODES:
        if n["node_id"] not in idx:
            nodes.append(n)
            log.append(f"p2 node += {n['node_id']}")
        else:
            log.append(f"p2 node exists (skip) {n['node_id']}")

    if isinstance(d, dict):
        d["nodes"] = nodes
        out = d
    else:
        out = nodes
    P2.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return log


def patch_worklist():
    d = json.loads(WORK.read_text(encoding="utf-8"))
    items = d["items"]
    idx = {it["id"]: it for it in items}
    log = []

    # A1: spherocyte.presented_by += hereditary_spherocytosis
    sp = idx.get("spherocyte")
    if sp is not None and "hereditary_spherocytosis" not in sp["presented_by"]:
        sp["presented_by"] = list(dict.fromkeys([*sp["presented_by"], "hereditary_spherocytosis"]))
        sp["n_diseases"] = len(sp["presented_by"])
        log.append(f"A1 spherocyte.presented_by -> {sp['presented_by']} (n={sp['n_diseases']})")

    # B2: 신규 소견
    for f in NEW_FINDINGS:
        if f["id"] in idx:
            log.append(f"finding exists (skip) {f['id']}")
            continue
        items.append({
            "id": f["id"], "q": f["q"],
            "presented_by": f["presented_by"], "n_diseases": len(f["presented_by"]),
            "hpo_search_url": HPO_SEARCH.format(q=f["q"].replace(" ", "%20")),
        })
        log.append(f"finding += {f['id']} (n={len(f['presented_by'])})")
    d["items"] = items
    WORK.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return log


def patch_enrichment():
    d = json.loads(ENRICH.read_text(encoding="utf-8"))
    results = d["result"]["results"]
    have = {r["id"] for r in results}
    log = []
    for f in NEW_FINDINGS:
        if f["id"] in have:
            log.append(f"enrich exists (skip) {f['id']}")
            continue
        results.append({"id": f["id"], "hpo_id": f["hpo_id"],
                        "hpo_label": f["hpo_label"], "body_system": FINDING_BODY_SYSTEM})
        log.append(f"enrich += {f['id']} hpo={f['hpo_id']}")
    ENRICH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return log


def patch_endpoint_types():
    d = json.loads(EPTYPES.read_text(encoding="utf-8"))
    types = d["types"]
    log = []
    for k, v in NEW_FINDING_TYPES.items():
        if types.get(k) != v:
            types[k] = v
            log.append(f"endpoint_type {k} -> {v}")
    d["total"] = len(types)
    EPTYPES.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return log


def main():
    all_log = []
    all_log += ["[p2_nodes]"] + patch_p2()
    all_log += ["[finding_hpo_worklist]"] + patch_worklist()
    all_log += ["[finding_hpo_enrichment]"] + patch_enrichment()
    all_log += ["[endpoint_types]"] + patch_endpoint_types()
    print("── PB/BM cross-validation source patch (idempotent) ──")
    for line in all_log:
        print(("  " + line) if not line.startswith("[") else line)


if __name__ == "__main__":
    main()
