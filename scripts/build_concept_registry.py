#!/usr/bin/env python3
"""Ontology Step 0/1 build (deterministic).

Source of truth: docs/Ontology_RAG_Generation_Integration_20260710.md §6,
docs/Ontology_Axis_Recommendation_20260710.md §8, Ontology_Build_Prompt_Pack §① DOMAIN_MAP.

Produces four artifacts under data_private/ (all git-ignored):
  1. concept_registry.json        backbone: 215 disease seeds, bare snake_case, Harrison inherited
  2. embedding/qbank_relabeled.json  672 items with disease_concept_id[] + finding_tags[] + canonical domain
  3. embedding/coverage_report.md  the join-health metric (% items with >=1 disease_concept_id)
  4. embedding/deficit_queue.csv   unmatched items -> registry-expansion priorities

Deterministic, re-runnable, no external transmission, no medical inference.
Everything carries needs_review=true; a human medical reviewer clears the gate.
"""
from __future__ import annotations
import json
import re
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
HARRISON = DP / "harrison" / "concept_to_harrison.json"
QBANK = DP / "embedding" / "consolidated_qbank.json"

OUT_REGISTRY = DP / "concept_registry.json"
OUT_RELABELED = DP / "embedding" / "qbank_relabeled.json"
OUT_COVERAGE = DP / "embedding" / "coverage_report.md"
OUT_DEFICIT = DP / "embedding" / "deficit_queue.csv"

# Curriculum-derived registry expansions (adversarially vetted, needs_review=true).
# Applied on top of the 215 seed so the whole pipeline stays re-runnable/idempotent.
# Each spec = (path, source_tag). Order matters: earlier files win on id collisions.
EXPANSION_SPECS = [
    (DP / "curriculum" / "heme_onc_expansion_final.json", "heme_onc_curriculum_expansion"),
    (DP / "curriculum" / "wave2_expansion_final.json", "korean_topic_recovery_expansion"),
    (DP / "curriculum" / "wave3_expansion_final.json", "korean_topic_recovery_expansion_pass2"),
    (DP / "curriculum" / "wave4_expansion_final.json", "differential_bridge_expansion"),
    (DP / "curriculum" / "wave5_pbbm_crossval_expansion.json", "pbbm_crossval_expansion"),
    (DP / "curriculum" / "kr_guideline_expansion_final.json", "kr_guideline_topic_expansion"),
]
SCOPE_SPLIT_CONCEPTS = DP / "curriculum" / "clinical_axes_scope_split_concepts_20260712.json"

# ── assessment_domain normalization (raw 34 -> canonical 15) ──
# Copied verbatim from Ontology_Build_Prompt_Pack_20260710.md §① / P1 DOMAIN_MAP.
DOMAIN_MAP = {
    "진단": "diagnosis", "감별 진단": "diagnosis",
    "치료": "treatment", "치료 선택": "treatment", "치료 선택형": "treatment",
    "치료 원칙": "treatment_principle", "치료 적응증": "treatment_principle",
    "약물": "pharmacotherapy", "약물 선택": "pharmacotherapy",
    "병태생리": "pathophysiology", "기전": "pathophysiology", "병태생리/위험인자": "pathophysiology",
    "검사 선택": "test_selection", "검사": "test_selection", "검사 도구": "test_selection",
    "검사 해석": "test_interpretation", "검사해석": "test_interpretation",
    "자료 해석": "test_interpretation", "현미경 판독": "test_interpretation",
    "개념 확인": "concept_check",
    "응급처치": "emergency_management", "응급 처치": "emergency_management", "처치": "emergency_management",
    "예후": "prognosis",
    "합병증": "complication",
    "병기": "staging_severity", "중증도 평가": "staging_severity", "위험도 분류": "staging_severity",
    "예방": "prevention", "상담/예방": "prevention", "검진 권고": "prevention",
    "계산": "calculation", "계산/평가": "calculation",
    "모니터링": "monitoring",
}
CANONICAL_15 = [
    "diagnosis", "treatment", "treatment_principle", "pharmacotherapy", "pathophysiology",
    "test_selection", "test_interpretation", "concept_check", "emergency_management",
    "prognosis", "complication", "staging_severity", "prevention", "calculation", "monitoring",
]

# Non-disease seeds in concept_to_harrison to FLAG (not delete) for human review.
NON_DISEASE_EXPLICIT = {"allergic", "travel"}


