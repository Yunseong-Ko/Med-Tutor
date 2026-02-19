import ast
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_export_helpers():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = {
        "get_unit_name",
        "filter_questions_by_subject",
        "filter_questions_by_subject_unit_hierarchy",
        "collect_export_questions",
    }
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(nodes) != len(wanted):
        raise RuntimeError("required export helper functions not found in app.py")
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    import random as _random
    namespace["random"] = _random
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace["collect_export_questions"]


class ExportSelectionRandomizationTests(unittest.TestCase):
    def test_export_ui_has_subject_selector(self):
        text = Path(APP_PATH).read_text(encoding="utf-8")
        self.assertIn("내보낼 분과 선택", text)
        self.assertIn("export_subjects", text)

    def test_collects_all_selected_subjects_when_include_all_units(self):
        fn = _load_export_helpers()
        questions = [
            {"id": "1", "subject": "성장발달노화", "unit": "A"},
            {"id": "2", "subject": "성장발달노화", "unit": "B"},
            {"id": "3", "subject": "생식계", "unit": "X"},
            {"id": "4", "subject": "순환기", "unit": "Y"},
        ]
        result = fn(
            questions,
            selected_subjects=["성장발달노화", "생식계"],
            unit_filter_by_subject={"성장발달노화": ["A"], "생식계": ["X"]},
            include_all_units=True,
            randomize=False,
        )
        self.assertEqual([q["id"] for q in result], ["1", "2", "3"])

    def test_randomize_mode_is_deterministic_with_seed(self):
        fn = _load_export_helpers()
        questions = [
            {"id": "1", "subject": "성장발달노화", "unit": "A"},
            {"id": "2", "subject": "성장발달노화", "unit": "B"},
            {"id": "3", "subject": "생식계", "unit": "X"},
        ]
        r1 = fn(
            questions,
            selected_subjects=["성장발달노화", "생식계"],
            unit_filter_by_subject={},
            include_all_units=True,
            randomize=True,
            random_seed=42,
        )
        r2 = fn(
            questions,
            selected_subjects=["성장발달노화", "생식계"],
            unit_filter_by_subject={},
            include_all_units=True,
            randomize=True,
            random_seed=42,
        )
        self.assertEqual([q["id"] for q in r1], [q["id"] for q in r2])
        self.assertEqual([q["id"] for q in r1], ["2", "1", "3"])


if __name__ == "__main__":
    unittest.main()
