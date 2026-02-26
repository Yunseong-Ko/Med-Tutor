import ast
import hashlib
import io
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


class _StStub:
    def __init__(self):
        self.session_state = {}


def _load_prewarm_helpers():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = {
        "build_upload_signature",
        "make_uploaded_file_from_bytes",
        "_prewarm_cache_key",
        "get_generation_prewarm_text",
        "set_generation_prewarm_text",
        "get_generation_prewarm_error",
        "set_generation_prewarm_error",
        "clear_generation_prewarm_error",
    }
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(body) != len(wanted):
        missing = wanted - {node.name for node in body}
        raise RuntimeError(f"Missing functions in app.py: {sorted(missing)}")
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "Path": Path,
        "hashlib": hashlib,
        "io": io,
        "st": _StStub(),
    }
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class GenerationPrewarmCacheTests(unittest.TestCase):
    def test_signature_is_stable_and_changes_with_content(self):
        ns = _load_prewarm_helpers()
        a1 = ns["build_upload_signature"]("sample.pdf", b"abc")
        a2 = ns["build_upload_signature"]("sample.pdf", b"abc")
        b1 = ns["build_upload_signature"]("sample.pdf", b"abcd")
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1, b1)

    def test_set_text_clears_error_for_same_key(self):
        ns = _load_prewarm_helpers()
        sig = ns["build_upload_signature"]("x.pdf", b"x")
        ns["set_generation_prewarm_error"]("raw", sig, "failed")
        self.assertEqual(ns["get_generation_prewarm_error"]("raw", sig), "failed")
        ns["set_generation_prewarm_text"]("raw", sig, "hello")
        self.assertEqual(ns["get_generation_prewarm_text"]("raw", sig), "hello")
        self.assertIsNone(ns["get_generation_prewarm_error"]("raw", sig))

    def test_uploaded_proxy_preserves_name_and_bytes(self):
        ns = _load_prewarm_helpers()
        proxy = ns["make_uploaded_file_from_bytes"]("demo.docx", b"xyz")
        self.assertEqual(getattr(proxy, "name", ""), "demo.docx")
        self.assertEqual(proxy.read(), b"xyz")


if __name__ == "__main__":
    unittest.main()