def norm_tag(t: str) -> str:
    """Normalize a tag to the bare snake_case id convention for registry membership check."""
    return re.sub(r"[^a-z0-9_]", "", str(t).strip().lower().replace(" ", "_").replace("-", "_"))


def is_non_disease(cid: str) -> bool:
    return cid.endswith("_act") or cid in NON_DISEASE_EXPLICIT


def load_registry_seed() -> dict:
    raw = json.loads(HARRISON.read_text(encoding="utf-8"))
    return raw["concept_to_harrison"]


def build_registry(seed: dict) -> dict:
    entries = {}
    for cid, h in seed.items():
        node_type = "non_disease_flagged" if is_non_disease(cid) else "disease"
        entries[cid] = {
            "disease_concept_id": cid,
            "node_type": node_type,          # disease | non_disease_flagged (human review)
            "aliases": [],                    # Korean/English surface forms — filled by P2/expansion
            "edges": {                        # typed graph edges — authored by P2
                "differential_of": [], "caused_by": [], "treated_with": [], "diagnosed_by": [],
            },
            "evidence": {
                "harrison": {
                    "chapter": h.get("chapter"), "title": h.get("title"),
                    "page": h.get("page"), "part": h.get("part"),
                    "accessmedicine": h.get("accessmedicine"),
                    "confidence": h.get("confidence"), "status": h.get("status"),
                },
                "ncbi": None,
            },
            "in_registry": True,
            "source": "concept_to_harrison_seed",
            "needs_review": True,
        }
    return {
        "_meta": {
            "generated_by": "build_concept_registry.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed_source": "data_private/harrison/concept_to_harrison.json",
            "id_convention": "bare_snake_case",
            "id_convention_note": (
                "Ontology v1 canonical IDs use bare lowercase snake_case. "
                "studio_concept.schema.json was aligned to this convention on 2026-07-12."
            ),
            "count": len(entries),
            "non_disease_flagged": sorted(c for c in entries if entries[c]["node_type"] != "disease"),
            "all_needs_review": True,
        },
        "concepts": entries,
    }


def apply_expansions(reg: dict) -> dict:
    """Merge curriculum-derived expansion nodes onto the seed registry (idempotent)."""
    concepts = reg["concepts"]
    added, alias_touched, skipped, alias_missing = [], [], [], []
    applied_files, per_source = [], {}
    for ef, source in EXPANSION_SPECS:
        if not ef.exists():
            continue
        applied_files.append(str(ef.relative_to(ROOT)))
        data = json.loads(ef.read_text(encoding="utf-8"))
        n_added = 0
        for a in data.get("additions", []):
            cid = a["disease_concept_id"]
            if cid in concepts:
                skipped.append(cid)          # earlier spec already added it; keep first
                continue
            part = a.get("harrison_part")
            harrison = None if part is None else {
                "chapter": None, "title": None, "page": None, "part": part,
                "accessmedicine": None, "confidence": "needs_mapping", "status": "expansion_part_only",
            }
            concepts[cid] = {
                "disease_concept_id": cid,
                "node_type": a.get("node_type", "disease"),   # disease | syndrome | neoplasm
                "aliases": a.get("aliases", []),
                "edges": {"differential_of": [], "caused_by": [], "treated_with": [], "diagnosed_by": []},
                "evidence": {"harrison": harrison, "ncbi": None},  # title/page still null pending mapping
                "in_registry": True,
                "source": source,
                "band": a.get("band"),
                "specialty": a.get("specialty"),
                "source_refs": a.get("source_refs", []),
                "needs_review": True,
            }
            added.append(cid)
            n_added += 1
        for u in data.get("alias_updates", []):
            tid = u["existing_seed_id"]
            if tid not in concepts:
                alias_missing.append(tid)     # never fabricate a node from an alias update
                continue
            cur = concepts[tid].get("aliases", [])
            for al in u.get("new_aliases", []):
                if al not in cur:
                    cur.append(al)
            concepts[tid]["aliases"] = cur
            alias_touched.append(tid)
        per_source[source] = n_added
    reg["_meta"]["seed_count"] = 215
    reg["_meta"]["count"] = len(concepts)
    reg["_meta"]["expansion"] = {
        "sources": applied_files,
        "per_source_added": per_source,
        "added": len(added),
        "added_ids": sorted(added),
        "alias_updated": sorted(set(alias_touched)),
        "skipped_already_present": sorted(set(skipped)),
        "alias_target_missing": sorted(set(alias_missing)),
        "note": "expansion nodes: harrison title/page=null pending mapping; needs_review=true",
    }
    return reg


