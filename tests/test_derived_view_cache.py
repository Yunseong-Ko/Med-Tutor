import ast
import json
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
        "_data_revision_key",
        "_get_data_revision",
        "_bump_data_revision",
        "get_cached_derived_view_value",
    }
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(body) != len(wanted):
        missing = wanted - {node.name for node in body}
        raise RuntimeError(f"Missing functions in app.py: {sorted(missing)}")
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "json": json,
        "re": re,
        "st": _StStub(),
        "use_remote_user_store": lambda: False,
        "get_current_user_id": lambda: "guest",
    }
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class DerivedViewCacheTests(unittest.TestCase):
    def test_cached_value_reuses_builder_until_revision_changes(self):
        ns = _load_cache_helpers()
        calls = {"count": 0}

        def builder():
            calls["count"] += 1
            return {"value": calls["count"]}

        first = ns["get_cached_derived_view_value"]("questions", "home_summary", {}, builder, user_id="tester")
        second = ns["get_cached_derived_view_value"]("questions", "home_summary", {}, builder, user_id="tester")

        self.assertEqual(first, {"value": 1})
        self.assertEqual(second, {"value": 1})
        self.assertEqual(calls["count"], 1)

        ns["_bump_data_revision"]("questions", user_id="tester")
        third = ns["get_cached_derived_view_value"]("questions", "home_summary", {}, builder, user_id="tester")

        self.assertEqual(third, {"value": 2})
        self.assertEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
