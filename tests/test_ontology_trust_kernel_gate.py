import json
from copy import deepcopy
from pathlib import Path

import jsonschema

from scripts.ontology_trust_kernel_gate import (
    evaluate_release,
    feedback_content_sha256,
    question_content_sha256,
)
from src.services.ontology_feedback import build_feedback_packet


ROOT = Path(__file__).resolve().parents[1]
AXIS_ID = "a:diagnosis:212b4a4134450b"
NODE_CLAIM_ID = "c:axis_node:1111111111111111"
REL_CLAIM_ID = "c:axis_relation:0123456789abcdef"


def verified_ref():
    return {
        "ref_id": "ev:synthetic",
        "scope": "claim_review",
        "entailment_status": "verified",
    }


def approved_claim_base():
    return {
        "review_status": "approved",
        "medical_approval": True,
        "applicability": "applicable",
        "needs_review": False,
        "provenance": {
            "claim_entailment": "verified",
            "evidence_refs": [verified_ref()],
        },
    }


def synthetic_question():
    return {
        "question_id": "Q001",
        "stem": "합성 테스트 문항",
        "stimulus": "합성 자료",
        "lab_values": [],
        "choices": {"1": "합성 정답", "2": "합성 오답"},
        "answer": "1",
        "review_status": "approved",
        "disease_concept_id": "synthetic_disease",
        "target_axis_type": "diagnosis",
        "target_axis_ids": [AXIS_ID],
        "question_blueprint": {
            "blueprint_id": "qb:synthetic",
            "target": {
                "disease_concept_id": "synthetic_disease",
                "axis_type": "diagnosis",
                "axis_ids": [AXIS_ID],
            },
        },
    }


def synthetic_registries():
    concept_registry = {
        "concepts": {
            "synthetic_disease": {
                "needs_review": False,
                "review_status": "approved",
                "medical_approval": True,
            }
        }
    }
    node = {
        "axis_id": AXIS_ID,
        "claim_id": NODE_CLAIM_ID,
        **approved_claim_base(),
    }
    relation = {
        "claim_id": REL_CLAIM_ID,
        "disease_concept_id": "synthetic_disease",
        "axis_id": AXIS_ID,
        **approved_claim_base(),
    }
    return concept_registry, {"nodes": [node], "relationships": [relation]}


def synthetic_release(question):
    item = {
        "exam_id": "SYNTH_EXAM",
        "question_id": "Q001",
        "question_content_sha256": question_content_sha256(question),
        "feedback_content_sha256": "0" * 64,
        "blueprint_id": "qb:synthetic",
        "disease_concept_id": "synthetic_disease",
        "target_axis_type": "diagnosis",
        "target_axis_ids": [AXIS_ID],
        "target_claim_ids": [REL_CLAIM_ID],
        "choice_bindings": [
            {
                "choice": "1",
                "role": "answer",
                "source_concept_id": "synthetic_disease",
                "feedback_claim_ids": [REL_CLAIM_ID],
                "why_attractive": "",
                "discriminating_rule": {
                    "claim_id": REL_CLAIM_ID,
                    "text": "합성 승인 규칙",
                },
            },
            {
                "choice": "2",
                "role": "distractor",
                "source_concept_id": "synthetic_distractor",
                "feedback_claim_ids": [REL_CLAIM_ID],
                "why_attractive": "합성 공통점",
                "discriminating_rule": {
                    "claim_id": REL_CLAIM_ID,
                    "text": "합성 구분 규칙",
                },
            },
        ],
        "evidence": [
            {
                "evidence_id": "ev:synthetic",
                "citation": "Synthetic evidence",
                "locator": "fixture",
                "status": "verified",
            }
        ],
        "next_action": {
            "kind": "contrast_retest",
            "target_claim_ids": [REL_CLAIM_ID],
            "due_bucket": "1d",
        },
        "media_release": "not_applicable",
    }
    item["feedback_content_sha256"] = feedback_content_sha256(item)
    return {
        "schema_version": "ontology_trust_kernel_releases.v1",
        "releases": [
            {
                "release_id": "tk:synthetic:release",
                "status": "released",
                "scope": "synthetic",
                "surfaces": ["practice_pre_answer", "post_answer_feedback", "analytics"],
                "source_snapshots": {
                    "axis_registry_sha256": "a" * 64,
                    "review_decisions_sha256": "b" * 64,
                },
                "concept_ids": ["synthetic_disease"],
                "questions": [item],
                "release_decision": {
                    "status": "released",
                    "reviewer_id": "reviewer:synthetic",
                    "reviewed_at": "2026-07-13T00:00:00+09:00",
                    "note": "Synthetic test only",
                },
            }
        ],
    }