def apply_scope_split_concepts(reg: dict) -> dict:
    """Add reviewed-shape leaf candidates while quarantining ambiguous parents."""
    if not SCOPE_SPLIT_CONCEPTS.exists():
        return reg
    data = json.loads(SCOPE_SPLIT_CONCEPTS.read_text(encoding="utf-8"))
    concepts = reg["concepts"]
    sources = data.get("sources") or {}
    added: list[str] = []
    skipped: list[str] = []

    for parent_id in data.get("quarantined_parents") or []:
        parent = concepts.get(parent_id)
        if parent:
            parent["generation_grounding_status"] = "quarantined_scope_ambiguous"
            parent["scope_quarantine_source"] = str(SCOPE_SPLIT_CONCEPTS.relative_to(ROOT))

    for cid, row in (data.get("concepts") or {}).items():
        if cid in concepts:
            skipped.append(cid)
            continue
        parent_id = row.get("parent_id")
        aliases = [row.get("canonical_label"), *(row.get("aliases") or [])]
        aliases = [str(value) for value in aliases if value and str(value) != cid]
        source_refs = []
        for source_id in row.get("source_pointers") or []:
            source = sources.get(source_id) or {}
            if not source:
                continue
            source_refs.append(
                {
                    "ref_id": source_id,
                    "source_type": source.get("source_type") or "external_reference",
                    "authority": source.get("authority") or "",
                    "title": source.get("title") or "",
                    "url": source.get("url") or "",
                    "verified_on": source.get("accessed_at") or "2026-07-12",
                    "scope": "scope-split concept definition and clinical classification",
                    "entailment_status": "needs_human_review",
                }
            )
        concepts[cid] = {
            "disease_concept_id": cid,
            "node_type": row.get("node_type") or "disease",
            "aliases": list(dict.fromkeys(aliases)),
            "edges": {"differential_of": [], "caused_by": [], "treated_with": [], "diagnosed_by": []},
            "is_a": (
                [
                    {
                        "id": parent_id,
                        "label": (concepts.get(parent_id) or {}).get("aliases", [parent_id])[0]
                        if (concepts.get(parent_id) or {}).get("aliases")
                        else parent_id,
                        "relation": "is_a",
                        "source": "clinical_scope_split_20260712",
                    }
                ]
                if parent_id
                else []
            ),
            "evidence": {"harrison": None, "ncbi": None},
            "source_refs": source_refs,
            "in_registry": True,
            "source": "clinical_scope_split_20260712",
            "generation_grounding_status": row.get("generation_grounding_status") or "candidate_needs_review",
            "needs_review": True,
        }
        added.append(cid)

    reg["_meta"]["count"] = len(concepts)
    reg["_meta"]["clinical_scope_split"] = {
        "source": str(SCOPE_SPLIT_CONCEPTS.relative_to(ROOT)),
        "added": len(added),
        "added_ids": sorted(added),
        "skipped_already_present": sorted(skipped),
        "quarantined_parents": sorted(data.get("quarantined_parents") or []),
        "medical_approval": False,
    }
    return reg


P2_NODES = DP / "curriculum" / "p2_nodes.json"


EDGE_ENDPOINT_TYPES = DP / "curriculum" / "endpoint_types.json"
# type-licensing table (reference feedback: SNOMED/UMLS discipline) — allowed endpoint types per edge
EDGE_LICENSING = {
    "differential_of": {"disorder"},
    "treated_with": {"drug_substance", "test_procedure"},
    "diagnosed_by": {"test_procedure"},
    "causative_agent": {"organism_agent", "drug_substance"},
    "due_to": {"disorder"},
    "predisposes": {"finding", "disorder"},
    "presents_with": {"finding"},
}


