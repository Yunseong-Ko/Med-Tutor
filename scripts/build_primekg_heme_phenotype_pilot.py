#!/usr/bin/env python3
"""Build a fail-closed PrimeKG disease-phenotype candidate pilot.

This importer deliberately does not merge PrimeKG facts into the canonical
P:accine ontology.  It creates a small, review-only graph from exact MONDO
CURIE matches and a second-pass comparison against the local finding layer.

The released Harvard Dataverse graph contains both orientations of each
undirected edge.  Reverse rows are collapsed deterministically while the
observed source orientations and original endpoint records are retained in
provenance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.external_kg_adapter import (
    FAIL_CLOSED_REVIEW,
    build_candidate_graph,
    canonical_sha256,
    normalize_optimuskg_record,
)


DEFAULT_OUTPUT_DIR = ROOT / "data_private" / "external_kg" / "primekg"
DEFAULT_FULL_OUTPUT_DIR = DEFAULT_OUTPUT_DIR / "heme_onc_full"

PROFILE_CORE20 = "core20"
PROFILE_HEME_ONC_FULL = "heme-onc-full"
SUPPORTED_PROFILES = {PROFILE_CORE20, PROFILE_HEME_ONC_FULL}

PRIMEKG_DATASET = {
    "name": "PrimeKG",
    "doi": "https://doi.org/10.7910/DVN/IXA7BM",
    "dataverse_persistent_id": "doi:10.7910/DVN/IXA7BM",
    "dataset_version": "2.1",
    "released_at": "2022-05-02T18:39:28Z",
    "license": "CC0-1.0",
}

PILOT_GENERATED_AT = "2026-07-13T08:00:15Z"
PRIMEKG_RETRIEVED_AT = "2026-07-13T07:51:01Z"
PRIMEKG_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
PRIMEKG_SOURCE_URL = "https://doi.org/10.7910/DVN/IXA7BM"

OFFICIAL_FILES = {
    "nodes": {
        "filename": "nodes.csv",
        "original_filename": "nodes.csv",
        "dataverse_file_id": 6180617,
        "download_url": "https://dataverse.harvard.edu/api/access/datafile/6180617?format=original",
        "bytes": 7_869_553,
        "md5": "7f9ab4109c54049e819ecd14e15a6038",
    },
    "edges": {
        "filename": "edges.csv",
        "original_filename": "edges.csv",
        "dataverse_file_id": 6180616,
        "download_url": "https://dataverse.harvard.edu/api/access/datafile/6180616",
        "bytes": 386_582_390,
        "md5": "5d4d211a22e88544b78fde2735e797bc",
    },
}

PHENOTYPE_RELATIONS = {
    "disease_phenotype_positive": "affirmed",
    "disease_phenotype_negative": "negated",
}

# Small enough to inspect manually, but representative of leukemia, lymphoma,
# plasma-cell, marrow-failure, myeloproliferative, and bleeding/anemia topics.
# Some are intentionally expected to be excluded because PrimeKG grouped their
# MONDO node; that exclusion is recorded rather than silently broadened.
DEFAULT_HEME_ONC_CONCEPT_IDS = [
    "acute_lymphoblastic_leukemia",
    "acute_myeloid_leukemia",
    "acute_promyelocytic_leukemia",
    "aplastic_anemia",
    "autoimmune_hemolytic_anemia",
    "chronic_lymphocytic_leukemia",
    "chronic_myeloid_leukemia",
    "essential_thrombocythemia",
    "hereditary_spherocytosis",
    "iron_deficiency_anemia",
    "multiple_myeloma",
    "myelodysplastic_syndrome",
    "neuroblastoma",
    "paroxysmal_nocturnal_hemoglobinuria",
    "polycythemia_vera",
    "primary_myelofibrosis",
    "thalassemia",
    "thrombotic_thrombocytopenic_purpura",
    "tumor_lysis_syndrome",
    "von_willebrand_disease",
]

SAFETY_REVIEW = FAIL_CLOSED_REVIEW


def concept_mondo_xref(concept: dict[str, Any]) -> str | None:
    xref = ((concept.get("evidence") or {}).get("ontology_xref") or {})
    return normalize_mondo(xref.get("mondo_id"))


def harrison_part(concept: dict[str, Any]) -> str | None:
    harrison = ((concept.get("evidence") or {}).get("harrison") or {})
    value = harrison.get("part")
    if value is None:
        return None
    return str(value).strip()


def heme_onc_scope_reasons(concept: dict[str, Any]) -> list[str]:
    """Return explicit, auditable heme-oncology scope signals.

    Harrison Part 4 is titled Oncology and Hematology in the local Harrison
    mapping.  It is deliberately an independent inclusion signal so concepts
    without a specialty or expansion-source tag are not silently omitted.
    """
    reasons: list[str] = []
    source = str(concept.get("source") or "")
    specialty = str(concept.get("specialty") or "")
    if source == "heme_onc_curriculum_expansion":
        reasons.append("source:heme_onc_curriculum_expansion")
    if "혈액" in specialty:
        reasons.append("specialty:contains_혈액")
    if "종양" in specialty:
        reasons.append("specialty:contains_종양")
    if harrison_part(concept) == "4":
        reasons.append("harrison:part_4_oncology_and_hematology")
    return reasons


def build_heme_onc_scope_audit(concepts: dict[str, dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    """Audit local MONDO concepts plus in-scope concepts missing a MONDO xref.

    Every valid local MONDO xref is assessed against the scope signals.  Local
    concepts that have a scope signal but no valid MONDO xref are also retained
    so a coverage gap cannot disappear before crosswalking.  The returned
    artifact is separate from the source-neutral crosswalk schema because a
    concept with no eligible external node cannot be represented as a mapping.
    """
    records: list[dict[str, Any]] = []
    selected: list[str] = []
    selected_reason_counts: Counter[str] = Counter()
    scope_reason_counts: Counter[str] = Counter()
    mondo_xref_count = 0
    scope_signaled_count = 0
    scope_missing_mondo_count = 0
    mondo_outside_scope_count = 0
    for concept_id, concept in sorted(concepts.items()):
        mondo_curie = concept_mondo_xref(concept)
        reasons = heme_onc_scope_reasons(concept)
        in_heme_onc_scope = bool(reasons)
        if not mondo_curie and not in_heme_onc_scope:
            continue
        if mondo_curie:
            mondo_xref_count += 1
        if in_heme_onc_scope:
            scope_signaled_count += 1
            scope_reason_counts.update(reasons)
        included = bool(mondo_curie and in_heme_onc_scope)
        if included:
            selected.append(concept_id)
            selected_reason_counts.update(reasons)
        elif in_heme_onc_scope:
            scope_missing_mondo_count += 1
        else:
            mondo_outside_scope_count += 1
        harrison = ((concept.get("evidence") or {}).get("harrison") or {})
        xref = ((concept.get("evidence") or {}).get("ontology_xref") or {})
        if included:
            exclusion_reason = None
        elif in_heme_onc_scope:
            exclusion_reason = "local_mondo_xref_missing_or_invalid"
        else:
            exclusion_reason = "no_explicit_heme_onc_scope_signal"
        records.append(
            {
                "local_concept_id": concept_id,
                "local_curie": f"PACCINE:{concept_id}",
                "local_mondo_curie": mondo_curie,
                "local_mondo_label": xref.get("mondo_label"),
                "local_name_match": str(xref.get("name_match") or "unknown"),
                "source": concept.get("source"),
                "specialty": concept.get("specialty"),
                "harrison_part": harrison_part(concept),
                "harrison_chapter": harrison.get("chapter"),
                "harrison_title": harrison.get("title"),
                "in_heme_onc_scope": in_heme_onc_scope,
                "has_valid_mondo_xref": bool(mondo_curie),
                "included": included,
                "inclusion_reasons": reasons,
                "exclusion_reason": exclusion_reason,
                "primekg_mapping_status": "not_evaluated",
                "candidate_import_eligible": False,
                "graph_exclusion_reason": (
                    "mapping_not_evaluated"
                    if included
                    else (
                        "local_mondo_xref_missing_or_invalid"
                        if in_heme_onc_scope
                        else "outside_heme_onc_scope"
                    )
                ),
            }
        )
    return selected, {
        "schema_version": "primekg_heme_onc_scope_audit.v1",
        "profile": PROFILE_HEME_ONC_FULL,
        "generated_at": PILOT_GENERATED_AT,
        "selection_policy": {
            "universe": "local_disease_concepts_with_syntactically_valid_mondo_xref",
            "inclusion_logic": "any",
            "inclusion_signals": [
                "source:heme_onc_curriculum_expansion",
                "specialty:contains_혈액",
                "specialty:contains_종양",
                "harrison:part_4_oncology_and_hematology",
            ],
            "notes": (
                "Harrison Part 4 is an independent signal to avoid under-selection by source/specialty tags. "
                "Every local valid MONDO xref is audited; in-scope concepts missing MONDO are retained as "
                "coverage gaps. Scope inclusion does not imply medical approval or PrimeKG mapping eligibility."
            ),
        },
        "stats": {
            "local_registry_concepts": len(concepts),
            "audited_concepts": len(records),
            "mondo_xref_universe": mondo_xref_count,
            "heme_onc_scope_signaled": scope_signaled_count,
            "heme_onc_scope_missing_valid_mondo": scope_missing_mondo_count,
            "mondo_xref_outside_heme_onc_scope": mondo_outside_scope_count,
            "included_concepts": len(selected),
            "excluded_audit_records": len(records) - len(selected),
            "inclusion_signal_counts": dict(sorted(selected_reason_counts.items())),
            "scope_signal_counts": dict(sorted(scope_reason_counts.items())),
            "mapping_status_counts": {},
            "candidate_import_eligible": 0,
            "all_external_candidates_fail_closed": True,
        },
        "concepts": records,
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(canonical_json(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def file_hashes(path: Path) -> dict[str, Any]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    return {"bytes": size, "md5": md5.hexdigest(), "sha256": sha256.hexdigest()}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def normalize_mondo(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.split(":", 1)[-1]
    if not raw.isdigit():
        return None
    return f"MONDO:{raw.zfill(7)}"


def normalize_hpo(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.split(":", 1)[-1]
    if not raw.isdigit():
        return None
    return f"HP:{raw.zfill(7)}"


def normalize_index(value: Any) -> int:
    raw = str(value).strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    return int(raw)


def node_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_index": normalize_index(row["node_index"]),
        "node_id": str(row.get("node_id") or ""),
        "node_type": str(row.get("node_type") or ""),
        "node_name": str(row.get("node_name") or ""),
        "node_source": str(row.get("node_source") or ""),
    }


def read_nodes(path: Path) -> dict[int, dict[str, Any]]:
    delimiter = "\t" if path.suffix.lower() in {".tab", ".tsv"} else ","
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        required = {"node_index", "node_id", "node_type", "node_name", "node_source"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"PrimeKG node columns missing: {sorted(required)}")
        return {record["node_index"]: record for record in map(node_record, reader)}


def concept_label(concept_id: str, concept: dict[str, Any]) -> str:
    xref = ((concept.get("evidence") or {}).get("ontology_xref") or {})
    if xref.get("mondo_label"):
        return str(xref["mondo_label"])
    aliases = concept.get("aliases") or []
    for alias in reversed(aliases):
        if alias and str(alias).lower() != concept_id:
            return str(alias)
    return concept_id.replace("_", " ")


def build_crosswalk(
    concepts: dict[str, dict[str, Any]],
    selected_ids: Iterable[str],
    nodes: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    exact_by_mondo: dict[str, dict[str, Any]] = {}
    grouped_by_mondo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes.values():
        if node["node_type"] != "disease":
            continue
        if node["node_source"] == "MONDO":
            curie = normalize_mondo(node["node_id"])
            if curie:
                exact_by_mondo[curie] = node
        elif node["node_source"] == "MONDO_grouped":
            for member in node["node_id"].split("_"):
                curie = normalize_mondo(member)
                if curie:
                    grouped_by_mondo[curie].append(node)

    records: list[dict[str, Any]] = []
    mapped_by_index: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for concept_id in sorted(set(selected_ids)):
        if concept_id not in concepts:
            raise ValueError(f"Unknown local concept_id: {concept_id}")
        concept = concepts[concept_id]
        xref = ((concept.get("evidence") or {}).get("ontology_xref") or {})
        mondo_curie = normalize_mondo(xref.get("mondo_id"))
        local_name_match = str(xref.get("name_match") or "unknown")
        exact = exact_by_mondo.get(mondo_curie or "")
        grouped = sorted(
            grouped_by_mondo.get(mondo_curie or "", []),
            key=lambda row: (row["node_index"], row["node_id"]),
        )
        if exact:
            status = "exact_mondo_id"
            match_class = f"curie_exact_name_{local_name_match}"
        elif grouped:
            status = "grouped_mondo_excluded"
            match_class = f"curie_grouped_name_{local_name_match}"
        elif mondo_curie:
            status = "mondo_not_found"
            match_class = f"curie_unmatched_name_{local_name_match}"
        else:
            status = "local_mondo_missing"
            match_class = "curie_missing"
        record = {
            "local_concept_id": concept_id,
            "local_curie": f"PACCINE:{concept_id}",
            "local_label": concept_label(concept_id, concept),
            "local_mondo_curie": mondo_curie,
            "local_mondo_label": xref.get("mondo_label"),
            "local_name_match": local_name_match,
            "match_class": match_class,
            "mapping_status": status,
            "candidate_import_eligible": bool(exact),
            "primekg_node": exact,
            "excluded_grouped_nodes": grouped,
            "review": dict(SAFETY_REVIEW),
        }
        records.append(record)
        if exact:
            mapped_by_index[exact["node_index"]].append(record)
    return records, mapped_by_index


def endpoint_curie(node: dict[str, Any]) -> str:
    if node["node_source"] == "HPO":
        hpo = normalize_hpo(node["node_id"])
        if hpo:
            return hpo
    return f"PRIMEKG:NODE_{node['node_index']}"


def read_candidate_pairs(
    edges_path: Path,
    nodes: dict[int, dict[str, Any]],
    mapped_by_index: dict[int, list[dict[str, Any]]],
) -> tuple[dict[tuple[str, str, int, int], dict[str, Any]], dict[str, int]]:
    accumulators: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    raw_relation_rows = Counter()
    matched_source_rows = 0
    with edges_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"relation", "display_relation", "x_index", "y_index"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"PrimeKG edge columns missing: {sorted(required)}")
        for row in reader:
            relation = str(row.get("relation") or "")
            if relation not in PHENOTYPE_RELATIONS:
                continue
            raw_relation_rows[relation] += 1
            x_index = normalize_index(row["x_index"])
            y_index = normalize_index(row["y_index"])
            x_node = nodes.get(x_index)
            y_node = nodes.get(y_index)
            if not x_node or not y_node:
                continue
            if x_index in mapped_by_index and y_node["node_type"] == "effect/phenotype":
                disease_index, phenotype_index = x_index, y_index
                orientation = "disease_to_phenotype"
            elif y_index in mapped_by_index and x_node["node_type"] == "effect/phenotype":
                disease_index, phenotype_index = y_index, x_index
                orientation = "phenotype_to_disease"
            else:
                continue
            matched_source_rows += 1
            display_relation = str(row.get("display_relation") or "")
            key = (relation, display_relation, disease_index, phenotype_index)
            accumulator = accumulators.setdefault(
                key,
                {
                    "relation": relation,
                    "display_relation": display_relation,
                    "disease_index": disease_index,
                    "phenotype_index": phenotype_index,
                    "source_rows": {},
                },
            )
            source_row = {
                "x_index": x_index,
                "y_index": y_index,
                "orientation": orientation,
            }
            accumulator["source_rows"][(x_index, y_index, orientation)] = source_row
    stats = {
        "source_positive_rows": raw_relation_rows["disease_phenotype_positive"],
        "source_negative_rows": raw_relation_rows["disease_phenotype_negative"],
        "matched_source_rows": matched_source_rows,
        "unique_source_pairs": len(accumulators),
        "reverse_or_duplicate_rows_collapsed": matched_source_rows - len(accumulators),
    }
    return accumulators, stats


def build_graph(
    crosswalk: list[dict[str, Any]],
    nodes: dict[int, dict[str, Any]],
    pair_accumulators: dict[tuple[str, str, int, int], dict[str, Any]],
    source_stats: dict[str, int],
    snapshot: dict[str, Any],
    selected_ids: list[str],
    selection_rule: str,
) -> dict[str, Any]:
    normalized_edges: list[dict[str, Any]] = []
    for key in sorted(pair_accumulators):
        accumulator = pair_accumulators[key]
        disease = nodes[accumulator["disease_index"]]
        phenotype = nodes[accumulator["phenotype_index"]]
        phenotype_curie = endpoint_curie(phenotype)
        source_rows = sorted(
            accumulator["source_rows"].values(),
            key=lambda row: (row["x_index"], row["y_index"], row["orientation"]),
        )
        orientations = sorted({row["orientation"] for row in source_rows})
        disease_curie = normalize_mondo(disease["node_id"])
        if not disease_curie:
            raise ValueError(f"Exact PrimeKG disease node lacks a MONDO identifier: {disease}")
        edge_id = stable_id(
            "primekg-source-pair",
            accumulator["relation"],
            accumulator["display_relation"],
            accumulator["disease_index"],
            accumulator["phenotype_index"],
        )
        normalized_edges.append(
            normalize_optimuskg_record(
                {
                    "edge_id": edge_id,
                    "subject": {
                        "curie": disease_curie,
                        "label": disease["node_name"],
                        "categories": ["disease"],
                        "namespace": disease["node_source"],
                        "source_local_id": disease["node_id"],
                    },
                    "object": {
                        "curie": phenotype_curie,
                        "label": phenotype["node_name"],
                        "categories": ["effect/phenotype", "finding"],
                        "namespace": phenotype["node_source"] or "PrimeKG",
                        "source_local_id": phenotype["node_id"] or str(phenotype["node_index"]),
                    },
                    "predicate": "presents_with",
                    "relation_code": accumulator["relation"],
                    "polarity": PHENOTYPE_RELATIONS[accumulator["relation"]],
                    "direction": "undirected",
                    "undirected": True,
                    "source_refs": ["PrimeKG", phenotype["node_source"]],
                    "publications": ["https://doi.org/10.1038/s41597-023-01960-3"],
                    "qualifiers": {
                        "verification_status": "unverified",
                        "primekg_source_record": {
                            "relation": accumulator["relation"],
                            "display_relation": accumulator["display_relation"],
                            "disease_endpoint": disease,
                            "phenotype_endpoint": phenotype,
                            "observed_orientations": orientations,
                            "source_rows": source_rows,
                            "reverse_row_observed": len(orientations) > 1,
                        },
                    },
                },
                snapshot,
            )
        )

    external_seeds = sorted(
        {
            mapping["local_mondo_curie"]
            for mapping in crosswalk
            if mapping["candidate_import_eligible"] and mapping["local_mondo_curie"]
        }
    )
    return build_candidate_graph(
        normalized_edges,
        snapshot,
        local_concept_ids=selected_ids,
        external_curie_seeds=external_seeds,
        max_hops=1,
        relation_allowlist=["presents_with"],
        notes=(
            "PrimeKG heme-onc disease-phenotype pilot; exact ungrouped MONDO CURIE only; "
            f"source_relation_allowlist={','.join(sorted(PHENOTYPE_RELATIONS))}; "
            f"reverse rows collapsed; selection_rule={selection_rule}; "
            f"matched_source_rows={source_stats['matched_source_rows']}; "
            f"collapsed_rows={source_stats['reverse_or_duplicate_rows_collapsed']}."
        ),
        generated_at=PILOT_GENERATED_AT,
    )


def build_validation_report(
    graph: dict[str, Any],
    crosswalk: list[dict[str, Any]],
    finding_registry: dict[str, Any],
    selected_ids: list[str],
    graph_artifact_sha256: str,
    local_ontology_snapshot_sha256: str,
) -> dict[str, Any]:
    external: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    external_subjects: dict[tuple[str, str], set[str]] = defaultdict(set)
    local_by_external_curie: dict[str, list[str]] = defaultdict(list)
    for mapping in crosswalk:
        if mapping["candidate_import_eligible"] and mapping["local_mondo_curie"]:
            local_by_external_curie[mapping["local_mondo_curie"]].append(mapping["local_concept_id"])
    for edge in graph["edges"]:
        external_subject_curie = edge["subject"]["curie"]
        hpo_curie = edge["object"]["curie"]
        if not hpo_curie.startswith("HP:"):
            continue
        for local_id in local_by_external_curie.get(external_subject_curie, []):
            pair_key = (local_id, hpo_curie)
            external[pair_key][edge["polarity"]].add(edge["candidate_edge_id"])
            external_subjects[pair_key].add(external_subject_curie)

    selected_set = set(selected_ids)
    local: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for finding in finding_registry.get("findings") or []:
        hpo_curie = normalize_hpo(finding.get("hpo_id"))
        if not hpo_curie:
            continue
        for concept_id in sorted(set(finding.get("presented_by") or []) & selected_set):
            local[(concept_id, hpo_curie)].append(
                {
                    "finding_id": finding.get("finding_id"),
                    "hpo_curie": hpo_curie,
                    "hpo_label": finding.get("hpo_label"),
                    "local_needs_review": bool(finding.get("needs_review", True)),
                }
            )

    crosswalk_by_id = {row["local_concept_id"]: row for row in crosswalk}
    items: list[dict[str, Any]] = []
    for concept_id, hpo_curie in sorted(set(local) | set(external)):
        local_findings = sorted(
            local.get((concept_id, hpo_curie), []),
            key=lambda row: str(row.get("finding_id") or ""),
        )
        ext = external.get((concept_id, hpo_curie), {})
        polarities = sorted(ext)
        edge_ids = sorted({edge_id for ids in ext.values() for edge_id in ids})
        if local_findings and "negated" in ext:
            classification = "external_conflict_candidate"
            interpretation = "PrimeKG negates a phenotype asserted by the local draft; adjudication required."
        elif local_findings and "affirmed" in ext:
            classification = "externally_concordant"
            interpretation = "PrimeKG independently contains the same disease-HPO pair; this is corroboration, not approval."
        elif local_findings:
            classification = "local_only_not_disproven"
            interpretation = "No matching PrimeKG pair was found; source absence is not contradictory evidence."
        else:
            classification = "external_new_candidate"
            interpretation = "PrimeKG supplies a disease-HPO candidate absent from the local finding layer."
        mapping = crosswalk_by_id[concept_id]
        finding_values: list[dict[str, Any] | None] = local_findings or [None]
        for finding in finding_values:
            finding_id = finding.get("finding_id") if finding else None
            if edge_ids:
                evaluation_status = "evaluated_exact_mapping"
                coverage_reason = "external_edge_present"
            elif mapping["mapping_status"] == "exact_mondo_id":
                evaluation_status = "evaluated_exact_mapping"
                coverage_reason = "exact_mapping_no_external_edge"
            elif mapping["mapping_status"] == "grouped_mondo_excluded":
                evaluation_status = "not_evaluable_grouped_mapping"
                coverage_reason = "grouped_mapping_excluded"
            else:
                evaluation_status = "not_evaluable_missing_mapping"
                coverage_reason = "local_mapping_missing"
            if classification == "local_only_not_disproven":
                if evaluation_status == "not_evaluable_grouped_mapping":
                    interpretation = (
                        "PrimeKG grouped this MONDO disease, so exact disease-level comparison was not evaluable; "
                        "the local finding is neither corroborated nor disproven."
                    )
                elif evaluation_status == "not_evaluable_missing_mapping":
                    interpretation = (
                        "No eligible PrimeKG disease mapping exists, so comparison was not evaluable; "
                        "the local finding is neither corroborated nor disproven."
                    )
                else:
                    interpretation = (
                        "An exact PrimeKG disease mapping was evaluated but no matching phenotype edge was found; "
                        "source absence is not contradictory evidence."
                    )
            elif classification == "external_new_candidate" and polarities == ["negated"]:
                interpretation = (
                    "PrimeKG supplies a negated external phenotype assertion absent from the local layer; "
                    "this is not a new positive finding candidate."
                )
            elif classification == "external_new_candidate" and "negated" in polarities:
                interpretation = (
                    "PrimeKG supplies conflicting affirmed and negated external assertions absent from the local layer; "
                    "this requires source-level adjudication and is not a positive finding candidate."
                )
            explanation = (
                f"{interpretation} match_class={mapping['match_class']}; "
                f"external_polarities={','.join(polarities) if polarities else 'none'}; "
                f"evaluation_status={evaluation_status}; coverage_reason={coverage_reason}; "
                "verification_status=unverified."
            )
            item_identity = {
                "graph_id": graph["graph_id"],
                "concept_id": concept_id,
                "finding_id": finding_id,
                "hpo_curie": hpo_curie,
                "classification": classification,
                "evaluation_status": evaluation_status,
                "coverage_reason": coverage_reason,
                "external_polarities": polarities,
                "candidate_edge_ids": edge_ids,
            }
            items.append(
                {
                    "validation_item_id": f"ekg:v:{canonical_sha256(item_identity)[:24]}",
                    "classification": classification,
                    "evaluation_status": evaluation_status,
                    "coverage_reason": coverage_reason,
                    "local_concept_id": concept_id,
                    "local_finding_id": finding_id,
                    "local_finding_label": finding.get("hpo_label") if finding else None,
                    "hpo_curie": hpo_curie,
                    "local_claim_ids": [],
                    "candidate_edge_ids": edge_ids,
                    "external_polarities": polarities,
                    "external_subject_curie": (
                        sorted(external_subjects[(concept_id, hpo_curie)])[0] if edge_ids else None
                    ),
                    "external_predicate": "presents_with" if edge_ids else None,
                    "external_object_curie": hpo_curie if edge_ids else None,
                    "explanation": explanation,
                    "absence_is_not_contradiction": True,
                    "review": dict(SAFETY_REVIEW),
                }
            )
    items.sort(key=lambda row: row["validation_item_id"])
    counts = Counter(row["classification"] for row in items)
    evaluation_counts = Counter(row["evaluation_status"] for row in items)
    report_identity = {
        "graph_id": graph["graph_id"],
        "graph_artifact_sha256": graph_artifact_sha256,
        "local_ontology_snapshot_sha256": local_ontology_snapshot_sha256,
        "item_ids": [row["validation_item_id"] for row in items],
    }
    return {
        "schema_version": "external_kg_validation_report.v1",
        "report_id": f"external_kg_validation:primekg:{canonical_sha256(report_identity)[:16]}",
        "generated_at": PILOT_GENERATED_AT,
        "candidate_graph_refs": [
            {
                "graph_id": graph["graph_id"],
                "snapshot_id": graph["snapshot"]["snapshot_id"],
                "artifact_sha256": graph_artifact_sha256,
            }
        ],
        "local_ontology_snapshot_sha256": local_ontology_snapshot_sha256,
        "interpretation_policy": {
            "absence_is_not_contradiction": True,
            "review": dict(SAFETY_REVIEW),
        },
        "stats": {
            "item_count": len(items),
            "externally_concordant": counts["externally_concordant"],
            "external_conflict_candidate": counts["external_conflict_candidate"],
            "local_only_not_disproven": counts["local_only_not_disproven"],
            "external_new_candidate": counts["external_new_candidate"],
            "evaluated_exact_mapping": evaluation_counts["evaluated_exact_mapping"],
            "not_evaluable_grouped_mapping": evaluation_counts["not_evaluable_grouped_mapping"],
            "not_evaluable_missing_mapping": evaluation_counts["not_evaluable_missing_mapping"],
            "all_needs_review": True,
        },
        "items": items,
    }


def verify_official_file(role: str, actual: dict[str, Any]) -> None:
    expected = OFFICIAL_FILES[role]
    mismatches = []
    for field in ("bytes", "md5"):
        if actual[field] != expected[field]:
            mismatches.append(f"{field}: expected={expected[field]} actual={actual[field]}")
    if mismatches:
        raise ValueError(f"PrimeKG {role} checksum mismatch ({'; '.join(mismatches)})")


def build_snapshot_manifest(
    hashes: dict[str, dict[str, Any]],
    profile: str = PROFILE_CORE20,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    bundle_sha256 = canonical_sha256({"nodes": hashes["nodes"], "edges": hashes["edges"]})
    license_record = {
        "name": "CC0 1.0 (Harvard Dataverse metadata)",
        "spdx_id": "CC0-1.0",
        "url": PRIMEKG_LICENSE_URL,
        "redistribution_status": "unknown",
        "notes": "Dataverse metadata is CC0; upstream source terms require review before redistribution.",
    }
    ingest_policy = {
        "mode": "local_snapshot",
        "external_candidate_only": True,
        "requires_human_review": True,
        "medical_approval": False,
        "student_visible": False,
        "analytics_eligible": False,
    }
    upstream_manifest_url = (
        "https://dataverse.harvard.edu/api/datasets/:persistentId"
        "?persistentId=doi:10.7910/DVN/IXA7BM"
    )

    def source_snapshot(role: str) -> dict[str, Any]:
        actual = hashes[role]
        filename = OFFICIAL_FILES[role]["filename"]
        return {
            "snapshot_id": f"external_kg_snapshot:primekg:{role}-v2.1-{actual['sha256'][:12]}",
            "provider": "primekg",
            "dataset_name": f"PrimeKG {filename}",
            "dataset_version": PRIMEKG_DATASET["dataset_version"],
            "source_url": OFFICIAL_FILES[role]["download_url"],
            "retrieved_at": PRIMEKG_RETRIEVED_AT,
            "artifact": {
                "format": "csv",
                "content_sha256": actual["sha256"],
                "byte_size": actual["bytes"],
                "relative_path": None,
                "media_type": "text/csv",
            },
            "license": license_record,
            "citation": (
                f"PrimeKG Harvard Dataverse {filename}; file_id={OFFICIAL_FILES[role]['dataverse_file_id']}; "
                f"md5={actual['md5']}; sha256={actual['sha256']}."
            ),
            "upstream_manifest_url": upstream_manifest_url,
            "ingest_policy": ingest_policy,
        }

    nodes_snapshot = source_snapshot("nodes")
    edges_snapshot = source_snapshot("edges")
    bundle_snapshot_id = f"external_kg_snapshot:primekg:bundle-v2.1-{bundle_sha256[:12]}"
    bundle_snapshot = {
        "snapshot_id": bundle_snapshot_id,
        "provider": "primekg",
        "dataset_name": "PrimeKG nodes+edges logical bundle",
        "dataset_version": PRIMEKG_DATASET["dataset_version"],
        "source_url": PRIMEKG_SOURCE_URL,
        "retrieved_at": PRIMEKG_RETRIEVED_AT,
        "artifact": {
            "format": "other",
            "content_sha256": bundle_sha256,
            "byte_size": hashes["nodes"]["bytes"] + hashes["edges"]["bytes"],
            "relative_path": None,
            "media_type": "application/x-primekg-csv-bundle",
        },
        "license": license_record,
        "citation": (
            "Logical bundle of the verified PrimeKG nodes.csv and edges.csv snapshots in this manifest; "
            f"nodes_sha256={hashes['nodes']['sha256']}; edges_sha256={hashes['edges']['sha256']}."
        ),
        "upstream_manifest_url": upstream_manifest_url,
        "ingest_policy": ingest_policy,
    }
    manifest = {
        "schema_version": "external_kg_snapshot_manifest.v1",
        "manifest_id": (
            "external_kg_manifest:primekg_heme_onc_pilot_v1"
            if profile == PROFILE_CORE20
            else "external_kg_manifest:primekg_heme_onc_full_v1"
        ),
        "created_at": PILOT_GENERATED_AT,
        "policy": {
            "external_candidate_only": True,
            "requires_human_review": True,
            "medical_approval": False,
            "student_visible": False,
            "analytics_eligible": False,
        },
        "snapshots": [nodes_snapshot, edges_snapshot, bundle_snapshot],
    }
    candidate_snapshot = {
        "snapshot_id": bundle_snapshot_id,
        "provider": "primekg",
        "dataset_name": "PrimeKG nodes+edges logical bundle",
        "dataset_version": PRIMEKG_DATASET["dataset_version"],
        "artifact_sha256": bundle_sha256,
        "license": license_record,
        "source_url": PRIMEKG_SOURCE_URL,
    }
    mapping_snapshot = {
        "snapshot_id": nodes_snapshot["snapshot_id"],
        "artifact_sha256": nodes_snapshot["artifact"]["content_sha256"],
    }
    return manifest, candidate_snapshot, mapping_snapshot


def build_crosswalk_artifact(
    crosswalk: list[dict[str, Any]],
    mapping_snapshot: dict[str, Any],
    profile: str = PROFILE_CORE20,
) -> dict[str, Any]:
    mappings: list[dict[str, Any]] = []
    for row in crosswalk:
        source_nodes: list[tuple[dict[str, Any], bool]] = []
        if row["primekg_node"]:
            source_nodes.append((row["primekg_node"], True))
        else:
            source_nodes.extend((node, False) for node in row["excluded_grouped_nodes"])
        for source_node, exact in source_nodes:
            if exact:
                external_curie = row["local_mondo_curie"]
                mapping_relation = "exact_match" if row["local_name_match"] == "exact" else "close_match"
                mapping_method = "identifier_exact"
                confidence = 1.0 if mapping_relation == "exact_match" else 0.9
            else:
                external_curie = f"PrimeKGGroup:{source_node['node_index']}"
                mapping_relation = "member_of_group"
                mapping_method = "group_member_candidate"
                confidence = 0.5
            source_record_sha256 = canonical_sha256(source_node)
            mapping_identity = {
                "snapshot_id": mapping_snapshot["snapshot_id"],
                "local_concept_id": row["local_concept_id"],
                "external_curie": external_curie,
                "mapping_relation": mapping_relation,
                "source_record_sha256": source_record_sha256,
            }
            mappings.append(
                {
                    "mapping_id": f"ekg:x:{canonical_sha256(mapping_identity)[:24]}",
                    "local_concept_id": row["local_concept_id"],
                    "external_curie": external_curie,
                    "external_label": source_node["node_name"],
                    "external_snapshot_id": mapping_snapshot["snapshot_id"],
                    "mapping_relation": mapping_relation,
                    "mapping_method": mapping_method,
                    "confidence": confidence,
                    "evidence": [
                        {
                            "source_record_id": f"primekg-node:{source_node['node_index']}",
                            "source_record_sha256": source_record_sha256,
                            "note": (
                                f"{row['match_class']}; local_name_match={row['local_name_match']}; "
                                f"local_mondo_curie={row['local_mondo_curie'] or 'none'}; "
                                f"mapping_status={row['mapping_status']}; verification_status=unverified"
                            ),
                        }
                    ],
                    "review": dict(SAFETY_REVIEW),
                }
            )
    mappings.sort(key=lambda row: row["mapping_id"])
    return {
        "schema_version": "external_kg_crosswalk.v1",
        "crosswalk_id": (
            "external_kg_crosswalk:primekg_heme_onc_pilot_v1"
            if profile == PROFILE_CORE20
            else "external_kg_crosswalk:primekg_heme_onc_full_v1"
        ),
        "generated_at": PILOT_GENERATED_AT,
        "source_snapshots": [
            {
                "snapshot_id": mapping_snapshot["snapshot_id"],
                "artifact_sha256": mapping_snapshot["artifact_sha256"],
            }
        ],
        "review_policy": dict(SAFETY_REVIEW),
        "mappings": mappings,
    }


def finalize_scope_audit(
    scope_audit: dict[str, Any],
    crosswalk: list[dict[str, Any]],
) -> dict[str, Any]:
    """Attach exact/grouped/missing PrimeKG coverage to the local scope audit."""
    finalized = json.loads(json.dumps(scope_audit, ensure_ascii=False))
    mapping_by_id = {row["local_concept_id"]: row for row in crosswalk}
    mapping_counts: Counter[str] = Counter()
    graph_exclusion_counts: Counter[str] = Counter()
    eligible_count = 0
    for record in finalized["concepts"]:
        if not record["included"]:
            graph_exclusion_counts[record["graph_exclusion_reason"]] += 1
            continue
        mapping = mapping_by_id[record["local_concept_id"]]
        status = mapping["mapping_status"]
        eligible = bool(mapping["candidate_import_eligible"])
        record["primekg_mapping_status"] = status
        record["candidate_import_eligible"] = eligible
        if eligible:
            exclusion_reason = None
            eligible_count += 1
        elif status == "grouped_mondo_excluded":
            exclusion_reason = "grouped_mondo_node_not_auto_merged"
        elif status == "mondo_not_found":
            exclusion_reason = "mondo_not_found_in_primekg_nodes"
        else:
            exclusion_reason = "no_eligible_exact_ungrouped_mapping"
        record["graph_exclusion_reason"] = exclusion_reason
        mapping_counts[status] += 1
        if exclusion_reason:
            graph_exclusion_counts[exclusion_reason] += 1
    finalized["stats"]["mapping_status_counts"] = dict(sorted(mapping_counts.items()))
    finalized["stats"]["candidate_import_eligible"] = eligible_count
    finalized["stats"]["graph_exclusion_reason_counts"] = dict(sorted(graph_exclusion_counts.items()))
    return finalized


def build_full_readme(
    *,
    scope_audit: dict[str, Any],
    graph: dict[str, Any],
    validation: dict[str, Any],
    hashes: dict[str, dict[str, Any]],
) -> str:
    scope_stats = scope_audit["stats"]
    mapping_stats = scope_stats["mapping_status_counts"]
    graph_stats = graph["stats"]
    validation_stats = validation["stats"]
    eligible_mondo = {
        record["local_mondo_curie"]
        for record in scope_audit["concepts"]
        if record["included"] and record["candidate_import_eligible"]
    }
    graph_subjects = {edge["subject"]["curie"] for edge in graph["edges"]}
    eligible_without_allowed_edge = len(eligible_mondo - graph_subjects)
    polarity_counts = Counter(edge["polarity"] for edge in graph["edges"])
    paccine_subject_count = sum(
        1 for edge in graph["edges"] if edge["subject"]["curie"].startswith("PACCINE:")
    )
    return f"""# PrimeKG 혈액종양 전체 범위 2차 검증

