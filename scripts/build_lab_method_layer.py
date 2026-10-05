#!/usr/bin/env python3
"""검사방법론(lab-method) typed overlay 빌드 (deterministic, additive).

혈액검사 전처리·항응고제·자동분석기 파라미터·염색·도말 워크플로우를 first-class typed 노드로
만든다. 질환/finding 그래프는 변형하지 않는다(순수 overlay). stain_reveals·parameter_clue 엣지는
실제 finding_registry / concept_registry id 로만 해결(resolve)하고, 미해결은 unresolved 로 표기한다.

Reads (data_private/):
  curriculum/lab_method_worklist.json   authored source (nodes + edges)
  curriculum/finding_registry.json      finding id 교차연결 검증
  concept_registry.json                 disease id 교차연결 검증

Writes (data_private/, needs_review):
  curriculum/lab_method_registry.json   typed 노드 + 해결된 엣지 + xref 리포트
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
WORK = DP / "curriculum" / "lab_method_worklist.json"
FINDINGS = DP / "curriculum" / "finding_registry.json"
CONCEPTS = DP / "concept_registry.json"
OUT = DP / "curriculum" / "lab_method_registry.json"

ALLOWED_NODE_TYPES = {"anticoagulant", "analyzer_parameter", "stain", "specimen_target"}
ALLOWED_RELS = {"specimen_of_choice", "preanalytic_interference", "derived_from",
                "parameter_clue", "stain_reveals", "workflow"}
# 이 relation 의 dst 는 각각 finding / disease registry 로 해결돼야 한다.
FINDING_RESOLVED_RELS = {"stain_reveals"}
DISEASE_RESOLVED_RELS = {"parameter_clue"}


def main() -> None:
    work = json.loads(WORK.read_text(encoding="utf-8"))
    finding_ids = {f["finding_id"] for f in json.loads(FINDINGS.read_text(encoding="utf-8"))["findings"]}
    concept_ids = set(json.loads(CONCEPTS.read_text(encoding="utf-8"))["concepts"].keys())

    nodes, by_type, bad_type = {}, Counter(), []
    for n in work["nodes"]:
        nt = n.get("node_type")
        if nt not in ALLOWED_NODE_TYPES:
            bad_type.append((n.get("id"), nt))
            continue
        node = dict(n)
        node["needs_review"] = True
        node["source"] = "pbbm_crossval_lab_method"
        nodes[n["id"]] = node
        by_type[nt] += 1

    node_ids = set(nodes)
    edges, by_rel, bad_rel = [], Counter(), []
    finding_xref = {"resolved": [], "unresolved": []}
    disease_xref = {"resolved": [], "unresolved": []}
    for e in work["edges"]:
        rel = e.get("rel")
        if rel not in ALLOWED_RELS:
            bad_rel.append((e.get("src"), rel, e.get("dst")))
            continue
        edge = dict(e)
        edge["needs_review"] = True
        edge["src_in_layer"] = e.get("src") in node_ids
        # 교차연결 해결
        dst = e.get("dst")
        if rel in FINDING_RESOLVED_RELS:
            hit = dst in finding_ids
            edge["dst_resolved"] = "finding_registry" if hit else "unresolved"
            (finding_xref["resolved"] if hit else finding_xref["unresolved"]).append(dst)
        elif rel in DISEASE_RESOLVED_RELS:
            hit = dst in concept_ids
            edge["dst_resolved"] = "concept_registry" if hit else "unresolved"
            (disease_xref["resolved"] if hit else disease_xref["unresolved"]).append(dst)
        edges.append(edge)
        by_rel[rel] += 1

    out = {
        "_meta": {
            "generated_by": "build_lab_method_layer.py",
            "source": str(WORK.relative_to(ROOT)),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "by_node_type": dict(by_type),
            "by_edge_rel": dict(by_rel),
            "finding_xref": {
                "resolved": sorted(set(finding_xref["resolved"])),
                "unresolved": sorted(set(finding_xref["unresolved"])),
            },
            "disease_xref": {
                "resolved": sorted(set(disease_xref["resolved"])),
                "unresolved": sorted(set(disease_xref["unresolved"])),
            },
            "invalid_node_types": bad_type,
            "invalid_rels": bad_rel,
            "all_needs_review": True,
            "note": ("additive typed overlay; 질환/finding 그래프 불변. stain_reveals/parameter_clue 는 "
                     "실제 registry 해결분만 resolved 로 표기, 나머지는 unresolved(성장 후보)."),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("── lab-method typed overlay ──")
    print(f"nodes: {len(nodes)}  {dict(by_type)}")
    print(f"edges: {len(edges)}  {dict(by_rel)}")
    print(f"stain→finding resolved: {sorted(set(finding_xref['resolved']))}")
    if finding_xref["unresolved"]:
        print(f"stain→finding UNRESOLVED (growth): {sorted(set(finding_xref['unresolved']))}")
    print(f"param→disease resolved: {sorted(set(disease_xref['resolved']))}")
    if disease_xref["unresolved"]:
        print(f"param→disease UNRESOLVED (growth): {sorted(set(disease_xref['unresolved']))}")
    if bad_type or bad_rel:
        print(f"INVALID node_types={bad_type} rels={bad_rel}")


if __name__ == "__main__":
    main()