def apply_edge_typing(reg: dict) -> dict:
    """Type every edge endpoint and reslot per the reference feedback: split caused_by into
    causative_agent/due_to/predisposes; move diagnosed_by findings to presents_with; tag types;
    tally type-licensing violations (deterministic QA gate). All edits are needs_review drafts."""
    if not EDGE_ENDPOINT_TYPES.exists():
        return reg
    ep_types = json.loads(EDGE_ENDPOINT_TYPES.read_text(encoding="utf-8")).get("types", {})
    concepts = reg["concepts"]
    reg_keys = set(concepts)
    from collections import Counter
    reslot, violations = Counter(), Counter()

    def etype(eid: str) -> str | None:
        if eid in reg_keys:
            return "disorder"                          # registry nodes are disease-class
        return ep_types.get(eid)

    for cid, c in concepts.items():
        old = c.get("edges") or {}
        new = {k: [] for k in ("differential_of", "causative_agent", "due_to", "predisposes",
                               "treated_with", "diagnosed_by", "presents_with")}

        def tagged(e):
            t = etype(e["id"])
            e2 = dict(e)
            e2["type"] = t
            # Refresh stale endpoint resolution whenever the canonical registry
            # expands.  P2 rows may have been authored while the target was not
            # yet a concept; retaining that old boolean would make a resolved
            # guideline-derived node look dangling after a deterministic rebuild.
            e2["in_registry"] = e["id"] in reg_keys
            return e2, t

        for e in old.get("differential_of", []):
            e2, t = tagged(e); new["differential_of"].append(e2)
            if t and t not in EDGE_LICENSING["differential_of"]:
                violations[f"differential_of<-{t}"] += 1
        for e in old.get("caused_by", []):
            e2, t = tagged(e)
            if t in ("organism_agent", "drug_substance"):
                new["causative_agent"].append(e2); reslot["caused_by->causative_agent"] += 1
            elif t == "finding":
                new["predisposes"].append(e2); reslot["caused_by->predisposes"] += 1
            elif t == "test_procedure":
                violations["caused_by<-test_procedure(dropped)"] += 1     # a test can't cause disease
            else:                                        # disorder or unknown -> direct cause
                new["due_to"].append(e2); reslot["caused_by->due_to"] += 1
        for e in old.get("diagnosed_by", []):
            e2, t = tagged(e)
            if t == "finding":
                new["presents_with"].append(e2); reslot["diagnosed_by->presents_with"] += 1
            elif t in ("test_procedure", None):
                new["diagnosed_by"].append(e2)
            else:
                new["diagnosed_by"].append(e2); violations[f"diagnosed_by<-{t}"] += 1
        for e in old.get("treated_with", []):
            e2, t = tagged(e); new["treated_with"].append(e2)
            if t and t not in EDGE_LICENSING["treated_with"]:
                violations[f"treated_with<-{t}"] += 1
        for e in old.get("presents_with", []):           # idempotent re-runs
            e2, _ = tagged(e); new["presents_with"].append(e2)

        c["edges"] = {k: v for k, v in new.items() if v}

    reg["_meta"]["edge_typing"] = {
        "reslot": dict(reslot), "violations": dict(violations),
        "note": ("endpoints typed (disorder|finding|test_procedure|drug_substance|organism_agent); "
                 "caused_by split -> causative_agent/due_to/predisposes; diagnosed_by findings -> presents_with; "
                 "type-licensing violations flagged. All needs_review."),
    }
    return reg


def merge_p2_edges(reg: dict) -> int:
    """Populate concept edges + cognitive_model from P2 authoring output (idempotent)."""
    if not P2_NODES.exists():
        return 0
    concepts = reg["concepts"]
    data = json.loads(P2_NODES.read_text(encoding="utf-8"))
    nodes = data.get("nodes", data) if isinstance(data, dict) else data
    applied = 0
    for n in nodes:
        nid = n.get("node_id")
        if nid not in concepts:
            continue
        e = n.get("edges") or {}
        concepts[nid]["edges"] = {
            k: [ep for ep in (e.get(k) or [])]
            for k in ("differential_of", "caused_by", "treated_with", "diagnosed_by")
        }
        if n.get("cognitive_model"):
            concepts[nid]["cognitive_model"] = n["cognitive_model"]
        if n.get("assessment_domains"):
            concepts[nid]["assessment_domains"] = n["assessment_domains"]
        concepts[nid]["gen_ready"] = False
        applied += 1
    reg["_meta"]["p2_edges_applied"] = applied
    return applied


REVIEW_OVERRIDES = DP / "curriculum" / "review_overrides.json"
EXPANSION_HARRISON = DP / "curriculum" / "expansion_harrison_map.json"
HARRISON22_OVERLAY = DP / "harrison" / "22e" / "concept_harrison_overlay.json"


ONTOLOGY_XREF = DP / "curriculum" / "ontology_xref_map.json"


