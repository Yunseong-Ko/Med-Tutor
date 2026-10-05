"""Source-neutral adapters for external biomedical knowledge graphs.

This module deliberately performs no download and grants no clinical trust.  It
normalizes already available PrimeKG CSV rows and OptimusKG-style row mappings
into the external candidate contract.  Promotion into P:accine's canonical
ontology is a separate, human-reviewed operation.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


_CURIE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[^\s]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

FAIL_CLOSED_REVIEW: dict[str, Any] = {
    "status": "external_candidate",
    "needs_review": True,
    "medical_approval": False,
    "student_visible": False,
    "analytics_eligible": False,
    "promotion_status": "not_promoted",
    "reviewer_id": None,
    "reviewed_at": None,
}


def canonical_sha256(value: Any) -> str:
    """Return a deterministic digest for JSON-like source records."""

    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and _text(value):
            return value
    return None


def _slug(value: Any, *, fallback: str) -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not text:
        text = fallback
    if not text[0].isalpha():
        text = f"relation_{text}"
    return text


def _provider_slug(value: Any) -> str:
    provider = _slug(value, fallback="external")
    return provider.replace("relation_", "", 1) if provider.startswith("relation_") else provider


def _list_of_strings(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            candidate = _first(item, ("id", "curie", "name", "label", "resource"))
            text = _text(candidate) or json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        else:
            text = _text(item)
        if text and text not in result:
            result.append(text)
    return result


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    normalized = _text(value).lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def _namespace_prefix(namespace: Any) -> str:
    raw = _text(namespace)
    aliases = {
        "drugbank": "DrugBank",
        "hpo": "HP",
        "hp": "HP",
        "mondo": "MONDO",
        "mesh": "MESH",
        "omim": "OMIM",
        "uniprot": "UniProtKB",
        "uniprotkb": "UniProtKB",
        "ncbi gene": "NCBIGene",
        "ncbigene": "NCBIGene",
    }
    if raw.lower() in aliases:
        return aliases[raw.lower()]
    prefix = re.sub(r"[^A-Za-z0-9._-]+", "", raw)
    if not prefix or not prefix[0].isalpha():
        raise ValueError(f"Cannot derive a CURIE prefix from namespace: {raw!r}")
    return prefix


def _curie(identifier: Any, *, namespace: Any = None, fallback_namespace: str) -> str:
    raw = _text(identifier)
    if not raw:
        raise ValueError("External node identifier is required")
    if _CURIE_RE.fullmatch(raw):
        prefix, local_id = raw.split(":", 1)
        if prefix.upper() in {"MONDO", "HP", "HPO"} and local_id.isdigit():
            canonical_prefix = "MONDO" if prefix.upper() == "MONDO" else "HP"
            return f"{canonical_prefix}:{local_id.zfill(7)}"
        return raw
    prefix = _namespace_prefix(namespace or fallback_namespace)
    if prefix.upper() in {"MONDO", "HP", "HPO"} and raw.isdigit():
        prefix = "MONDO" if prefix.upper() == "MONDO" else "HP"
        raw = raw.zfill(7)
    curie = f"{prefix}:{raw}"
    if not _CURIE_RE.fullmatch(curie):
        raise ValueError(f"Cannot normalize external identifier as CURIE: {raw!r}")
    return curie


def _node(
    *,
    identifier: Any,
    label: Any,
    categories: Any,
    namespace: Any,
    source_local_id: Any,
    fallback_namespace: str,
) -> dict[str, Any]:
    curie = _curie(identifier, namespace=namespace, fallback_namespace=fallback_namespace)
    category_values = _list_of_strings(categories) or ["unknown"]
    return {
        "curie": curie,
        "label": _text(label) or curie,
        "categories": sorted(category_values),
        "source_namespace": _text(namespace) or None,
        "source_local_id": _text(source_local_id) or _text(identifier),
    }


def _predicate(*, source_label: Any, source_code: Any = None, predicate_curie: Any = None) -> dict[str, Any]:
    label = _text(source_label) or _text(source_code) or _text(predicate_curie)
    if not label:
        raise ValueError("External relation label is required")
    curie_value = _text(predicate_curie)
    if not curie_value:
        for candidate in (source_code, source_label):
            text = _text(candidate)
            if _CURIE_RE.fullmatch(text):
                curie_value = text
                break
    if curie_value and not _CURIE_RE.fullmatch(curie_value):
        raise ValueError(f"Invalid predicate CURIE: {curie_value!r}")
    canonical_source = label.split(":", 1)[-1] if _CURIE_RE.fullmatch(label) else label
    return {
        "canonical": _slug(canonical_source, fallback="related_to"),
        "curie": curie_value or None,
        "source_label": label,
        "source_code": _text(source_code) or None,
    }


def _polarity(row: Mapping[str, Any], predicate: Mapping[str, Any]) -> str:
    explicit = _first(row, ("polarity", "assertion_polarity", "edge_polarity"))
    normalized = _text(explicit).lower().replace("-", "_").replace(" ", "_")
    if normalized in {"affirmed", "positive", "present", "true", "+", "1"}:
        return "affirmed"
    if normalized in {"negated", "negative", "absent", "false", "-", "0"}:
        return "negated"
    if explicit is not None:
        return "unknown"

    negated = _bool(row.get("negated"))
    if negated is not None:
        return "negated" if negated else "affirmed"

    relation = "_".join(
        filter(
            None,
            (
                _text(predicate.get("canonical")),
                _slug(predicate.get("source_label"), fallback="related_to"),
            ),
        )
    )
    if any(token in relation for token in ("phenotype_absent", "absent_phenotype", "not_present")):
        return "negated"
    if any(token in relation for token in ("phenotype_present", "present_phenotype")):
        return "affirmed"
    return "unknown"


def _direction(row: Mapping[str, Any], *, default_undirected: bool = False) -> tuple[str, bool]:
    undirected_value = _first(row, ("undirected", "is_undirected"))
    undirected = _bool(undirected_value)
    directed_value = _first(row, ("directed", "is_directed"))
    directed = _bool(directed_value)

    raw_direction = _text(_first(row, ("direction", "edge_direction"))).lower()
    raw_direction = raw_direction.replace("-", "_").replace(" ", "_")
    if raw_direction in {"undirected", "bidirectional", "both", "symmetric"}:
        direction = "undirected"
    elif raw_direction in {
        "subject_to_object",
        "source_to_target",
        "x_to_y",
        "forward",
        "directed",
    }:
        direction = "subject_to_object"
    elif raw_direction in {"object_to_subject", "target_to_source", "y_to_x", "reverse"}:
        direction = "object_to_subject"
    else:
        direction = "unknown"

    if undirected is True or directed is False:
        if direction not in {"unknown", "undirected"}:
            raise ValueError("External row has conflicting direction and undirected flags")
        return "undirected", True
    if direction == "undirected":
        if undirected is False or directed is True:
            raise ValueError("External row has conflicting direction and directed flags")
        return "undirected", True
    if directed is True and direction == "unknown":
        direction = "subject_to_object"
    if (
        default_undirected
        and undirected is None
        and directed is None
        and not raw_direction
    ):
        return "undirected", True
    return direction, False


def _snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    artifact = snapshot.get("artifact") if isinstance(snapshot.get("artifact"), Mapping) else {}
    license_value = snapshot.get("license")
    license_record = license_value if isinstance(license_value, Mapping) else {}
    provider_raw = _text(snapshot.get("provider"))
    if not provider_raw:
        raise ValueError("Snapshot provider is required")
    license_name = (
        _text(license_record.get("name"))
        if isinstance(license_value, Mapping)
        else _text(license_value)
    )
    artifact_sha256 = _text(
        artifact.get("content_sha256")
        or snapshot.get("artifact_sha256")
        or snapshot.get("content_sha256")
        or snapshot.get("sha256")
    )
    values = {
        "snapshot_id": _text(snapshot.get("snapshot_id")),
        "provider": _provider_slug(provider_raw),
        "dataset_name": _text(snapshot.get("dataset_name") or snapshot.get("name")),
        "dataset_version": _text(snapshot.get("dataset_version") or snapshot.get("version")),
        "artifact_sha256": artifact_sha256,
        "license": license_name,
        "license_url": _text(license_record.get("url") or snapshot.get("license_url")) or None,
        "redistribution_status": _text(
            license_record.get("redistribution_status") or snapshot.get("redistribution_status") or "unknown"
        ).lower(),
        "source_url": _text(snapshot.get("source_url")),
    }
    for key in ("snapshot_id", "dataset_name", "dataset_version", "license", "source_url"):
        if not values[key]:
            raise ValueError(f"Snapshot {key} is required")
    if not _SHA256_RE.fullmatch(values["artifact_sha256"]):
        raise ValueError("Snapshot artifact_sha256 must be a lowercase SHA-256 digest")
    if values["redistribution_status"] not in {"allowed", "restricted", "prohibited", "unknown"}:
        raise ValueError("Snapshot redistribution_status is invalid")
    return values


def _record_provenance(
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    source_record_id: Any = None,
) -> dict[str, Any]:
    snapshot_value = _snapshot(snapshot)
    record_hash = canonical_sha256(row)
    record_id = _text(source_record_id) or f"{snapshot_value['provider']}:{record_hash[:20]}"
    source_refs = _list_of_strings(
        _first(row, ("source_refs", "sources", "primary_knowledge_source", "knowledge_sources"))
    )
    publications = _list_of_strings(
        _first(row, ("publications", "publication", "pmids", "pmid", "references"))
    )
    return {
        **snapshot_value,
        "source_record_id": record_id,
        "source_record_sha256": record_hash,
        "source_refs": source_refs,
        "publications": publications,
    }


def _safe_qualifiers(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get("qualifiers")
    if not isinstance(value, Mapping):
        value = row.get("properties")
    if not isinstance(value, Mapping):
        return {}
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _candidate_edge(
    *,
    subject: dict[str, Any],
    predicate: dict[str, Any],
    object_: dict[str, Any],
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    source_record_id: Any,
    default_undirected: bool = False,
) -> dict[str, Any]:
    direction, undirected = _direction(row, default_undirected=default_undirected)
    provenance = _record_provenance(row, snapshot, source_record_id=source_record_id)
    polarity = _polarity(row, predicate)
    identity = _candidate_identity(
        subject=subject,
        predicate=predicate,
        object_=object_,
        provenance=provenance,
        direction=direction,
        undirected=undirected,
        polarity=polarity,
    )
    return {
        "candidate_edge_id": f"ekg:e:{canonical_sha256(identity)[:24]}",
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "polarity": polarity,
        "direction": direction,
        "undirected": undirected,
        "qualifiers": _safe_qualifiers(row),
        "provenance": provenance,
        "review": deepcopy(FAIL_CLOSED_REVIEW),
    }


def _candidate_identity(
    *,
    subject: Mapping[str, Any],
    predicate: Mapping[str, Any],
    object_: Mapping[str, Any],
    provenance: Mapping[str, Any],
    direction: str,
    undirected: bool,
    polarity: str,
) -> dict[str, Any]:
    """Return the canonical assertion identity used by candidate edge IDs."""
    endpoint_identity = [
        {"curie": subject["curie"], "source_local_id": subject["source_local_id"]},
        {"curie": object_["curie"], "source_local_id": object_["source_local_id"]},
    ]
    if undirected:
        endpoint_identity.sort(key=lambda value: (value["curie"], value["source_local_id"]))
    identity = {
        "snapshot_id": provenance["snapshot_id"],
        "endpoints" if undirected else "subject": (
            endpoint_identity if undirected else subject["curie"]
        ),
        "predicate": predicate["canonical"],
        "direction": direction,
        "undirected": undirected,
        "polarity": polarity,
    }
    if undirected:
        # An undirected assertion has one identity regardless of which endpoint
        # the source CSV serialized as x/y.  Individual source rows remain in
        # provenance and are merged by ``build_candidate_graph``.
        identity["source_code"] = predicate.get("source_code")
    else:
        identity["source_record_id"] = provenance["source_record_id"]
        identity["object"] = object_["curie"]
    return identity


def normalize_primekg_row(row: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one PrimeKG ``kg.csv``-style row.

    Both the current conventional columns (``x_id``/``y_id``) and explicit
    subject/object aliases are accepted.  Existing CURIE spelling and case are
    preserved exactly; unprefixed IDs are namespaced without replacing the raw
    ``source_local_id``.
    """

    snapshot_value = _snapshot(snapshot)
    subject_id = _first(row, ("x_id", "subject_id", "source_id"))
    object_id = _first(row, ("y_id", "object_id", "target_id"))
    subject = _node(
        identifier=subject_id,
        label=_first(row, ("x_name", "subject_name", "source_name")),
        categories=_first(row, ("x_type", "subject_type", "source_type")),
        namespace=_first(row, ("x_source", "subject_namespace", "source_namespace")),
        source_local_id=subject_id or _first(row, ("x_index", "subject_index")),
        fallback_namespace=snapshot_value["provider"],
    )
    object_ = _node(
        identifier=object_id,
        label=_first(row, ("y_name", "object_name", "target_name")),
        categories=_first(row, ("y_type", "object_type", "target_type")),
        namespace=_first(row, ("y_source", "object_namespace", "target_namespace")),
        source_local_id=object_id or _first(row, ("y_index", "object_index")),
        fallback_namespace=snapshot_value["provider"],
    )
    source_code = _first(row, ("relation", "relation_code", "edge_type"))
    source_label = _first(row, ("display_relation", "relation_label", "predicate")) or source_code
    predicate = _predicate(source_label=source_label, source_code=source_code)
    if _text(source_code) in {"disease_phenotype_positive", "disease_phenotype_negative"}:
        # Positive/negative are assertion polarity, not two different semantic
        # predicates.  Keeping ``phenotype_absent`` as the predicate while also
        # setting polarity=negated would create a misleading double negative.
        predicate["canonical"] = "presents_with"
    return _candidate_edge(
        subject=subject,
        predicate=predicate,
        object_=object_,
        row=row,
        snapshot=snapshot,
        source_record_id=_first(row, ("edge_id", "relation_id", "index", "row_id")),
        default_undirected=True,
    )


