"""Build post-answer FeedbackPacket objects from an approved Trust Kernel release."""
from __future__ import annotations

from typing import Any

from scripts.ontology_trust_kernel_gate import canonical_sha256, question_content_sha256


def build_feedback_packet(
    *,
    question: dict[str, Any] | None,
    event: dict[str, Any],
    gate: dict[str, Any],
    release_mode: str = "immediate",
) -> dict[str, Any]:
    question = question or {}
    event_id = str(event.get("event_id") or "unknown_attempt")
    question_id = str(event.get("question_id") or question.get("question_id") or "unknown_question")
    item_version = gate.get("item_version") or (question_content_sha256(question) if question else None)
    feedback_id = "fb:" + canonical_sha256(
        {
            "event_id": event_id,
            "question_id": question_id,
            "item_version": item_version,
            "release_id": gate.get("release_id"),
        }
    )[:16]
    result = {
        "is_correct": bool(event.get("is_correct")),
        "selected_choices": [str(value) for value in event.get("selected_choices") or []],
    }

    if not gate.get("allowed"):
        return {
            "schema_version": "feedback_packet.v1",
            "feedback_id": feedback_id,
            "attempt_event_id": event_id,
            "question_id": question_id,
            "item_version": item_version,
            "status": "withheld",
            "release_mode": release_mode,
            "result": result,
            "withheld_reasons": gate.get("reasons") or ["trust_kernel_release_missing"],
            "safe_message": "검토가 완료된 Ontology 해설이 아직 없습니다.",
        }

    release = gate["release"]
    item = gate["question_release"]
    answer_keys = [str(value) for value in event.get("answer_keys") or []]
    result["correct_choices"] = answer_keys
    answer_set = set(answer_keys)
    selected_distractors = []
    for binding in item.get("choice_bindings") or []:
        choice = str(binding.get("choice"))
        if choice not in result["selected_choices"] or choice in answer_set:
            continue
        selected_distractors.append(
            {
                "choice": choice,
                "source_concept_id": str(binding.get("source_concept_id") or ""),
                "why_attractive": str(binding.get("why_attractive") or ""),
                "discriminating_rule": binding.get("discriminating_rule") or {},
            }
        )

    decision = release.get("release_decision") or {}
    return {
        "schema_version": "feedback_packet.v1",
        "feedback_id": feedback_id,
        "attempt_event_id": event_id,
        "question_id": question_id,
        "item_version": item_version,
        "status": "released",
        "release_mode": release_mode,
        "result": result,
        "target": {
            "disease_concept_id": item["disease_concept_id"],
            "axis_type": item["target_axis_type"],
            "axis_ids": item["target_axis_ids"],
            "claim_ids": item["target_claim_ids"],
        },
        "selected_distractors": selected_distractors,
        "next_action": item["next_action"],
        "evidence": item["evidence"],
        "approval": {
            "release_id": release["release_id"],
            "approved_by": decision.get("reviewer_id"),
            "approved_at": decision.get("reviewed_at"),
            "content_hash": item["feedback_content_sha256"],
            "release_digest": gate.get("release_digest"),
        },
        "safe_message": "검토된 해설입니다.",
    }