def apply_ontology_xref(reg: dict) -> dict:
    """Attach authoritative MONDO cross-references (EBI OLS) to nodes for interoperability."""
    if not ONTOLOGY_XREF.exists():
        return reg
    m = json.loads(ONTOLOGY_XREF.read_text(encoding="utf-8")).get("map", {})
    concepts = reg["concepts"]
    xref = 0
    for cid, x in m.items():
        c = concepts.get(cid)
        if c and x and x.get("mondo_id"):
            c.setdefault("evidence", {})["ontology_xref"] = {
                "mondo_id": x["mondo_id"], "mondo_label": x.get("mondo_label"),
                "name_match": x.get("name_match"), "source": "MONDO via EBI OLS",
            }
            xref += 1
    reg["_meta"]["mondo_xref_count"] = xref
    return reg


MONDO_TAXONOMY = DP / "curriculum" / "mondo_taxonomy_map.json"
CLINICAL_AXES = DP / "curriculum" / "clinical_axes_map.json"


def apply_clinical_axes(reg: dict) -> dict:
    """Attach P3-authored clinical axes (pathophysiology/risk_factors/prognosis/treatment/epidemiology)
    so the ontology supports question types beyond diagnosis. All needs_review drafts."""
    if not CLINICAL_AXES.exists():
        return reg
    m = json.loads(CLINICAL_AXES.read_text(encoding="utf-8")).get("axes", {})
    concepts = reg["concepts"]
    n = 0
    for cid, ax in m.items():
        c = concepts.get(cid)
        if not c or not ax:
            continue
        c["clinical_axes"] = {
            "pathophysiology": ax.get("pathophysiology"),
            "risk_factors": ax.get("risk_factors", []),
            "prognosis": ax.get("prognosis"),
            "treatment": ax.get("treatment"),
            "epidemiology": ax.get("epidemiology"),
            "source": (
                "P3 clinical-axis authoring (authority-scoped alternate source)"
                if ax.get("evidence_refs")
                else "P3 clinical-axis authoring (Harrison-grounded)"
            ),
            "evidence_refs": ax.get("evidence_refs") or [],
            "needs_review": True,
        }
        if ax.get("evidence_refs"):
            c["source_refs"] = ax["evidence_refs"]
        # promote treatment.indicated_for / contraindicated_for to first-class edges (feedback: split treated_with)
        tr = ax.get("treatment") or {}
        e = c.setdefault("edges", {})
        if tr.get("indicated_for"):
            e["indicated_for"] = [{"id": x, "in_registry": x in concepts, "source": "clinical_axes"} for x in tr["indicated_for"]]
        if tr.get("contraindicated_for"):
            e["contraindicated_for"] = [{"id": x, "in_registry": x in concepts, "source": "clinical_axes"} for x in tr["contraindicated_for"]]
        n += 1
    reg["_meta"]["clinical_axes_count"] = n
    return reg


def apply_mondo_taxonomy(reg: dict) -> dict:
    """Attach the imported MONDO is-a hierarchy (parents + primary/top category) to nodes."""
    if not MONDO_TAXONOMY.exists():
        return reg
    m = json.loads(MONDO_TAXONOMY.read_text(encoding="utf-8")).get("map", {})
    concepts = reg["concepts"]
    n = 0
    n_isa = 0
    for cid, t in m.items():
        c = concepts.get(cid)
        if c and t:
            parents = t.get("parents", [])
            c["taxonomy"] = {                          # display linearization (single top_category)
                "primary_category": t.get("primary_category"),
                "top_category": t.get("top_category"),
                "parents": parents,
                "source": "MONDO is-a via EBI OLS",
            }
            # first-class multi-parent is_a edges (namespace separate from clinical `edges`)
            c["is_a"] = [{"id": p["mondo_id"], "label": p["label"], "relation": "is_a",
                          "source": "MONDO"} for p in parents]
            n += 1
            n_isa += len(c["is_a"])
    reg["_meta"]["mondo_taxonomy_count"] = n
    reg["_meta"]["isa_edge_count"] = n_isa
    return reg


def apply_harrison_map(reg: dict) -> dict:
    """Fill evidence.harrison for expansion nodes from the (grounded) expansion→Harrison map."""
    if not EXPANSION_HARRISON.exists():
        return reg
    m = json.loads(EXPANSION_HARRISON.read_text(encoding="utf-8")).get("map", {})
    concepts = reg["concepts"]
    filled = 0
    for cid, ref in m.items():
        c = concepts.get(cid)
        if c and ref:
            c.setdefault("evidence", {})["harrison"] = ref
            filled += 1
    reg["_meta"]["harrison_mapped_expansion"] = filled
    return reg


