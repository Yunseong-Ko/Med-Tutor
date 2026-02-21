import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


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
    namespace = {}
    namespace.update(extra or {})
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class SupabaseRequiredModeTests(unittest.TestCase):
    def test_is_supabase_required_default_true(self):
        import os

        prev = os.environ.get("AXIOMA_REQUIRE_SUPABASE")
        if "AXIOMA_REQUIRE_SUPABASE" in os.environ:
            del os.environ["AXIOMA_REQUIRE_SUPABASE"]
        try:
            ns = _load_functions(["is_supabase_required"], {"os": os})
            self.assertTrue(ns["is_supabase_required"]())
        finally:
            if prev is not None:
                os.environ["AXIOMA_REQUIRE_SUPABASE"] = prev

    def test_is_supabase_required_false_values(self):
        import os

        ns = _load_functions(["is_supabase_required"], {"os": os})
        prev = os.environ.get("AXIOMA_REQUIRE_SUPABASE")
        try:
            os.environ["AXIOMA_REQUIRE_SUPABASE"] = "0"
            self.assertFalse(ns["is_supabase_required"]())
            os.environ["AXIOMA_REQUIRE_SUPABASE"] = "false"
            self.assertFalse(ns["is_supabase_required"]())
        finally:
            if prev is None:
                del os.environ["AXIOMA_REQUIRE_SUPABASE"]
            else:
                os.environ["AXIOMA_REQUIRE_SUPABASE"] = prev

    def test_authenticate_blocks_without_supabase_when_required(self):
        import os

        ns = _load_functions(
            ["is_supabase_enabled", "is_supabase_required", "authenticate_user_account"],
            {"os": os, "st": SimpleNamespace(session_state={}), "SUPABASE_URL": "", "SUPABASE_ANON_KEY": ""},
        )
        prev = os.environ.get("AXIOMA_REQUIRE_SUPABASE")
        try:
            os.environ["AXIOMA_REQUIRE_SUPABASE"] = "1"
            ok, message = ns["authenticate_user_account"]("user", "pw")
            self.assertFalse(ok)
            self.assertIn("Supabase", message)
        finally:
            if prev is None:
                del os.environ["AXIOMA_REQUIRE_SUPABASE"]
            else:
                os.environ["AXIOMA_REQUIRE_SUPABASE"] = prev


if __name__ == "__main__":
    unittest.main()
