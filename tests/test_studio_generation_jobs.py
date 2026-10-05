import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services import studio_generation_jobs as jobs


class StudioGenerationJobTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.job_dir_patcher = patch.object(jobs, "GENERATION_JOB_DIR", self.root / "jobs")
        self.job_dir_patcher.start()
        jobs._FUTURES.clear()

    def tearDown(self):
        jobs._FUTURES.clear()
        self.job_dir_patcher.stop()
        self.tempdir.cleanup()

    def request(self, *, count=3):
        return {
            "topic": "다발골수종 초기 치료",
            "set_name": "대기열 검증 세트",
            "subject": "혈액종양내과",
            "unit": "다발골수종",
            "num_questions": count,
            "difficulty": "국가고시형",
            "question_type": "clinical_case",
            "disease_concept_id": "multiple_myeloma",
            "target_axis_type": "treatment",
        }

    def fake_generator(self, lecture, **kwargs):
        item_number = int(lecture.path.stem.rsplit("_", 1)[-1])
        record = {
            "question_id": f"QUEUE_Q{item_number}",
            "problem": f"서로 다른 임상 상황 {item_number}",
            "options": ["A", "B", "C", "D", "E"],
            "answer": 1,
            "needs_review": True,
            "gen_ready": False,
        }
        output = lecture.path.with_suffix(".questions.json")
        output.write_text(json.dumps([record], ensure_ascii=False), encoding="utf-8")
        return {
            "status": "generated",
            "provider": "fake",
            "paths": {"output": str(output)},
            "_records": [record],
        }

    def test_three_questions_complete_and_archive_once(self):
        archived = []

        def archive(set_id, metadata, records):
            archived.append((set_id, metadata, records))
            path = self.root / f"{set_id}.question_set.json"
            path.write_text("{}", encoding="utf-8")
            return path

        job, duplicate = jobs.create_generation_job(self.request(), auto_submit=False)
        result = jobs.run_generation_job(job["job_id"], generator=self.fake_generator, archive_fn=archive)

        self.assertFalse(duplicate)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["success_count"], 3)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(result["progress_percent"], 100)
        self.assertEqual([item["status"] for item in result["items"]], ["done", "done", "done"])
        self.assertEqual(len(archived), 1)
        self.assertEqual(len(archived[0][2]), 3)
        self.assertEqual(archived[0][1]["set_name"], "대기열 검증 세트")
        self.assertEqual(archived[0][1]["generation_profile"], "queued_fast")
        self.assertNotIn("request", result)
        self.assertNotIn("output_path", json.dumps(result, ensure_ascii=False))

    def test_only_failed_question_is_retried(self):
        failures_left = {2}
        archived_counts = []

        def flaky_generator(lecture, **kwargs):
            item_number = int(lecture.path.stem.rsplit("_", 1)[-1])
            if item_number in failures_left:
                failures_left.remove(item_number)
                raise TimeoutError("model timed out")
            return self.fake_generator(lecture, **kwargs)

        def archive(set_id, metadata, records):
            archived_counts.append(len(records))
            path = self.root / f"{set_id}.question_set.json"
            path.write_text("{}", encoding="utf-8")
            return path

        job, _ = jobs.create_generation_job(self.request(), auto_submit=False)
        partial = jobs.run_generation_job(job["job_id"], generator=flaky_generator, archive_fn=archive)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["success_count"], 2)
        self.assertEqual(partial["failed_count"], 1)
        self.assertEqual(partial["items"][1]["attempts"], 1)

        queued = jobs.retry_failed_generation_job(job["job_id"], auto_submit=False)
        self.assertEqual(queued["status"], "retrying")
        done = jobs.run_generation_job(job["job_id"], generator=flaky_generator, archive_fn=archive)
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["success_count"], 3)
        self.assertEqual(done["items"][1]["attempts"], 2)
        self.assertEqual(done["items"][0]["attempts"], 1)
        self.assertEqual(done["items"][2]["attempts"], 1)
        self.assertEqual(archived_counts, [2, 3])

    def test_duplicate_active_request_returns_same_job(self):
        first, first_duplicate = jobs.create_generation_job(self.request(), auto_submit=False)
        second, second_duplicate = jobs.create_generation_job(self.request(), auto_submit=False)
        self.assertFalse(first_duplicate)
        self.assertTrue(second_duplicate)
        self.assertEqual(first["job_id"], second["job_id"])

    def test_saved_media_ids_are_forwarded_to_each_item(self):
        kwargs = jobs._generation_kwargs(
            {"topic": "흉부 영상", "selected_media_ids": ["media_1"]},
            "다른 임상 장면",
        )
        self.assertEqual(kwargs["selected_media_ids"], ["media_1"])
        self.assertEqual(kwargs["image_policy"], "clinical_visuals")
        self.assertFalse(kwargs["archive_result"])

    def test_distinct_item_intents_generate_into_one_review_set(self):
        captured = []
        archived = []
        request = {
            "topic": "혈액종양내과 교수 선택 출제 의도 3개",
            "set_name": "교수 배정 3문항",
            "subject": "혈액종양내과",
            "unit": "임상의학종합평가",
            "num_questions": 3,
            "difficulty": "국가고시형",
            "ontology_review_policy": "faculty_draft",
            "item_intents": [
                {
                    "intent_id": "intent:mm-treatment",
                    "intent_title": "다발골수종 · 치료",
                    "topic": "다발골수종",
                    "unit": "다발골수종",
                    "teaching_points": "초기 치료를 선택한다.",
                    "disease_concept_id": "multiple_myeloma",
                    "target_axis_type": "treatment",
                    "question_type": "clinical_case",
                    "reasoning_hops": 2,
                    "faculty_question_intent": {"assessment_claim": {"task": "first_line_treatment"}},
                },
                {
                    "intent_id": "intent:aml-diagnosis",
                    "intent_title": "급성골수성백혈병 · 진단",
                    "topic": "급성골수성백혈병",
                    "unit": "급성골수성백혈병",
                    "teaching_points": "진단검사를 선택한다.",
                    "disease_concept_id": "acute_myeloid_leukemia",
                    "target_axis_type": "diagnosis",
                    "question_type": "clinical_case",
                    "reasoning_hops": 2,
                    "faculty_question_intent": {"assessment_claim": {"task": "test_selection"}},
                },
                {
                    "intent_id": "intent:tls-management",
                    "intent_title": "종양용해증후군 · 초기 처치",
                    "topic": "종양용해증후군",
                    "unit": "종양용해증후군",
                    "teaching_points": "초기 처치를 선택한다.",
                    "disease_concept_id": "tumor_lysis_syndrome",
                    "target_axis_type": "treatment",
                    "question_type": "clinical_case",
                    "reasoning_hops": 2,
                    "faculty_question_intent": {"assessment_claim": {"task": "immediate_management"}},
                },
            ],
        }

        def generator(lecture, **kwargs):
            captured.append(
                {
                    "text": lecture.path.read_text(encoding="utf-8"),
                    "concept": kwargs["grounding_concept_id"],
                    "axis": kwargs["target_axis_type"],
                }
            )
            return self.fake_generator(lecture, **kwargs)

        def archive(set_id, metadata, records):
            archived.append((set_id, metadata, records))
            path = self.root / f"{set_id}.question_set.json"
            path.write_text("{}", encoding="utf-8")
            return path

        job, _ = jobs.create_generation_job(request, auto_submit=False)
        result = jobs.run_generation_job(job["job_id"], generator=generator, archive_fn=archive)

        self.assertEqual(result["status"], "done")
        self.assertEqual([item["intent_id"] for item in result["items"]], [
            "intent:mm-treatment", "intent:aml-diagnosis", "intent:tls-management",
        ])
        self.assertEqual([item["concept"] for item in captured], [
            "multiple_myeloma", "acute_myeloid_leukemia", "tumor_lysis_syndrome",
        ])
        self.assertIn("초기 치료를 선택한다", captured[0]["text"])
        self.assertIn("진단검사를 선택한다", captured[1]["text"])
        self.assertEqual(len(archived), 1)
        self.assertEqual(len(archived[0][2]), 3)
        self.assertEqual(len(archived[0][1]["faculty_item_intents"]), 3)
        for record, expected_intent in zip(archived[0][2], [
            "intent:mm-treatment", "intent:aml-diagnosis", "intent:tls-management",
        ]):
            self.assertEqual(record["faculty_intent_id"], expected_intent)
            self.assertTrue(record["needs_review"])
            self.assertFalse(record["gen_ready"])

    def test_only_item_generation_released_claims_enter_item_source(self):
        job, _ = jobs.create_generation_job(self.request(count=1), auto_submit=False)
        raw = jobs.load_generation_job(job["job_id"])
        approved = [{
            "claim_id": "kr-claim:approved",
            "object_text": "표준 위험도 평가 뒤 치료 전략을 선택한다.",
            "population": "다발골수종 성인",
            "clinical_axis": "treatment",
            "source_title": "국내 진료지침",
            "page": 11,
        }]
        with patch.object(jobs, "list_valid_released_claims", return_value=approved) as released:
            upload, _variant = jobs._build_item_source(raw, 1)
        text = upload.path.read_text(encoding="utf-8")
        released.assert_called_once_with(
            surface="item_generation",
            concept_ids=["multiple_myeloma"],
        )
        self.assertIn("문항 생성용으로 release된", text)
        self.assertIn("kr-claim:approved", text)
        self.assertIn("다발골수종 성인", text)

    def test_recoverable_running_job_can_be_resumed(self):
        job, _ = jobs.create_generation_job(self.request(count=1), auto_submit=False)
        raw = jobs.load_generation_job(job["job_id"])
        raw["status"] = "running"
        raw["items"][0]["status"] = "running"
        jobs._save_job_unlocked(raw)

        public = jobs.get_generation_job(job["job_id"])
        self.assertTrue(public["recoverable"])
        resumed = jobs.resume_generation_job(job["job_id"], auto_submit=False)
        self.assertEqual(resumed["status"], "queued")
        self.assertEqual(resumed["items"][0]["status"], "queued")


if __name__ == "__main__":
    unittest.main()