def _node_record(
    row: Mapping[str, Any],
    *,
    role: str,
    node_lookup: Mapping[str, Mapping[str, Any]] | None,
    fallback_namespace: str,
) -> dict[str, Any]:
    if role == "subject":
        raw = _first(row, ("subject", "subject_id", "source_id", "from", "source"))
        name_keys = ("subject_name", "source_name")
        category_keys = ("subject_categories", "subject_category", "source_categories", "source_category")
        namespace_keys = ("subject_namespace", "source_namespace")
    else:
        raw = _first(row, ("object", "object_id", "target_id", "to", "target"))
        name_keys = ("object_name", "target_name")
        category_keys = ("object_categories", "object_category", "target_categories", "target_category")
        namespace_keys = ("object_namespace", "target_namespace")

    embedded = dict(raw) if isinstance(raw, Mapping) else {}
    identifier = _first(embedded, ("curie", "id", "identifier", "node_id")) or raw
    identifier_text = _text(identifier)
    lookup = dict((node_lookup or {}).get(identifier_text) or {})
    merged = {**lookup, **embedded}
    identifier = _first(merged, ("curie", "id", "identifier", "node_id")) or identifier
    label = _first(merged, ("label", "name")) or _first(row, name_keys)
    categories = _first(merged, ("categories", "category", "types", "type")) or _first(row, category_keys)
    namespace = _first(merged, ("namespace", "identifier_prefix")) or _first(row, namespace_keys)
    source_local_id = _first(merged, ("source_local_id", "id", "identifier", "node_id")) or identifier
    return _node(
        identifier=identifier,
        label=label,
        categories=categories,
        namespace=namespace,
        source_local_id=source_local_id,
        fallback_namespace=fallback_namespace,
    )


