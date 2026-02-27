import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_functions(names, extra=None):
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
    }
    namespace.update(extra or {})
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class _PendingFuture:
    def done(self):
        return False


class _DoneFuture:
    def __init__(self, value):
        self._value = value

    def done(self):
        return True

    def result(self):
        return self._value


class _ErrorFuture:
    def done(self):
        return True

    def result(self):
        raise RuntimeError("boom")


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))
        return _DoneFuture([{"type": "mcq"}])


class GenerationAsyncJobTests(unittest.TestCase):
    def test_update_running_job_keeps_running_status(self):
        ns = _load_functions(["update_generation_async_job_state"])
        job = {"status": "running", "future": _PendingFuture()}
        updated = ns["update_generation_async_job_state"](job)
        self.assertEqual(updated.get("status"), "running")
        self.assertNotIn("result", updated)

    def test_update_done_job_sets_result_and_done(self):
        ns = _load_functions(["update_generation_async_job_state"])
        job = {"status": "running", "future": _DoneFuture([{"id": "q1"}])}
        updated = ns["update_generation_async_job_state"](job)
        self.assertEqual(updated.get("status"), "done")
        self.assertEqual(updated.get("result"), [{"id": "q1"}])
        self.assertIn("completed_at", updated)

    def test_update_job_error_sets_error_status(self):
        ns = _load_functions(["update_generation_async_job_state"])
        job = {"status": "running", "future": _ErrorFuture()}
        updated = ns["update_generation_async_job_state"](job)
        self.assertEqual(updated.get("status"), "error")
        self.assertIn("boom", updated.get("error", ""))

    def test_start_generation_async_job_submits_with_progress_off(self):
        fake_executor = _FakeExecutor()

        def _fake_get_generation_executor():
            return fake_executor

        def _fake_generate_content_in_chunks(*args, **kwargs):
            return []

        ns = _load_functions(
            ["start_generation_async_job"],
            extra={
                "get_generation_executor": _fake_get_generation_executor,
                "generate_content_in_chunks": _fake_generate_content_in_chunks,
                "uuid": __import__("uuid"),
            },
        )

        job = ns["start_generation_async_job"](
            raw_text="abc",
            mode="mode",
            ai_model="model",
            num_items=5,
            chunk_size=8000,
            overlap=500,
            api_key="k1",
            openai_api_key="k2",
            style_text="style",
            subject="S",
            unit="U",
        )

        self.assertEqual(job.get("status"), "running")
        self.assertEqual(job.get("num_items"), 5)
        self.assertEqual(len(fake_executor.calls), 1)
        _, args = fake_executor.calls[0]
        self.assertEqual(args[0], "abc")
        self.assertEqual(args[-3], False)
        self.assertIsNone(args[-2])
        self.assertIsNone(args[-1])

    def test_start_generation_async_job_passes_runtime_context(self):
        fake_executor = _FakeExecutor()

        def _fake_get_generation_executor():
            return fake_executor

        def _fake_generate_content_in_chunks(*args, **kwargs):
            return []

        ns = _load_functions(
            ["start_generation_async_job"],
            extra={
                "get_generation_executor": _fake_get_generation_executor,
                "generate_content_in_chunks": _fake_generate_content_in_chunks,
                "uuid": __import__("uuid"),
            },
        )

        ns["start_generation_async_job"](
            raw_text="abc",
            mode="mode",
            ai_model="model",
            num_items=5,
            chunk_size=8000,
            overlap=500,
            api_key="k1",
            openai_api_key="k2",
            style_text="style",
            subject="S",
            unit="U",
            runtime_context={"gemini_model_id": "gemini-2.5-flash", "audit_user_id": "u1"},
        )

        _, args = fake_executor.calls[0]
        self.assertEqual(args[-3], False)
        self.assertEqual(args[-2], "gemini-2.5-flash")
        self.assertEqual(args[-1], "u1")


if __name__ == "__main__":
    unittest.main()
