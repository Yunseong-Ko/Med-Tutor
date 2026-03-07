import tempfile
import unittest
import importlib.util
from pathlib import Path

APP_ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")
MODULE_PATH = APP_ROOT / "src" / "repositories" / "json_store.py"
_spec = importlib.util.spec_from_file_location("json_store_repo", MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
load_json_file = _mod.load_json_file
save_json_file = _mod.save_json_file


class JsonStoreRepositoryTests(unittest.TestCase):
    def test_load_json_returns_default_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "missing.json"
            out = load_json_file(p, {"text": [], "cloze": []})
            self.assertEqual(out, {"text": [], "cloze": []})

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "store.json"
            payload = {"a": 1, "b": ["x", "y"]}
            self.assertTrue(save_json_file(p, payload))
            out = load_json_file(p, {})
            self.assertEqual(out, payload)

    def test_type_mismatch_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "store.json"
            self.assertTrue(save_json_file(p, ["not", "dict"]))
            out = load_json_file(p, {"k": "v"})
            self.assertEqual(out, {"k": "v"})


if __name__ == "__main__":
    unittest.main()
