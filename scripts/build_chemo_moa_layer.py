#!/usr/bin/env python3
"""세포주기 기반 항암제 작용기전(chemo MoA) typed overlay 빌드 (deterministic, additive).

약물 클래스·분자 타깃·세포 과정·세포주기 phase를 first-class typed 노드로, 기전을 typed 엣지로
인코딩한다. 질환/finding 그래프는 변형하지 않는다(순수 overlay). indicated_for 엣지는 실제
concept_registry id 로만 resolve 하고, 미해결은 unresolved(growth 후보)로 표기한다.

추가 검증:
  - 모든 노드/엣지 타입 화이트리스트 검사
  - 각 약물이 leads_to/inhibits/activates/depletes 경로로 cell_death 에 도달하는지 reachability
  - dangling 엣지(정의되지 않은 노드 참조) 탐지

Reads (data_private/):
  curriculum/chemo_moa_worklist.json    authored source (nodes + edges)
  concept_registry.json                 indicated_for 교차연결 검증

Writes (data_private/, needs_review):
  curriculum/chemo_moa_registry.json    typed 노드 + 해결된 엣지 + xref/reachability 리포트
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
WORK = DP / "curriculum" / "chemo_moa_worklist.json"
CONCEPTS = DP / "concept_registry.json"
OUT = DP / "curriculum" / "chemo_moa_registry.json"

ALLOWED_NODE_TYPES = {"antineoplastic_agent", "molecular_target", "cell_process", "cell_cycle_phase"}
ALLOWED_RELS = {"acts_in_phase", "inhibits", "activates", "depletes", "leads_to", "indicated_for"}
MECHANISM_RELS = {"inhibits", "activates", "depletes", "leads_to"}   # cell_death 도달 경로
SINK = "cell_death"


def reaches_sink(start: str, adj: dict) -> bool:
    seen, stack = set(), [start]
    while stack:
        n = stack.pop()
        if n == SINK:
            return True
        if n in seen:
            continue
        seen.add(n)
        stack.extend(adj.get(n, ()))
    return False


def main() -> None:
    work = json.loads(WORK.read_text(encoding="utf-8"))
    concept_ids = set(json.loads(CONCEPTS.read_text(encoding="utf-8"))["concepts"].keys())

    nodes, by_type, bad_type = {}, Counter(), []
    for n in work["nodes"]:
        nt = n.get("node_type")
        if nt not in ALLOWED_NODE_TYPES:
            bad_type.append((n.get("id"), nt))
            continue
        node = dict(n)
        node["needs_review"] = True
        node["source"] = "chemo_moa_cellcycle"
        nodes[n["id"]] = node
        by_type[nt] += 1

    node_ids = set(nodes)
    adj = defaultdict(list)               # mechanism reachability graph
    edges, by_rel, bad_rel, dangling = [], Counter(), [], []
    indication_xref = {"resolved": [], "unresolved": []}
    for e in work["edges"]:
        rel = e.get("rel")
        if rel not in ALLOWED_RELS:
            bad_rel.append((e.get("src"), rel, e.get("dst")))
            continue
        src, dst = e.get("src"), e.get("dst")
        edge = dict(e)
        edge["needs_review"] = True
        edge["src_in_layer"] = src in node_ids
        if rel == "indicated_for":
            hit = dst in concept_ids
            edge["dst_resolved"] = "concept_registry" if hit else "unresolved"
            (indication_xref["resolved"] if hit else indication_xref["unresolved"]).append(dst)
        else:
            # 내부 노드 엣지: dangling 검사 + reachability adjacency
            if dst not in node_ids and rel != "acts_in_phase":
                dangling.append((src, rel, dst))
            if rel in MECHANISM_RELS:
                adj[src].append(dst)
        edges.append(edge)
        by_rel[rel] += 1

    # 각 약물이 cell_death 로 수렴하는지
    drugs = [nid for nid, n in nodes.items() if n["node_type"] == "antineoplastic_agent"]
    reach = {d: reaches_sink(d, adj) for d in drugs}
    not_converging = sorted(d for d, ok in reach.items() if not ok)

    out = {
        "_meta": {
            "generated_by": "build_chemo_moa_layer.py",
            "source": str(WORK.relative_to(ROOT)),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "by_node_type": dict(by_type),
            "by_edge_rel": dict(by_rel),
            "drug_count": len(drugs),
            "indication_xref": {
                "resolved": sorted(set(indication_xref["resolved"])),
                "unresolved": sorted(set(indication_xref["unresolved"])),
            },
            "all_drugs_converge_to_cell_death": not not_converging,
            "not_converging": not_converging,
            "dangling_edges": dangling,
            "invalid_node_types": bad_type,
            "invalid_rels": bad_rel,
            "all_needs_review": True,
            "note": ("additive typed overlay; 질환/finding 그래프 불변. indicated_for 는 실제 registry "
                     "해결분만 resolved 로 표기. 모든 약물 기전 경로는 cell_death 로 수렴 검증."),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("── chemo MoA typed overlay ──")
    print(f"nodes: {len(nodes)}  {dict(by_type)}")
    print(f"edges: {len(edges)}  {dict(by_rel)}")
    print(f"drugs → cell_death 수렴: {sum(reach.values())}/{len(drugs)}" + (f"  MISSING={not_converging}" if not_converging else "  (all)"))
    print(f"indicated_for resolved: {len(set(indication_xref['resolved']))} distinct → {sorted(set(indication_xref['resolved']))}")
    if indication_xref["unresolved"]:
        print(f"indicated_for UNRESOLVED (registry gap/growth): {sorted(set(indication_xref['unresolved']))}")
    if dangling or bad_type or bad_rel:
        print(f"⚠ dangling={dangling} bad_type={bad_type} bad_rel={bad_rel}")


if __name__ == "__main__":
    main()
