"""Tests for local concept-registry grounding without private exam text."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.generate_lecture_questions import normalize_question
from scripts.generation_grounding import (
    apply_grounding_trace,
    build_generation_grounding,
    build_ranked_distractor_pool,
    match_topic_to_concept,
    retrieve_item_harrison_evidence,
)


def synthetic_registry(path: Path) -> None:
    concepts = {}
    distractors = ["disease_b", "disease_c", "disease_d", "disease_e"]
    for index, cid in enumerate(["target_disease", *distractors]):
        concepts[cid] = {
            "disease_concept_id": cid,
            "aliases": ["표적 질환" if cid == "target_disease" else f"감별 질환 {index}"],
            "node_type": "disease",
            "edges": {
                "differential_of": [{"id": item} for item in distractors]
                if cid == "target_disease"
                else []
            },
            "evidence": {
                "harrison": {"chapter": "1", "page": "10", "title": "Synthetic reference"}
                if cid == "target_disease"
                else None,
                "ncbi": None,
            },
            "needs_review": True,
        }
    path.write_text(json.dumps({"_meta": {"generated_at": "test"}, "concepts": concepts}, ensure_ascii=False), encoding="utf-8")


def synthetic_axis_registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0-test",
                "stats": {"nodes": 2, "relationships": 2},
                "nodes": [
                    {
                        "axis_id": "a:risk_factor:smoking",
                        "axis_type": "risk_factor",
                        "label": "흡연",
                        "dimension": "",
                        "sources": ["synthetic"],
                        "needs_review": True,
                    },
                    {
                        "axis_id": "a:diagnosis:test",
                        "axis_type": "diagnosis",
                        "label": "표적 검사",
                        "dimension": "test",
                        "sources": ["synthetic"],
                        "needs_review": True,
                    },
                ],
                "relationships": [
                    {
                        "disease_concept_id": "target_disease",
                        "axis_id": "a:risk_factor:smoking",
                        "relation": "has_risk_factor",
                        "source": "synthetic",
                    },
                    {
                        "disease_concept_id": "target_disease",
                        "axis_id": "a:diagnosis:test",
                        "relation": "diagnosed_by",
                        "source": "synthetic",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class GenerationGroundingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp.name) / "concept_registry.json"
        self.axis_registry_path = Path(self.temp.name) / "axis_registry.json"
        self.review_decisions_path = Path(self.temp.name) / "ontology_review_decisions.json"
        synthetic_registry(self.registry_path)
        synthetic_axis_registry(self.axis_registry_path)
        self.review_decisions_path.write_text(
            json.dumps(
                {
                    "schema_version": "ontology_review_decisions.v1",
                    "concepts": [
                        {
                            "concept_id": "target_disease",
                            "review_status": "approved",
                            "medical_approval": True,
                            "applicability": "applicable",
                            "review_flags": [],
                            "reviewer_id": "faculty:test",
                            "reviewed_at": "2026-07-12T12:00:00+09:00",
                            "claim_entailment": "verified",
                        }
                    ],
                    "axis_nodes": [],
                    "axis_relationships": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_topic_alias_matches_and_inherits_evidence_and_distractors(self):
        grounding = build_generation_grounding(
            "표적 질환",
            self.registry_path,
            axis_registry_path=self.axis_registry_path,
        )
        self.assertEqual(grounding["match"]["status"], "matched")
        self.assertEqual(grounding["pack"]["disease_concept_id"], "target_disease")
        self.assertTrue(grounding["pack"]["evidence_available"])
        self.assertEqual(len(grounding["pack"]["distractor_pool"]), 4)
        self.assertFalse(grounding["fallback_general_generation"])
        self.assertEqual(grounding["review_policy"], "faculty_draft")
        self.assertEqual(grounding["pack"]["review_policy"], "faculty_draft")
        self.assertEqual(grounding["pack"]["axis_context"]["review_policy"], "faculty_draft")
        self.assertEqual(grounding["pack"]["axis_context"]["node_count"], 2)
        self.assertEqual(grounding["pack"]["axis_context"]["type_counts"]["diagnosis"], 1)

    def test_unmatched_topic_blocks_without_general_fallback(self):
        grounding = build_generation_grounding("등록되지 않은 주제", self.registry_path)
        self.assertEqual(grounding["match"]["status"], "unmatched")
        self.assertFalse(grounding["fallback_general_generation"])
        self.assertTrue(grounding["blocked"])
        self.assertIn("concept_registry_match", grounding["missing"])

    def test_specific_topic_never_falls_back_to_generic_parent_substring(self):
        concepts = {
            "leukemia": {"aliases": ["백혈병"], "node_type": "disease"},
            "chronic_myeloid_leukemia": {
                "aliases": ["만성골수성백혈병"],
                "node_type": "disease",
            },
        }
        result = match_topic_to_concept(
            "만성골수백혈병",
            concepts,
            {},
            semantic_matcher=lambda _query, _candidates: [],
        )
        self.assertEqual(result["status"], "unmatched")
        self.assertIsNone(result["disease_concept_id"])
        self.assertFalse(result["substring_fallback"])

    def test_semantic_match_requires_threshold_and_rejects_generic_parent(self):
        concepts = {
            "leukemia": {"aliases": ["백혈병"], "node_type": "disease"},
            "chronic_myeloid_leukemia": {
                "aliases": ["만성골수성백혈병"],
                "node_type": "disease",
            },
        }
        result = match_topic_to_concept(
            "CML 의심 증례",
            concepts,
            {},
            semantic_matcher=lambda _query, _candidates: [
                {"concept_id": "chronic_myeloid_leukemia", "label": "만성골수성백혈병", "similarity": 0.91},
            ],
        )
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["disease_concept_id"], "chronic_myeloid_leukemia")

    def test_ambiguous_semantic_shortlist_uses_context_resolver_membership(self):
        concepts = {
            "acute_myeloid_leukemia": {"aliases": ["급성골수성백혈병"], "node_type": "disease"},
            "chronic_myeloid_leukemia": {"aliases": ["만성골수성백혈병"], "node_type": "disease"},
        }
        result = match_topic_to_concept(
            "BCR::ABL1 양성 만성 경과 증례",
            concepts,
            {},
            semantic_matcher=lambda _query, _candidates: [
                {"concept_id": "acute_myeloid_leukemia", "label": "AML", "similarity": 0.90},
                {"concept_id": "chronic_myeloid_leukemia", "label": "CML", "similarity": 0.89},
            ],
            context_resolver=lambda _query, _candidates: "chronic_myeloid_leukemia",
        )
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["match_method"], "context_resolver")
        self.assertEqual(result["disease_concept_id"], "chronic_myeloid_leukemia")

    def test_distractor_pool_filters_cross_domain_noise(self):
        concepts = {
            "atrial_fibrillation": {
                "aliases": ["심방세동"],
                "node_type": "disease",
                "edges": {"differential_of": [{"id": "broca_aphasia"}, {"id": "atrial_flutter"}]},
            },
            "broca_aphasia": {"aliases": ["브로카실어증"], "node_type": "disease", "edges": {}},
            "atrial_flutter": {"aliases": ["심방조동"], "node_type": "disease", "edges": {}},
        }
        pool, diagnostics = build_ranked_distractor_pool("atrial_fibrillation", concepts, topic="심방세동")
        self.assertEqual([row["id"] for row in pool], ["atrial_flutter"])
        self.assertEqual(diagnostics["excluded_by_reason"]["cross_domain"], 1)
        self.assertEqual(diagnostics["status"], "insufficient_same_domain_candidates")

    def test_explicit_concept_id_overrides_topic_matching(self):
        grounding = build_generation_grounding(
            "완전히 다른 주제",
            self.registry_path,
            axis_registry_path=self.axis_registry_path,
            disease_concept_id="target_disease",
        )
        self.assertEqual(grounding["match"]["match_method"], "explicit_concept_id")
        self.assertEqual(grounding["pack"]["disease_concept_id"], "target_disease")

    def test_harrison_retrieval_query_includes_canonical_english_terms(self):
        concept = {
            "aliases": ["면역혈소판감소증", "ITP", "immune thrombocytopenia"],
            "node_type": "disease",
            "evidence": {
                "harrison": {"chapter": 120, "page": 924, "title": "Disorders of Platelets and Vessel Wall"}
            },
        }
        captured = {}

        def fake_retrieve(query, concepts, intents, **_kwargs):
            captured["query"] = query
            captured["concepts"] = concepts
            captured["intents"] = intents
            return [], []

        with mock.patch("src.services.medical_copilot.retrieve_harrison_evidence", side_effect=fake_retrieve):
            retrieve_item_harrison_evidence(
                "면역혈소판감소증",
                "immune_thrombocytopenia",
                concept,
                intents=["diagnosis"],
                root=Path(self.temp.name),
            )

        self.assertIn("면역혈소판감소증", captured["query"])
        self.assertIn("immune thrombocytopenia", captured["query"])
        self.assertIn("ITP", captured["query"])

    def test_scope_parent_and_classification_node_are_not_generation_targets(self):
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        data["concepts"]["umbrella_disease"] = {
            "disease_concept_id": "umbrella_disease",
            "aliases": ["넓은 질환"],
            "node_type": "disease",
            "generation_grounding_status": "quarantined_scope_ambiguous",
            "edges": {},
            "evidence": {},
            "needs_review": True,
        }
        self.registry_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        grounding = build_generation_grounding(
            "넓은 질환",
            self.registry_path,
            disease_concept_id="umbrella_disease",
        )
        self.assertEqual(grounding["match"]["status"], "scope_quarantined_concept")
        self.assertIsNone(grounding["pack"])
        self.assertIn("scope_quarantined_not_generation_target", grounding["missing"])

    def test_authority_scoped_source_refs_count_as_draft_evidence(self):
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        target = data["concepts"]["target_disease"]
        target["evidence"] = {"harrison": None, "ncbi": None}
        target["source_refs"] = [{"ref_id": "society:guideline", "url": "https://example.org"}]
        self.registry_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        grounding = build_generation_grounding(
            "표적 질환",
            self.registry_path,
            axis_registry_path=self.axis_registry_path,
        )
        self.assertTrue(grounding["pack"]["evidence_available"])
        self.assertEqual(grounding["pack"]["evidence"]["source_refs"][0]["ref_id"], "society:guideline")

    def test_trace_accepts_in_scope_distractors_and_rejects_out_of_scope(self):
        grounding = build_generation_grounding("표적 질환", self.registry_path)
        grounding["pack"]["evidence"]["harrison_sources"] = [
            {
                "source_id": "H1",
                "chapter": 1,
                "printed_page": 10,
                "locator": "22e · Ch.1 · p.10",
                "entailment_status": "verified",
            }
        ]
        grounding["pack"]["evidence_available"] = True
        raw = {
            "problem": (
                "55세 남자가 복통으로 내원하였다. 혈압 118/72 mmHg, 맥박 92회/분이다. "
                "주어진 소견을 종합할 때 다음으로 시행할 가장 적절한 검사는?"
            ),
            "options": ["표적 검사", "감별 질환 1", "감별 질환 2", "감별 질환 3", "감별 질환 4"],
            "answer": 1,
            "reasoning_hops": 2,
            "cognitive_model": {"confounders": ["경계치 소견"]},
            "choice_explanations": {
                "1": {"rationale": "상속 근거"},
                **{
                    str(index + 2): {
                        "rationale": "감별 근거",
                        "misconception": "실제 감별",
                        "why_attractive": "유사한 소견",
                        "source_id": cid,
                    }
                    for index, cid in enumerate(["disease_b", "disease_c", "disease_d", "disease_e"])
                },
            },
            "pma_solution": {"correct_reason": "상속 근거 H1", "source_anchor": "H1 · 22e · Ch.1 · p.10"},
            "evidence_refs": [
                {
                    "source_id": "H1",
                    "source": "Harrison 22e",
                    "locator": "22e · Ch.1 · p.10",
                    "chapter": 1,
                    "printed_page": 10,
                    "source_type": "textbook",
                    "entailment_status": "verified",
                }
            ],
        }
        record = normalize_question(raw, idx=1, source_name="synthetic.txt", subject="General", unit="test")
        traced = apply_grounding_trace(record, grounding)
        self.assertEqual(traced["disease_concept_id"], "target_disease")
        self.assertTrue(traced["grounding_trace"]["all_distractors_in_scope"])
        self.assertTrue(traced["self_check"]["evidence_within_inherited_only"])
        self.assertNotIn("distractor_outside_registry_scope", traced["review_reasons"])

        traced["choice_explanations"]["5"]["source_id"] = "outside_registry"
        retraced = apply_grounding_trace(traced, grounding)
        self.assertFalse(retraced["grounding_trace"]["all_distractors_in_scope"])
        self.assertIn("distractor_outside_registry_scope", retraced["review_reasons"])

    def test_trace_prefers_question_blueprint_same_domain_sources(self):
        grounding = build_generation_grounding("표적 질환", self.registry_path)
        source_ids = [f"a:treatment:{index}" for index in range(1, 5)]
        raw = {
            "problem": "55세 환자의 상태와 이전 치료 반응을 고려할 때 다음 치료는?",
            "options": ["정답 치료", "치료 A", "치료 B", "치료 C", "치료 D"],
            "answer": 1,
            "reasoning_hops": 2,
            "cognitive_model": {"decision_cues": ["이전 치료 실패", "환자 위험"]},
            "choice_explanations": {
                "1": {"rationale": "정답 근거"},
                **{
                    str(index + 2): {
                        "rationale": "오답 근거",
                        "why_attractive": "임상적으로 고려 가능한 치료",
                        "source_id": source_id,
                    }
                    for index, source_id in enumerate(source_ids)
                },
            },
            "pma_solution": {"correct_reason": "근거", "source_anchor": "a:treatment:key"},
            "question_blueprint": {
                "distractor_sources": [
                    {
                        "source_id": source_id,
                        "label": f"치료 {index}",
                        "aliases": [f"치료 {index}"],
                        "provenance": "treated_with",
                        "in_registry": True,
                    }
                    for index, source_id in enumerate(source_ids, 1)
                ]
            },
        }
        record = normalize_question(raw, idx=1, source_name="synthetic.txt", subject="General", unit="test")
        record["question_blueprint"] = raw["question_blueprint"]

        traced = apply_grounding_trace(record, grounding)

        self.assertEqual(traced["grounding_trace"]["distractor_contract"], "question_blueprint")
        self.assertEqual(traced["grounding_trace"]["allowed_distractor_ids"], source_ids)
        self.assertTrue(traced["grounding_trace"]["all_distractors_in_scope"])
        self.assertNotIn("distractor_outside_registry_scope", traced["review_reasons"])

    def test_student_approved_includes_only_approved_verified_axis_claims(self):
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        registry["concepts"]["target_disease"]["edges"]["differential_of"] = [
            {
                "id": cid,
                "review_status": "approved",
                "medical_approval": True,
                "applicability": "applicable",
                "review": {
                    "reviewer_id": "faculty:test",
                    "reviewed_at": "2026-07-12T12:00:00+09:00",
                },
                "provenance": {"claim_entailment": "verified"},
            }
            for cid in ("disease_b", "disease_c", "disease_d", "disease_e")
        ]
        self.registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

        axes = json.loads(self.axis_registry_path.read_text(encoding="utf-8"))
        for node in axes["nodes"]:
            node["review_status"] = "approved"
            node["medical_approval"] = True
            node["applicability"] = "applicable"
            node["review"] = {
                "reviewer_id": "faculty:test",
                "reviewed_at": "2026-07-12T12:00:00+09:00",
            }
            node["provenance"] = {"claim_entailment": "verified"}
            node["needs_review"] = False
        approved_edge = axes["relationships"][0]
        approved_edge.update(
            {
                "review_status": "approved",
                "medical_approval": True,
                "applicability": "applicable",
                "review": {
                    "reviewer_id": "faculty:test",
                    "reviewed_at": "2026-07-12T12:00:00+09:00",
                },
                "needs_review": False,
            }
        )
        approved_edge["provenance"] = {
            "claim_entailment": "verified",
            "evidence_refs": [
                {
                    "ref_id": "guideline:synthetic:1",
                    "source_type": "guideline",
                    "entailment_status": "verified",
                }
            ],
        }
        excluded_edge = axes["relationships"][1]
        excluded_edge.update(
            {
                "review_status": "approved",
                "medical_approval": True,
                "applicability": "applicable",
                "review": {
                    "reviewer_id": "faculty:test",
                    "reviewed_at": "2026-07-12T12:00:00+09:00",
                },
                "needs_review": False,
            }
        )
        excluded_edge["provenance"] = {
            "claim_entailment": "unverified",
            "evidence_refs": [],
        }
        self.axis_registry_path.write_text(json.dumps(axes, ensure_ascii=False), encoding="utf-8")

        grounding = build_generation_grounding(
            "표적 질환",
            self.registry_path,
            axis_registry_path=self.axis_registry_path,
            review_policy="student_approved",
            review_decisions_path=self.review_decisions_path,
        )

        context = grounding["pack"]["axis_context"]
        self.assertEqual(grounding["review_policy"], "student_approved")
        self.assertFalse(grounding["blocked"])
        self.assertTrue(grounding["pack"]["policy_ready"])
        self.assertEqual(context["node_count"], 1)
        self.assertEqual(context["types"]["risk_factor"][0]["axis_id"], "a:risk_factor:smoking")
        self.assertEqual(context["excluded_counts"]["policy_total"], 1)
        self.assertEqual(context["excluded_counts"]["claim_entailment_not_verified"], 1)
        self.assertEqual(context["verified_evidence_ref_count"], 1)
        self.assertTrue(grounding["pack"]["evidence_available"])
        self.assertEqual(len(grounding["pack"]["distractor_pool"]), 4)
        self.assertEqual(grounding["missing"], [])

    def test_student_approved_fails_closed_for_draft_only_ontology(self):
        grounding = build_generation_grounding(
            "표적 질환",
            self.registry_path,
            axis_registry_path=self.axis_registry_path,
            review_policy="student_approved",
            review_decisions_path=self.review_decisions_path,
        )

        context = grounding["pack"]["axis_context"]
        self.assertTrue(grounding["blocked"])
        self.assertFalse(grounding["fallback_general_generation"])
        self.assertEqual(context["status"], "no_approved_axis_claims")
        self.assertEqual(context["node_count"], 0)
        self.assertEqual(context["excluded_counts"]["policy_total"], 2)
        self.assertEqual(context["excluded_counts"]["axis_medical_approval_not_true"], 2)
        self.assertEqual(context["excluded_counts"]["relationship_medical_approval_not_true"], 2)
        self.assertEqual(context["excluded_counts"]["axis_reviewer_missing"], 2)
        self.assertEqual(context["excluded_counts"]["relationship_reviewer_missing"], 2)
        self.assertEqual(len(grounding["pack"]["distractor_pool"]), 0)
        self.assertFalse(grounding["pack"]["evidence_available"])
        self.assertIn("approved_axis_claims_missing", grounding["missing"])
        self.assertIn("verified_claim_evidence_missing", grounding["missing"])
        self.assertIn("approved_distractor_pool_lt_4", grounding["missing"])
        self.assertEqual(grounding["excluded_counts"]["axis_relationships_by_policy"], 2)

    def test_student_approved_trace_records_policy_exclusions_and_block(self):
        axes = json.loads(self.axis_registry_path.read_text(encoding="utf-8"))
        axes["review_overrides"] = {
            "status": "loaded",
            "schema_version": "ontology_review_decisions.v1",
            "path": "data_private/curriculum/ontology_review_decisions.json",
            "applied_count": 0,
        }
        self.axis_registry_path.write_text(json.dumps(axes, ensure_ascii=False), encoding="utf-8")
        grounding = build_generation_grounding(
            "표적 질환",
            self.registry_path,
            axis_registry_path=self.axis_registry_path,
            review_policy="student_approved",
            review_decisions_path=self.review_decisions_path,
        )
        record = {
            "problem": "55세 남자가 복통으로 내원하였다. 다음으로 가장 적절한 검사는?",
            "options": ["검사 A", "검사 B", "검사 C", "검사 D", "검사 E"],
            "answer": 1,
            "choice_explanations": {},
            "review_reasons": [],
            "self_check": {},
        }

        traced = apply_grounding_trace(record, grounding)

        trace = traced["grounding_trace"]
        self.assertEqual(trace["review_policy"], "student_approved")
        self.assertTrue(trace["policy_blocked"])
        self.assertEqual(trace["excluded_counts"]["axis_relationships_by_policy"], 2)
        self.assertEqual(trace["axis_registry_review"]["review_decisions_status"], "loaded")
        self.assertEqual(trace["axis_registry_review"]["review_decisions_applied"], 0)
        self.assertIn("approved_axis_claims_missing", trace["block_reasons"])
        self.assertIn("ontology_review_policy_blocked", traced["review_reasons"])
        self.assertEqual(traced["concept_grounding_status"], "matched_policy_blocked")
        self.assertTrue(traced["needs_review"])
        self.assertFalse(traced["gen_ready"])

    def test_student_approved_blocks_unapproved_concept_without_exposing_pack(self):
        missing_decisions = Path(self.temp.name) / "missing_review_decisions.json"
        grounding = build_generation_grounding(
            "표적 질환",
            self.registry_path,
            axis_registry_path=self.axis_registry_path,
            review_policy="student_approved",
            review_decisions_path=missing_decisions,
        )

        self.assertTrue(grounding["blocked"])
        self.assertIsNone(grounding["pack"])
        self.assertFalse(grounding["fallback_general_generation"])
        self.assertEqual(grounding["missing"], ["concept_not_medically_approved"])
        self.assertEqual(grounding["block_reasons"], ["concept_not_medically_approved"])
        self.assertEqual(grounding["review_decisions"]["status"], "review_decisions_missing")
        self.assertFalse(grounding["concept_review"]["medically_approved"])
        self.assertEqual(grounding["excluded_counts"]["concepts_by_policy"], 1)

    def test_review_status_alone_never_medically_approves_concept(self):
        incomplete_path = Path(self.temp.name) / "incomplete_review_decisions.json"
        incomplete_path.write_text(
            json.dumps(
                {
                    "schema_version": "ontology_review_decisions.v1",
                    "concepts": [
                        {"concept_id": "target_disease", "review_status": "approved"}
                    ],
                    "axis_nodes": [],
                    "axis_relationships": [],
                }
            ),
            encoding="utf-8",
        )

        grounding = build_generation_grounding(
            "표적 질환",
            self.registry_path,
            axis_registry_path=self.axis_registry_path,
            review_policy="student_approved",
            review_decisions_path=incomplete_path,
        )

        self.assertTrue(grounding["blocked"])
        self.assertIsNone(grounding["pack"])
        self.assertIn("concept_medical_approval_not_true", grounding["concept_review"]["approval_failures"])
        self.assertIn("concept_claim_entailment_not_verified", grounding["concept_review"]["approval_failures"])
        self.assertIn("concept_reviewer_missing", grounding["concept_review"]["approval_failures"])

    def test_unknown_review_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            build_generation_grounding(
                "표적 질환",
                self.registry_path,
                axis_registry_path=self.axis_registry_path,
                review_policy="auto_approve",
            )


if __name__ == "__main__":
    unittest.main()