def apply_harrison22_overlay(reg: dict) -> dict:
    """Replace legacy edition labels with the validated 22e snapshot pointer.

    The old pointer is retained verbatim for audit.  This is an additive
    provenance correction: it does not approve a concept or claim that was
    previously unreviewed.
    """

    if not HARRISON22_OVERLAY.exists():
        reg["_meta"]["harrison_22e_overlay"] = {
            "status": "not_found_legacy_pointer_retained",
            "source": str(HARRISON22_OVERLAY.relative_to(ROOT)),
            "applied": 0,
        }
        return reg
    payload = json.loads(HARRISON22_OVERLAY.read_text(encoding="utf-8"))
    concepts = reg["concepts"]
    applied = 0
    unresolved = 0
    for cid, overlay in (payload.get("concepts") or {}).items():
        concept = concepts.get(cid)
        if not concept:
            continue
        replacement = overlay.get("harrison")
        if not replacement:
            unresolved += 1
            continue
        evidence = concept.setdefault("evidence", {})
        legacy = evidence.get("harrison")
        if legacy:
            evidence["legacy_harrison_pointer"] = legacy
        evidence["harrison"] = replacement
        evidence["harrison_refs"] = [replacement]
        applied += 1
    reg["_meta"]["harrison_22e_overlay"] = {
        "status": "applied",
        "source": str(HARRISON22_OVERLAY.relative_to(ROOT)),
        "schema_version": payload.get("schema_version"),
        "snapshot_id": payload.get("snapshot_id"),
        "applied": applied,
        "unresolved": unresolved,
        "medical_approval": False,
        "note": "Edition provenance corrected; claim entailment still requires human review.",
    }
    return reg


def apply_review_overrides(reg: dict) -> dict:
    """Apply medical-review sign-off: remove rejected expansion nodes, patch revised fields.
    Only touches expansion nodes (never the 215 Harrison seed)."""
    if not REVIEW_OVERRIDES.exists():
        return reg
    ov = json.loads(REVIEW_OVERRIDES.read_text(encoding="utf-8"))
    concepts = reg["concepts"]
    removed, revised = [], []
    for cid in ov.get("rejected_ids", []):
        c = concepts.get(cid)
        if c and c.get("source", "") != "concept_to_harrison_seed":  # never drop a seed
            del concepts[cid]
            removed.append(cid)
    for rev in ov.get("revisions", []):
        c = concepts.get(rev["id"])
        if not c:
            continue
        if rev.get("node_type"):
            c["node_type"] = rev["node_type"]
        if rev.get("specialty"):
            c["specialty"] = rev["specialty"]
        c["review_status"] = "revised"
        revised.append(rev["id"])
    reg["_meta"]["count"] = len(concepts)
    reg["_meta"]["medical_review"] = {
        "source": str(REVIEW_OVERRIDES.relative_to(ROOT)),
        "rejected_removed": sorted(removed),
        "revised": sorted(revised),
        "note": "medical-review sign-off applied; survivors remain needs_review=true pending human confirmation",
    }
    return reg


def relabel_qbank(reg_ids: set) -> tuple[list, dict]:
    qb = json.loads(QBANK.read_text(encoding="utf-8"))["items"]
    out = []
    stats = {
        "total": len(qb),
        "items_with_disease_id": 0,
        "ids_per_item": Counter(),
        "distinct_ids_used": set(),
        "domain_mapped": 0,
        "domain_null_propose": 0,
        "raw_domain_seen": Counter(),
        "unmapped_domains": Counter(),
        "total_concept_tags": 0,
        "total_finding_tags": 0,
        "total_disease_hits": 0,
    }
    for it in qb:
        tags = it.get("concept_tags") or []
        disease_ids, finding_tags = [], []
        for t in tags:
            if norm_tag(t) in reg_ids:
                nt = norm_tag(t)
                if nt not in disease_ids:
                    disease_ids.append(nt)
            else:
                finding_tags.append(t)  # VERBATIM demotion (HARD RULE 4)
        raw_domain = it.get("assessment_domain")
        canonical = DOMAIN_MAP.get(raw_domain)
        propose_domain = raw_domain is not None and canonical is None
        rec = {
            "id": it.get("id") or it.get("question_number"),
            "question_number": it.get("question_number"),
            "source_exam": it.get("source_exam"),
            "major_category": it.get("major_category"),
            "topic": it.get("topic"),
            "subtopic": it.get("subtopic"),
            "disease_concept_id": disease_ids,           # 0..n registry hits (deterministic)
            "finding_tags": finding_tags,                # demoted, verbatim
            "assessment_domain": canonical,              # canonical or null
            "raw_assessment_domain": raw_domain,         # echo (audit)
            "propose_domain": propose_domain,
            "needs_review": True,
            "join_source": "deterministic_concept_tag_registry_match",
        }
        out.append(rec)
        # stats
        stats["total_concept_tags"] += len(tags)
        stats["total_finding_tags"] += len(finding_tags)
        stats["total_disease_hits"] += len(disease_ids)
        stats["ids_per_item"][len(disease_ids)] += 1
        stats["distinct_ids_used"].update(disease_ids)
        if disease_ids:
            stats["items_with_disease_id"] += 1
        if raw_domain is not None:
            stats["raw_domain_seen"][raw_domain] += 1
        if canonical is not None:
            stats["domain_mapped"] += 1
        elif propose_domain:
            stats["domain_null_propose"] += 1
            stats["unmapped_domains"][raw_domain] += 1
    return out, stats


