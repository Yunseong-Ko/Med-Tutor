import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import api_server


class CanonicalStudentQbankApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.qbank_path = self.root / "qbank.json"
        self.analytics = self.root / "analytics"
        self.attempts = self.analytics / "attempts.jsonl"
        self.qbank_path.write_text(
            json.dumps(
                {
                    "questions": [
                        {
                            "id": "Q1",
                            "exam": "혈액종양내과 · 2026 1차",
                            "subject": "혈액종양내과",
                            "major": "혈액",
                            "topic": "혈액 기초",
                            "subtopic": "혈장",
                            "qtype": "단일선택",
                            "tags": ["albumin"],
                            "faculty": "교수자",
                            "stem": "옳은 것을 고르시오.",
                            "stimulus": "",
                            "choices": [
                                {"n": "1", "text": "오답", "expl": "오답 해설"},
                                {"n": "2", "text": "정답", "expl": "정답 해설"},
                            ],
                            "answer": "2",
                            "explanation": "서버 검증 해설",
                            "points": ["핵심"],
                            "imgs": [],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.patchers = [
            patch.object(api_server, "STUDENT_QBANK_PATH", self.qbank_path),
            patch.object(api_server, "LEARNING_ANALYTICS_DIR", self.analytics),
            patch.object(api_server, "ATTEMPTS_LOG_PATH", self.attempts),
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

    def test_catalog_excludes_truth_fields(self):
        response = self.client.get("/api/student/qbank")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["question_count"], 1)
        question = payload["questions"][0]
        self.assertNotIn("answer", question)
        self.assertNotIn("explanation", question)
        self.assertNotIn("expl", question["choices"][0])
        self.assertEqual(question["course"], "혈액종양내과")
        self.assertTrue(question["practice_ready"])
        self.assertEqual(payload["practice_ready_count"], 1)
        self.assertEqual(payload["media_review_count"], 0)

    def test_missing_required_visual_is_fail_closed(self):
        payload = json.loads(self.qbank_path.read_text(encoding="utf-8"))
        payload["questions"][0]["stimulus"] = "<그림>"
        self.qbank_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        api_server.load_student_qbank.cache_clear()

        catalog = self.client.get("/api/student/qbank")
        self.assertEqual(catalog.status_code, 200)
        self.assertFalse(catalog.json()["questions"][0]["practice_ready"])
        self.assertEqual(catalog.json()["practice_ready_count"], 0)
        self.assertEqual(catalog.json()["media_review_count"], 1)

        answer = self.client.post(
            "/api/student/questions/Q1/answer",
            json={"selected_choices": ["2"]},
        )
        self.assertEqual(answer.status_code, 409)
        self.assertIn("제시자료", answer.json()["detail"])

    def test_legacy_neuro_image_is_served_from_course_media_api(self):
        media_root = self.root / "media"
        source = media_root / "COURSE_2_20251103_NEURO_SPECIAL_SENSES_2차"
        source.mkdir(parents=True)
        (source / "BIN0004.jpeg").write_bytes(b"jpeg")
        payload = json.loads(self.qbank_path.read_text(encoding="utf-8"))
        payload["questions"][0]["stimulus"] = "<그림>"
        payload["questions"][0]["imgs"] = ["media/neuro_BIN0004.jpeg"]
        self.qbank_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        api_server.load_student_qbank.cache_clear()

        with patch.object(api_server, "COURSE_EXAM_MEDIA_DIR", media_root):
            catalog = self.client.get("/api/student/qbank")

        self.assertEqual(catalog.status_code, 200)
        question = catalog.json()["questions"][0]
        self.assertTrue(question["practice_ready"])
        self.assertTrue(question["imgs"][0].startswith("/api/course-exams/media/"))
        self.assertIn("BIN0004.jpeg", question["imgs"][0])

    def test_answer_is_verified_and_feedback_released_after_submission(self):
        response = self.client.post(
            "/api/student/questions/Q1/answer",
            json={
                "event_id": "event-q1",
                "session_id": "session-qbank",
                "selected_choices": ["2"],
                "answer_keys": ["1"],
                "is_correct": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["is_correct"])
        self.assertEqual(payload["answer_keys"], ["2"])
        self.assertEqual(payload["explanation"], "서버 검증 해설")
        stored = json.loads(self.attempts.read_text(encoding="utf-8").strip())
        self.assertTrue(stored["is_correct"])
        self.assertEqual(stored["answer_keys"], ["2"])


if __name__ == "__main__":
    unittest.main()
