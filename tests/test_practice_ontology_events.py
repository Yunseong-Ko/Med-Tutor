import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema
from fastapi.testclient import TestClient

import api_server


class PracticeOntologyEventTests(unittest.TestCase):
    @staticmethod
    def _released_gate(exam_id, question, surface):
        blueprint = question.get("question_blueprint") if isinstance(question.get("question_blueprint"), dict) else {}
        if (
            exam_id != "ONTOLOGY_ATTEMPT_TEST"
            or question.get("review_status") != "approved"
            or not blueprint
        ):
            return {
                "allowed": False,
                "release_id": None,
                "reasons": ["trust_kernel_release_missing"],
                "item_version": api_server.question_content_sha256(question),
            }
        item = {
            "disease_concept_id": "multiple_myeloma",
            "target_axis_type": "diagnosis",
            "target_axis_ids": ["a:diagnosis:212b4a4134450b"],
            "target_claim_ids": ["c:axis_relation:0123456789abcdef"],
            "choice_bindings": [
                {
                    "choice": "1",
                    "role": "answer",
                    "source_concept_id": "multiple_myeloma",
                    "feedback_claim_ids": ["c:axis_relation:0123456789abcdef"],
                    "why_attractive": "",
                    "discriminating_rule": {
                        "claim_id": "c:axis_relation:0123456789abcdef",
                        "text": "승인된 합성 테스트 규칙",
                    },
                },
                {
                    "choice": "2",
                    "role": "distractor",
                    "source_concept_id": "mgus",
                    "feedback_claim_ids": ["c:axis_relation:0123456789abcdef"],
                    "why_attractive": "승인된 합성 테스트 공통점",
                    "discriminating_rule": {
                        "claim_id": "c:axis_relation:0123456789abcdef",
                        "text": "승인된 합성 테스트 구분점",
                    },
                },
            ],
            "evidence": [
                {
                    "evidence_id": "ev:test",
                    "citation": "Synthetic test evidence",
                    "locator": "fixture",
                    "status": "verified",
                }
            ],
            "next_action": {
                "kind": "contrast_retest",
                "target_claim_ids": ["c:axis_relation:0123456789abcdef"],
                "due_bucket": "1d",
            },
            "feedback_content_sha256": "0" * 64,
        }
        release = {
            "release_id": "tk:test:release",
            "release_decision": {
                "reviewer_id": "reviewer:test",
                "reviewed_at": "2026-07-13T00:00:00+09:00",
            },
        }
        return {
            "allowed": True,
            "release_id": release["release_id"],
            "release_digest": "1" * 64,
            "reasons": [],
            "release": release,
            "question_release": item,
            "item_version": api_server.question_content_sha256(question),
        }

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.extracted_dir = self.root / "extracted"
        self.analytics_dir = self.root / "analytics"
        self.extracted_dir.mkdir(parents=True)
        self.analytics_dir.mkdir(parents=True)
        self.attempts_path = self.analytics_dir / "attempts.jsonl"
        self.exam_id = "ONTOLOGY_ATTEMPT_TEST"
        self.question = {
            "question_id": "Q001",
            "question_number": 1,
            "stem": "다발골수종의 진단을 가장 잘 뒷받침하는 소견은?",
            "choices": {"1": "정답 소견", "2": "MGUS에 가까운 소견"},
            "answer": "1",
            "review_status": "approved",
            "labels": {
                "course_name": "혈액종양",
                "assessment_domain": "진단",
                "question_type": "검사해석",
            },
            "disease_concept_id": "multiple_myeloma",
            "question_blueprint": {
                "schema_version": "question_blueprint.v1",
                "blueprint_id": "qb:1234567890abcdef",
                "status": "draft_blueprint",
                "question_type": "diagnosis",
                "selection": {
                    "target_axis_source": "explicit_axis_type",
                    "target_axis_ids_source": "explicit_axis_ids",
                    "option_domain_source": "explicit",
                },
                "target": {
                    "disease_concept_id": "multiple_myeloma",
                    "axis_type": "diagnosis",
                    "axis_ids": ["a:diagnosis:212b4a4134450b"],
                },
                "supporting_axes": [],
                "option_domain": "disease",
                "distractor_source_ids": ["mgus"],
                "distractor_sources": [
                    {
                        "source_id": "mgus",
                        "label": "MGUS",
                        "aliases": ["monoclonal gammopathy of undetermined significance"],
                        "provenance": "differential_of",
                        "in_registry": True,
                    }
                ],
                "misconceptions": [
                    {
                        "misconception_id": "mc:fedcba0987654321",
                        "kind": "distractor_confusion_candidate",
                        "target_disease_concept_id": "multiple_myeloma",
                        "target_axis_type": "diagnosis",
                        "distractor_source_id": "mgus",
                        "review_status": "draft_unreviewed",
                        "needs_review": True,
                        "medical_approval": False,
                    }
                ],
                "review_status": "draft_unreviewed",
                "needs_review": True,
                "medical_approval": False,
                "gen_ready": False,
                "block_reasons": [],
                "source_contract": {
                    "grounding_review_policy": "student_approved",
                    "grounding_blocked": False,
                    "grounding_pack_present": True,
                },
            },
            "choice_explanations": {
                "1": {
                    "source_id": "multiple_myeloma",
                    "misconception_id": "",
                    "misconception": "",
                    "why_attractive": "",
                    "provenance": "answer_target",
                },
                "2": {
                    "source_id": "mgus",
                    "misconception_id": "mc:fedcba0987654321",
                    "misconception": "장기 손상 유무를 구분하지 못함",
                    "why_attractive": "M 단백만 보고 판단함",
                    "provenance": "differential_of",
                },
            },
        }
        record = {
            "exam": {"source_exam": self.exam_id, "course_name": "혈액종양"},
            "questions": [self.question],
            "media_assets": [],
        }
        (self.extracted_dir / f"{self.exam_id}.json").write_text(
            json.dumps(record, ensure_ascii=False),
            encoding="utf-8",
        )
        self.patches = [
            patch.object(api_server, "COURSE_EXAM_EXTRACTED_DIR", self.extracted_dir),
            patch.object(api_server, "LEARNING_ANALYTICS_DIR", self.analytics_dir),
            patch.object(api_server, "ATTEMPTS_LOG_PATH", self.attempts_path),
            patch.object(api_server, "evaluate_practice_release", side_effect=self._released_gate),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(api_server.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_practice_serializer_preserves_blueprint_and_choice_provenance(self):
        serialized = api_server.course_exam_practice_question(self.question, {})

        self.assertEqual(serialized["disease_concept_id"], "multiple_myeloma")
        self.assertEqual(serialized["question_blueprint"]["blueprint_id"], "qb:1234567890abcdef")
        self.assertEqual(serialized["target_axis_type"], "diagnosis")
        self.assertEqual(serialized["target_axis_ids"], ["a:diagnosis:212b4a4134450b"])
        self.assertEqual(serialized["choice_ontology"]["2"]["source_id"], "mgus")
        self.assertEqual(
            serialized["choice_ontology"]["2"]["misconception_id"],
            "mc:fedcba0987654321",
        )
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "schemas" / "question_blueprint.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.validate(serialized["question_blueprint"], schema)
        self.assertNotIn("target_axis_ids", serialized["question_blueprint"])

    def test_draft_offline_grounding_is_server_only_and_not_student_visible(self):
        record_path = self.extracted_dir / f"{self.exam_id}.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        question = record["questions"][0]
        question.pop("disease_concept_id", None)
        question.pop("question_blueprint", None)
        question["review_status"] = "needs_review"
        question["ontology_grounding"] = {
            "disease_concept_id": "multiple_myeloma",
            "grounding_source": "concept_registry_v598_deterministic",
            "needs_review": True,
        }
        record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

        # The pre-answer serializer must not reveal a draft diagnosis label.
        public_question = api_server.course_exam_practice_question(question, {})
        self.assertIsNone(public_question["disease_concept_id"])
        self.assertNotIn("ontology_grounding", public_question)

        response = self.client.post(
            "/api/practice/attempts",
            json={
                "event_id": "offline_grounding_attempt",
                "user_id": "student_1",
                "exam_id": self.exam_id,
                "question_id": "Q001",
                "selected_choice_numbers": ["2"],
            },
        )
        self.assertEqual(response.status_code, 200)
        receipt = response.json()["attempt"]
        self.assertEqual(receipt["ontology"]["status"], "withheld_unapproved")
        self.assertFalse(receipt["ontology"]["student_visible"])
        self.assertIsNone(receipt["ontology"]["disease_concept_id"])
        self.assertFalse(receipt["ontology"]["analytics_eligible"])

        stored = json.loads(self.attempts_path.read_text(encoding="utf-8").strip())
        self.assertEqual(stored["disease_concept_id"], "multiple_myeloma")
        self.assertEqual(stored["ontology_snapshot"]["mapping_source"], "ontology_grounding")
        self.assertEqual(
            stored["ontology_snapshot"]["mapping_review_status"],
            "draft_unreviewed",
        )
        self.assertTrue(stored["ontology_snapshot"]["mapping_needs_review"])
        self.assertFalse(stored["ontology_snapshot"]["student_visible"])

    def test_attempt_uses_server_question_and_snapshots_selected_distractor(self):
        response = self.client.post(
            "/api/practice/attempts",
            json={
                "event_id": "attempt_wrong",
                "user_id": "student_1",
                "exam_id": self.exam_id,
                "question_id": "Q001",
                "selected_choice_numbers": ["2"],
                # Deliberately false client metadata; none may override storage.
                "answer_keys": ["2"],
                "is_correct": True,
                "labels": {"assessment_domain": "spoofed"},
                "disease_concept_id": "spoofed_concept",
                "target_axis_ids": ["a:treatment:00000000000000"],
                "time_ms": 12000,
            },
        )

        self.assertEqual(response.status_code, 200)
        receipt = response.json()["attempt"]
        self.assertFalse(receipt["is_correct"])
        self.assertNotIn("answer_keys", receipt)
        self.assertNotIn("choice_texts", receipt)
        self.assertEqual(receipt["labels"]["assessment_domain"], "진단")
        self.assertEqual(receipt["ontology"]["disease_concept_id"], "multiple_myeloma")
        self.assertEqual(receipt["ontology"]["target_axis_type"], "diagnosis")
        self.assertEqual(receipt["ontology"]["target_axis_ids"], ["a:diagnosis:212b4a4134450b"])
        self.assertTrue(receipt["ontology"]["analytics_eligible"])
        self.assertTrue(receipt["ontology"]["student_visible"])
        self.assertEqual(receipt["ontology"]["status"], "available")
        feedback = response.json()["feedback"]
        self.assertEqual(feedback["status"], "released")
        self.assertEqual(feedback["selected_distractors"][0]["source_concept_id"], "mgus")

        stored = json.loads(self.attempts_path.read_text(encoding="utf-8").strip())
        self.assertEqual(stored["answer_keys"], ["1"])
        self.assertEqual(stored["misconception_ids"], ["mc:fedcba0987654321"])
        self.assertEqual(stored["distractor_source_ids"], ["mgus"])
        self.assertEqual(stored["ontology_snapshot"]["blueprint_id"], "qb:1234567890abcdef")
        self.assertEqual(stored["selected_choice_ontology"][0]["source_id"], "mgus")

    def test_student_analytics_groups_by_concept_axis_with_sample_size(self):
        for event_id, selected in (("attempt_wrong", "2"), ("attempt_right", "1")):
            response = self.client.post(
                "/api/practice/attempts",
                json={
                    "event_id": event_id,
                    "user_id": "student_1",
                    "exam_id": self.exam_id,
                    "question_id": "Q001",
                    "selected_choice_numbers": [selected],
                    "time_ms": 10000,
                },
            )
            self.assertEqual(response.status_code, 200)

        response = self.client.get(
            "/api/practice/analytics/student",
            params={"user_id": "student_1"},
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()["ontology_weakness"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["disease_concept_id"], "multiple_myeloma")
        self.assertEqual(row["axis_type"], "diagnosis")
        self.assertEqual(row["axis_id"], "a:diagnosis:212b4a4134450b")
        self.assertEqual(row["sample_size"], 2)
        self.assertEqual(row["correct_count"], 1)
        self.assertEqual(row["correct_rate_pct"], 50.0)
        self.assertEqual(row["misconceptions"], [{"misconception_id": "mc:fedcba0987654321", "count": 1}])

    def test_legacy_attempt_without_exam_id_remains_writable_but_untrusted(self):
        response = self.client.post(
            "/api/practice/attempts",
            json={
                "event_id": "legacy_attempt",
                "question_id": "legacy_q",
                "selected_choice_numbers": ["1"],
                "disease_concept_id": "client_claimed_concept",
            },
        )

        self.assertEqual(response.status_code, 200)
        event = response.json()["attempt"]
        self.assertEqual(event["ontology_snapshot_status"], "unresolved_legacy_missing_exam_id")
        self.assertNotIn("disease_concept_id", event)

    def test_unapproved_question_is_excluded_from_ontology_mastery(self):
        record_path = self.extracted_dir / f"{self.exam_id}.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["questions"][0]["review_status"] = "draft"
        record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

        saved = self.client.post(
            "/api/practice/attempts",
            json={
                "event_id": "draft_attempt",
                "user_id": "student_1",
                "exam_id": self.exam_id,
                "question_id": "Q001",
                "selected_choice_numbers": ["2"],
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(saved.json()["attempt"]["ontology"]["analytics_eligible"])
        self.assertFalse(saved.json()["attempt"]["ontology"]["student_visible"])
        self.assertIsNone(saved.json()["attempt"]["ontology"]["disease_concept_id"])
        analytics = self.client.get(
            "/api/practice/analytics/student",
            params={"user_id": "student_1"},
        )
        self.assertEqual(analytics.json()["ontology_weakness"], [])

    def test_inline_approval_flags_cannot_replace_external_release(self):
        record_path = self.extracted_dir / f"{self.exam_id}.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["questions"][0]["ontology_analytics_approved"] = True
        record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        denied = {
            "allowed": False,
            "release_id": None,
            "reasons": ["trust_kernel_release_missing"],
            "item_version": api_server.question_content_sha256(record["questions"][0]),
        }
        with patch.object(api_server, "evaluate_practice_release", return_value=denied):
            saved = self.client.post(
                "/api/practice/attempts",
                json={
                    "event_id": "inline_flag_attempt",
                    "user_id": "student_1",
                    "exam_id": self.exam_id,
                    "question_id": "Q001",
                    "selected_choice_numbers": ["2"],
                },
            )
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(saved.json()["attempt"]["ontology"]["analytics_eligible"])
        self.assertEqual(saved.json()["feedback"]["status"], "withheld")

    def test_student_question_endpoint_uses_strict_pre_answer_allowlist(self):
        response = self.client.get(f"/api/practice/exams/{self.exam_id}/questions")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["released_count"], 1)
        question = payload["questions"][0]
        forbidden = {
            "answer",
            "generated_answer",
            "explanation",
            "answer_rationale",
            "choice_explanations",
            "key_info",
            "key_learning_points",
            "anki_cards",
            "disease_concept_id",
            "question_blueprint",
            "target_axis_type",
            "target_axis_ids",
            "choice_ontology",
            "grounding_trace",
            "evidence",
        }
        self.assertTrue(forbidden.isdisjoint(question))
        self.assertEqual(question["choices"], {"1": "정답 소견", "2": "MGUS에 가까운 소견"})

    def test_attempt_rejects_invalid_choice_and_duplicate_event_id(self):
        invalid = self.client.post(
            "/api/practice/attempts",
            json={
                "event_id": "invalid_choice",
                "exam_id": self.exam_id,
                "question_id": "Q001",
                "selected_choice_numbers": ["9"],
            },
        )
        self.assertEqual(invalid.status_code, 400)

        payload = {
            "event_id": "one_event",
            "exam_id": self.exam_id,
            "question_id": "Q001",
            "selected_choice_numbers": ["1"],
        }
        self.assertEqual(self.client.post("/api/practice/attempts", json=payload).status_code, 200)
        duplicate = self.client.post("/api/practice/attempts", json=payload)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.attempts_path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
