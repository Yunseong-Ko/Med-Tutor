import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import api_server


class StudentV3ApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.qbank = self.root / "qbank.json"
        self.attempts = self.root / "attempts.jsonl"
        self.preferences = self.root / "preferences.jsonl"
        self.bookmarks = self.root / "bookmarks.jsonl"
        self.fsrs = self.root / "fsrs.jsonl"
        self.notes = self.root / "notes.json"
        self.links = self.root / "links.json"
        self.qbank.write_text(
            json.dumps(
                {
                    "questions": [
                        self.question("NEURO_Q1", "신경 및 특수감각기학 · 2025 2차", "신경 및 특수감각기학"),
                        self.question("HEME_Q1", "혈액종양내과 · 2026 1차", "혈액종양내과"),
                        self.question("PMA_Q1", "임상종합평가 · 2025 B군 1교시", "내과"),
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.notes.write_text(
            json.dumps({"notes": [{"disease_concept_id": "concept_a", "title": "검수 전", "needs_review": True, "gen_ready": False}]}),
            encoding="utf-8",
        )
        self.links.write_text(
            json.dumps({"questions": {"HEME_Q1": {"concept": "concept_a", "label": "노출 금지"}}}),
            encoding="utf-8",
        )
        self.patchers = [
            patch.object(api_server, "STUDENT_QBANK_PATH", self.qbank),
            patch.object(api_server, "ATTEMPTS_LOG_PATH", self.attempts),
            patch.object(api_server, "STUDENT_COURSE_PREFERENCES_LOG_PATH", self.preferences),
            patch.object(api_server, "PRACTICE_BOOKMARKS_LOG_PATH", self.bookmarks),
            patch.object(api_server, "STUDENT_FSRS_LOG_PATH", self.fsrs),
            patch.object(api_server, "STUDENT_CONCEPT_NOTES_PATH", self.notes),
            patch.object(api_server, "STUDENT_QUESTION_LINKS_PATH", self.links),
        ]
        for patcher in self.patchers:
            patcher.start()
        api_server.load_student_qbank.cache_clear()
        self.client = TestClient(api_server.app)

    def tearDown(self):
        api_server.load_student_qbank.cache_clear()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tempdir.cleanup()

    @staticmethod
    def question(question_id, exam, subject):
        return {
            "id": question_id,
            "exam": exam,
            "subject": subject,
            "major": "대분류",
            "topic": "주제",
            "subtopic": "세부",
            "qtype": "단일선택",
            "stem": "정답을 고르시오.",
            "choices": [{"n": "1", "text": "오답", "expl": "오답 해설"}, {"n": "2", "text": "정답", "expl": "정답 해설"}],
            "answer": "2",
            "explanation": "검증된 해설",
            "points": ["핵심 포인트"],
            "imgs": [],
        }

    def test_catalog_keeps_sixteen_courses_and_assessment_separate(self):
        payload = self.client.get("/api/student/catalog").json()
        self.assertEqual(len(payload["courses"]), 16)
        self.assertNotIn("임상종합평가", {course["name"] for course in payload["courses"]})
        self.assertEqual(payload["assessments"][0]["question_count"], 1)
        neuro = next(course for course in payload["courses"] if course["id"] == "neuro")
        self.assertEqual(neuro["question_count"], 1)

    def test_course_favorite_and_question_bookmark_are_persisted(self):
        response = self.client.patch("/api/student/courses/cardio/favorite", json={"on": True})
        self.assertEqual(response.status_code, 200)
        self.assertIn("cardio", self.client.get("/api/student/preferences").json()["favorite_course_ids"])
        response = self.client.patch("/api/student/questions/HEME_Q1/bookmark", json={"on": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/student/bookmarks").json()["question_ids"], ["HEME_Q1"])

    def test_answer_is_idempotent_and_draft_ontology_is_fail_closed(self):
        body = {"event_id": "same-event", "session_id": "student-v3", "selected_choices": ["2"]}
        first = self.client.post("/api/student/questions/HEME_Q1/answer", json=body)
        second = self.client.post("/api/student/questions/HEME_Q1/answer", json=body)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["is_correct"])
        self.assertEqual(first.json()["learning_context"]["ontology"]["status"], "reviewing")
        self.assertNotIn("label", first.json()["learning_context"]["ontology"])
        self.assertEqual(second.json()["status"], "already_saved")
        self.assertEqual(len(self.attempts.read_text(encoding="utf-8").splitlines()), 1)

    def test_fsrs_review_is_real_and_idempotent(self):
        body = {"event_id": "fsrs-event", "question_id": "HEME_Q1", "rating": 3}
        first = self.client.post("/api/student/fsrs/reviews", json=body)
        second = self.client.post("/api/student/fsrs/reviews", json=body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["algorithm"], "FSRS-6")
        self.assertTrue(first.json()["card"]["due"])
        self.assertEqual(second.json()["status"], "already_saved")
        self.assertEqual(len(self.fsrs.read_text(encoding="utf-8").splitlines()), 1)

    def test_unapproved_concepts_are_not_returned(self):
        payload = self.client.get("/api/student/concepts").json()
        self.assertEqual(payload["approved"], [])
        self.assertEqual(payload["reviewing_count"], 1)


if __name__ == "__main__":
    unittest.main()
