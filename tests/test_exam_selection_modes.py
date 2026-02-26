import ast
import unittest
from pathlib import Path

APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_namespace(function_names, extra=None):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = set(function_names)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(selected) != len(wanted):
        missing = sorted(wanted - {n.name for n in selected})
        raise RuntimeError(f"required functions not found in app.py: {missing}")
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "random": __import__("random"),
    }
    namespace.update(extra or {})
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class ExamSelectionModeTests(unittest.TestCase):
    def test_select_exam_questions_balanced_proportional(self):
        ns = _load_namespace(["get_unit_name", "_exam_group_key", "select_exam_questions_balanced"])
        qs = []
        for i in range(8):
            qs.append({"id": f"A{i}", "subject": "A", "unit": "u1"})
        for i in range(2):
            qs.append({"id": f"B{i}", "subject": "B", "unit": "u1"})

        out = ns["select_exam_questions_balanced"](
            qs,
            5,
            distribution_mode="비례(보유 문항 기준)",
            group_mode="분과",
            random_seed=7,
        )
        self.assertEqual(len(out), 5)
        count_a = sum(1 for q in out if q["subject"] == "A")
        count_b = sum(1 for q in out if q["subject"] == "B")
        self.assertEqual((count_a, count_b), (4, 1))

    def test_select_exam_questions_balanced_equal(self):
        ns = _load_namespace(["get_unit_name", "_exam_group_key", "select_exam_questions_balanced"])
        qs = []
        for i in range(9):
            qs.append({"id": f"A{i}", "subject": "A", "unit": "u1"})
        for i in range(9):
            qs.append({"id": f"B{i}", "subject": "B", "unit": "u1"})

        out = ns["select_exam_questions_balanced"](
            qs,
            6,
            distribution_mode="균등(선택 그룹 기준)",
            group_mode="분과",
            random_seed=11,
        )
        self.assertEqual(len(out), 6)
        count_a = sum(1 for q in out if q["subject"] == "A")
        count_b = sum(1 for q in out if q["subject"] == "B")
        self.assertEqual((count_a, count_b), (3, 3))

    def test_select_learning_session_questions_browse(self):
        ns = _load_namespace(["get_unit_name", "select_learning_session_questions"])
        qs = [
            {"id": "3", "subject": "B", "unit": "u2", "problem": "p3"},
            {"id": "1", "subject": "A", "unit": "u1", "problem": "p1"},
            {"id": "2", "subject": "A", "unit": "u1", "problem": "p2"},
        ]
        out = ns["select_learning_session_questions"](qs, learning_mode="탐색형(단원 전체)", num_questions=2)
        self.assertEqual([x["id"] for x in out], ["1", "2", "3"])


if __name__ == "__main__":
    unittest.main()
