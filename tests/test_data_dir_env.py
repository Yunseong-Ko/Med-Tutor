import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_get_app_data_dir():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    target = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "get_app_data_dir":
            target = node
            break
    if target is None:
        raise RuntimeError("get_app_data_dir not found in app.py")
    module = ast.Module(body=[target], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"os": os, "sys": sys, "Path": Path}
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace["get_app_data_dir"]


class DataDirEnvTests(unittest.TestCase):
    def test_uses_env_data_dir_when_set(self):
        fn = _load_get_app_data_dir()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "medtutor-data"
            os.environ["MEDTUTOR_DATA_DIR"] = str(target)
            try:
                resolved = fn()
            finally:
                os.environ.pop("MEDTUTOR_DATA_DIR", None)
            self.assertEqual(resolved, target)
            self.assertTrue(target.exists())

    def test_falls_back_to_cwd_without_env(self):
        fn = _load_get_app_data_dir()
        old = os.environ.pop("MEDTUTOR_DATA_DIR", None)
        try:
            resolved = fn()
        finally:
            if old is not None:
                os.environ["MEDTUTOR_DATA_DIR"] = old
        self.assertEqual(resolved, Path.cwd())


if __name__ == "__main__":
    unittest.main()