이 디렉터리는 기존 `core20` 파일럿과 분리된 `heme-onc-full` 프로필 산출물이다.
PrimeKG의 지식을 P:accine 정식 온톨로지에 병합하지 않으며, 모든 관계와 검증 결과는
`external_candidate` / `needs_review=true` / `medical_approval=false` /
`student_visible=false` / `analytics_eligible=false` 상태로 고정된다.

## 범위 감사

- local registry 전체: {scope_stats['local_registry_concepts']}
- 유효 local MONDO xref 전체 감사: {scope_stats['mondo_xref_universe']}
- 혈액종양 scope 신호 보유: {scope_stats['heme_onc_scope_signaled']}
- 혈액종양 scope + 유효 MONDO 포함: {scope_stats['included_concepts']}
- 혈액종양 scope지만 MONDO 누락/무효: {scope_stats['heme_onc_scope_missing_valid_mondo']}
- 유효 MONDO가 있지만 혈액종양 scope 밖: {scope_stats['mondo_xref_outside_heme_onc_scope']}
- exact ungrouped graph eligible: {scope_stats['candidate_import_eligible']}
- grouped 자동병합 제외: {mapping_stats.get('grouped_mondo_excluded', 0)}
- PrimeKG MONDO 미발견: {mapping_stats.get('mondo_not_found', 0)}

