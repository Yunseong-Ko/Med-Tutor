import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


class _SessionState(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


def _load_namespace(names, extra=None):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = set(names)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(selected) != len(wanted):
        missing = sorted(wanted - {node.name for node in selected})
        raise RuntimeError(f"required functions not found in app.py: {missing}")
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "datetime": datetime,
        "timezone": timezone,
        "uuid": __import__("uuid"),
        "MODE_MCQ": "mcq",
        "st": __import__("types").SimpleNamespace(session_state=_SessionState()),
    }
    namespace.update(extra or {})
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class GenerationQueueHelperTests(unittest.TestCase):
    def test_build_generation_queue_item_sets_required_fields(self):
        ns = _load_namespace(["build_generation_queue_item"])
        item = ns["build_generation_queue_item"](
            source_name="a.pdf",
            source_signature="sig123",
            raw_text="abc",
            style_text="",
            mode="mode",
            num_items=12,
            subject="S",
            unit="U",
            ai_model="M",
            chunk_size=8000,
            overlap=500,
            quality_filter=True,
            min_length=20,
        )
        self.assertEqual(item["status"], "queued")
        self.assertEqual(item["source_name"], "a.pdf")
        self.assertEqual(item["source_signature"], "sig123")
        self.assertEqual(item["num_items"], 12)
        self.assertEqual(item["subject"], "S")
        self.assertEqual(item["unit"], "U")
        self.assertIn("id", item)

    def test_is_duplicate_generation_queue_item(self):
        ns = _load_namespace(["is_duplicate_generation_queue_item"])
        queue = [
            {
                "status": "queued",
                "source_signature": "s1",
                "mode": "m",
                "num_items": 10,
                "subject": "A",
                "unit": "U1",
            },
            {
                "status": "done",
                "source_signature": "s1",
                "mode": "m",
                "num_items": 10,
                "subject": "A",
                "unit": "U1",
            },
        ]
        self.assertTrue(
            ns["is_duplicate_generation_queue_item"](
                queue, "s1", "m", 10, "A", "U1"
            )
        )
        self.assertFalse(
            ns["is_duplicate_generation_queue_item"](
                queue, "s2", "m", 10, "A", "U1"
            )
        )

    def test_remove_generation_queue_job(self):
        ns = _load_namespace(["remove_generation_queue_job"])
        changed, out = ns["remove_generation_queue_job"](
            [{"id": "1"}, {"id": "2"}],
            "2",
        )
        self.assertTrue(changed)
        self.assertEqual(out, [{"id": "1"}])

    def test_start_next_generation_queue_job_if_idle(self):
        calls = []

        def _fake_start_generation_async_job(**kwargs):
            calls.append(kwargs)
            return {"status": "running", "future": object()}

        ns = _load_namespace(
            ["start_next_generation_queue_job_if_idle"],
            extra={
                "start_generation_async_job": _fake_start_generation_async_job,
            },
        )
        queue = [
            {"id": "q1", "status": "queued", "raw_text": "x", "num_items": 3, "subject": "S", "unit": "U", "mode": "m", "ai_model": "a", "chunk_size": 8000, "overlap": 500},
            {"id": "q2", "status": "queued", "raw_text": "y"},
        ]
        updated, started = ns["start_next_generation_queue_job_if_idle"](queue, api_key="k", openai_api_key="ok")
        self.assertTrue(started)
        self.assertEqual(updated[0]["status"], "running")
        self.assertEqual(len(calls), 1)
        self.assertEqual(ns["st"].session_state["generation_async_job"]["queue_id"], "q1")

    def test_revive_stale_running_queue_items(self):
        ns = _load_namespace(["revive_stale_running_queue_items"])
        ns["st"].session_state["generation_async_job"] = None
        queue = [{"id": "q1", "status": "running", "started_at": "x"}, {"id": "q2", "status": "queued"}]
        updated, changed = ns["revive_stale_running_queue_items"](queue)
        self.assertTrue(changed)
        self.assertEqual(updated[0]["status"], "queued")
        self.assertNotIn("started_at", updated[0])


if __name__ == "__main__":
    unittest.main()
