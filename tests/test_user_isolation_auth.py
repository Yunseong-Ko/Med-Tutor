import ast
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}


def _load_functions(function_names, base_dir):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in function_names]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    fake_st = _FakeStreamlit()
    namespace = {
        "os": os,
        "re": __import__("re"),
        "json": json,
        "hashlib": __import__("hashlib"),
        "datetime": datetime,
        "timezone": timezone,
        "Path": Path,
        "DATA_DIR": Path(base_dir),
        "AUTH_USERS_FILE": str(Path(base_dir) / "auth_users.json"),
        "st": fake_st,
    }
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class UserIsolationAuthTests(unittest.TestCase):
    def test_user_scoped_paths_are_separated(self):
        names = {
            "sanitize_user_id",
            "get_current_user_id",
            "get_user_data_dir",
            "get_question_bank_file",
            "get_exam_history_file",
            "get_user_settings_file",
        }
        with tempfile.TemporaryDirectory() as td:
            ns = _load_functions(names, td)
            q_alice = Path(ns["get_question_bank_file"]("alice"))
            q_bob = Path(ns["get_question_bank_file"]("bob"))
            self.assertNotEqual(q_alice, q_bob)
            self.assertIn("/users/alice/", str(q_alice).replace("\\", "/"))
            self.assertIn("/users/bob/", str(q_bob).replace("\\", "/"))

            q_alice.write_text(json.dumps({"text": [{"id": "a"}], "cloze": []}, ensure_ascii=False), encoding="utf-8")
            q_bob.write_text(json.dumps({"text": [{"id": "b"}], "cloze": []}, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(json.loads(q_alice.read_text(encoding="utf-8"))["text"][0]["id"], "a")
            self.assertEqual(json.loads(q_bob.read_text(encoding="utf-8"))["text"][0]["id"], "b")

    def test_register_and_authenticate_user(self):
        names = {
            "sanitize_user_id",
            "get_current_user_id",
            "get_user_data_dir",
            "load_auth_users",
            "save_auth_users",
            "_hash_password",
            "register_user_account",
            "authenticate_user_account",
        }
        with tempfile.TemporaryDirectory() as td:
            ns = _load_functions(names, td)
            ok, msg = ns["register_user_account"]("alice", "secret12")
            self.assertTrue(ok, msg)

            ok, user_id = ns["authenticate_user_account"]("alice", "secret12")
            self.assertTrue(ok)
            self.assertEqual(user_id, "alice")

            ok, _ = ns["authenticate_user_account"]("alice", "wrong-password")
            self.assertFalse(ok)

            ok, _ = ns["register_user_account"]("alice", "secret12")
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
