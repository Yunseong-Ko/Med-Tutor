import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import api_server
from src.services import lecture_studio


class StudentPracticeV2ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.question_bank = self.root / "question_bank"
        self.review_sets = self.root / "review_sets"
        self.analytics = self.root / "analytics"
        self.anki_exports = self.root / "anki_exports"
        self.student_releases = self.root / "student_releases.json"
        for directory in (self.question_bank, self.review_sets, self.analytics, self.anki_exports):
            directory.mkdir(parents=True)

        packet = {
            "set_id": "approved_demo",
            "review_status": "faculty_review_pending",
            "created_at": "2026-07-16T00:00:00+00:00",
            "updated_at": "2026-07-16T00:00:00+00:00",
            "metadata": {
                "source_name": "approved-demo.docx",
                "subject": "응급의학",
                "unit": "외상",
                "question_type": "clinical_case",
                "exam_year": "2026",
                "professor": "김교수",
                "major_category": "외상학",
                "topic": "초기 처치",
                "assessment_domain": "임상 판단",
                "difficulty": "보통",
            },
            "questions": [
                {
                    "question_id": "APPROVED_Q001",
                    "problem": "교수 승인 테스트 문항입니다. 가장 적절한 선택지는?",
                    "options": ["정답 선택지", "오답 선택지"],
                    "answer": 1,
                    "explanation": "교수 검토가 완료된 테스트 해설입니다.",
                    "question_type": "clinical_case",
                    "review_status": "approved",
                    "subject": "응급의학",
                    "unit": "외상",
                    "image_refs": [{"id": "safe_image", "url": "/api/media/assets/safe.png"}],
                    "disease_concept_id": "must_never_leak",
                    "target_axis_type": "must_never_leak",
                },
                {
                    "question_id": "DRAFT_Q002",
                    "problem": "검토 중 문항",
                    "options": ["A", "B"],
                    "answer": 2,
                    "explanation": "검토 중 해설",
                    "review_status": "draft",
                },
            ],
        }
        (self.question_bank / "approved_demo.question_set.json").write_text(
            json.dumps(packet, ensure_ascii=False), encoding="utf-8"
        )
        unapproved = {
            **packet,
            "set_id": "draft_only",
            "questions": [{**packet["questions"][1], "question_id": "DRAFT_ONLY_Q001"}],
        }
        (self.question_bank / "draft_only.question_set.json").write_text(
            json.dumps(unapproved, ensure_ascii=False), encoding="utf-8"
        )
        self.student_releases.write_text(
            json.dumps(
                {
                    "schema_version": "student_releases.v1",
                    "assignments": [
                        {
                            "assignment_id": "release_approved_demo",
                            "set_id": "approved_demo",
                            "status": "released",
                            "audience": {"type": "all_local_students"},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        self.patches = [
            patch.object(lecture_studio, "QUESTION_BANK_DIR", self.question_bank),
            patch.object(lecture_studio, "REVIEW_SET_DIR", self.review_sets),
            patch.object(api_server, "LEARNING_ANALYTICS_DIR", self.analytics),
            patch.object(api_server, "STUDENT_RELEASES_PATH", self.student_releases),
            patch.object(api_server, "ATTEMPTS_LOG_PATH", self.analytics / "attempts.jsonl"),
            patch.object(api_server, "PRACTICE_SESSIONS_LOG_PATH", self.analytics / "practice_sessions.jsonl"),
            patch.object(api_server, "PRACTICE_BOOKMARKS_LOG_PATH", self.analytics / "practice_bookmarks.jsonl"),
            patch.object(api_server, "PRACTICE_SNAPSHOTS_LOG_PATH", self.analytics / "practice_snapshots.jsonl"),
            patch.object(api_server, "ANKI_EXPORT_DIR", self.anki_exports),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(api_server.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_catalog_includes_only_sets_with_approved_questions(self):
        response = self.client.get("/api/practice/catalog")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["set_id"] for item in payload["sets"]], ["approved_demo"])
        self.assertEqual(payload["available_question_count"], 1)
        self.assertEqual(payload["sets"][0]["exam_year"], "2026")
        self.assertEqual(payload["sets"][0]["instructor"], "김교수")
        self.assertEqual(payload["sets"][0]["assessment_domain"], "임상 판단")
        serialized = json.dumps(payload, ensure_ascii=False)
        for forbidden in ("answer", "explanation", "must_never_leak", "disease_concept", "target_axis"):
            self.assertNotIn(forbidden, serialized)

    def test_pre_answer_payload_is_strictly_safe(self):
        response = self.client.get("/api/practice/sets/approved_demo/questions")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["released_count"], 1)
        question = payload["questions"][0]
        self.assertEqual(question["selection_mode"], "single")
        self.assertEqual(question["media_refs"], [{"media_id": "safe_image", "url": "/api/media/assets/safe.png"}])
        serialized = json.dumps(question, ensure_ascii=False)
        for forbidden in ("answer", "explanation", "must_never_leak", "disease_concept", "target_axis"):
            self.assertNotIn(forbidden, serialized)

    def test_attempt_uses_server_truth_and_releases_feedback_after_submit(self):
        response = self.client.post(
            "/api/practice/attempts",
            json={
                "event_id": "attempt_server_truth",
                "session_id": "session_truth",
                "exam_id": "set:approved_demo",
                "question_id": "APPROVED_Q001",
                "selected_choices": ["1"],
                "answer_keys": ["2"],
                "is_correct": False,
                "time_ms": 1200,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["attempt"]["is_correct"])
        self.assertEqual(payload["feedback"]["status"], "released")
        self.assertEqual(payload["feedback"]["result"]["correct_choices"], ["1"])
        self.assertIn("교수 검토", payload["feedback"]["explanation"])

    def test_anki_export_requires_an_attempt_from_the_same_session(self):
        denied = self.client.post(
            "/api/practice/anki-export",
            json={
                "session_id": "session_anki",
                "items": [{"exam_id": "set:approved_demo", "question_id": "APPROVED_Q001"}],
            },
        )
        self.assertEqual(denied.status_code, 404)

        attempt = self.client.post(
            "/api/practice/attempts",
            json={
                "event_id": "attempt_anki",
                "session_id": "session_anki",
                "exam_id": "set:approved_demo",
                "question_id": "APPROVED_Q001",
                "selected_choices": ["2"],
            },
        )
        self.assertEqual(attempt.status_code, 200)
        exported = self.client.post(
            "/api/practice/anki-export",
            json={
                "session_id": "session_anki",
                "items": [{"exam_id": "set:approved_demo", "question_id": "APPROVED_Q001"}],
            },
        )
        self.assertEqual(exported.status_code, 200)
        payload = exported.json()
        self.assertEqual(payload["question_count"], 1)
        self.assertEqual(payload["card_count"], 2)
        self.assertTrue((self.anki_exports / Path(payload["download_url"]).name).exists())
        self.assertNotIn("file_path", payload)

    def test_question_report_requires_a_released_server_item(self):
        response = self.client.post(
            "/api/practice/reports",
            json={
                "session_id": "session_report",
                "exam_id": "set:approved_demo",
                "question_id": "APPROVED_Q001",
                "reason": "오타를 확인해 주세요.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "received")
        report_path = self.analytics / "question_reports.jsonl"
        self.assertTrue(report_path.exists())
        stored = json.loads(report_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(stored["question_id"], "APPROVED_Q001")

        denied = self.client.post(
            "/api/practice/reports",
            json={"exam_id": "set:approved_demo", "question_id": "DRAFT_Q002", "reason": "검토"},
        )
        self.assertEqual(denied.status_code, 404)

    def test_session_start_resolves_public_items_and_finalize_is_logged(self):
        started = self.client.post(
            "/api/practice/sessions",
            json={
                "title": "응급의학 맞춤 세트",
                "mode": "learning",
                "questions": [{"exam_id": "set:approved_demo", "question_id": "APPROVED_Q001"}],
            },
        )
        self.assertEqual(started.status_code, 200)
        session_id = started.json()["session_id"]
        self.assertTrue(session_id.startswith("practice_"))

        finalized = self.client.post(
            f"/api/practice/sessions/{session_id}/finalize",
            json={"answered_count": 1, "correct_count": 1, "elapsed_ms": 3200},
        )
        self.assertEqual(finalized.status_code, 200)
        events = [
            json.loads(line)
            for line in (self.analytics / "practice_sessions.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual([event["event_type"] for event in events], ["session_started", "session_finalized"])

        denied = self.client.post(
            "/api/practice/sessions",
            json={"questions": [{"exam_id": "set:approved_demo", "question_id": "DRAFT_Q002"}]},
        )
        self.assertEqual(denied.status_code, 404)

    def test_session_question_bookmark_snapshot_and_result_contract(self):
        started = self.client.post(
            "/api/practice/sessions",
            json={
                "title": "응급의학 학습 세트",
                "mode": "learning",
                "questions": [{"exam_id": "set:approved_demo", "question_id": "APPROVED_Q001"}],
            },
        )
        session_id = started.json()["session_id"]

        question_response = self.client.get(f"/api/practice/sessions/{session_id}/questions/0")
        self.assertEqual(question_response.status_code, 200)
        serialized = json.dumps(question_response.json(), ensure_ascii=False)
        for forbidden in ("answer", "explanation", "must_never_leak", "disease_concept", "target_axis"):
            self.assertNotIn(forbidden, serialized)

        bookmark = self.client.patch(
            "/api/questions/APPROVED_Q001/bookmark",
            json={"session_id": session_id, "exam_id": "set:approved_demo", "on": True},
        )
        self.assertEqual(bookmark.status_code, 200)
        self.assertTrue(bookmark.json()["on"])

        snapshot = self.client.put(
            f"/api/practice/sessions/{session_id}/snapshot",
            json={"index": 0, "answers": {"APPROVED_Q001": ["1"]}, "elapsed_ms": 2100, "flags": {"bookmarks": ["APPROVED_Q001"]}},
        )
        self.assertEqual(snapshot.status_code, 200)
        self.assertTrue((self.analytics / "practice_snapshots.jsonl").exists())

        attempt = self.client.post(
            "/api/practice/attempts",
            json={
                "event_id": "attempt_full_session_contract",
                "session_id": session_id,
                "exam_id": "set:approved_demo",
                "question_id": "APPROVED_Q001",
                "selected_choices": ["1"],
                "time_ms": 2100,
                "is_bookmarked": True,
            },
        )
        self.assertEqual(attempt.status_code, 200)
        self.client.post(
            f"/api/practice/sessions/{session_id}/finalize",
            json={"answered_count": 1, "correct_count": 1, "elapsed_ms": 2100},
        )

        result = self.client.get(f"/api/practice/sessions/{session_id}/result")
        self.assertEqual(result.status_code, 200)
        payload = result.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["score_percent"], 100)
        self.assertEqual(payload["rows"][0]["question_id"], "APPROVED_Q001")
        self.assertTrue(payload["rows"][0]["bookmarked"])


if __name__ == "__main__":
    unittest.main()
