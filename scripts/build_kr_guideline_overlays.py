#!/usr/bin/env python3
"""Build fail-closed ontology-topic and specialty-agent guideline overlays.

The overlays route review retrieval.  They do not copy guideline assertions
into the canonical ontology and cannot enable student or generation retrieval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data_private" / "kr_guidelines" / "verified_latest_registry.json"
DEFAULT_CONCEPTS = ROOT / "data_private" / "concept_registry.json"
DEFAULT_ONTOLOGY_OUT = ROOT / "data_private" / "kr_guidelines" / "ontology_overlay.json"
DEFAULT_AGENT_OUT = ROOT / "data_private" / "kr_guidelines" / "specialty_agent_registry.json"
ONTOLOGY_SCHEMA = ROOT / "schemas" / "kr_guideline_ontology_overlay.schema.json"
AGENT_SCHEMA = ROOT / "schemas" / "kr_guideline_agent_registry.schema.json"


# Keyword matching only creates review candidates.  It never attaches a source
# to a canonical concept.  Explicit seed mappings are separately visible.
TITLE_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("지역사회획득 폐렴", "community-acquired pneumonia", "community acquired pneumonia"), ("community_acquired_pneumonia",)),
    (("병원획득 폐렴", "hospital-acquired pneumonia", "hospital acquired pneumonia"), ("hospital_acquired_pneumonia",)),
    (("요로감염", "urinary tract infection"), ("urinary_tract_infection", "cystitis", "pyelonephritis")),
    (("복강내 감염", "intra-abdominal infection"), ("peritonitis", "appendicitis", "acute_cholecystitis", "diverticulitis")),
    (("피부 및 연조직", "skin and soft tissue"), ("cellulitis", "necrotizing_fasciitis")),
    (("결핵", "tuberculosis"), ("pulmonary_tuberculosis",)),
    (("패혈증", "sepsis", "septic shock"), ("sepsis",)),
    (("만성폐쇄성폐질환", "copd"), ("chronic_obstructive_pulmonary_disease",)),
    (("간질성폐질환", "interstitial lung disease"), ("interstitial_lung_disease",)),
    (("천식", "asthma"), ("asthma",)),
    (("심폐소생", "cardiopulmonary resuscitation"), ("cardiac_arrest",)),
    (("고혈압", "hypertension"), ("chronic_hypertension",)),
    (("심방세동", "atrial fibrillation"), ("atrial_fibrillation",)),
    (("심부전", "heart failure"), ("heart_failure",)),
    (("당뇨", "diabetes"), ("diabetes_mellitus", "type_1_diabetes", "type_2_diabetes")),
    (("갑상선결절", "thyroid nodule"), ("thyroid_nodule",)),
    (("갑상선암", "thyroid cancer"), ("thyroid_cancer",)),
    (("유두갑상선", "papillary thyroid"), ("papillary_thyroid_carcinoma",)),
    (("갑상선기능항진", "hyperthyroidism"), ("hyperthyroidism",)),
    (("만성콩팥", "만성 신장", "chronic kidney", "ckd"), ("chronic_kidney_disease",)),
    (("alport", "알포트"), ("alport_syndrome",)),
    (("통풍", "gout"), ("gout",)),
    (("골다공증", "osteoporosis"), ("osteoporosis",)),
    (("b형간염", "hepatitis b"), ("hepatitis_b",)),
    (("c형간염", "hepatitis c"), ("hepatitis_c",)),
    (("간경변", "cirrhosis"), ("cirrhosis",)),
    (("간세포암", "hepatocellular carcinoma"), ("hepatocellular_carcinoma",)),
    (("지방간", "masld", "nafld"), ("metabolic_dysfunction_associated_steatotic_liver_disease",)),
    (("클로스트리디오이데스", "clostridioides difficile"), ("clostridioides_difficile_colitis",)),
    (("crohn", "크론"), ("crohn_disease",)),
    (("ulcerative colitis", "궤양성 대장염"), ("ulcerative_colitis",)),
    (("위암", "gastric cancer"), ("gastric_cancer",)),
    (("대장암", "결장암", "colorectal cancer", "colon cancer"), ("colorectal_cancer",)),
    (("난소암", "ovarian cancer"), ("ovarian_cancer",)),
    (("자궁경부암", "cervical cancer"), ("cervical_cancer",)),
    (("자궁체부암", "endometrial cancer"), ("endometrial_cancer",)),
    (("전립선", "prostate cancer"), ("prostate_cancer",)),
    (("마이코플라스마 폐렴", "mycoplasma pneumonia"), ("mycoplasma_pneumonia",)),
    (("아토피피부염", "atopic dermatitis"), ("atopic_dermatitis",)),
    (("지주막하출혈", "subarachnoid hemorrhage"), ("subarachnoid_hemorrhage",)),
    (("뇌경색", "ischemic stroke"), ("acute_ischemic_stroke",)),
    (("뇌졸중", "stroke"), ("acute_ischemic_stroke", "intracerebral_hemorrhage")),
    (("쌍태임신", "twin pregnancy"), ("multiple_gestation",)),
    (("급성 상기도 감염", "acute upper respiratory"), ("acute_upper_respiratory_tract_infection",)),
    (("비만", "obesity"), ("obesity",)),
    (("이상지질혈증", "dyslipidemia"), ("dyslipidemia",)),
    (("당뇨병콩팥병", "diabetic kidney disease"), ("diabetic_kidney_disease",)),
    (("고혈압콩팥병", "hypertensive kidney disease"), ("hypertensive_kidney_disease",)),
    (("파브리신병증", "fabry nephropathy"), ("fabry_disease",)),
    (("카바페넴 내성 장내세균", "carbapenem-resistant enterobacterales"), ("carbapenem_resistant_enterobacterales_infection",)),
)

CURRENT_STATUSES = {"verified_latest_on_official_source", "living_guideline_current"}
INTENT_AXIS_MAP = {
    "diagnosis": ["diagnosis", "screening"],
    "treatment": ["treatment", "indication", "contraindication", "procedure"],
    "prevention": ["prevention", "public_health"],
    "follow_up": ["follow_up", "prognosis", "rehabilitation"],
    "epidemiology": ["epidemiology", "risk_factor"],
}

LABELS = {
    "cardiology": "심장내과",
    "pulmonology": "호흡기내과",
    "gastroenterology_hepatology": "소화기·간담도",
    "hematology_oncology": "혈액종양",
    "endocrinology": "내분비내과",
    "nephrology": "신장내과",
    "infectious_disease": "감염내과",
    "neurology": "신경과",
    "rheumatology": "류마티스내과",
    "obstetrics_gynecology": "산부인과",
    "pediatrics": "소아청소년과",
    "emergency_critical_care": "응급·중환자의학",
    "surgery_procedure": "외과·시술",
    "primary_care_prevention": "예방·일차의료",
    "oncology": "종양학",
    "diagnostic_support": "영상·병리·검사의학",
    "allergy_immunology": "알레르기·면역",
    "dermatology": "피부과",
    "anesthesiology": "마취통증의학",
    "rehabilitation": "재활의학",
    "urology": "비뇨의학",
    "orthopedics": "정형외과",
    "medical_genetics": "의학유전",
    "geriatrics": "노인의학",
    "psychiatry": "정신건강의학",
}

CANONICAL_SPECIALTY = {
    "endocrinology_metabolism": "endocrinology",
    "gastroenterology": "gastroenterology_hepatology",
    "genetics": "medical_genetics",
    "laboratory_medicine": "diagnostic_support",
    "maternal_fetal_medicine": "obstetrics_gynecology",
    "neonatology": "pediatrics",
    "nuclear_medicine": "diagnostic_support",
    "pathology": "diagnostic_support",
    "radiation_oncology": "hematology_oncology",
    "radiology": "diagnostic_support",
    "rehabilitation_medicine": "rehabilitation",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_ref(path: Path) -> dict:
    try:
        display_path = str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        display_path = str(path.resolve())
    return {
        "path": display_path,
        "bytes": path.stat().st_size,
        "sha256": sha256_path(path),
    }


def validate(payload: dict, schema_path: Path, *, label: str) -> None:
    validator = Draft7Validator(load_json(schema_path), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        detail = "\n".join(f"{list(error.path)}: {error.message}" for error in errors[:25])
        raise ValueError(f"{label}: schema validation failed ({len(errors)} errors)\n{detail}")


def candidate_matches(title: str, concept_ids: set[str]) -> list[dict]:
    normalized = re.sub(r"\s+", " ", title.casefold())
    matches: dict[tuple[str, str], dict] = {}
    for terms, candidates in TITLE_RULES:
        matched = next((term for term in terms if term.casefold() in normalized), None)
        if not matched:
            continue
        for concept_id in candidates:
            matches[(concept_id, matched)] = {
                "concept_id": concept_id,
                "matched_term": matched,
                "resolved_in_registry": concept_id in concept_ids,
                "mapping_status": "review_candidate_not_attached",
            }
    return [matches[key] for key in sorted(matches)]


def build_ontology_overlay(source_path: Path, concept_path: Path) -> dict:
    source_registry = load_json(source_path)
    concepts = (load_json(concept_path).get("concepts") or {})
    concept_ids = set(concepts)
    links = []
    concept_index: dict[str, list[str]] = defaultdict(list)
    candidate_concept_index: dict[str, list[str]] = defaultdict(list)
    unresolved: dict[str, list[str]] = defaultdict(list)
    sources_without_explicit = 0
    title_candidate_count = 0
    for source in source_registry.get("sources") or []:
        explicit = sorted(set(source.get("topic_concept_ids") or []))
        if not explicit:
            sources_without_explicit += 1
        resolved = sorted(concept_id for concept_id in explicit if concept_id in concept_ids)
        unresolved_explicit = sorted(concept_id for concept_id in explicit if concept_id not in concept_ids)
        candidates = candidate_matches(source["title"], concept_ids)
        title_candidate_count += len(candidates)
        for concept_id in resolved:
            concept_index[concept_id].append(source["source_id"])
        for concept_id in unresolved_explicit:
            unresolved[concept_id].append(source["source_id"])
        for candidate in candidates:
            if candidate["resolved_in_registry"]:
                candidate_concept_index[candidate["concept_id"]].append(source["source_id"])
            else:
                unresolved[candidate["concept_id"]].append(source["source_id"])
        links.append(
            {
                "source_id": source["source_id"],
                "title": source["title"],
                "latest_status": source["latest_status"],
                "clinical_axes": sorted(set(source.get("clinical_axes") or [])),
                "explicit_topic_concept_ids": explicit,
                "resolved_topic_concept_ids": resolved,
                "unresolved_topic_concept_ids": unresolved_explicit,
                "title_rule_candidates": candidates,
                "needs_review": True,
                "medical_approval": False,
                "canonical_registry_mutated": False,
            }
        )
    payload = {
        "schema_version": "kr_guideline_ontology_overlay.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_registry": file_ref(source_path),
        "concept_registry": file_ref(concept_path),
        "overlay_role": "topic_routing_review_overlay_not_claim_evidence",
        "safety_boundary": {
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "generation_eligible": False,
            "automatic_canonical_merge": False,
        },
        "summary": {
            "sources": len(links),
            "sources_without_explicit_topic_mapping": sources_without_explicit,
            "explicit_resolved_links": sum(len(row["resolved_topic_concept_ids"]) for row in links),
            "explicit_unresolved_links": sum(len(row["unresolved_topic_concept_ids"]) for row in links),
            "title_rule_review_candidates": title_candidate_count,
            "title_rule_resolved_review_candidates": sum(len(value) for value in candidate_concept_index.values()),
            "unresolved_concept_candidate_ids": len(unresolved),
            "canonical_registry_mutations": 0,
        },
        "source_links": links,
        "concept_index": {key: sorted(set(value)) for key, value in sorted(concept_index.items())},
        "candidate_concept_index": {
            key: sorted(set(value)) for key, value in sorted(candidate_concept_index.items())
        },
        "unresolved_concept_candidates": {
            key: sorted(set(value)) for key, value in sorted(unresolved.items())
        },
    }
    validate(payload, ONTOLOGY_SCHEMA, label="ontology overlay")
    return payload


def normalize_agent_id(value: str) -> str:
    if value.startswith("kr-specialist:"):
        return value
    slug = re.sub(r"[^a-z0-9._-]+", "_", value.casefold()).strip("_")
    return f"kr-specialist:{slug or 'unclassified'}"


def derive_intents(axes: list[str]) -> list[str]:
    intents = [intent for intent, allowed in INTENT_AXIS_MAP.items() if set(axes) & set(allowed)]
    return sorted(set(intents or ["general_reference"]))


def build_agent_registry(source_path: Path) -> dict:
    registry = load_json(source_path)
    agents: dict[str, dict] = {}
    for source in registry.get("sources") or []:
        explicit_routes = source.get("agent_routes") or []
        route_intents = sorted(
            {
                intent
                for route in explicit_routes
                for intent in (route.get("intents") or [])
            }
        ) or derive_intents(source.get("clinical_axes") or [])
        specialty_groups = {
            CANONICAL_SPECIALTY.get(specialty, specialty)
            for specialty in (source.get("specialties") or ["unclassified"])
        }
        for slug in sorted(specialty_groups):
            agent_id = f"kr-specialist:{slug}"
            row = agents.setdefault(
                agent_id,
                {
                    "agent_id": agent_id,
                    "label_ko": LABELS.get(slug, slug.replace("_", " ")),
                    "specialties": set(),
                    "intents": set(),
                    "clinical_axes": set(),
                    "source_ids": set(),
                    "current_source_ids": set(),
                    "review_only_source_ids": set(),
                },
            )
            row["specialties"].update(source.get("specialties") or [slug])
            row["intents"].update(route_intents or ["general_reference"])
            row["clinical_axes"].update(source.get("clinical_axes") or [])
            row["source_ids"].add(source["source_id"])
            if source["latest_status"] in CURRENT_STATUSES:
                row["current_source_ids"].add(source["source_id"])
            else:
                row["review_only_source_ids"].add(source["source_id"])

    output_agents = []
    for agent_id in sorted(agents):
        row = agents[agent_id]
        source_ids = sorted(row["source_ids"])
        output_agents.append(
            {
                "agent_id": agent_id,
                "label_ko": row["label_ko"],
                "specialties": sorted(row["specialties"]),
                "intents": sorted(row["intents"]),
                "clinical_axes": sorted(row["clinical_axes"]),
                "source_ids": source_ids,
                "source_count": len(source_ids),
                "current_source_ids": sorted(row["current_source_ids"]),
                "review_only_source_ids": sorted(row["review_only_source_ids"]),
                "review_retrieval_enabled": True,
                "student_retrieval_enabled": False,
                "generation_retrieval_enabled": False,
            }
        )
    payload = {
        "schema_version": "kr_guideline_agent_registry.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_registry": file_ref(source_path),
        "routing_role": "retrieval_scope_registry_not_separate_medical_models",
        "routing_policy": {
            "architecture": "one_retrieval_runtime_with_specialty_scopes",
            "separate_model_weights_required": False,
            "intent_axis_map": INTENT_AXIS_MAP,
            "current_source_status_allowlist": sorted(CURRENT_STATUSES),
            "default_top_k_claims": 12,
            "maximum_source_documents_per_answer": 4,
            "conflict_policy": "show_version_and_source_conflict; never silently choose",
            "claim_gate": "medical_approval_required_before_student_or_generation_use",
        },
        "safety_boundary": {
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "generation_eligible": False,
            "review_retrieval_enabled": True,
        },
        "summary": {
            "agents": len(output_agents),
            "source_route_links": sum(row["source_count"] for row in output_agents),
            "current_source_route_links": sum(len(row["current_source_ids"]) for row in output_agents),
            "review_only_source_route_links": sum(len(row["review_only_source_ids"]) for row in output_agents),
            "student_enabled_agents": 0,
            "generation_enabled_agents": 0,
        },
        "agents": output_agents,
    }
    validate(payload, AGENT_SCHEMA, label="specialty agent registry")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--concept-registry", type=Path, default=DEFAULT_CONCEPTS)
    parser.add_argument("--ontology-output", type=Path, default=DEFAULT_ONTOLOGY_OUT)
    parser.add_argument("--agent-output", type=Path, default=DEFAULT_AGENT_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ontology = build_ontology_overlay(args.source_registry, args.concept_registry)
    agents = build_agent_registry(args.source_registry)
    args.ontology_output.parent.mkdir(parents=True, exist_ok=True)
    args.ontology_output.write_text(json.dumps(ontology, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.agent_output.write_text(json.dumps(agents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"ontology": ontology["summary"], "agents": agents["summary"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
