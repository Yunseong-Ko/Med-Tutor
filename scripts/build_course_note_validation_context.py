#!/usr/bin/env python3
"""Attach historical-exam and local Ontology context to lecture note packets."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


EXAM_FILES = (
    "data_private/course_exams/final_review/HEME2026_1차/MASTER_혈종2026_1차_해설.json",
    "data_private/course_exams/final_review/HEME2026_2차/MASTER_혈종2026_2차_해설.json",
    "data_private/course_exams/final_review/HEME2023/MASTER_HEME2023_explanations.json",
)

STOPWORDS = {
    "혈액",
    "종양",
    "질환",
    "진단",
    "치료",
    "환자",
    "강의",
    "임상",
    "일반",
    "검사",
    "대한",
    "에서",
    "및",
    "the",
    "and",
    "with",
    "for",
    "disease",
    "cancer",
}

MANUAL_CONCEPT_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("철결핍", "iron deficiency"), ("iron_deficiency_anemia",)),
    (("대구성", "megaloblastic", "macrocy"), ("megaloblastic_anemia", "non_megaloblastic_macrocytosis")),
    (("후천성용혈", "autoimmune hemol"), ("autoimmune_hemolytic_anemia", "microangiopathic_hemolytic_anemia", "hemolytic_anemia")),
    (("선천용혈", "hereditary hemol"), ("hereditary_spherocytosis", "g6pd_deficiency", "thalassemia", "sickle_cell_disease")),
    (("소아 빈혈", "pediatric anemia"), ("iron_deficiency_anemia", "thalassemia", "hereditary_spherocytosis", "g6pd_deficiency")),
    (("aa and mds", "재생불량", "골수이형성"), ("aplastic_anemia", "myelodysplastic_syndrome")),
    (("acute leukemia", "급성백혈"), ("acute_myeloid_leukemia", "acute_lymphoblastic_leukemia", "acute_promyelocytic_leukemia")),
    (("소아백혈",), ("acute_lymphoblastic_leukemia", "acute_myeloid_leukemia", "cns_leukemia")),
    (("만성백혈",), ("chronic_myeloid_leukemia", "chronic_lymphocytic_leukemia")),
    (("골수증식", "myeloprolifer"), ("polycythemia_vera", "essential_thrombocythemia", "primary_myelofibrosis", "chronic_myeloid_leukemia")),
    (("lymphoma", "림프종"), ("hodgkin_lymphoma", "diffuse_large_b_cell_lymphoma", "follicular_lymphoma", "mantle_cell_lymphoma", "burkitt_lymphoma", "extranodal_nk_t_cell_lymphoma")),
    (("mm 강의", "multiple myeloma", "다발골수"), ("multiple_myeloma",)),
    (("혈소판",), ("immune_thrombocytopenia", "thrombotic_thrombocytopenic_purpura", "thrombocytopenia")),
    (("혈전",), ("deep_vein_thrombosis", "pulmonary_embolism")),
    (("응고질환", "지혈", "coagulation"), ("disseminated_intravascular_coagulation", "von_willebrand_disease", "hemophilia_a", "hemophilia_b")),
    (("유전성응고",), ("von_willebrand_disease", "hemophilia_a", "hemophilia_b", "hemophilia_c")),
    (("신생아혈액",), ("neonatal_alloimmune_thrombocytopenia", "hemolytic_disease_of_newborn", "rh_incompatibility_hemolytic_disease", "abo_incompatibility_hemolytic_disease")),
    (("수혈",), ("emergency_transfusion", "febrile_nonhemolytic_transfusion_reaction")),
    (("부종양",), ("humoral_hypercalcemia_of_malignancy", "paraneoplastic_thrombophlebitis")),
    (("종양응급",), ("tumor_lysis_syndrome", "malignant_spinal_cord_compression", "humoral_hypercalcemia_of_malignancy", "febrile_neutropenia")),
    (("원발불명",), ("carcinoma_of_unknown_primary",)),
)


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def tokenize(value: str) -> set[str]:
    normalized = nfc(value).lower().replace("_", " ")
    tokens = set(re.findall(r"[a-z][a-z0-9+\-]{2,}|[가-힣]{2,}", normalized))
    return {token for token in tokens if token not in STOPWORDS and len(token) >= 3}


def load_exam_items(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative in EXAM_FILES:
        path = root / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("items", []):
            if item.get("needs_review"):
                continue
            labels = item.get("labels", {})
            records.append(
                {
                    "source_exam": item.get("source_exam", payload.get("exam", path.stem)),
                    "question_number": str(item.get("question_number", "")),
                    "major_category": labels.get("major_category", ""),
                    "topic": labels.get("topic", ""),
                    "subtopic": labels.get("subtopic", ""),
                    "assessment_domain": labels.get("assessment_domain", ""),
                    "question_type": labels.get("question_type", ""),
                    "concept_tags": labels.get("concept_tags", []),
                    "key_learning_points": item.get("key_learning_points", []),
                    "important_clues": item.get("key_info", {}).get("important_clues", []),
                    "faculty_verified": labels.get("faculty_verified"),
                }
            )
    return records


def exam_item_text(item: dict[str, Any]) -> str:
    fields: list[str] = [
        item.get("major_category", ""),
        item.get("topic", ""),
        item.get("subtopic", ""),
        " ".join(item.get("concept_tags", [])),
        " ".join(item.get("key_learning_points", [])),
        " ".join(item.get("important_clues", [])),
    ]
    return nfc(" ".join(fields)).lower()


def rank_exam_items(title: str, packet_text: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    title_text = nfc(title).lower()
    packet_lower = nfc(packet_text).lower()
    title_tokens = tokenize(title_text)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for item in items:
        item_text = exam_item_text(item)
        item_tokens = tokenize(item_text)
        title_overlap = len(title_tokens & item_tokens)
        concept_hits = 0
        for tag in item.get("concept_tags", []):
            phrase = nfc(str(tag)).lower().replace("_", " ")
            if len(phrase) >= 4 and (phrase in packet_lower or str(tag).lower() in packet_lower):
                concept_hits += 1
        topic_hits = 0
        for value in (item.get("topic", ""), item.get("subtopic", "")):
            lowered = nfc(str(value)).lower().strip()
            if len(lowered) >= 3 and lowered in title_text:
                topic_hits += 3
            elif len(lowered) >= 3 and lowered in packet_lower:
                topic_hits += 1
        packet_token_hits = sum(1 for token in item_tokens if len(token) >= 4 and token in packet_lower)
        score = title_overlap * 7.0 + concept_hits * 4.0 + topic_hits * 2.5 + min(packet_token_hits, 6) * 0.4
        if score > 0:
            ranked.append((score, item))
    ranked.sort(key=lambda row: (-row[0], row[1]["source_exam"], row[1]["question_number"]))
    result = []
    for score, item in ranked[:16]:
        result.append({"match_score": round(score, 2), **item})
    return result


def collect_concept_terms(concept_id: str, concept: dict[str, Any]) -> set[str]:
    terms = {concept_id.lower(), concept_id.lower().replace("_", " ")}
    aliases = concept.get("aliases", [])
    if isinstance(aliases, list):
        terms.update(nfc(str(alias)).lower() for alias in aliases if str(alias).strip())
    return {term for term in terms if len(term) >= 5}


def summarize_concept(concept_id: str, concept: dict[str, Any]) -> dict[str, Any]:
    axes = concept.get("clinical_axes", {})
    harrison = concept.get("evidence", {}).get("harrison") or {}
    selected_axes: dict[str, Any] = {}
    for axis_name in (
        "pathophysiology",
        "symptoms",
        "diagnosis",
        "treatment",
        "prognosis",
        "risk_factors",
        "epidemiology",
    ):
        if axis_name in axes:
            selected_axes[axis_name] = axes[axis_name]
    return {
        "concept_id": concept_id,
        "needs_review": bool(concept.get("needs_review", True)),
        "medical_approval": bool(concept.get("medical_approval", False)),
        "harrison22_pointer": {
            "chapter": harrison.get("chapter"),
            "title": harrison.get("title"),
            "page": harrison.get("page"),
            "scope": harrison.get("pointer_scope"),
        }
        if harrison
        else None,
        "clinical_axes": selected_axes,
    }


def rank_concepts(title: str, packet_text: str, concepts: dict[str, Any]) -> list[dict[str, Any]]:
    title_lower = nfc(title).lower()
    packet_lower = nfc(packet_text).lower()
    manual_ids: list[str] = []
    for triggers, concept_ids in MANUAL_CONCEPT_RULES:
        if any(nfc(trigger).lower() in title_lower for trigger in triggers):
            manual_ids.extend(concept_ids)

    scored: Counter[str] = Counter()
    for concept_id in manual_ids:
        if concept_id in concepts:
            scored[concept_id] += 20
    for concept_id, concept in concepts.items():
        for term in collect_concept_terms(concept_id, concept):
            if term in title_lower:
                scored[concept_id] += 12
            elif term in packet_lower:
                scored[concept_id] += min(5, packet_lower.count(term))
    ranked = []
    for concept_id, score in scored.most_common(12):
        ranked.append({"match_score": score, **summarize_concept(concept_id, concepts[concept_id])})
    return ranked


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_context(root: Path, build_root: Path) -> None:
    inventory_path = build_root / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    concepts = json.loads((root / "data_private/concept_registry.json").read_text(encoding="utf-8"))["concepts"]
    exam_items = load_exam_items(root)

    topic_counts = Counter((item["topic"], item["subtopic"]) for item in exam_items)
    topic_summary = [
        {"topic": topic, "subtopic": subtopic, "question_count": count}
        for (topic, subtopic), count in topic_counts.most_common()
    ]
    write_json(build_root / "exam_topic_frequency.json", topic_summary)

    for group in inventory["groups"]:
        group_dir = build_root / "groups" / group["group_id"]
        packet_path = group_dir / "source_packet.md"
        packet_text = packet_path.read_text(encoding="utf-8")
        validation = {
            "schema_version": "1.0.0",
            "group_id": group["group_id"],
            "title": group["title"],
            "periods": group["periods"],
            "expected_question_count": group["expected_question_count"],
            "historical_exam_matches": rank_exam_items(group["title"], packet_text, exam_items),
            "ontology_matches": rank_concepts(group["title"], packet_text, concepts),
            "validation_boundary": {
                "lecture_material_is_primary_for_course_exam": True,
                "ontology_is_consistency_check_only": True,
                "ontology_claims_medically_approved": False,
                "harrison_pointer_is_not_claim_entailment": True,
                "historical_exam_frequency_is_not_future_exam_guarantee": True,
            },
        }
        write_json(group_dir / "validation_context.json", validation)

    print(
        "course_note_validation_context_built "
        f"groups={len(inventory['groups'])} exam_items={len(exam_items)} concepts={len(concepts)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--build-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_context(args.root.resolve(), args.build_root.resolve())


if __name__ == "__main__":
    main()
