"""QuestionBlueprint integration tests for the Studio generation service."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services import lecture_studio


def synthetic_grounding(*, review_policy: str = "faculty_draft") -> dict:
    distractors = ["disease_a", "disease_b", "disease_c", "disease_d"]
    return {
        "topic": "target disease",
        "review_policy": review_policy,
        "policy_requirements": {},
        "review_decisions": {},
        "concept_review": {
            "disease_concept_id": "target_disease",
            "medically_approved": review_policy == "student_approved",
        },
        "registry": {"concept_count": 5},
        "match": {
            "status": "matched",
            "disease_concept_id": "target_disease",
            "match_method": "explicit_concept_id",
        },
        "pack": {
            "review_policy": review_policy,
            "disease_concept_id": "target_disease",
            "label": "Target disease",
            "axis_context": {
                "types": {
                    "diagnosis": [
                        {
                            "axis_id": "a:diagnosis:test",
                            "label": "diagnostic test",
                            "relation": "diagnosed_by",
                        }
                    ],
                    "symptom": [
                        {
                            "axis_id": "a:symptom:finding",
                            "label": "clinical finding",
                            "relation": "presents_with",
                        }
                    ],
                },
                "type_counts": {"diagnosis": 1, "symptom": 1},
                "node_count": 2,
                "registry": {},
            },
            "distractor_pool": [
                {
                    "id": disease_id,
                    "label": disease_id,
                    "aliases": [disease_id],
                    "provenance": "differential_of",
                    "in_registry": True,
                }
                for disease_id in reversed(distractors)
            ],
            "evidence": {
                "source_refs": [
                    {"ref_id": "synthetic:source", "source_type": "synthetic"}
                ]
            },
            "evidence_available": True,
            "inherited_edges": {},
            "draft_generation_ready": True,
            "needs_review": True,
            "gen_ready": False,
        },
        "fallback_general_generation": False,
        "missing": [],
        "blocked": False,
        "block_reasons": [],
        "excluded_counts": {},
        "needs_review": True,
        "gen_ready": False,
    }


def generated_question_payload() -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "problem": (
                        "55세 환자가 임상 소견으로 내원하였다. 다음 중 가장 적절한 진단은?"
                    ),
                    "options": ["정답", "오답 1", "오답 2", "오답 3", "오답 4"],
                    "answer": 1,
                    "explanation": "제공된 근거에 따른 검수용 해설",
                    "pma_solution": {
                        "reasoning_summary": "근거를 종합한다.",
                        "correct_reason": "제공된 진단 축에 해당한다.",
                        "choice_explanations": {
                            "1": "정답",
                            "2": "오답",
                            "3": "오답",
                            "4": "오답",
                            "5": "오답",
                        },
                        "high_yield_point": "검수 필요",
                        "trap": "감별 혼동",
                        "source_anchor": "a:diagnosis:test",
                    },
                    "choice_explanations": {
                        "2": {"source_id": "disease_d"},
                        "3": {"source_id": "disease_b"},
                        "4": {"source_id": "disease_a"},
                        "5": {"source_id": "disease_c"},
                    },
                    "evidence_refs": [],
                    "needs_review": True,
                    "gen_ready": False,
                }
            ]
        },
        ensure_ascii=False,
    )


class LectureStudioQuestionBlueprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        path_values = {
            "DATA_ROOT": self.root,
            "UPLOAD_DIR": self.root / "uploads",
            "EXTRACTED_DIR": self.root / "extracted",
            "GENERATED_DIR": self.root / "generated",
            "IMAGE_DIR": self.root / "images",
            "CONVERTED_DIR": self.root / "converted",
            "MEDIA_DIR": self.root / "media_bank",
            "MEDIA_ASSET_DIR": self.root / "media_bank" / "assets",
            "MEDIA_INDEX_PATH": self.root / "media_bank" / "media_assets.json",
            "QUESTION_BANK_DIR": self.root / "question_bank",
            "REVIEW_SET_DIR": self.root / "review_sets",
            "EXPORT_SET_DIR": self.root / "export_sets",
        }
        self.path_patchers = [
            patch.object(lecture_studio, name, value) for name, value in path_values.items()
        ]
        for patcher in self.path_patchers:
            patcher.start()
        self.timestamp_patcher = patch.object(
            lecture_studio,
            "timestamp_slug",
            return_value="20260712T120000Z",
        )
        self.timestamp_patcher.start()
        lecture_studio.ensure_studio_dirs()
        lecture_path = self.root / "lecture.txt"
        lecture_path.write_text("Synthetic lecture evidence for a target disease.", encoding="utf-8")
        self.lecture = lecture_studio.SavedUpload(
            path=lecture_path,
            original_name="lecture.txt",
            kind="lecture",
        )

    def tearDown(self) -> None:
        self.timestamp_patcher.stop()
        for patcher in reversed(self.path_patchers):
            patcher.stop()
        self.temp.cleanup()

    def test_storage_slug_is_ascii_and_safe_for_long_korean_topic(self):
        source = "topic_" + ("다발골수종_초기치료_" * 20) + ".txt"
        slug = lecture_studio.source_storage_slug(source)
        self.assertTrue(slug.isascii())
        self.assertLess(len(f"{slug}.question_set.json".encode("utf-8")), 255)

    def test_prompt_only_preserves_blueprint_and_explicit_target_contract(self):
        with patch.object(
            lecture_studio,
            "build_generation_grounding",
            return_value=synthetic_grounding(),
        ):
            result = lecture_studio.generate_studio_questions(
                self.lecture,
                set_name="Ontology QA Set",
                subject="Medicine",
                unit="Target disease",
                question_type="clinical_case",
                grounding_concept_id="target_disease",
                target_axis_type="diagnosis",
                target_axis_ids=["a:diagnosis:test"],
                supporting_axis_types=["symptom"],
                option_domain="test_selection",
                generation_profile="fast",
                provider="prompt-only",
                model="prompt-only",
            )

        self.assertEqual(result["status"], "prompt_ready")
        self.assertEqual(result["set_name"], "Ontology QA Set")
        self.assertEqual(result["question_blueprint"]["status"], "draft_blueprint")
        self.assertEqual(result["target_axis_type"], "diagnosis")
        self.assertEqual(result["target_axis_ids"], ["a:diagnosis:test"])
        self.assertEqual(result["option_domain"], "test_selection")
        self.assertEqual(result["sample"], [])
        prompt = Path(result["paths"]["prompt"]).read_text(encoding="utf-8")
        self.assertIn("QuestionBlueprint 교육 Ontology 계약", prompt)
        self.assertIn('"target_axis_type": "diagnosis"', prompt)
        self.assertIn('"option_domain": "test_selection"', prompt)
        self.assertIn('"allowed_distractor_source_ids"', prompt)
        self.assertIn('"allowed_distractor_sources"', prompt)
        self.assertIn("rationale과 why_attractive 또는 misconception", prompt)
        self.assertIn("disease_a", prompt)

    def test_faculty_draft_keeps_blocked_blueprint_as_reviewable_prompt(self):
        with patch.object(
            lecture_studio,
            "build_generation_grounding",
            return_value=synthetic_grounding(),
        ):
            result = lecture_studio.generate_studio_questions(
                self.lecture,
                question_type="clinical_case",
                provider="prompt-only",
                model="prompt-only",
            )

        self.assertEqual(result["status"], "prompt_ready")
        self.assertEqual(result["question_blueprint"]["status"], "blocked")
        self.assertIn("question_blueprint_blocked", result["review_reasons"])
        self.assertIn(
            "question_blueprint:target_axis_type_missing",
            result["review_reasons"],
        )

    def test_student_approved_blueprint_block_stops_before_model_call(self):
        with (
            patch.object(
                lecture_studio,
                "build_generation_grounding",
                return_value=synthetic_grounding(review_policy="student_approved"),
            ),
            patch.object(lecture_studio, "generate_openai") as model_call,
        ):
            with self.assertRaisesRegex(ValueError, "question_blueprint_blocked"):
                lecture_studio.generate_studio_questions(
                    self.lecture,
                    question_type="clinical_case",
                    ontology_review_policy="student_approved",
                    provider="openai",
                    model="test-model",
                )
        model_call.assert_not_called()

    def test_candidate_axis_ids_are_not_all_counted_as_assessed_claims(self):
        grounding = synthetic_grounding()
        grounding["pack"]["axis_context"]["types"]["diagnosis"].append(
            {
                "axis_id": "a:diagnosis:second",
                "label": "second diagnostic criterion",
                "relation": "diagnosed_by",
            }
        )
        blueprint = lecture_studio.build_question_blueprint(
            grounding,
            target_axis_type="diagnosis",
        )
        record = {
            "answer": 1,
            "options": ["정답", "오답1", "오답2", "오답3", "오답4"],
            "pma_solution": {"source_anchor": "lecture.txt"},
            "choice_explanations": {},
            "review_reasons": [],
        }

        linked = lecture_studio.apply_question_blueprint(record, blueprint)

        self.assertEqual(
            linked["target_axis_candidate_ids"],
            ["a:diagnosis:second", "a:diagnosis:test"],
        )
        self.assertEqual(linked["target_axis_ids"], [])
        self.assertEqual(linked["target_axis_resolution"], "axis_type_only")
        self.assertIn(
            "question_blueprint_target_axis_id_unresolved",
            linked["review_reasons"],
        )
        self.assertTrue(
            all(
                linked["choice_explanations"][str(index)]["source_id"] == ""
                for index in range(2, 6)
            )
        )
        self.assertIn(
            "question_blueprint_distractor_source_missing",
            linked["review_reasons"],
        )

    def test_answer_choice_can_resolve_one_target_axis_without_fabricating_it(self):
        grounding = synthetic_grounding()
        grounding["pack"]["axis_context"]["types"]["treatment"] = [
            {"axis_id": "a:treatment:drug_a", "label": "imatinib", "relation": "treated_with"},
            {"axis_id": "a:treatment:drug_b", "label": "ponatinib", "relation": "treated_with"},
            {"axis_id": "a:treatment:drug_c", "label": "hydroxyurea", "relation": "treated_with"},
            {"axis_id": "a:treatment:drug_d", "label": "transplant", "relation": "treated_with"},
        ]
        blueprint = lecture_studio.build_question_blueprint(
            grounding,
            target_axis_type="treatment",
        )
        record = {
            "answer": 2,
            "options": ["이마티닙 유지", "포나티닙(ponatinib) 투여", "하이드록시우레아", "동종이식", "관찰"],
            "pma_solution": {"source_anchor": "a:indication:wrong_domain"},
            "choice_explanations": {},
            "review_reasons": [],
        }

        linked = lecture_studio.apply_question_blueprint(record, blueprint)

        self.assertEqual(linked["target_axis_ids"], ["a:treatment:drug_b"])
        self.assertEqual(linked["target_axis_resolution"], "answer_choice_label")
        self.assertNotIn("question_blueprint_target_axis_id_unresolved", linked["review_reasons"])

    def test_generated_record_sample_and_archive_keep_blueprint_and_trace_ids(self):
        with (
            patch.object(
                lecture_studio,
                "build_generation_grounding",
                return_value=synthetic_grounding(),
            ),
            patch.object(
                lecture_studio,
                "generate_openai",
                return_value=generated_question_payload(),
            ),
        ):
            result = lecture_studio.generate_studio_questions(
                self.lecture,
                subject="Medicine",
                unit="Target disease",
                question_type="diagnostic",
                grounding_concept_id="target_disease",
                target_axis_type="diagnosis",
                provider="openai",
                model="test-model",
            )

        self.assertEqual(result["status"], "generated")
        self.assertEqual(result["question_blueprint"]["status"], "draft_blueprint")
        sample = result["sample"][0]
        self.assertEqual(sample["question_blueprint"]["blueprint_id"], result["question_blueprint"]["blueprint_id"])
        self.assertEqual(sample["target_axis_type"], "diagnosis")
        self.assertEqual(sample["target_axis_ids"], ["a:diagnosis:test"])
        self.assertEqual(sample["option_domain"], "diagnosis")

        explanations = sample["choice_explanations"]
        self.assertEqual(explanations["1"]["source_id"], "")
        distractor_source_ids = [explanations[str(index)]["source_id"] for index in range(2, 6)]
        self.assertEqual(set(distractor_source_ids), {"disease_a", "disease_b", "disease_c", "disease_d"})
        misconception_by_source = {
            row["distractor_source_id"]: row["misconception_id"]
            for row in result["question_blueprint"]["misconceptions"]
        }
        for index in range(2, 6):
            row = explanations[str(index)]
            self.assertEqual(row["misconception_id"], misconception_by_source[row["source_id"]])
        self.assertTrue(sample["grounding_trace"]["all_distractors_in_scope"])
        self.assertNotIn(
            "question_blueprint_distractor_source_assigned_by_server",
            sample["review_reasons"],
        )

        output_records = json.loads(Path(result["paths"]["output"]).read_text(encoding="utf-8"))
        self.assertEqual(
            output_records[0]["question_blueprint"]["blueprint_id"],
            result["question_blueprint"]["blueprint_id"],
        )
        archive = json.loads(Path(result["paths"]["question_bank"]).read_text(encoding="utf-8"))
        self.assertEqual(
            archive["metadata"]["question_blueprint"]["blueprint_id"],
            result["question_blueprint"]["blueprint_id"],
        )
        self.assertEqual(archive["questions"][0]["target_axis_type"], "diagnosis")


if __name__ == "__main__":
    unittest.main()
