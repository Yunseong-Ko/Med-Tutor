import ast
import hashlib
import re
import unittest
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_daily_helpers():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = {
        "normalize_daily_dx_text",
        "get_daily_dx_answer_text",
        "score_daily_dx_candidate",
        "select_daily_dx_question",
        "grade_daily_dx_guess",
        "build_daily_dx_share_text",
        "build_daily_dx_anki_tag",
    }
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(body) != len(wanted):
        missing = wanted - {node.name for node in body}
        raise RuntimeError(f"Missing functions in app.py: {sorted(missing)}")
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "datetime": datetime,
        "hashlib": hashlib,
        "re": re,
        "SequenceMatcher": SequenceMatcher,
        "REVIEW_STATUS_ASSIGNED": "assigned",
        "REVIEW_STATUS_APPROVED": "approved",
    }
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class DailyDxHelperTests(unittest.TestCase):
    def test_answer_text_uses_correct_mcq_option(self):
        ns = _load_daily_helpers()
        item = {"type": "mcq", "options": ["A", "B diagnosis", "C"], "answer": 2}
        self.assertEqual(ns["get_daily_dx_answer_text"](item), "B diagnosis")

    def test_grade_accepts_close_or_contained_answer(self):
        ns = _load_daily_helpers()
        self.assertTrue(ns["grade_daily_dx_guess"]("간경변", "간경변증"))
        self.assertTrue(ns["grade_daily_dx_guess"]("liver cirrhosis", "Liver cirrhosis"))
        self.assertFalse(ns["grade_daily_dx_guess"]("폐렴", "간경변증"))

    def test_select_daily_dx_question_prefers_case_like_items(self):
        ns = _load_daily_helpers()
        items = [
            {"id": "basic", "type": "mcq", "problem": "다음 중 효소에 대한 설명은?", "options": ["a", "b"], "answer": 1},
            {
                "id": "case",
                "type": "mcq",
                "problem": "55세 남자가 복부 팽만과 조기 포만감으로 내원하였다. 가장 가능성이 높은 진단은?",
                "options": ["간경변증", "폐렴"],
                "answer": 1,
                "review_status": "assigned",
                "cognitive_level": "L3 Clinical Reasoning",
            },
        ]
        picked = ns["select_daily_dx_question"](items, today_key="2026-04-25", user_key="tester")
        self.assertEqual(picked["id"], "case")

    def test_share_text_hides_answer(self):
        ns = _load_daily_helpers()
        item = {"subject": "소화기", "unit": "간질환"}
        text = ns["build_daily_dx_share_text"](item, True, attempts=2, today_key="2026-04-25")
        self.assertIn("Axioma Daily Dx", text)
        self.assertIn("소화기 / 간질환", text)
        self.assertNotIn("정답:", text)


if __name__ == "__main__":
    unittest.main()
