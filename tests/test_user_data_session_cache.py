import ast
import re
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


class _StStub:
    def __init__(self):
        self.session_state = {}


def _load_cache_helpers():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = {
        "sanitize_user_id",
        "_user_data_cache_key",
        "_get_user_data_cache",
        "_set_user_data_cache",
        "_get_or_load_user_data",
    }
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(body) != len(wanted):
        missing = wanted - {node.name for node in body}
        raise RuntimeError(f"Missing functions in app.py: {sorted(missing)}")

    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "re": re,
        "st": _StStub(),
        "get_current_user_id": lambda: "guest",
        "use_remote_user_store": lambda: False,
    }
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class UserDataSessionCacheTests(unittest.TestCase):
    def test_get_or_load_calls_loader_once_when_cached(self):
        ns = _load_cache_helpers()
        calls = {"count": 0}

        def loader():
            calls["count"] += 1
            return {"value": calls["count"]}

        first = ns["_get_or_load_user_data"]("questions", loader, user_id="u1")
        second = ns["_get_or_load_user_data"]("questions", loader, user_id="u1")

        self.assertEqual(calls["count"], 1)
        self.assertEqual(first, second)

    def test_get_or_load_force_true_refreshes_cache(self):
        ns = _load_cache_helpers()
        calls = {"count": 0}

        def loader():
            calls["count"] += 1
            return {"value": calls["count"]}

        ns["_get_or_load_user_data"]("questions", loader, user_id="u2")
        refreshed = ns["_get_or_load_user_data"]("questions", loader, user_id="u2", force=True)

        self.assertEqual(calls["count"], 2)
        self.assertEqual(refreshed["value"], 2)

    def test_cache_key_uses_remote_scope_when_remote_store_enabled(self):
        ns = _load_cache_helpers()
        ns["st"].session_state["auth_user_id"] = "user@example.com"
        ns["use_remote_user_store"] = lambda: True
        key = ns["_user_data_cache_key"]("questions")
        self.assertEqual(key, "questions:remote:user_example.com")


if __name__ == "__main__":
    unittest.main()