포함 기준은 다음 신호의 합집합이다.

1. `source=heme_onc_curriculum_expansion`
2. specialty에 `혈액` 포함
3. specialty에 `종양` 포함
4. Harrison Part 4 (Oncology and Hematology)

`heme_onc_scope_audit.json`에 각 concept의 포함 신호, 제외 이유, PrimeKG mapping 상태,
graph eligibility를 machine-readable하게 기록한다. grouped MONDO는 crosswalk에 후보로만
남기고 graph에는 넣지 않는다. PrimeKG에 관계가 없다는 사실은 모순이 아니다.

## 실측 결과

- 후보 graph: {graph_stats['node_count']} nodes / {graph_stats['edge_count']} edges
- exact 질환 중 허용 phenotype edge가 있는 질환: {len(eligible_mondo & graph_subjects)}
- exact 질환 중 허용 phenotype edge가 없는 질환: {eligible_without_allowed_edge} (부재는 모순이 아님)
- affirmed / negated edges: {polarity_counts['affirmed']} / {polarity_counts['negated']}
- PACCINE subject: {paccine_subject_count}
- 검증 items: {validation_stats['item_count']}
- externally concordant: {validation_stats['externally_concordant']}
- external conflict candidate: {validation_stats['external_conflict_candidate']}
- local only, not disproven: {validation_stats['local_only_not_disproven']}
- external new candidate: {validation_stats['external_new_candidate']}

