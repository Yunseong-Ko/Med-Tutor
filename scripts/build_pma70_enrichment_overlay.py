#!/usr/bin/env python3
"""Build the deployable enrichment overlay for one 70-item PMA exam.

The immutable student qbank remains untouched.  This builder joins the
answer-key-aligned learning content, explicit curriculum concept routing,
10-Axis type labels, Anki cards, and reviewed PDF-flow media references into
the separate qbank enrichment documents used by the live demo.

Harrison rows in this artifact are *locators*, not claim-entailing quotes.
No licensed segment text is written to either overlay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
TARGET_EXAM = "임상종합평가 · 2025 B군 1교시"
TARGET_EXTRACTED = ROOT / "data_private/course_exams/extracted/PMA_202511_G3_B군_1교시.json"
TARGET_MEDIA_DIR = ROOT / "data_private/course_exams/media/PMA_202511_G3_B군_1교시"
QBANK_PATH = ROOT / "data_private/student/qbank.json"
DRAFT_PATH = ROOT / "data_private/student/qbank_enrichment.draft.json"
RELEASES_PATH = ROOT / "data_private/student/qbank_enrichment.releases.json"
CONCEPT_REGISTRY_PATH = ROOT / "data_private/concept_registry.json"

AXIS_LABELS = {
    "contraindication": "금기",
    "diagnosis": "진단",
    "epidemiology": "역학",
    "etiology": "원인",
    "indication": "적응증",
    "pathophysiology": "병태생리",
    "prognosis": "예후",
    "risk_factor": "위험인자",
    "symptom": "증상",
    "treatment": "치료",
}

# The source extraction linked 41 items.  These explicit corrections cover
# missing curriculum nodes and replace several over-broad draft matches.
CONCEPT_OVERRIDES = {
    5: "pma_topic_burn_injury",
    6: "pma_topic_burn_injury",
    7: "pma_topic_hypovolemic_resuscitation",
    8: "tubo_ovarian_abscess",
    9: "pma_topic_variable_fetal_deceleration",
    10: "syphilis",
    14: "pma_topic_labor_augmentation",
    15: "child_physical_abuse",
    16: "death_certificate",
    17: "systemic_lupus_erythematosus",
    18: "pma_topic_pediatric_dehydration",
    19: "pma_topic_pediatric_dehydration",
    22: "major_depressive_disorder",
    25: "strangulated_bowel_obstruction",
    26: "pma_topic_superior_mesenteric_artery_syndrome",
    27: "perforated_peptic_ulcer",
    30: "ulcerative_colitis",
    33: "functional_constipation",
    34: "bowel_obstruction",
    37: "functional_ovarian_cyst",
    38: "cervical_cancer",
    41: "functional_ovarian_cyst",
    44: "uterine_leiomyoma",
    46: "polycystic_ovary_syndrome",
    53: "hyperthyroidism",
    54: "type_1_diabetes",
    60: "food_allergy",
    61: "nephrotic_syndrome",
    63: "major_depressive_disorder",
    64: "separation_anxiety_disorder",
    65: "bipolar_disorder",
    66: "bipolar_disorder",
    68: "major_depressive_disorder",
}

# One canonical educational axis per item.  Claim-level axis IDs are not
# fabricated: the overlay stays at disease/topic x axis_type resolution until
# a faculty reviewer selects a claim-level node.
AXIS_TYPES = {
    1: "treatment", 2: "treatment", 3: "diagnosis", 4: "treatment",
    5: "diagnosis", 6: "treatment", 7: "treatment", 8: "treatment",
    9: "etiology", 10: "diagnosis", 11: "treatment", 12: "treatment",
    13: "treatment", 14: "treatment", 15: "diagnosis", 16: "etiology",
    17: "diagnosis", 18: "treatment", 19: "treatment", 20: "etiology",
    21: "treatment", 22: "pathophysiology", 23: "treatment",
    24: "pathophysiology", 25: "treatment", 26: "diagnosis",
    27: "treatment", 28: "diagnosis", 29: "diagnosis", 30: "prognosis",
    31: "diagnosis", 32: "diagnosis", 33: "diagnosis", 34: "treatment",
    35: "treatment", 36: "treatment", 37: "treatment", 38: "treatment",
    39: "diagnosis", 40: "treatment", 41: "treatment", 42: "treatment",
    43: "risk_factor", 44: "treatment", 45: "treatment", 46: "treatment",
    47: "treatment", 48: "treatment", 49: "treatment", 50: "diagnosis",
    51: "prognosis", 52: "treatment", 53: "treatment", 54: "treatment",
    55: "diagnosis", 56: "diagnosis", 57: "diagnosis", 58: "treatment",
    59: "diagnosis", 60: "diagnosis", 61: "diagnosis", 62: "diagnosis",
    63: "treatment", 64: "treatment", 65: "diagnosis", 66: "treatment",
    67: "diagnosis", 68: "treatment", 69: "diagnosis", 70: "diagnosis",
}

# These stems fully state the visual finding; no source image was present in
# the extracted exam assets.  The release may be practiced without inventing a
# replacement image.
TEXT_SUFFICIENT_VISUALS = {15, 35}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _question_number(question_id: str) -> int:
    match = re.search(r"_Q(\d+)$", str(question_id))
    if not match:
        raise ValueError(f"invalid PMA question id: {question_id}")
    return int(match.group(1))


def _concept_label(concept_id: str, question: dict[str, Any], registry: dict[str, Any]) -> str:
    concept = registry.get(concept_id) if isinstance(registry.get(concept_id), dict) else {}
    aliases = concept.get("aliases") if isinstance(concept.get("aliases"), list) else []
    korean = next((str(alias) for alias in aliases if re.search(r"[가-힣]", str(alias))), "")
    return korean or str(question.get("topic") or concept_id)


def _harrison_locators(concept_id: str, registry: dict[str, Any]) -> list[dict[str, Any]]:
    concept = registry.get(concept_id) if isinstance(registry.get(concept_id), dict) else {}
    evidence = concept.get("evidence") if isinstance(concept.get("evidence"), dict) else {}
    pointer = evidence.get("harrison") if isinstance(evidence.get("harrison"), dict) else {}
    chapter = pointer.get("chapter")
    if not chapter:
        return []
    page = pointer.get("page") or pointer.get("printed_page")
    return [{
        "source_id": "H1",
        "source_type": "licensed_textbook_private_locator",
        "edition": str(pointer.get("edition") or "22e"),
        "chapter": int(chapter),
        "title": str(pointer.get("title") or "Harrison's Principles of Internal Medicine"),
        "printed_page": int(page) if page else None,
        "locator": f"Harrison 22e · Ch.{int(chapter)} · p.{page or '확인 필요'}",
        "concept_id": concept_id,
        "support_scope": "chapter_pointer_not_claim_entailment",
        "quote_exposed": False,
        "medical_approval": False,
        "needs_review": True,
    }]


def _choice_explanations(question: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for choice in question.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        result.append({
            "n": str(choice.get("n") or ""),
            "expl": str(choice.get("expl") or ""),
            "source": "qbank_answer_key_aligned",
            "needs_review": False,
        })
    return result


def _structured_explanation(
    question: dict[str, Any],
    *,
    concept_label: str,
    axis_type: str,
    axis_label: str,
) -> dict[str, Any]:
    """Repackage verified qbank content into a richer learning hierarchy.

    This deliberately does not ask a model to invent additional medicine.  It
    only promotes the answer-key-aligned explanation, correct-choice rationale,
    author points, and Ontology route into stable UI sections.
    """
    explanation = str(question.get("explanation") or "").strip()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", explanation) if part.strip()]
    answer_keys = {
        value.strip()
        for value in re.split(r"[,/\s]+", str(question.get("answer") or ""))
        if value.strip()
    }
    choices = [choice for choice in (question.get("choices") or []) if isinstance(choice, dict)]
    correct = [choice for choice in choices if str(choice.get("n") or "") in answer_keys]
    correct_labels = [f"{choice.get('n')}. {str(choice.get('text') or '').strip()}" for choice in correct]
    correct_rationales = [str(choice.get("expl") or "").strip() for choice in correct if str(choice.get("expl") or "").strip()]
    points = [str(point).strip() for point in (question.get("points") or []) if str(point).strip()]
    return {
        "schema_version": "paccine.structured_explanation.v1",
        "summary": paragraphs[0] if paragraphs else explanation,
        "conclusion": paragraphs[-1] if len(paragraphs) > 1 else (
            f"정답은 {' · '.join(correct_labels)}입니다." if correct_labels else explanation
        ),
        "correct_answer": " · ".join(correct_labels),
        "correct_answer_rationale": " ".join(correct_rationales),
        "clinical_reasoning": paragraphs,
        "key_points": points,
        "axis_focus": {
            "concept_label": concept_label,
            "axis_type": axis_type,
            "axis_label": axis_label,
            "message": f"이 문항은 {concept_label}에서 {axis_label} 축을 평가합니다.",
        },
    }


def _media_rows(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    refs = (extracted.get("media") or {}).get("media_refs") or []
    for index, ref in enumerate(refs, start=1):
        storage_id = str(ref.get("storage_id") or "").strip()
        candidates = sorted(TARGET_MEDIA_DIR.glob(f"{storage_id}.*"))
        if not storage_id or len(candidates) != 1:
            raise ValueError(f"media reference is not deterministic: {storage_id}")
        asset = candidates[0]
        rows.append({
            "url": f"/api/course-exams/media/{quote(TARGET_MEDIA_DIR.name, safe='')}/{quote(asset.name, safe='')}",
            "checksum": _sha256(asset),
            "caption": f"제시자료 {index}",
            "media_id": str(ref.get("media_id") or storage_id),
            "storage_id": storage_id,
            "match_method": str(ref.get("match_method") or "pdf_page_block_flow"),
            "release_review": "visual_sequence_checked_20260723",
        })
    return rows


def build(*, reviewed_at: str, reviewer_id: str) -> dict[str, Any]:
    qbank_payload = _load(QBANK_PATH)
    qbank_sha = _sha256(QBANK_PATH)
    questions = [
        question for question in qbank_payload.get("questions") or []
        if isinstance(question, dict) and question.get("exam") == TARGET_EXAM
    ]
    extracted_questions = {
        str(question.get("question_id")): question
        for question in _load(TARGET_EXTRACTED).get("questions") or []
        if isinstance(question, dict)
    }
    registry = _load(CONCEPT_REGISTRY_PATH).get("concepts") or {}
    if len(questions) != 70 or len(extracted_questions) != 70:
        raise ValueError("the target PMA set must contain exactly 70 questions")
    if set(AXIS_TYPES) != set(range(1, 71)):
        raise ValueError("all 70 questions require an explicit Axis type")

    draft_payload = _load(DRAFT_PATH) if DRAFT_PATH.exists() else {}
    releases_payload = _load(RELEASES_PATH) if RELEASES_PATH.exists() else {}
    drafts = draft_payload.get("drafts") if isinstance(draft_payload.get("drafts"), dict) else {}
    releases = releases_payload.get("releases") if isinstance(releases_payload.get("releases"), dict) else {}

    media_count = 0
    registry_concepts = 0
    for question in questions:
        qid = str(question.get("id") or "")
        number = _question_number(qid)
        extracted = extracted_questions.get(qid)
        if not isinstance(extracted, dict):
            raise ValueError(f"missing extracted question: {qid}")
        grounding = extracted.get("ontology_grounding") if isinstance(extracted.get("ontology_grounding"), dict) else {}
        concept_id = CONCEPT_OVERRIDES.get(number) or str(grounding.get("disease_concept_id") or "")
        if not concept_id:
            raise ValueError(f"missing concept route: {qid}")
        concept_status = "canonical_registry" if concept_id in registry else "curriculum_topic_node"
        concept_label = _concept_label(concept_id, question, registry)
        registry_concepts += int(concept_status == "canonical_registry")
        axis_type = AXIS_TYPES[number]
        axis_label = AXIS_LABELS[axis_type]
        media = _media_rows(extracted)
        media_count += len(media)
        anki_cards = extracted.get("anki_cards") if isinstance(extracted.get("anki_cards"), list) else []
        if not anki_cards:
            raise ValueError(f"missing Anki card: {qid}")
        evidence = [{
            "source_id": "PMA",
            "source_type": "answer_key_aligned_learning_explanation",
            "title": TARGET_EXAM,
            "support_scope": "curated_exam_explanation_not_external_guideline",
            "quote_exposed": False,
            "needs_review": False,
        }, *_harrison_locators(concept_id, registry)]
        overlay = {
            "explanation": str(question.get("explanation") or ""),
            "structured_explanation": _structured_explanation(
                question,
                concept_label=concept_label,
                axis_type=axis_type,
                axis_label=axis_label,
            ),
            "choice_explanations": _choice_explanations(question),
            "points": [str(point) for point in question.get("points") or [] if str(point).strip()],
            "concept_id": concept_id,
            "concept_label": concept_label,
            "concept_registry_status": concept_status,
            "target_axis_type": axis_type,
            "target_axis_label": axis_label,
            "target_axis_ids": [],
            "target_axis_resolution": "disease_or_topic_by_axis_type",
            "anki_cards": anki_cards,
            "connected_media": media,
            "media_requirement_satisfied_by_text": number in TEXT_SUFFICIENT_VISUALS,
            "evidence": evidence,
            "source": {
                "exam": TARGET_EXAM,
                "question_id": qid,
                "qbank_sha256": qbank_sha,
            },
            "provenance": {
                "builder": "scripts/build_pma70_enrichment_overlay.py",
                "ontology_policy": "explicit_concept_route_plus_type_level_10_axis",
                "harrison_policy": "locator_only_no_segment_text",
                "media_policy": "pdf_flow_reference_plus_visual_sequence_check",
            },
        }
        if not overlay["explanation"] or len(overlay["choice_explanations"]) != len(question.get("choices") or []):
            raise ValueError(f"incomplete explanation coverage: {qid}")

        drafts[qid] = {
            **overlay,
            "release_eligible": True,
            "needs_review": True,
            "review_status": "owner_curated_demo_ready",
        }
        releases[qid] = {
            **overlay,
            "approved": True,
            "medical_approval": False,
            "curated_demo_release": True,
            "demo_release": True,
            "needs_real_faculty_review": True,
            "review_status": "owner_curated_demo_release",
            "reviewer_id": reviewer_id,
            "reviewed_at": reviewed_at,
            "review_note": "70문항 시연용 콘텐츠·Axis·Anki·미디어 연결 검수. 교수 의학 검수는 별도 대기.",
        }

    draft_payload.update({
        "schema_version": "paccine.qbank_enrichment.draft.v1",
        "built_against_sha256": qbank_sha,
        "notice": "초안은 학생 API에 직접 병합하지 않습니다.",
        "drafts": drafts,
    })
    releases_payload.update({
        "schema_version": "paccine.qbank_enrichment.releases.v1",
        "built_against_sha256": qbank_sha,
        "notice": "실제 교수 승인과 소유자 검수 시연 release를 명시적으로 구분합니다.",
        "releases": releases,
    })
    DRAFT_PATH.write_text(json.dumps(draft_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    RELEASES_PATH.write_text(json.dumps(releases_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "exam": TARGET_EXAM,
        "questions": len(questions),
        "registry_concepts": registry_concepts,
        "curriculum_topic_nodes": len(questions) - registry_concepts,
        "axis_assigned": len(questions),
        "anki_cards": sum(len((extracted_questions[q["id"]].get("anki_cards") or [])) for q in questions),
        "connected_media": media_count,
        "text_sufficient_visuals": len(TEXT_SUFFICIENT_VISUALS),
        "qbank_sha256": qbank_sha,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-id", default="owner:goyunseong")
    parser.add_argument("--reviewed-at", default=datetime.now(timezone.utc).isoformat())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(build(reviewed_at=args.reviewed_at, reviewer_id=args.reviewer_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
