import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_extract_text_from_hwp():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    fn_node = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "extract_text_from_hwp":
            fn_node = node
            break
    if fn_node is None:
        raise RuntimeError("extract_text_from_hwp not found in app.py")

    module = ast.Module(body=[fn_node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "tempfile": tempfile,
        "subprocess": subprocess,
        "os": os,
        "re": re,
        "ET": ET,
        "shutil": __import__("shutil"),
        "sys": sys,
        "zipfile": zipfile,
    }
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace["extract_text_from_hwp"]


class _UploadedFileStub:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


class HwpFallbackTest(unittest.TestCase):
    def test_relaxng_failure_falls_back_to_hwp5txt_output(self):
        extract_text_from_hwp = _load_extract_text_from_hwp()
        placeholder_text = "<표>\n<표>\n<표>\n"

        def fake_run(cmd, capture_output=True, text=True):
            if cmd[0] == "hwp5txt":
                return subprocess.CompletedProcess(cmd, 0, placeholder_text, "")
            if cmd[0] == "hwp5odt":
                return subprocess.CompletedProcess(cmd, 1, "", "ValidationFailed: RelaxNG")
            raise AssertionError(f"Unexpected command: {cmd}")

        def fake_which(name):
            if name in {"hwp5txt", "hwp5odt"}:
                return f"/usr/bin/{name}"
            return None

        with patch("subprocess.run", side_effect=fake_run), patch("shutil.which", side_effect=fake_which):
            output = extract_text_from_hwp(_UploadedFileStub(b"dummy"))

        self.assertEqual(output, placeholder_text)


if __name__ == "__main__":
    unittest.main()
