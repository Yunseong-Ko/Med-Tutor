import ast
import random
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_helper(name):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if not body:
        raise RuntimeError(f"Missing function in app.py: {name}")
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"random": random}
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace[name]


class WaitingReviewHelperTests(unittest.TestCase):
    def test_select_generation_waiting_review_candidates_prioritizes_bookmarked_and_wrong(self):
        helper = _load_helper("select_generation_waiting_review_candidates")
        questions = [
            {"id": "q1", "type": "mcq", "options": ["a"], "stats": {"wrong": 0, "right": 0}, "bookmarked": False},
            {"id": "q2", "type": "mcq", "options": ["a"], "stats": {"wrong": 3, "right": 1}, "bookmarked": False},
            {"id": "q3", "type": "mcq", "options": ["a"], "stats": {"wrong": 1, "right": 0}, "bookmarked": True},
            {"id": "q4", "type": "cloze", "response_type": "essay", "stats": {"wrong": 5, "right": 0}, "bookmarked": True},
        ]
        picked = helper(questions, limit=2)
        picked_ids = [item["id"] for item in picked]
        self.assertEqual(picked_ids, ["q3", "q2"])


if __name__ == "__main__":
    unittest.main()