def evaluate(registry, question):
    concept_registry, axis_registry = synthetic_registries()
    return evaluate_release(
        registry=registry,
        exam_id="SYNTH_EXAM",
        question=question,
        surface="post_answer_feedback",
        concept_registry=concept_registry,
        axis_registry=axis_registry,
        source_hashes={
            "axis_registry_sha256": "a" * 64,
            "review_decisions_sha256": "b" * 64,
        },
    )


def test_empty_registry_is_valid_and_fails_closed():
    registry = {"schema_version": "ontology_trust_kernel_releases.v1", "releases": []}
    schema = json.loads((ROOT / "schemas" / "ontology_trust_kernel_release.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(registry, schema)
    gate = evaluate(registry, synthetic_question())
    assert gate["allowed"] is False
    assert gate["reasons"] == ["trust_kernel_release_missing"]


def test_complete_synthetic_release_opens_gate_and_feedback_packet():
    question = synthetic_question()
    registry = synthetic_release(question)
    schema = json.loads((ROOT / "schemas" / "ontology_trust_kernel_release.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(registry, schema)
    gate = evaluate(registry, question)
    assert gate["allowed"] is True
    packet = build_feedback_packet(
        question=question,
        event={
            "event_id": "attempt_synthetic",
            "question_id": "Q001",
            "selected_choices": ["2"],
            "answer_keys": ["1"],
            "is_correct": False,
        },
        gate=gate,
    )
    packet_schema = json.loads((ROOT / "schemas" / "feedback_packet.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(packet, packet_schema)
    assert packet["status"] == "released"
    assert packet["selected_distractors"][0]["source_concept_id"] == "synthetic_distractor"
    assert "misconception_id" not in json.dumps(packet, ensure_ascii=False)


def test_question_or_feedback_change_invalidates_release():
    question = synthetic_question()
    registry = synthetic_release(question)
    changed_question = deepcopy(question)
    changed_question["stem"] += " 변경"
    assert "question_content_hash_mismatch" in evaluate(registry, changed_question)["reasons"]

    changed_release = deepcopy(registry)
    changed_release["releases"][0]["questions"][0]["choice_bindings"][1]["why_attractive"] = "변경"
    assert "feedback_content_hash_mismatch" in evaluate(changed_release, question)["reasons"]


def test_unverified_claim_or_source_hash_mismatch_blocks_release():
    question = synthetic_question()
    registry = synthetic_release(question)
    concept_registry, axis_registry = synthetic_registries()
    axis_registry["relationships"][0]["provenance"]["claim_entailment"] = "unverified"
    gate = evaluate_release(
        registry=registry,
        exam_id="SYNTH_EXAM",
        question=question,
        surface="post_answer_feedback",
        concept_registry=concept_registry,
        axis_registry=axis_registry,
        source_hashes={
            "axis_registry_sha256": "c" * 64,
            "review_decisions_sha256": "b" * 64,
        },
    )
    assert gate["allowed"] is False
    assert "source_snapshot_mismatch:axis_registry_sha256" in gate["reasons"]
    assert f"target_claim_not_approved:{REL_CLAIM_ID}" in gate["reasons"]


def test_withheld_packet_never_contains_answer_or_target():
    question = synthetic_question()
    gate = evaluate({"schema_version": "ontology_trust_kernel_releases.v1", "releases": []}, question)
    packet = build_feedback_packet(
        question=question,
        event={
            "event_id": "attempt_withheld",
            "question_id": "Q001",
            "selected_choices": ["2"],
            "answer_keys": ["1"],
            "is_correct": False,
        },
        gate=gate,
    )
    schema = json.loads((ROOT / "schemas" / "feedback_packet.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(packet, schema)
    assert packet["status"] == "withheld"
    assert "correct_choices" not in packet["result"]
    assert "target" not in packet
    assert "evidence" not in packet