def normalize_optimuskg_record(
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    node_lookup: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize an OptimusKG-style JSON/Parquet edge row mapping.

    ``subject`` and ``object`` may be CURIE strings or embedded node mappings.
    A caller may optionally provide a node table keyed by source node ID.
    """

    snapshot_value = _snapshot(snapshot)
    subject = _node_record(
        row,
        role="subject",
        node_lookup=node_lookup,
        fallback_namespace=snapshot_value["provider"],
    )
    object_ = _node_record(
        row,
        role="object",
        node_lookup=node_lookup,
        fallback_namespace=snapshot_value["provider"],
    )
    raw_predicate = _first(row, ("predicate", "relation", "edge_type", "type"))
    predicate_record = dict(raw_predicate) if isinstance(raw_predicate, Mapping) else {}
    predicate_curie = _first(predicate_record, ("curie", "id", "identifier"))
    source_label = _first(predicate_record, ("label", "name")) or raw_predicate
    source_code = _first(row, ("relation_code", "predicate_id")) or predicate_curie or raw_predicate
    predicate = _predicate(
        source_label=source_label,
        source_code=source_code,
        predicate_curie=predicate_curie,
    )
    return _candidate_edge(
        subject=subject,
        predicate=predicate,
        object_=object_,
        row=row,
        snapshot=snapshot,
        source_record_id=_first(row, ("edge_id", "id", "record_id", "row_id")),
    )


def build_candidate_graph(
    edges: Iterable[Mapping[str, Any]],
    snapshot: Mapping[str, Any],
    *,
    local_concept_ids: Iterable[str] = (),
    external_curie_seeds: Iterable[str] = (),
    max_hops: int = 1,
    relation_allowlist: Iterable[str] = (),
    notes: str = "",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble normalized edges into one deterministic candidate graph."""

    if max_hops not in (0, 1, 2):
        raise ValueError("External candidate graph max_hops must be 0, 1, or 2")
    snapshot_value = _snapshot(snapshot)
    raw_edge_values = [deepcopy(dict(edge)) for edge in edges]
    raw_edge_values.sort(
        key=lambda edge: (
            _text(edge.get("candidate_edge_id")),
            canonical_sha256(edge),
        )
    )

    # Validate every raw record before any duplicate collapse.  A malformed or
    # approval-bypassing reverse row must never disappear behind a safe
    # representative.
    for edge in raw_edge_values:
        if edge.get("review") != FAIL_CLOSED_REVIEW:
            raise ValueError("Every external edge must retain the fail-closed review state")
        provenance = edge.get("provenance") if isinstance(edge.get("provenance"), Mapping) else {}
        for key in (
            "snapshot_id",
            "provider",
            "dataset_name",
            "dataset_version",
            "artifact_sha256",
            "license",
            "license_url",
            "redistribution_status",
            "source_url",
        ):
            if provenance.get(key) != snapshot_value.get(key):
                raise ValueError(f"External edge provenance does not match graph snapshot: {key}")
        subject = edge.get("subject")
        object_ = edge.get("object")
        predicate = edge.get("predicate")
        if not all(isinstance(value, Mapping) for value in (subject, object_, predicate)):
            raise ValueError("External candidate edge endpoint or predicate is missing")
        expected_identity = _candidate_identity(
            subject=subject,
            predicate=predicate,
            object_=object_,
            provenance=provenance,
            direction=_text(edge.get("direction")),
            undirected=edge.get("undirected") is True,
            polarity=_text(edge.get("polarity")),
        )
        expected_id = f"ekg:e:{canonical_sha256(expected_identity)[:24]}"
        if edge.get("candidate_edge_id") != expected_id:
            raise ValueError("External candidate edge ID does not match its assertion identity")

    # PrimeKG serializes both orientations of undirected relations.  Collapse
    # those rows by their orientation-neutral candidate ID while retaining the
    # complete record-level provenance in an open qualifier field.
    edge_values: list[dict[str, Any]] = []
    undirected_groups: dict[str, list[dict[str, Any]]] = {}
    for edge in raw_edge_values:
        if edge.get("undirected") is True:
            undirected_groups.setdefault(_text(edge.get("candidate_edge_id")), []).append(edge)
        else:
            edge_values.append(edge)
    for candidate_id, group in sorted(undirected_groups.items()):
        if not candidate_id:
            raise ValueError("External candidate edge ID is required")
        representative = min(group, key=canonical_sha256)
        if len(group) > 1:
            qualifiers = deepcopy(representative.get("qualifiers") or {})
            qualifiers["collapsed_undirected_rows"] = len(group)
            qualifiers["collapsed_source_records"] = sorted(
                [
                    {
                        "subject_curie": (edge.get("subject") or {}).get("curie"),
                        "object_curie": (edge.get("object") or {}).get("curie"),
                        "source_record_id": (edge.get("provenance") or {}).get("source_record_id"),
                        "source_record_sha256": (edge.get("provenance") or {}).get(
                            "source_record_sha256"
                        ),
                        "source_refs": (edge.get("provenance") or {}).get("source_refs") or [],
                        "publications": (edge.get("provenance") or {}).get("publications") or [],
                        "qualifiers": edge.get("qualifiers") or {},
                    }
                    for edge in group
                ],
                key=lambda value: (
                    _text(value.get("source_record_id")),
                    _text(value.get("source_record_sha256")),
                ),
            )
            representative["qualifiers"] = qualifiers
        edge_values.append(representative)
    edge_values.sort(key=lambda edge: _text(edge.get("candidate_edge_id")))

    nodes_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in edge_values:
        for endpoint in (edge.get("subject"), edge.get("object")):
            if not isinstance(endpoint, Mapping):
                raise ValueError("External candidate edge endpoint is missing")
            node_value = dict(endpoint)
            key = (_text(node_value.get("curie")), _text(node_value.get("source_local_id")))
            nodes_by_key.setdefault(key, node_value)

    predicate_counts = Counter(
        _text((edge.get("predicate") or {}).get("canonical")) for edge in edge_values
    )
    category_counts: Counter[str] = Counter()
    for node_value in nodes_by_key.values():
        category_counts.update(_list_of_strings(node_value.get("categories")))

    identity = {
        "snapshot_id": snapshot_value["snapshot_id"],
        "artifact_sha256": snapshot_value["artifact_sha256"],
        "edge_ids": [edge.get("candidate_edge_id") for edge in edge_values],
        "local_concept_ids": sorted(set(map(str, local_concept_ids))),
        "external_curie_seeds": sorted(set(map(str, external_curie_seeds))),
        "max_hops": max_hops,
    }
    return {
        "schema_version": "external_kg_candidate_graph.v1",
        "graph_id": f"external_kg_graph:{snapshot_value['provider']}:{canonical_sha256(identity)[:16]}",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "snapshot": snapshot_value,
        "scope": {
            "local_concept_ids": sorted({_text(value) for value in local_concept_ids if _text(value)}),
            "external_curie_seeds": sorted({_text(value) for value in external_curie_seeds if _text(value)}),
            "max_hops": max_hops,
            "relation_allowlist": sorted({_text(value) for value in relation_allowlist if _text(value)}),
            "notes": notes,
        },
        "review_policy": deepcopy(FAIL_CLOSED_REVIEW),
        "stats": {
            "node_count": len(nodes_by_key),
            "edge_count": len(edge_values),
            "counts_by_predicate": dict(sorted(predicate_counts.items())),
            "counts_by_category": dict(sorted(category_counts.items())),
            "all_external_candidates": True,
        },
        "nodes": sorted(nodes_by_key.values(), key=lambda node: (node["curie"], node["source_local_id"])),
        "edges": edge_values,
    }


__all__ = [
    "FAIL_CLOSED_REVIEW",
    "build_candidate_graph",
    "canonical_sha256",
    "normalize_optimuskg_record",
    "normalize_primekg_row",
]