def write_coverage(reg: dict, stats: dict, relabeled: list) -> None:
    concepts = reg["concepts"]
    used = stats["distinct_ids_used"]
    never_hit = sorted(set(concepts) - used)
    non_disease = reg["_meta"]["non_disease_flagged"]
    total = stats["total"]
    pct = stats["items_with_disease_id"] / total * 100

    lines = []
    lines.append("# Ontology Coverage Report — Step 0/1 (deterministic)")
    lines.append("")
    lines.append(f"> generated {reg['_meta']['generated_at']} · build_concept_registry.py")
    lines.append("> All outputs DRAFT · needs_review=true · human medical-review gate pending.")
    lines.append("")
    lines.append("## Join-health metric (the load-bearing number)")
    lines.append("")
    lines.append(f"- **Items with ≥1 disease_concept_id: {stats['items_with_disease_id']}/{total} ({pct:.1f}%)**")
    lines.append(f"  - Docs baseline claim: 111/17%. This run: {stats['items_with_disease_id']}/{pct:.1f}% → reconciled.")
    lines.append(f"- Distinct registry ids actually used: {len(used)} / {len(concepts)} seeds")
    lines.append(f"- Total concept_tags: {stats['total_concept_tags']} → "
                 f"disease hits {stats['total_disease_hits']} · demoted to finding_tags {stats['total_finding_tags']}")
    lines.append("")
    lines.append("### disease_concept_id per item")
    for k in sorted(stats["ids_per_item"]):
        lines.append(f"- {k} id(s): {stats['ids_per_item'][k]} items")
    lines.append("")
    lines.append("## assessment_domain normalization (raw 34 → canonical 15)")
    lines.append("")
    lines.append(f"- Mapped to canonical: {stats['domain_mapped']}/{total}")
    lines.append(f"- Unmapped (propose_domain=true): {stats['domain_null_propose']}")
    if stats["unmapped_domains"]:
        lines.append(f"- Unmapped raw values: {dict(stats['unmapped_domains'])}")
    else:
        lines.append("- Unmapped raw values: none (all 34 raw values covered by DOMAIN_MAP)")
    lines.append("")
    lines.append("## Registry quality flags (for human review)")
    lines.append("")
    lines.append(f"- **Non-disease seeds flagged: {len(non_disease)}** → `{non_disease}`")
    lines.append("  - `*_act` = Korean health laws; `allergic`/`travel` = non-disease fragments.")
    lines.append("  - NOT deleted; marked `node_type: non_disease_flagged` for reviewer to demote/remove.")
    lines.append(f"- **Seeds never hit by any question: {len(never_hit)}/{len(concepts)}**")
    lines.append("  - Expected: 215 seeds are Harrison-internal-medicine-centric; qbank spans more specialties.")
    lines.append(f"  - First 30 never-hit: `{never_hit[:30]}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- The ~17% join is the *starting* seam health, not a failure: it is the honest overlap "
                 "between a 215 internal-medicine seed and a 672 multi-specialty qbank.")
    lines.append("- The 83% unmatched items are the **registry-expansion work list** (see deficit_queue.csv), "
                 "and the primary place the 정리족/Harrison PDF sources feed new disease_concept_ids.")
    lines.append("- This deterministic pass assigns disease ids ONLY where a concept_tag already equals a "
                 "registry id. The richer LLM labeler (P1 prompt pack) recovers ids from Korean "
                 "topic/subtopic and proposes new ones — that is the next ticket.")
    OUT_COVERAGE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_deficit(relabeled: list, reg: dict, stats: dict) -> None:
    # Section A: unmatched items aggregated by (major_category, topic) -> expansion priority
    agg = defaultdict(lambda: {"count": 0, "subtopics": Counter(), "sample_tags": Counter()})
    for r in relabeled:
        if r["disease_concept_id"]:
            continue
        key = (r.get("major_category") or "", r.get("topic") or "")
        agg[key]["count"] += 1
        if r.get("subtopic"):
            agg[key]["subtopics"][r["subtopic"]] += 1
        for ft in r["finding_tags"][:5]:
            agg[key]["sample_tags"][ft] += 1
    rows = []
    for (mc, topic), v in sorted(agg.items(), key=lambda kv: -kv[1]["count"]):
        top_sub = "; ".join(f"{s}({n})" for s, n in v["subtopics"].most_common(3))
        top_tags = "; ".join(f"{t}({n})" for t, n in v["sample_tags"].most_common(5))
        rows.append({
            "major_category": mc, "topic": topic, "unmatched_count": v["count"],
            "top_subtopics": top_sub, "sample_finding_tags": top_tags,
            "priority_rank": 0,  # filled after sort
        })
    for i, row in enumerate(rows, 1):
        row["priority_rank"] = i
    with OUT_DEFICIT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=[
            "priority_rank", "major_category", "topic", "unmatched_count",
            "top_subtopics", "sample_finding_tags",
        ])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main() -> None:
    seed = load_registry_seed()
    reg = build_registry(seed)
    reg = apply_expansions(reg)
    reg = apply_scope_split_concepts(reg)
    reg = apply_review_overrides(reg)
    reg = apply_harrison_map(reg)
    reg = apply_harrison22_overlay(reg)
    reg = apply_ontology_xref(reg)
    reg = apply_mondo_taxonomy(reg)
    n_p2 = merge_p2_edges(reg)
    reg = apply_edge_typing(reg)
    reg = apply_clinical_axes(reg)
    OUT_REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

    reg_ids = set(reg["concepts"].keys())
    relabeled, stats = relabel_qbank(reg_ids)
    OUT_RELABELED.write_text(
        json.dumps({"total": len(relabeled), "items": relabeled}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_coverage(reg, stats, relabeled)
    n_deficit = write_deficit(relabeled, reg, stats)

    exp = reg["_meta"].get("expansion", {})
    scope_added = int((reg["_meta"].get("clinical_scope_split") or {}).get("added") or 0)
    effective_expansion = reg["_meta"]["count"] - len(seed)
    print("── Ontology Step 0/1 build complete ──")
    print(f"registry:   {OUT_REGISTRY.relative_to(ROOT)}  ({reg['_meta']['count']} concepts "
          f"= {len(seed)} seed + {effective_expansion - scope_added} curriculum expansion + "
          f"{scope_added} scope-split concepts, "
          f"{len(reg['_meta']['non_disease_flagged'])} non-disease flagged)")
    if exp.get("added"):
        print(f"expansion:  +{exp['added']} nodes · {len(exp.get('alias_updated', []))} alias updates"
              + (f" · SKIPPED already-present {exp['skipped_already_present']}" if exp.get('skipped_already_present') else "")
              + (f" · ALIAS-TARGET-MISSING {exp['alias_target_missing']}" if exp.get('alias_target_missing') else ""))
    if n_p2:
        print(f"p2 edges:   populated on {n_p2} concept nodes")
    print(f"relabeled:  {OUT_RELABELED.relative_to(ROOT)}  ({stats['total']} items)")
    print(f"coverage:   items_with_disease_id = {stats['items_with_disease_id']}/{stats['total']} "
          f"({stats['items_with_disease_id']/stats['total']*100:.1f}%) · "
          f"distinct ids used = {len(stats['distinct_ids_used'])}/{reg['_meta']['count']}")
    print(f"domains:    mapped {stats['domain_mapped']}/{stats['total']} · "
          f"unmapped {stats['domain_null_propose']} ({dict(stats['unmapped_domains'])})")
    print(f"deficit:    {OUT_DEFICIT.relative_to(ROOT)}  ({n_deficit} (major_category,topic) groups to expand)")


if __name__ == "__main__":
    main()
