#!/usr/bin/env python3
"""Serve an Obsidian-like, auto-refreshing local ontology graph."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
from collections import Counter
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jsonschema import Draft202012Validator

try:
    from scripts.build_typed_entity_registry import load_active_entities
except ModuleNotFoundError:  # direct script execution
    from build_typed_entity_registry import load_active_entities

try:
    from src.services.external_kg_review import list_external_kg_review
except ModuleNotFoundError:  # direct script execution outside the repository root
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.services.external_kg_review import list_external_kg_review


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data_private" / "concept_registry.json"
FINDINGS = ROOT / "data_private" / "curriculum" / "finding_registry.json"
AXES = ROOT / "data_private" / "curriculum" / "axis_registry.json"
TYPED_ENTITIES = ROOT / "data_private" / "curriculum" / "typed_entity_registry.json"
INDEX = ROOT / "frontend" / "ontology_graph_live.html"
EXTERNAL_KG_DIR = ROOT / "data_private" / "external_kg" / "primekg"
EXTERNAL_KG_PROFILES = {
    "core20": {
        "label": "PrimeKG 혈액종양 핵심 20",
        "candidate_graph": EXTERNAL_KG_DIR / "heme_onc_phenotype_candidate_graph.json",
        "validation_report": EXTERNAL_KG_DIR / "heme_onc_validation_report.json",
        "review_worklist": EXTERNAL_KG_DIR / "review_worklist.json",
    },
    "heme_onc_full": {
        "label": "PrimeKG 혈액종양 전체 감사 범위",
        "candidate_graph": EXTERNAL_KG_DIR
        / "heme_onc_full"
        / "heme_onc_phenotype_candidate_graph.json",
        "validation_report": EXTERNAL_KG_DIR
        / "heme_onc_full"
        / "heme_onc_validation_report.json",
        "review_worklist": EXTERNAL_KG_DIR / "heme_onc_full" / "review_worklist.json",
    },
}
DEFAULT_EXTERNAL_KG_PROFILE = "core20"
EXTERNAL_KG_CANDIDATES = EXTERNAL_KG_PROFILES[DEFAULT_EXTERNAL_KG_PROFILE]["candidate_graph"]
EXTERNAL_KG_CANDIDATE_SCHEMA = ROOT / "schemas" / "external_kg_candidate_graph.schema.json"
MAX_EXTERNAL_NODES = 500

EXTERNAL_FAIL_CLOSED_REVIEW = {
    "status": "external_candidate",
    "needs_review": True,
    "medical_approval": False,
    "student_visible": False,
    "analytics_eligible": False,
    "promotion_status": "not_promoted",
    "reviewer_id": None,
    "reviewed_at": None,
}

PART = {1:"의학총론",2:"주요증상",3:"약리",4:"혈액종양",5:"감염",6:"순환기",7:"호흡기",8:"중환자",9:"신장비뇨",10:"소화기",11:"면역류마",12:"내분비",13:"신경",14:"중독",15:"환경",16:"유전",17:"국제",18:"노화",19:"자문",20:"신흥"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def external_profile(name: str | None) -> tuple[str, dict]:
    """Resolve only an allow-listed external profile; never accept a file path."""
    key = _text(name) or DEFAULT_EXTERNAL_KG_PROFILE
    if key not in EXTERNAL_KG_PROFILES:
        key = DEFAULT_EXTERNAL_KG_PROFILE
    return key, EXTERNAL_KG_PROFILES[key]


def public_asset_path(request_path: str) -> Path | None:
    """Expose only the self-contained graph page, never other repository assets."""
    if request_path in {"/", "/index.html", "/frontend/ontology_graph_live.html"}:
        return INDEX if INDEX.is_file() else None
    return None


@lru_cache(maxsize=1)
def _external_candidate_validator() -> Draft202012Validator:
    return Draft202012Validator(load(EXTERNAL_KG_CANDIDATE_SCHEMA))


def _external_candidate_payload_is_safe(payload: dict) -> bool:
    """Reject malformed or provenance-mixed overlays before visualization."""
    try:
        _external_candidate_validator().validate(payload)
    except Exception:
        return False

    snapshot = payload.get("snapshot") or {}
    if payload.get("review_policy") != EXTERNAL_FAIL_CLOSED_REVIEW:
        return False
    provenance_keys = (
        "snapshot_id",
        "provider",
        "dataset_name",
        "dataset_version",
        "artifact_sha256",
        "license",
        "license_url",
        "redistribution_status",
        "source_url",
    )
    candidate_ids: set[str] = set()
    for edge in payload.get("edges") or []:
        if edge.get("review") != EXTERNAL_FAIL_CLOSED_REVIEW:
            return False
        candidate_id = _text(edge.get("candidate_edge_id"))
        if not candidate_id or candidate_id in candidate_ids:
            return False
        candidate_ids.add(candidate_id)
        provenance = edge.get("provenance") or {}
        if any(provenance.get(key) != snapshot.get(key) for key in provenance_keys):
            return False
    return True


def ko_label(node: dict, fallback: str) -> str:
    for alias in node.get("aliases", []):
        if any("가" <= ch <= "힣" for ch in str(alias)):
            return str(alias)
    return fallback.replace("_", " ")


def group(node: dict) -> str:
    h = (node.get("evidence") or {}).get("harrison") or {}
    specialty = node.get("specialty") or ""
    if specialty:
        return re.split(r"[/·]", specialty)[0].strip()
    return PART.get(h.get("part"), "기타")


def _text(value: object) -> str:
    return str(value or "").strip()


def _curie(endpoint: dict) -> str:
    return _text(endpoint.get("curie") or endpoint.get("id") or endpoint.get("identifier"))


def _external_node_id(source_name: str, curie: str) -> str:
    """Return an identity that can never collide with a canonical graph node."""
    digest = hashlib.sha256(f"{source_name}\0{curie}".encode("utf-8")).hexdigest()[:20]
    source_slug = re.sub(r"[^a-z0-9]+", "-", source_name.lower()).strip("-") or "external-kg"
    return f"external:{source_slug}:{digest}"


def _canonical_id_from_endpoint(
    endpoint: dict,
    concepts: dict[str, dict],
    mondo_to_concepts: dict[str, list[str]],
) -> str | None:
    """Resolve only explicit identifiers; never infer a disease from a label."""
    curie = _curie(endpoint)
    if curie.upper().startswith("PACCINE:"):
        candidate = curie.split(":", 1)[1]
        if candidate in concepts:
            return candidate

    exact_xrefs: set[str] = set()
    if curie.upper().startswith("MONDO:"):
        exact_xrefs.add(curie.upper())
    for value in endpoint.get("xrefs") or []:
        if isinstance(value, dict):
            value = value.get("curie") or value.get("id")
        value = _text(value).upper()
        if value.startswith("MONDO:"):
            exact_xrefs.add(value)
    matches = {
        concept_id
        for mondo_id in exact_xrefs
        for concept_id in mondo_to_concepts.get(mondo_id, [])
    }
    return next(iter(matches)) if len(matches) == 1 else None


def external_candidate_overlay(
    concepts: dict[str, dict],
    path: Path = EXTERNAL_KG_CANDIDATES,
    limit: int = MAX_EXTERNAL_NODES,
) -> dict:
    """Build a fail-closed, display-only overlay from a candidate graph artifact."""
    limit = max(0, min(int(limit), MAX_EXTERNAL_NODES))
    empty = {
        "available": False,
        "path": str(path),
        "nodes": [],
        "edges": [],
        "candidate_nodes": 0,
        "candidate_edges": 0,
        "truncated": False,
        "source": "PrimeKG",
    }
    if not path.is_file() or limit == 0:
        return empty
    try:
        payload = load(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return empty
    if not _external_candidate_payload_is_safe(payload):
        return empty

    source_meta = payload.get("source") or payload.get("source_graph") or payload.get("snapshot") or {}
    source_name = (
        _text(
            source_meta.get("name")
            or source_meta.get("dataset_name")
            or source_meta.get("provider")
            if isinstance(source_meta, dict) else source_meta
        )
        or "PrimeKG"
    )
    node_index = {
        _curie(row): row
        for row in payload.get("nodes") or []
        if isinstance(row, dict) and _curie(row)
    }
    mondo_to_concepts: dict[str, list[str]] = {}
    for concept_id, row in concepts.items():
        mondo_id = _text(
            (((row.get("evidence") or {}).get("ontology_xref") or {}).get("mondo_id"))
        ).upper()
        if mondo_id:
            mondo_to_concepts.setdefault(mondo_id, []).append(concept_id)

    output_nodes: dict[str, dict] = {}
    output_edges: list[dict] = []
    seen_edges: set[tuple[str, str, str, str]] = set()
    source_edges = [row for row in payload.get("edges") or [] if isinstance(row, dict)]
    source_edges.sort(
        key=lambda row: _text(row.get("candidate_edge_id") or row.get("edge_id") or row.get("id"))
    )
    eligible_external_curies: set[str] = set()

    for row in source_edges:
        subject = row.get("subject") if isinstance(row.get("subject"), dict) else {}
        obj = row.get("object") if isinstance(row.get("object"), dict) else {}
        subject_curie, object_curie = _curie(subject), _curie(obj)
        subject_meta = {**node_index.get(subject_curie, {}), **subject}
        object_meta = {**node_index.get(object_curie, {}), **obj}
        subject_local = _canonical_id_from_endpoint(subject_meta, concepts, mondo_to_concepts)
        object_local = _canonical_id_from_endpoint(object_meta, concepts, mondo_to_concepts)
        if bool(subject_local) == bool(object_local):
            # No canonical anchor, or a canonical-to-canonical edge: neither belongs in this overlay.
            continue
        canonical_id = subject_local or object_local
        external_meta = object_meta if subject_local else subject_meta
        external_curie = _curie(external_meta)
        if not canonical_id or not external_curie:
            continue
        external_id = _external_node_id(source_name, external_curie)
        if external_id not in output_nodes and len(output_nodes) >= limit:
            eligible_external_curies.add(external_curie)
            continue
        eligible_external_curies.add(external_curie)

        predicate = row.get("predicate") if isinstance(row.get("predicate"), dict) else {}
        predicate_name = _text(predicate.get("canonical") or predicate.get("raw") or row.get("relation"))
        edge_identity = _text(row.get("candidate_edge_id") or row.get("edge_id") or row.get("id"))
        edge_key = (canonical_id, external_id, predicate_name, edge_identity)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        provenance = row.get("provenance") or {}
        provenance_sources = (
            provenance.get("source_refs")
            or provenance.get("sources")
            or provenance.get("publications")
            if isinstance(provenance, dict) else []
        )
        if not isinstance(provenance_sources, list):
            provenance_sources = [provenance_sources]
        label = _text(external_meta.get("label") or external_meta.get("name") or external_curie)
        categories = external_meta.get("categories") or []
        external_type = _text(
            external_meta.get("node_type")
            or external_meta.get("type")
            or external_meta.get("kind")
            or (categories[0] if categories else "")
        ) or "external_entity"
        output_nodes.setdefault(external_id, {"data": {
            "id": external_id,
            "external_id": external_curie,
            "concept_id": external_curie,
            "label": label,
            "kind": "external_candidate",
            "group": f"{source_name} 후보",
            "node_type": external_type,
            "harrison": "",
            "mondo": external_curie,
            "clinical_axes": False,
            "needs_review": True,
            "specialty": "외부 2차 검증 후보",
            "source": source_name,
            "dimension": "external_candidate",
            "claim_id": "",
            "review_status": "external_candidate",
            "medical_approval": False,
            "applicability": "unknown",
            "claim_entailment": "unverified",
            "external_candidate": True,
        }})
        output_edges.append({"data": {
            "id": f"external-edge:{hashlib.sha256(repr(edge_key).encode('utf-8')).hexdigest()[:20]}",
            "source": f"d:{canonical_id}",
            "target": external_id,
            "relation": "EXTERNAL_CANDIDATE",
            "candidate_predicate": predicate_name,
            "candidate_edge_id": edge_identity,
            "candidate_source": source_name,
            "polarity": _text(row.get("polarity") or "unknown"),
            "direction": _text(row.get("direction") or "unknown"),
            "undirected": bool(row.get("undirected")),
            "provenance": ", ".join(_text(value) for value in provenance_sources if _text(value)),
            "snapshot_id": _text(provenance.get("snapshot_id")),
            "artifact_sha256": _text(provenance.get("artifact_sha256")),
            "source_record_id": _text(provenance.get("source_record_id")),
            "source_record_sha256": _text(provenance.get("source_record_sha256")),
            "license": _text(provenance.get("license")),
            "redistribution_status": _text(provenance.get("redistribution_status") or "unknown"),
            "source_url": _text(provenance.get("source_url")),
            "review_status": "external_candidate",
            "medical_approval": False,
            "applicability": "unknown",
            "claim_entailment": "unverified",
            "external_candidate": True,
        }})

    return {
        **empty,
        "available": True,
        "nodes": list(output_nodes.values()),
        "edges": output_edges,
        "candidate_nodes": len(output_nodes),
        "candidate_edges": len(output_edges),
        "truncated": len(eligible_external_curies) > len(output_nodes),
        "source": source_name,
    }


def graph_payload(
    *,
    include_external: bool = False,
    external_limit: int = MAX_EXTERNAL_NODES,
    external_path: Path | None = None,
    external_profile_name: str = DEFAULT_EXTERNAL_KG_PROFILE,
) -> dict:
    registry = load(REGISTRY)
    all_concepts = registry["concepts"]
    typed_entities = load_active_entities(TYPED_ENTITIES)
    concepts = {cid: row for cid, row in all_concepts.items() if cid not in typed_entities}
    finding_rows = load(FINDINGS).get("findings", [])
    findings = {row["finding_id"]: row for row in finding_rows}
    axis_payload = load(AXES) if AXES.exists() else {"nodes": [], "relationships": []}
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}

    for cid, node in concepts.items():
        h = (node.get("evidence") or {}).get("harrison") or {}
        x = (node.get("evidence") or {}).get("ontology_xref") or {}
        nodes[f"d:{cid}"] = {
            "data": {
                "id": f"d:{cid}", "concept_id": cid, "label": ko_label(node, cid),
                "kind": "classification" if node.get("node_type") == "category" else "disease",
                "group": group(node), "node_type": node.get("node_type") or "disease",
                "harrison": f"Ch{h.get('chapter')} p{h.get('page')} · {h.get('title')}" if h.get("chapter") else "Harrison 미연결",
                "mondo": x.get("mondo_id") or "", "clinical_axes": bool(node.get("clinical_axes")),
                "needs_review": bool(node.get("needs_review", True)), "specialty": node.get("specialty") or "",
                "source": node.get("source") or "concept_registry", "dimension": "",
                "claim_id": "", "review_status": "draft_unreviewed",
                "medical_approval": False, "applicability": "unknown", "claim_entailment": "unverified",
            }
        }
    for cid, row in typed_entities.items():
        entity_type = row.get("entity_type") or "typed_entity"
        entity_id = row["entity_id"]
        nodes[entity_id] = {
            "data": {
                "id": entity_id, "concept_id": cid, "label": row.get("label") or cid.replace("_", " "),
                "kind": entity_type, "group": entity_type, "node_type": entity_type,
                "harrison": "비질환 타입 레이어", "mondo": "", "clinical_axes": False,
                "needs_review": True, "specialty": row.get("destination_layer") or "",
                "source": "typed_entity_registry", "dimension": row.get("entity_subtype") or "",
                "claim_id": "", "review_status": "draft_unreviewed",
                "medical_approval": False, "applicability": "unknown", "claim_entailment": "unverified",
            }
        }
    for fid, row in findings.items():
        nodes[f"f:{fid}"] = {
            "data": {
                "id": f"f:{fid}", "concept_id": fid, "label": row.get("hpo_label") or fid.replace("_", " "),
                "kind": "finding", "group": row.get("body_system") or "finding", "node_type": "finding",
                "harrison": "", "mondo": row.get("hpo_id") or "", "clinical_axes": False,
                "needs_review": True, "specialty": row.get("body_system") or "",
                "source": row.get("source") or "finding_registry", "dimension": "symptom_or_finding",
                "claim_id": "", "review_status": "draft_unreviewed",
                "medical_approval": False, "applicability": "unknown", "claim_entailment": "unverified",
            }
        }
    for row in axis_payload.get("nodes", []):
        aid = row["axis_id"]
        nodes[aid] = {
            "data": {
                "id": aid, "concept_id": row.get("canonical_id") or aid, "label": row.get("label") or aid,
                "kind": row.get("axis_type") or "axis", "group": row.get("axis_type") or "axis",
                "node_type": row.get("axis_type") or "axis", "harrison": "",
                "mondo": "", "clinical_axes": False, "needs_review": bool(row.get("needs_review", True)),
                "specialty": "", "source": ", ".join(row.get("sources") or []),
                "dimension": row.get("dimension") or "",
                "claim_id": row.get("claim_id") or "",
                "review_status": row.get("review_status") or "draft_unreviewed",
                "medical_approval": bool(row.get("medical_approval")),
                "applicability": row.get("applicability") or "unknown",
                "claim_entailment": (row.get("provenance") or {}).get("claim_entailment") or "unverified",
            }
        }

    for cid, node in concepts.items():
        start = f"d:{cid}"
        for parent in node.get("is_a", []):
            tid = parent["id"]
            if tid in concepts:
                end = f"d:{tid}"
            else:
                end = f"t:{tid}"
                nodes.setdefault(end, {"data": {
                    "id": end, "concept_id": tid, "label": parent.get("label") or tid,
                    "kind": "taxonomy", "group": "MONDO", "node_type": "taxonomy",
                    "harrison": "", "mondo": tid, "clinical_axes": False, "needs_review": True, "specialty": "MONDO",
                    "source": "MONDO", "dimension": "taxonomy",
                }})
            edges[(start, end, "is_a")] = {"data": {"id": f"e:{len(edges)}", "source": start, "target": end, "relation": "is_a"}}
        for relation, values in (node.get("edges") or {}).items():
            if not isinstance(values, list):
                continue
            for edge in values:
                target = edge.get("id") if isinstance(edge, dict) else edge
                if target in concepts:
                    end = f"d:{target}"
                elif target in typed_entities:
                    end = typed_entities[target]["entity_id"]
                elif target in findings:
                    end = f"f:{target}"
                else:
                    continue
                key = (start, end, relation)
                edges[key] = {"data": {"id": f"e:{len(edges)}", "source": start, "target": end, "relation": relation}}
    for fid, row in findings.items():
        for cid in row.get("presented_by", []):
            if cid in concepts:
                key = (f"d:{cid}", f"f:{fid}", "presents_with")
                edges[key] = {"data": {"id": f"e:{len(edges)}", "source": key[0], "target": key[1], "relation": key[2]}}

    for row in axis_payload.get("relationships", []):
        start = f"d:{row.get('disease_concept_id')}"
        end = row.get("axis_id")
        relation = row.get("relation")
        if start in nodes and end in nodes and relation:
            key = (start, end, relation)
            edges[key] = {"data": {
                "id": f"e:{len(edges)}", "source": start, "target": end,
                "relation": relation, "provenance": row.get("source") or "axis_registry",
                "claim_id": row.get("claim_id") or "",
                "review_status": row.get("review_status") or "draft_unreviewed",
                "medical_approval": bool(row.get("medical_approval")),
                "applicability": row.get("applicability") or "unknown",
                "claim_entailment": (row.get("provenance") or {}).get("claim_entailment") or "unverified",
            }}

    version = max(
        REGISTRY.stat().st_mtime_ns,
        FINDINGS.stat().st_mtime_ns,
        AXES.stat().st_mtime_ns if AXES.exists() else 0,
        TYPED_ENTITIES.stat().st_mtime_ns if TYPED_ENTITIES.exists() else 0,
    )
    overlay = None
    if include_external:
        resolved_profile, profile_config = external_profile(external_profile_name)
        candidate_path = external_path or profile_config["candidate_graph"]
        overlay = external_candidate_overlay(
            concepts,
            path=candidate_path,
            limit=external_limit,
        )
        for row in overlay["nodes"]:
            nodes[row["data"]["id"]] = row
        for row in overlay["edges"]:
            data = row["data"]
            edges[(data["source"], data["target"], data["id"])] = row
        if candidate_path.exists():
            version = max(version, candidate_path.stat().st_mtime_ns)

    kind_counts = Counter(n["data"]["kind"] for n in nodes.values())
    relation_counts = Counter(e["data"]["relation"] for e in edges.values())
    disease_like_count = sum(
        row.get("node_type") in {"disease", "neoplasm", "syndrome"} for row in concepts.values()
    )
    classification_count = sum(row.get("node_type") == "category" for row in concepts.values())
    result = {
        "version": str(version), "nodes": list(nodes.values()), "edges": list(edges.values()),
        "stats": {
            "nodes": len(nodes), "edges": len(edges), "kinds": dict(kind_counts),
            "relations": dict(relation_counts), "concepts": len(concepts),
            "diseases": disease_like_count, "classification_nodes": classification_count,
            "active_concepts": len(concepts), "source_concepts": len(all_concepts),
            "typed_entities": len(typed_entities),
            "axis_nodes": len(axis_payload.get("nodes", [])), "finding_nodes": len(findings),
            "axis_claims": int((axis_payload.get("stats") or {}).get("nodes") or 0)
            + int((axis_payload.get("stats") or {}).get("relationships") or 0),
            "approved_axis_claims": int((axis_payload.get("stats") or {}).get("medical_approval_claims") or 0),
        },
    }
    if overlay is not None:
        result["stats"]["external_overlay"] = {
            "requested": True,
            "available": overlay["available"],
            "profile": resolved_profile,
            "profile_label": profile_config["label"],
            "source": overlay["source"],
            "candidate_nodes": overlay["candidate_nodes"],
            "candidate_edges": overlay["candidate_edges"],
            "limit": max(0, min(int(external_limit), MAX_EXTERNAL_NODES)),
            "truncated": overlay["truncated"],
        }
    return result


class Handler(BaseHTTPRequestHandler):
    def _write_body(self, raw: bytes) -> None:
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            # A graph reload can cancel the previous multi-megabyte response.
            # Treat that as a normal client disconnect, not a server failure.
            return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/external-validation":
            query = parse_qs(parsed.query)
            try:
                payload = list_external_kg_review(
                    profile=(query.get("profile") or [DEFAULT_EXTERNAL_KG_PROFILE])[0],
                    priority=(query.get("priority") or [""])[0],
                    classification=(query.get("classification") or [""])[0],
                    evaluation_status=(query.get("evaluation_status") or [""])[0],
                    polarity=(query.get("polarity") or [""])[0],
                    query=(query.get("q") or [""])[0],
                    offset=int((query.get("offset") or ["0"])[0]),
                    limit=int((query.get("limit") or ["50"])[0]),
                )
                status = 200
            except (TypeError, ValueError) as exc:
                payload = {
                    "status": "invalid_request",
                    "detail": str(exc),
                    "safety_boundary": {
                        "medical_approval": False,
                        "student_visible": False,
                        "analytics_eligible": False,
                        "generation_eligible": False,
                        "canonical_ontology_mutation": False,
                        "automatic_promotion": False,
                    },
                    "items": [],
                }
                status = 400
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self._write_body(raw)
            return
        if parsed.path == "/api/graph":
            query = parse_qs(parsed.query)
            include_external = (query.get("include_external") or [""])[0].lower() in {"1", "true", "yes"}
            external_profile_name = (query.get("external_profile") or [DEFAULT_EXTERNAL_KG_PROFILE])[0]
            try:
                external_limit = int((query.get("external_limit") or [str(MAX_EXTERNAL_NODES)])[0])
            except ValueError:
                external_limit = MAX_EXTERNAL_NODES
            raw = json.dumps(
                graph_payload(
                    include_external=include_external,
                    external_limit=external_limit,
                    external_profile_name=external_profile_name,
                ),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self._write_body(raw)
            return
        path = public_asset_path(parsed.path)
        if path is None:
            self.send_error(404)
            return
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self._write_body(raw)

    def log_message(self, fmt, *args):
        request_line = str(args[0]) if args else ""
        if "/api/graph" not in request_line and "/api/external-validation" not in request_line:
            super().log_message(fmt, *args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not INDEX.exists():
        raise SystemExit(f"missing frontend: {INDEX}")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"ontology graph: http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
