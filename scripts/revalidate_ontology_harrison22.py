#!/usr/bin/env python3
"""Attach Harrison 22e claim-level retrieval candidates to the Ontology.

This is an evidence-candidate builder, not a medical approval system.  It
corrects edition provenance and locates likely supporting passages, but every
result remains ``needs_human_review`` and cannot make content student-visible.
The preserved baseline was already sourced from 22e despite legacy 21e labels,
so this program intentionally does not claim to compute a 21e-to-22e diff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
DEFAULT_SNAPSHOT = DP / "harrison" / "22e"
DEFAULT_CONCEPTS = DP / "concept_registry.json"
DEFAULT_AXIS = DP / "curriculum" / "axis_registry.json"
SCHEMA_VERSION = "harrison22_claim_revalidation.v1"
TOKEN_RE = re.compile(r"[a-z0-9]+", flags=re.I)
HIGH_RISK_AXIS_TYPES = {"contraindication", "diagnosis", "indication", "treatment"}
HIGH_RISK_RELATIONS = {
    "diagnosed_by",
    "has_contraindication",
    "has_diagnostic_evidence",
    "has_diagnostic_feature",
    "has_indication",
    "has_treatment_principle",
    "treated_with",
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(value: object, *, length: int | None = None) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return digest[:length] if length else digest


def normalize_title(value: object) -> str:
    text = str(value or "").casefold().replace("\u00ad", "")
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def normalize_text(value: object) -> str:
    text = str(value or "").replace("\u00ad", "")
    text = re.sub(r"-\s*\n\s*(?=[a-z])", "", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(value: object) -> list[str]:
    stop = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
        "in", "is", "it", "of", "or", "that", "the", "this", "to", "with",
    }
    return [token.casefold() for token in TOKEN_RE.findall(str(value or "")) if token.casefold() not in stop]


def chunks_for_page(text: str, *, size: int = 900, overlap: int = 160) -> list[tuple[int, int, str]]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= size:
        return [(0, len(normalized), normalized)]
    rows: list[tuple[int, int, str]] = []
    start = 0
    while start < len(normalized):
        raw_end = min(len(normalized), start + size)
        end = raw_end
        if raw_end < len(normalized):
            boundary = max(
                normalized.rfind(". ", start + size // 2, raw_end),
                normalized.rfind("; ", start + size // 2, raw_end),
            )
            if boundary > start:
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            rows.append((start, end, chunk))
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return rows


class ChapterRetriever:
    def __init__(self, chapter: int, page_rows: list[dict[str, Any]]) -> None:
        self.chapter = chapter
        self.chunks: list[dict[str, Any]] = []
        document_frequency: Counter[str] = Counter()
        for page in page_rows:
            if not page.get("inside_chapter_boundary"):
                continue
            for chunk_index, (start, end, text) in enumerate(chunks_for_page(page.get("segment_text") or ""), start=1):
                token_counts = Counter(tokens(text))
                if not token_counts:
                    continue
                # Document frequency counts chunks containing a term, not raw
                # occurrences.  Counting occurrences can make IDF negative.
                document_frequency.update(token_counts.keys())
                text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                self.chunks.append(
                    {
                        "chapter": chapter,
                        "source_file": page["source_file"],
                        "source_file_sha256": page["source_file_sha256"],
                        "pdf_page": page["pdf_page"],
                        "printed_page": page.get("printed_page"),
                        "chunk_index": chunk_index,
                        "start_char": start,
                        "end_char": end,
                        "text": text,
                        "text_sha256": text_hash,
                        "token_counts": token_counts,
                        "token_set": set(token_counts),
                    }
                )
        count = max(1, len(self.chunks))
        self.idf = {
            token: math.log((count + 1) / (frequency + 1)) + 1.0
            for token, frequency in document_frequency.items()
        }

    def search(self, query: str, *, primary_query: str | None = None) -> dict[str, Any] | None:
        query_counts = Counter(tokens(query))
        primary_counts = Counter(tokens(primary_query if primary_query is not None else query))
        if not query_counts or not self.chunks:
            return None
        query_weight = sum(self.idf.get(token, 1.0) * frequency for token, frequency in query_counts.items())
        primary_weight = sum(
            self.idf.get(token, 1.0) * frequency for token, frequency in primary_counts.items()
        )
        if not query_weight:
            return None
        best: tuple[float, str, dict[str, Any], list[str]] | None = None
        for chunk in self.chunks:
            overlap = sorted(set(query_counts) & chunk["token_set"])
            if not overlap:
                continue
            primary_overlap = sorted(set(primary_counts) & chunk["token_set"])
            if primary_counts and not primary_overlap:
                # A disease-name match alone is not a claim-level locator.
                continue
            matched = sum(
                self.idf.get(token, 1.0)
                * min(query_counts[token], 1 + math.log1p(chunk["token_counts"][token]))
                for token in overlap
            )
            context_coverage = min(1.0, matched / query_weight)
            primary_matched = sum(
                self.idf.get(token, 1.0)
                * min(primary_counts[token], 1 + math.log1p(chunk["token_counts"][token]))
                for token in primary_overlap
            )
            primary_coverage = min(1.0, primary_matched / primary_weight) if primary_weight else 0.0
            density = min(1.0, len(overlap) / max(3.0, math.sqrt(len(chunk["token_counts"]))))
            score = round(0.75 * primary_coverage + 0.15 * context_coverage + 0.10 * density, 6)
            tie_breaker = chunk["text_sha256"]
            candidate = (score, tie_breaker, chunk, overlap)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
        if best is None:
            return None
        score, _, chunk, overlap = best
        level = "candidate_high" if score >= 0.45 else "candidate_medium" if score >= 0.23 else "candidate_low"
        locator_id = (
            f"harrison:22e:ch{self.chapter}:p{chunk.get('printed_page') or 'na'}:"
            f"pdf{chunk['pdf_page']}:chunk{chunk['chunk_index']}:{chunk['text_sha256'][:12]}"
        )
        return {
            "ref_id": locator_id,
            "source_type": "textbook_retrieval_candidate",
            "edition": "22e",
            "chapter": self.chapter,
            "source_file": chunk["source_file"],
            "source_file_sha256": chunk["source_file_sha256"],
            "pdf_page": chunk["pdf_page"],
            "printed_page": chunk.get("printed_page"),
            "chunk_index": chunk["chunk_index"],
            "chunk_text_sha256": chunk["text_sha256"],
            "retrieval_method": "deterministic_lexical_bm25_like_v1",
            "retrieval_score": score,
            "retrieval_level": level,
            "matched_terms": overlap[:24],
            "review_excerpt": chunk["text"][:420],
            "scope": "claim_level_candidate_not_entailment",
            "entailment_status": "needs_human_review",
        }


def load_pages(path: Path) -> dict[int, list[dict[str, Any]]]:
    pages: dict[int, list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            pages[int(row["chapter"])].append(row)
    for rows in pages.values():
        rows.sort(key=lambda row: int(row["pdf_page"]))
    return pages


def concept_display(concept_id: str, concept: dict[str, Any]) -> str:
    aliases = [str(value) for value in concept.get("aliases") or [] if value]
    return " ".join([concept_id.replace("_", " "), *aliases[:4]])


def review_priority(axis_type: str, relation: str, label: str, has_candidate: bool) -> str:
    high_risk_word = bool(
        re.search(
            r"\b(?:avoid|contraindicat|dose|mg|mcg|pregnan|do not|never|must|first[- ]line|emergen)",
            label,
            flags=re.I,
        )
    )
    if axis_type in HIGH_RISK_AXIS_TYPES or relation in HIGH_RISK_RELATIONS or high_risk_word:
        return "P0"
    if not has_candidate:
        return "P1"
    return "P1" if axis_type in {"pathophysiology", "prognosis", "risk_factor"} else "P2"


def output_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build(
    snapshot_dir: Path,
    concept_path: Path,
    axis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    manifest_path = snapshot_dir / "snapshot_manifest.json"
    chapter_index_path = snapshot_dir / "chapter_index.json"
    pages_path = snapshot_dir / "pages.jsonl"
    manifest = load_json(manifest_path)
    chapter_index_payload = load_json(chapter_index_path)
    concepts_payload = load_json(concept_path)
    axis_payload = load_json(axis_path)
    concepts = concepts_payload.get("concepts") or {}
    chapter_index = {int(row["chapter"]): row for row in chapter_index_payload.get("chapters", [])}
    pages = load_pages(pages_path)

    baseline = {
        "schema_version": "ontology_harrison_baseline.v1",
        "scope": "pre-Harrison-22e-claim-revalidation",
        "reality_check": (
            "Legacy files were labelled 21e, but the preserved TOC and Part PDFs are 22e. "
            "This is not a verified 21e-to-22e edition delta."
        ),
        "inputs": {
            "concept_registry": {"path": str(concept_path.relative_to(ROOT)), "sha256": sha256_file(concept_path)},
            "axis_registry": {"path": str(axis_path.relative_to(ROOT)), "sha256": sha256_file(axis_path)},
            "harrison_snapshot": {"snapshot_id": manifest["snapshot_id"], "sha256": sha256_file(manifest_path)},
        },
        "counts": {
            "concepts": len(concepts),
            "axis_nodes": len(axis_payload.get("nodes") or []),
            "axis_relationships": len(axis_payload.get("relationships") or []),
            "claims": len(axis_payload.get("nodes") or []) + len(axis_payload.get("relationships") or []),
        },
    }
    baseline_path = output_dir / "baseline" / "current_ontology_manifest.json"
    if not baseline_path.exists():
        output_json(baseline_path, baseline)

    concept_overlay: dict[str, dict[str, Any]] = {}
    concept_status_counts: Counter[str] = Counter()
    for concept_id, concept in sorted(concepts.items()):
        legacy = ((concept.get("evidence") or {}).get("harrison") or {})
        chapter = legacy.get("chapter")
        if chapter is None:
            status = "no_chapter_mapping"
            concept_overlay[concept_id] = {
                "concept_id": concept_id,
                "mapping_status": status,
                "needs_review": True,
                "medical_approval": False,
            }
            concept_status_counts[status] += 1
            continue
        chapter = int(chapter)
        source = chapter_index.get(chapter)
        if not source:
            status = "chapter_not_in_snapshot"
            concept_overlay[concept_id] = {
                "concept_id": concept_id,
                "legacy_harrison": legacy,
                "mapping_status": status,
                "needs_review": True,
                "medical_approval": False,
            }
            concept_status_counts[status] += 1
            continue
        title_match = normalize_title(legacy.get("title")) == normalize_title(source.get("title"))
        page_match = legacy.get("page") == source.get("toc_printed_page")
        status = "exact_22e_pointer" if title_match and page_match else "22e_pointer_needs_review"
        concept_overlay[concept_id] = {
            "concept_id": concept_id,
            "mapping_status": status,
            "legacy_harrison": legacy,
            "harrison": {
                "source_id": manifest["snapshot_id"],
                "edition": "22e",
                "chapter": chapter,
                "title": source.get("title"),
                "page": source.get("toc_printed_page"),
                "part": source.get("part"),
                "source_file": source.get("source_file"),
                "source_file_sha256": source.get("source_file_sha256"),
                "first_pdf_page": source.get("first_segmented_pdf_page"),
                "pointer_scope": "chapter_pointer_not_claim_entailment",
                "confidence": legacy.get("confidence") or "needs_review",
                "status": "harrison_22e_snapshot_validated",
                "needs_review": True,
                "medical_approval": False,
                "accessmedicine": None,
            },
            "validation": {
                "chapter_match": True,
                "title_match": title_match,
                "printed_page_match": page_match,
                "legacy_accessmedicine_removed_from_primary": bool(legacy.get("accessmedicine")),
            },
            "needs_review": True,
            "medical_approval": False,
        }
        concept_status_counts[status] += 1

    concept_overlay_payload = {
        "schema_version": "harrison22_concept_overlay.v1",
        "snapshot_id": manifest["snapshot_id"],
        "baseline_note": "provenance correction and mapping validation; not a 21e-to-22e diff",
        "summary": {
            "concepts": len(concept_overlay),
            "mapping_statuses": dict(sorted(concept_status_counts.items())),
            "automatic_medical_approvals": 0,
        },
        "concepts": concept_overlay,
    }
    output_json(output_dir / "concept_harrison_overlay.json", concept_overlay_payload)

    node_index = {row["axis_id"]: row for row in axis_payload.get("nodes") or []}
    retrievers: dict[int, ChapterRetriever] = {}

    def retrieve(chapter: int, query: str, primary_query: str) -> dict[str, Any] | None:
        if chapter not in retrievers:
            retrievers[chapter] = ChapterRetriever(chapter, pages.get(chapter) or [])
        return retrievers[chapter].search(query, primary_query=primary_query)

    claim_rows: dict[str, dict[str, Any]] = {}
    worklist: list[dict[str, Any]] = []
    retrieval_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    axis_type_counts: Counter[str] = Counter()

    raw_claims: list[tuple[dict[str, Any], list[str], str, str, str]] = []
    for node in axis_payload.get("nodes") or []:
        raw_claims.append(
            (node, list(node.get("disease_ids") or []), str(node.get("axis_type") or ""), "axis_node", "")
        )
    for relationship in axis_payload.get("relationships") or []:
        node = node_index.get(relationship.get("axis_id")) or {}
        raw_claims.append(
            (
                relationship,
                [str(relationship.get("disease_concept_id") or "")],
                str(node.get("axis_type") or ""),
                "axis_relationship",
                str(relationship.get("relation") or ""),
            )
        )

    for claim, disease_ids, axis_type, claim_kind, relation in raw_claims:
        claim_identifier = str(claim.get("claim_id") or "")
        node = claim if claim_kind == "axis_node" else node_index.get(claim.get("axis_id")) or {}
        label = str(node.get("label") or "")
        candidates: list[dict[str, Any]] = []
        mapped_diseases: list[str] = []
        for disease_id in sorted(set(filter(None, disease_ids))):
            concept = concepts.get(disease_id) or {}
            overlay = concept_overlay.get(disease_id) or {}
            harrison = overlay.get("harrison") or {}
            chapter = harrison.get("chapter")
            if chapter is None:
                continue
            mapped_diseases.append(disease_id)
            query = " ".join(
                value for value in (concept_display(disease_id, concept), relation.replace("_", " "), label) if value
            )
            candidate = retrieve(int(chapter), query, label)
            if candidate:
                candidate = dict(candidate)
                candidate["disease_concept_id"] = disease_id
                candidate["query_sha256"] = hashlib.sha256(query.encode("utf-8")).hexdigest()
                candidates.append(candidate)
        candidates.sort(
            key=lambda row: (-float(row["retrieval_score"]), row["disease_concept_id"], row["ref_id"])
        )
        candidates = candidates[:3]
        retrieval_level = candidates[0]["retrieval_level"] if candidates else (
            "no_candidate" if mapped_diseases else "no_chapter_mapping"
        )
        priority = review_priority(axis_type, relation, label, bool(candidates))
        row = {
            "claim_id": claim_identifier,
            "claim_kind": claim_kind,
            "axis_id": claim.get("axis_id") if claim_kind == "axis_relationship" else node.get("axis_id"),
            "axis_type": axis_type,
            "relation": relation or None,
            "label_sha256": hashlib.sha256(label.encode("utf-8")).hexdigest(),
            "disease_ids": sorted(set(filter(None, disease_ids))),
            "mapped_disease_ids": mapped_diseases,
            "retrieval_status": retrieval_level,
            "evidence_status": "needs_human_review",
            "proposed_change_class": "unmappable_pending_human_comparison",
            "change_class_basis": (
                "A retrieval candidate cannot establish unchanged, modified, new, or deprecated status."
            ),
            "review_priority": priority,
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "analytics_eligible": False,
            "promotion_status": "not_promoted",
            "candidates": candidates,
        }
        claim_rows[claim_identifier] = row
        retrieval_counts[retrieval_level] += 1
        priority_counts[priority] += 1
        axis_type_counts[axis_type or "unknown"] += 1
        worklist.append(
            {
                "claim_id": claim_identifier,
                "priority": priority,
                "axis_type": axis_type,
                "relation": relation or None,
                "disease_ids": row["disease_ids"],
                "retrieval_status": retrieval_level,
                "best_ref_id": candidates[0]["ref_id"] if candidates else None,
                "review_decision": None,
                "medical_approval": False,
            }
        )

    worklist.sort(key=lambda row: ({"P0": 0, "P1": 1, "P2": 2}[row["priority"]], row["claim_id"]))
    summary = {
        "claims": len(claim_rows),
        "retrieval_statuses": dict(sorted(retrieval_counts.items())),
        "review_priorities": dict(sorted(priority_counts.items())),
        "axis_types": dict(sorted(axis_type_counts.items())),
        "automatic_medical_approvals": 0,
        "student_visible_claims": 0,
        "verified_entailment_claims": 0,
    }
    overlay_payload = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": manifest["snapshot_id"],
        "source_manifest_sha256": sha256_file(manifest_path),
        "baseline_axis_registry_sha256": sha256_file(axis_path),
        "method": {
            "retrieval": "deterministic lexical candidate retrieval within mapped Harrison 22e chapter",
            "boundary_aware": True,
            "entailment_inference_performed": False,
            "edition_delta_inference_performed": False,
            "automatic_approval_performed": False,
        },
        "summary": summary,
        "claims": claim_rows,
    }
    worklist_payload = {
        "schema_version": "harrison22_claim_review_worklist.v1",
        "snapshot_id": manifest["snapshot_id"],
        "summary": summary,
        "items": worklist,
    }
    impact_payload = {
        "schema_version": "harrison22_downstream_impact.v1",
        "snapshot_id": manifest["snapshot_id"],
        "scope": "evidence provenance enrichment only",
        "identity_invariants": {
            "concept_ids_expected_unchanged": len(concepts),
            "claim_ids_expected_unchanged": len(claim_rows),
            "medical_approval_changes": 0,
        },
        "consumers_requiring_fresh_derived_export": [
            "axis_registry",
            "Neo4j import bundle",
            "Obsidian export",
            "ontology graph visualization",
            "question-generation evidence packets",
            "Q&A retrieval packets",
            "Anki evidence disclosures",
            "student feedback packets",
        ],
        "consumer_policy": (
            "Retrieval candidates may be shown as unverified source locators, but cannot be used as "
            "verified medical claims until an explicit human review decision exists."
        ),
    }
    output_json(output_dir / "validation" / "claim_support_overlay.json", overlay_payload)
    output_json(output_dir / "validation" / "review_worklist.json", worklist_payload)
    output_json(output_dir / "validation" / "downstream_impact.json", impact_payload)
    output_json(output_dir / "validation" / "summary.json", {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": manifest["snapshot_id"],
        "concept_summary": concept_overlay_payload["summary"],
        "claim_summary": summary,
        "artifact_hashes": {
            "concept_overlay": sha256_file(output_dir / "concept_harrison_overlay.json"),
            "claim_overlay": sha256_file(output_dir / "validation" / "claim_support_overlay.json"),
            "review_worklist": sha256_file(output_dir / "validation" / "review_worklist.json"),
            "downstream_impact": sha256_file(output_dir / "validation" / "downstream_impact.json"),
        },
    })
    return {"snapshot_id": manifest["snapshot_id"], **summary}


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--concept-registry", type=Path, default=DEFAULT_CONCEPTS)
    parser.add_argument("--axis-registry", type=Path, default=DEFAULT_AXIS)
    parser.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    result = build(args.snapshot, args.concept_registry, args.axis_registry, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
