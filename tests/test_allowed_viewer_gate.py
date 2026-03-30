import ast
import os
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}


def _load_functions(names):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    found = {node.name for node in body}
    missing = set(names) - found
    if missing:
        raise RuntimeError(f"Missing functions: {sorted(missing)}")
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"os": os, "st": _FakeStreamlit()}
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class AllowedViewerGateTests(unittest.TestCase):
    def test_default_allowed_email_is_specific_account(self):
        ns = _load_functions({"get_allowed_viewer_emails"})
        previous = os.environ.pop("AXIOMA_ALLOWED_VIEWER_EMAILS", None)
        try:
            allowed = ns["get_allowed_viewer_emails"]()
            self.assertEqual(allowed, {"dbstjdrh@pusan.ac.kr"})
        finally:
            if previous is not None:
                os.environ["AXIOMA_ALLOWED_VIEWER_EMAILS"] = previous

    def test_is_allowed_viewer_checks_explicit_identifier(self):
        ns = _load_functions({"get_allowed_viewer_emails", "is_allowed_viewer"})
        previous = os.environ.get("AXIOMA_ALLOWED_VIEWER_EMAILS")
        os.environ["AXIOMA_ALLOWED_VIEWER_EMAILS"] = "a@example.com,b@example.com"
        try:
            self.assertTrue(ns["is_allowed_viewer"]("a@example.com"))
            self.assertFalse(ns["is_allowed_viewer"]("c@example.com"))
        finally:
            if previous is None:
                os.environ.pop("AXIOMA_ALLOWED_VIEWER_EMAILS", None)
            else:
                os.environ["AXIOMA_ALLOWED_VIEWER_EMAILS"] = previous


if __name__ == "__main__":
    unittest.main()
