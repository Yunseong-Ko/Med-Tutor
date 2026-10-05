#!/usr/bin/env python3
"""Export the private ontology registry as a generated Obsidian mirror vault.

The vault is a consumer view. Edit the JSON sources, not the generated notes.
No question stems, answers, or patient records are read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

try:
    from scripts.build_typed_entity_registry import load_active_entities
except ModuleNotFoundError:  # direct script execution
    from build_typed_entity_registry import load_active_entities


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
REGISTRY = DP / "concept_registry.json"
FINDINGS = DP / "curriculum" / "finding_registry.json"
AXES = DP / "curriculum" / "axis_registry.json"
TYPED_ENTITIES = DP / "curriculum" / "typed_entity_registry.json"
DEFAULT_OUT = DP / "ontology_vault"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def safe(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value)).strip("_") or "unknown"


def yaml_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def korean_label(node: dict, fallback: str) -> str:
    for alias in node.get("aliases", []):
        if any("가" <= ch <= "힣" for ch in str(alias)):
            return str(alias)
    return fallback.replace("_", " ")


def link(folder: str, note_id: str, label: str | None = None) -> str:
    target = f"{folder}/{safe(note_id)}"
    return f"[[{target}|{label or note_id}]]"


def unique_filenames(ids: list[str]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for raw in ids:
        grouped.setdefault(safe(raw).casefold(), []).append(raw)
    result = {}
    for values in grouped.values():
        for raw in values:
            base = safe(raw)
            if len(values) > 1:
                base += "__" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
            result[raw] = base
    return result


def bullets(values: list[str], empty: str = "- 없음") -> str:
    return "\n".join(f"- {v}" for v in values) if values else empty


def clean_generated(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for path in folder.glob("*.md"):
        path.unlink()


def export(out: Path) -> dict:
    registry = load(REGISTRY)
    all_concepts = registry["concepts"]
    typed_entities = load_active_entities(TYPED_ENTITIES)
    concepts = {cid: row for cid, row in all_concepts.items() if cid not in typed_entities}
    typed_files = unique_filenames(list(typed_entities))
    finding_data = load(FINDINGS)
    finding_rows = finding_data.get("findings", [])
    findings = {row["finding_id"]: row for row in finding_rows}
    finding_files = unique_filenames(list(findings))
    axis_payload = load(AXES) if AXES.exists() else {"nodes": [], "relationships": []}
    axis_nodes = {row["axis_id"]: row for row in axis_payload.get("nodes", [])}
    axis_files = unique_filenames(list(axis_nodes))
    disease_axis_edges: dict[str, list[dict]] = {}
    for row in axis_payload.get("relationships", []):
        disease_axis_edges.setdefault(row["disease_concept_id"], []).append(row)

    disease_dir = out / "Diseases"
    finding_dir = out / "Findings"
    taxonomy_dir = out / "Taxonomy"
    axis_dir = out / "Axes"
    entity_dir = out / "Typed Entities"
    meta_dir = out / "_meta"
    for folder in (disease_dir, finding_dir, taxonomy_dir, axis_dir, entity_dir, meta_dir):
        clean_generated(folder)
    (out / ".obsidian").mkdir(parents=True, exist_ok=True)

    taxonomy: dict[str, dict] = {}
    for cid, node in concepts.items():
        for parent in node.get("is_a", []):
            if parent["id"] in concepts:
                continue
            taxonomy.setdefault(parent["id"], {"label": parent.get("label") or parent["id"], "children": []})
            taxonomy[parent["id"]]["children"].append(cid)

    for tid, row in taxonomy.items():
        body = [
            "---",
            f"id: {yaml_value(tid)}",
            "node_type: taxonomy",
            "source: MONDO",
            "needs_review: true",
            "---",
            f"# {row['label']}",
            "",
            f"`{tid}` · MONDO 상위분류 초안",
            "",
            "## 하위 질환",
            bullets([link("Diseases", cid, korean_label(concepts[cid], cid)) for cid in sorted(set(row["children"]))]),
            "",
        ]
        (taxonomy_dir / f"{safe(tid)}.md").write_text("\n".join(body), encoding="utf-8")

    for fid, row in findings.items():
        presented = [cid for cid in row.get("presented_by", []) if cid in concepts]
        label = row.get("hpo_label") or fid.replace("_", " ")
        body = [
            "---",
            f"id: {yaml_value(fid)}",
            "node_type: finding",
            f"body_system: {yaml_value(row.get('body_system'))}",
            f"hpo_id: {yaml_value(row.get('hpo_id'))}",
            "needs_review: true",
            "---",
            f"# {label}",
            "",
            f"`{fid}`",
            "",
            "## 관련 질환",
            bullets([link("Diseases", cid, korean_label(concepts[cid], cid)) for cid in presented]),
            "",
        ]
        (finding_dir / f"{finding_files[fid]}.md").write_text("\n".join(body), encoding="utf-8")

    for cid, row in typed_entities.items():
        entity_type = row.get("entity_type") or "typed_entity"
        relation = row.get("recommended_relation") or {}
        pointer = row.get("legacy_harrison_pointer") or {}
        body = [
            "---",
            f"id: {yaml_value(cid)}",
            f"entity_id: {yaml_value(row.get('entity_id'))}",
            f"node_type: {yaml_value(entity_type)}",
            f"entity_subtype: {yaml_value(row.get('entity_subtype'))}",
            f"destination_layer: {yaml_value(row.get('destination_layer'))}",
            "migration_status: active_typed_overlay",
            "excluded_from_disease_exports: true",
            "needs_review: true",
            f"tags: [ontology, typed-entity, {safe(entity_type)}]",
            "---",
            f"# {row.get('label') or cid.replace('_', ' ')}",
            "",
            f"`{cid}` · **{entity_type}** · 질환 레지스트리에서 타입 레이어로 전환",
            "",
            "## 분류",
            f"- 세부 유형: `{row.get('entity_subtype') or '미지정'}`",
            f"- 대상 레이어: `{row.get('destination_layer') or '미지정'}`",
            f"- 사유: {row.get('reason') or '미기록'}",
            "",
            "## 관계 후보",
            f"- `{relation.get('name') or '없음'}` · {relation.get('direction') or '방향 미지정'}",
            "- 현재 materialized=false (스키마 검토 전)",
            "",
            "## 기존 교과과정 포인터",
            (
                f"- Harrison Ch{pointer.get('chapter')} p{pointer.get('page')} — {pointer.get('title')}"
                if pointer.get("chapter") is not None
                else "- Harrison: 미연결"
            ),
            "- 위 포인터는 교육과정 위치이며 질환이라는 주장이나 근거가 아님",
            "",
        ]
        (entity_dir / f"{typed_files[cid]}.md").write_text("\n".join(body), encoding="utf-8")

    for aid, row in axis_nodes.items():
        related = [cid for cid in row.get("disease_ids", []) if cid in concepts]
        body = [
            "---",
            f"id: {yaml_value(aid)}",
            f"claim_id: {yaml_value(row.get('claim_id'))}",
            f"node_type: {yaml_value(row.get('axis_type'))}",
            f"dimension: {yaml_value(row.get('dimension'))}",
            f"source: {yaml_value(row.get('sources') or [])}",
            f"review_status: {yaml_value(row.get('review_status') or 'draft_unreviewed')}",
            f"medical_approval: {str(bool(row.get('medical_approval'))).lower()}",
            f"applicability: {yaml_value(row.get('applicability') or 'unknown')}",
            f"claim_entailment: {yaml_value((row.get('provenance') or {}).get('claim_entailment') or 'unverified')}",
            f"needs_review: {str(bool(row.get('needs_review', True))).lower()}",
            f"tags: [ontology, axis, {safe(row.get('axis_type') or 'axis')}]",
            "---",
            f"# {row.get('label') or aid}",
            "",
            f"`{aid}` · **{row.get('axis_type') or 'axis'}** · 의학검토 전 초안",
            "",
            "## 관련 질환",
            bullets([link("Diseases", cid, korean_label(concepts[cid], cid)) for cid in related]),
            "",
        ]
        (axis_dir / f"{axis_files[aid]}.md").write_text("\n".join(body), encoding="utf-8")

    relation_order = ("differential_of", "due_to", "predisposes", "causative_agent")
    for cid, node in concepts.items():
        label = korean_label(node, cid)
        evidence = node.get("evidence") or {}
        harrison = evidence.get("harrison") or {}
        xref = evidence.get("ontology_xref") or {}
        edges = node.get("edges") or {}
        clinical_axes = node.get("clinical_axes") or {}
        aliases = [str(x) for x in node.get("aliases", [])]
        frontmatter = [
            "---",
            f"id: {yaml_value(cid)}",
            f"node_type: {yaml_value(node.get('node_type'))}",
            f"specialty: {yaml_value(node.get('specialty'))}",
            f"source: {yaml_value(node.get('source'))}",
            f"aliases: {yaml_value(aliases)}",
            f"harrison_chapter: {yaml_value(harrison.get('chapter'))}",
            f"harrison_page: {yaml_value(harrison.get('page'))}",
            f"mondo_id: {yaml_value(xref.get('mondo_id'))}",
            f"clinical_axes: {str(bool(clinical_axes)).lower()}",
            "needs_review: true",
            "tags: [ontology, disease]",
            "---",
        ]
        content = [f"# {label}", "", f"`{cid}` · 자동 생성된 소비자 뷰 · **의학검토 전 초안**", "", "## 근거"]
        if harrison.get("chapter"):
            content.append(f"- Harrison Ch{harrison['chapter']} p{harrison.get('page')} — {harrison.get('title')}")
        else:
            content.append("- Harrison: 미연결")
        content.append(f"- MONDO: {xref.get('mondo_id') or '미연결'}")

        content.extend(["", "## 질환 관계"])
        relation_lines = []
        for relation in relation_order:
            targets = []
            for edge in edges.get(relation, []):
                tid = edge.get("id") if isinstance(edge, dict) else edge
                if tid in concepts:
                    targets.append(link("Diseases", tid, korean_label(concepts[tid], tid)))
                elif tid in typed_entities:
                    targets.append(link("Typed Entities", typed_files[tid], typed_entities[tid].get("label") or tid))
            if targets:
                relation_lines.append(f"- **{relation}**: " + ", ".join(dict.fromkeys(targets)))
        content.append("\n".join(relation_lines) if relation_lines else "- 레지스트리 내부 질환 관계 없음")

        parents = [
            link("Diseases", p["id"], korean_label(concepts[p["id"]], p["id"]))
            if p["id"] in concepts
            else link("Taxonomy", p["id"], p.get("label") or p["id"])
            for p in node.get("is_a", [])
        ]
        content.extend(["", "## 상위분류", bullets(parents)])

        finding_links = []
        for edge in edges.get("presents_with", []):
            fid = edge.get("id") if isinstance(edge, dict) else edge
            if fid in findings:
                finding_links.append(link("Findings", finding_files[fid], findings[fid].get("hpo_label") or fid))
        content.extend(["", "## 주요 소견", bullets(list(dict.fromkeys(finding_links)))])

        tests = [str(e.get("id") if isinstance(e, dict) else e) for e in edges.get("diagnosed_by", [])]
        treatment = [str(e.get("id") if isinstance(e, dict) else e) for e in edges.get("treated_with", [])]
        content.extend(["", "## 진단 검사", bullets([f"`{x}`" for x in tests])])
        content.extend(["", "## 치료", bullets([f"`{x}`" for x in treatment])])

        axis_links: dict[str, list[str]] = {}
        for edge in disease_axis_edges.get(cid, []):
            axis_row = axis_nodes.get(edge.get("axis_id"))
            if not axis_row:
                continue
            axis_type = axis_row.get("axis_type") or "axis"
            axis_links.setdefault(axis_type, []).append(
                link("Axes", axis_files[axis_row["axis_id"]], axis_row.get("label") or axis_row["axis_id"])
            )
        content.extend(["", "## Ontology axes"])
        if axis_links:
            for axis_type, values in sorted(axis_links.items()):
                content.append(f"- **{axis_type}**: " + ", ".join(dict.fromkeys(values)))
        else:
            content.append("- 축 노드 미연결")

        if clinical_axes:
            path = clinical_axes.get("pathophysiology") or {}
            prognosis = clinical_axes.get("prognosis") or {}
            therapy = clinical_axes.get("treatment") or {}
            epi = clinical_axes.get("epidemiology") or {}
            content.extend([
                "", "## Clinical axes",
                f"- **병태생리**: {path.get('summary') or '미작성'}",
                f"- **위험인자**: {', '.join(clinical_axes.get('risk_factors') or []) or '미작성'}",
                f"- **자연경과**: {prognosis.get('natural_history') or '미작성'}",
                f"- **치료 원칙**: {therapy.get('principles') or '미작성'}",
                f"- **역학**: {epi.get('frequency') or '미작성'}",
            ])
        content.append("")
        (disease_dir / f"{safe(cid)}.md").write_text("\n".join(frontmatter + content), encoding="utf-8")

    disease_like_count = sum(
        row.get("node_type") in {"disease", "neoplasm", "syndrome"} for row in concepts.values()
    )
    classification_count = sum(row.get("node_type") == "category" for row in concepts.values())
    index = [
        "---", "tags: [ontology, index]", "---", "# P:accine Ontology Mirror", "",
        "> 이 vault는 `concept_registry.json`에서 생성되는 읽기 전용 소비자 뷰입니다.", "",
        f"- 질환: **{disease_like_count}**", f"- 로컬 분류노드: **{classification_count}**",
        f"- 소견: **{len(findings)}**", f"- 임상 축 노드: **{len(axis_nodes)}**", f"- MONDO 분류노드: **{len(taxonomy)}**",
        f"- 비질환 타입 전환: **{len(typed_entities)}**",
        "- 모든 자동 산출은 `needs_review=true`", "", "## 시작점",
        "- [[Diseases/multiple_myeloma|다발골수종]]",
        "- [[Diseases/asthma|천식]]",
        "- [[Diseases/acute_ischemic_stroke|급성 허혈성 뇌졸중]]",
        "",
    ]
    (out / "Ontology Home.md").write_text("\n".join(index), encoding="utf-8")

    graph_config = {
        "collapse-filter": False, "search": "", "showTags": False, "showAttachments": False,
        "hideUnresolved": True, "showOrphans": True, "collapse-color-groups": False,
        "colorGroups": [
            {"query": "path:Diseases", "color": {"a": 1, "rgb": 5025616}},
            {"query": "path:Findings", "color": {"a": 1, "rgb": 3199183}},
            {"query": "path:Taxonomy", "color": {"a": 1, "rgb": 10181046}},
            {"query": "path:Axes", "color": {"a": 1, "rgb": 15769039}},
            {"query": "path:\"Typed Entities\"", "color": {"a": 1, "rgb": 11043876}},
        ],
        "collapse-display": False, "showArrow": True, "textFadeMultiplier": 0,
        "nodeSizeMultiplier": 1, "lineSizeMultiplier": 1, "collapse-forces": False,
        "centerStrength": 0.5, "repelStrength": 10, "linkStrength": 1, "linkDistance": 250,
        "scale": 1, "close": True,
    }
    (out / ".obsidian" / "graph.json").write_text(json.dumps(graph_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / ".obsidian" / "app.json").write_text(json.dumps({"showLineNumber": True, "alwaysUpdateLinks": False}, indent=2) + "\n", encoding="utf-8")
    (meta_dir / "README.md").write_text(
        "# Generated vault\n\n원본 JSON을 수정한 뒤 exporter를 다시 실행하세요. 이 폴더의 생성 노트는 직접 편집하지 않습니다.\n",
        encoding="utf-8",
    )
    return {
        "diseases": disease_like_count, "classification_nodes": classification_count,
        "active_concepts": len(concepts), "typed_entities": len(typed_entities),
        "findings": len(findings), "axes": len(axis_nodes),
        "taxonomy": len(taxonomy), "out": str(out),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--watch", action="store_true", help="poll registry mtime and refresh generated notes")
    parser.add_argument("--interval", type=float, default=1.5)
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    last = None
    while True:
        stamp = (
            REGISTRY.stat().st_mtime_ns,
            FINDINGS.stat().st_mtime_ns,
            AXES.stat().st_mtime_ns if AXES.exists() else 0,
            TYPED_ENTITIES.stat().st_mtime_ns if TYPED_ENTITIES.exists() else 0,
        )
        if stamp != last:
            stats = export(out)
            print(
                f"obsidian_vault diseases={stats['diseases']} typed_entities={stats['typed_entities']} "
                f"classification={stats['classification_nodes']} findings={stats['findings']} "
                f"axes={stats['axes']} taxonomy={stats['taxonomy']} -> {out}",
                flush=True,
            )
            last = stamp
        if not args.watch:
            break
        time.sleep(max(args.interval, 0.5))


if __name__ == "__main__":
    main()