## 파일

- `source_manifest.json`: 검증한 PrimeKG raw snapshot과 fail-closed ingest policy
- `heme_onc_mondo_crosswalk.json`: local concept ↔ PrimeKG node 후보 매핑
- `heme_onc_phenotype_candidate_graph.json`: exact ungrouped MONDO만 사용한 후보 graph
- `heme_onc_validation_report.json`: local finding layer와의 2차 비교
- `heme_onc_scope_audit.json`: 범위 선택·제외·mapping coverage 감사

## 공식 raw 검증

- nodes: {hashes['nodes']['bytes']} bytes, MD5 `{hashes['nodes']['md5']}`, SHA-256 `{hashes['nodes']['sha256']}`
- edges: {hashes['edges']['bytes']} bytes, MD5 `{hashes['edges']['md5']}`, SHA-256 `{hashes['edges']['sha256']}`

공식 raw는 저장소에 복사하지 않고 `/private/tmp`에서 checksum 검증 후 읽는다.
Dataverse 메타데이터는 CC0이지만 통합 원천별 이용 조건은 별도 검토가 필요하므로
redistribution 상태는 `unknown`이다.

## 재생성

```bash
python scripts/build_primekg_heme_phenotype_pilot.py --profile heme-onc-full
```

기존 기본 실행은 계속 `core20`만 재생성하며 이 디렉터리를 덮어쓰지 않는다.
"""


def build_pilot(
    *,
    concept_registry_path: Path,
    finding_registry_path: Path,
    nodes_path: Path,
    edges_path: Path,
    output_dir: Path,
    selected_ids: Iterable[str] | None = None,
    verify_official_checksums: bool = False,
    selection_rule: str | None = None,
    profile: str = PROFILE_CORE20,
    scope_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"Unsupported profile: {profile}")
    if profile == PROFILE_CORE20 and scope_audit is not None:
        raise ValueError("scope_audit is only valid for the heme-onc-full profile")
    if profile == PROFILE_HEME_ONC_FULL and scope_audit is None:
        raise ValueError("heme-onc-full requires a machine-readable scope_audit")
    using_default = selected_ids is None
    selected = sorted(set(selected_ids or DEFAULT_HEME_ONC_CONCEPT_IDS))
    selection_rule = selection_rule or (
        "default_core_20_prioritizing_existing_local_hpo_pairs"
        if using_default
        else "explicit_concept_ids"
    )
    if not selected:
        raise ValueError("At least one concept_id is required")
    concept_registry = load_json(concept_registry_path)
    concepts = concept_registry.get("concepts") or {}
    finding_registry = load_json(finding_registry_path)
    hashes = {
        "nodes": file_hashes(nodes_path),
        "edges": file_hashes(edges_path),
        "concept_registry": file_hashes(concept_registry_path),
        "finding_registry": file_hashes(finding_registry_path),
    }
    if verify_official_checksums:
        verify_official_file("nodes", hashes["nodes"])
        verify_official_file("edges", hashes["edges"])
    manifest, snapshot, mapping_snapshot = build_snapshot_manifest(hashes, profile=profile)
    nodes = read_nodes(nodes_path)
    crosswalk, mapped_by_index = build_crosswalk(concepts, selected, nodes)
    pairs, source_stats = read_candidate_pairs(edges_path, nodes, mapped_by_index)
    graph = build_graph(
        crosswalk,
        nodes,
        pairs,
        source_stats,
        snapshot,
        selected,
        selection_rule,
    )
    graph_artifact_sha256 = hashlib.sha256(json_bytes(graph)).hexdigest()
    local_ontology_snapshot_sha256 = canonical_sha256(
        {
            "concept_registry_sha256": hashes["concept_registry"]["sha256"],
            "finding_registry_sha256": hashes["finding_registry"]["sha256"],
        }
    )
    validation = build_validation_report(
        graph,
        crosswalk,
        finding_registry,
        selected,
        graph_artifact_sha256,
        local_ontology_snapshot_sha256,
    )
    mapping_counts = Counter(row["mapping_status"] for row in crosswalk)
    match_class_counts = Counter(row["match_class"] for row in crosswalk)
    crosswalk_artifact = build_crosswalk_artifact(crosswalk, mapping_snapshot, profile=profile)

    write_json(output_dir / "source_manifest.json", manifest)
    write_json(output_dir / "heme_onc_mondo_crosswalk.json", crosswalk_artifact)
    write_json(output_dir / "heme_onc_phenotype_candidate_graph.json", graph)
    write_json(output_dir / "heme_onc_validation_report.json", validation)
    result = {
        "profile": profile,
        "snapshot_id": snapshot["snapshot_id"],
        "graph_id": graph["graph_id"],
        "report_id": validation["report_id"],
        "graph_stats": graph["stats"],
        "validation_stats": validation["stats"],
        "source_stats": source_stats,
        "crosswalk_stats": {
            "selected": len(selected),
            "emitted_mappings": len(crosswalk_artifact["mappings"]),
            "mapping_statuses": dict(sorted(mapping_counts.items())),
            "match_classes": dict(sorted(match_class_counts.items())),
        },
        "output_dir": str(output_dir),
    }
    if scope_audit is not None:
        finalized_scope_audit = finalize_scope_audit(scope_audit, crosswalk)
        write_json(output_dir / "heme_onc_scope_audit.json", finalized_scope_audit)
        (output_dir / "README.md").write_text(
            build_full_readme(
                scope_audit=finalized_scope_audit,
                graph=graph,
                validation=validation,
                hashes=hashes,
            ),
            encoding="utf-8",
        )
        result["scope_audit_stats"] = finalized_scope_audit["stats"]
    return result


def load_concept_list(path: Path) -> list[str]:
    if path.suffix.lower() == ".json":
        value = load_json(path)
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, dict) and isinstance(value.get("concept_ids"), list):
            return [str(item) for item in value["concept_ids"]]
        raise ValueError("JSON concept list must be a list or {'concept_ids': [...]} object")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def select_all_exact_heme_onc(concept_registry_path: Path, nodes_path: Path) -> list[str]:
    """Select all heme-tagged local concepts with an ungrouped PrimeKG MONDO node."""
    concepts = (load_json(concept_registry_path).get("concepts") or {})
    exact_mondo = {
        normalize_mondo(node["node_id"])
        for node in read_nodes(nodes_path).values()
        if node["node_type"] == "disease" and node["node_source"] == "MONDO"
    }
    selected = []
    for concept_id, concept in concepts.items():
        specialty = str(concept.get("specialty") or "")
        is_heme = concept.get("source") == "heme_onc_curriculum_expansion" or "혈액" in specialty
        xref = ((concept.get("evidence") or {}).get("ontology_xref") or {})
        if is_heme and normalize_mondo(xref.get("mondo_id")) in exact_mondo:
            selected.append(concept_id)
    return sorted(selected)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=sorted(SUPPORTED_PROFILES),
        default=PROFILE_CORE20,
        help=(
            "core20 preserves the existing fixed pilot; heme-onc-full audits all local MONDO xrefs "
            "and writes to the separate heme_onc_full directory by default."
        ),
    )
    parser.add_argument("--concept-registry", type=Path, default=ROOT / "data_private" / "concept_registry.json")
    parser.add_argument(
        "--finding-registry",
        type=Path,
        default=ROOT / "data_private" / "curriculum" / "finding_registry.json",
    )
    parser.add_argument("--nodes", type=Path, default=Path("/private/tmp/primekg_nodes_original.csv"))
    parser.add_argument("--edges", type=Path, default=Path("/private/tmp/primekg_edges.csv"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--concept-id", action="append", default=[])
    parser.add_argument("--concept-list", type=Path)
    parser.add_argument(
        "--all-exact-heme-onc",
        action="store_true",
        help="Use every heme-tagged local concept with an exact, ungrouped PrimeKG MONDO CURIE.",
    )
    parser.add_argument(
        "--skip-official-checksum-verification",
        action="store_true",
        help="Only for fixtures or rebuilt PrimeKG snapshots; official pilot runs verify bytes and MD5.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.profile == PROFILE_HEME_ONC_FULL and (
        args.concept_id or args.concept_list or args.all_exact_heme_onc
    ):
        raise SystemExit(
            "--profile heme-onc-full uses its audited deterministic scope and cannot be combined "
            "with --concept-id/--concept-list/--all-exact-heme-onc"
        )
    if args.all_exact_heme_onc and (args.concept_id or args.concept_list):
        raise SystemExit("--all-exact-heme-onc cannot be combined with --concept-id/--concept-list")
    output_dir = args.output_dir or (
        DEFAULT_FULL_OUTPUT_DIR if args.profile == PROFILE_HEME_ONC_FULL else DEFAULT_OUTPUT_DIR
    )
    selected = list(args.concept_id)
    if args.concept_list:
        selected.extend(load_concept_list(args.concept_list))
    selection_rule = None
    scope_audit = None
    if args.all_exact_heme_onc:
        selected = select_all_exact_heme_onc(args.concept_registry, args.nodes)
        selection_rule = "all_heme_tagged_exact_ungrouped_primekg_mondo"
    elif args.profile == PROFILE_HEME_ONC_FULL:
        concepts = (load_json(args.concept_registry).get("concepts") or {})
        selected, scope_audit = build_heme_onc_scope_audit(concepts)
        selection_rule = (
            "all_local_valid_mondo_xrefs_matching_any_of_explicit_heme_onc_source_"
            "specialty_or_harrison_part_4"
        )
    result = build_pilot(
        concept_registry_path=args.concept_registry,
        finding_registry_path=args.finding_registry,
        nodes_path=args.nodes,
        edges_path=args.edges,
        output_dir=output_dir,
        selected_ids=(
            selected
            if (selected or args.all_exact_heme_onc or args.profile == PROFILE_HEME_ONC_FULL)
            else None
        ),
        verify_official_checksums=not args.skip_official_checksum_verification,
        selection_rule=selection_rule,
        profile=args.profile,
        scope_audit=scope_audit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
