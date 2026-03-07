import importlib.util
import unittest
from pathlib import Path


APP_ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")
MODULE_PATH = APP_ROOT / "src" / "services" / "generation_pipeline.py"
_spec = importlib.util.spec_from_file_location("generation_pipeline_service", MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
reconcile_generation_queue_items = _mod.reconcile_generation_queue_items


class GenerationPipelineServiceTests(unittest.TestCase):
    def test_reconcile_done_updates_counts_and_notice(self):
        queue = [
            {"id": "q1", "source_name": "a.pdf", "mode": "mcq", "subject": "S", "unit": "U", "quality_filter": True, "min_length": 30}
        ]
        async_job = {"queue_id": "q1", "status": "done", "result": [{"problem": "x"}]}

        calls = []

        def fake_add(result, mode, subject, unit, quality_filter, min_length):
            calls.append((result, mode, subject, unit, quality_filter, min_length))
            return 1

        items, next_job, notices = reconcile_generation_queue_items(
            items=queue,
            async_job=async_job,
            add_questions_fn=fake_add,
            drop_payload_fn=lambda item: item,
            now_iso="2026-03-08T00:00:00+00:00",
            default_quality_filter=True,
            default_min_length=30,
            mode_mcq="mcq",
        )

        self.assertIsNone(next_job)
        self.assertEqual(items[0]["status"], "done")
        self.assertEqual(items[0]["result_count"], 1)
        self.assertEqual(items[0]["saved_count"], 1)
        self.assertTrue(notices)
        self.assertEqual(len(calls), 1)

    def test_reconcile_when_queue_id_missing_clears_async_job(self):
        queue = [{"id": "q1", "source_name": "a.pdf"}]
        async_job = {"queue_id": "q2", "status": "done", "result": [{"problem": "x"}]}

        items, next_job, notices = reconcile_generation_queue_items(
            items=queue,
            async_job=async_job,
            add_questions_fn=lambda *args, **kwargs: 0,
            drop_payload_fn=lambda item: item,
            now_iso="2026-03-08T00:00:00+00:00",
            mode_mcq="mcq",
        )

        self.assertEqual(items, queue)
        self.assertIsNone(next_job)
        self.assertEqual(notices, [])

    def test_reconcile_cancelled_sets_cancel_state(self):
        queue = [{"id": "q1", "source_name": "a.pdf"}]
        async_job = {"queue_id": "q1", "status": "cancelled", "error": "stop"}

        items, next_job, notices = reconcile_generation_queue_items(
            items=queue,
            async_job=async_job,
            add_questions_fn=lambda *args, **kwargs: 0,
            drop_payload_fn=lambda item: item,
            now_iso="2026-03-08T00:00:00+00:00",
            mode_mcq="mcq",
        )

        self.assertEqual(items[0]["status"], "cancelled")
        self.assertEqual(items[0]["error"], "stop")
        self.assertIsNone(next_job)
        self.assertTrue(notices)


if __name__ == "__main__":
    unittest.main()
