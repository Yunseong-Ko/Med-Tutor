import ast
import re
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_functions(names):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "LAB_SUBJECTS":
                    body.append(node)
                    break
        if isinstance(node, ast.FunctionDef) and node.name in names:
            body.append(node)
    found = set()
    for node in body:
        if isinstance(node, ast.FunctionDef):
            found.add(node.name)
    missing = set(names) - found
    if missing:
        raise RuntimeError(f"Missing functions: {sorted(missing)}")
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"re": re}
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class StudyCoachHelperTests(unittest.TestCase):
    def test_build_exam_payload_supports_mixed_all_type(self):
        ns = _load_functions(["build_exam_payload", "parse_mcq_content", "parse_cloze_content", "sanitize_mcq_problem_text"])
        parsed = ns["build_exam_payload"](
            [
                {"type": "mcq", "problem": "ABO typing의 목적은?", "options": ["A", "B", "C", "D", "E"], "answer": 1},
                {"type": "cloze", "front": "serum은 ____ 후 얻는다.", "answer": "응고", "response_type": "cloze"},
            ],
            "전체",
        )
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["type"], "mcq")
        self.assertEqual(parsed[1]["type"], "cloze")

    def test_normalize_cloze_item_allows_oral_and_ox(self):
        ns = _load_functions(["normalize_cloze_item"])
        oral = ns["normalize_cloze_item"]({"front": "ABO typing이란?", "answer": "적혈구 ABO 항원 확인", "response_type": "oral"})
        ox = ns["normalize_cloze_item"]({"front": "serum과 plasma는 같다", "answer": "X", "response_type": "ox"})
        self.assertEqual(oral["response_type"], "oral")
        self.assertEqual(ox["response_type"], "ox")

    def test_select_relevant_reference_excerpt_prioritizes_keyword_sections(self):
        ns = _load_functions(["split_text_by_page_markers", "select_relevant_reference_excerpt"])
        text = (
            "=== 페이지 1 ===\n일반 총론 내용\n\n"
            "=== 페이지 2 ===\nABO typing 과 crossmatch 는 수혈의학에서 중요하다.\n\n"
            "=== 페이지 3 ===\n다른 임상화학 내용"
        )
        excerpt = ns["select_relevant_reference_excerpt"](text, ["abo", "crossmatch"], max_sections=1, max_chars=500)
        self.assertIn("페이지 2", excerpt)
        self.assertIn("ABO typing", excerpt)

    def test_normalize_study_coach_result_keeps_fixed_top_level_keys(self):
        ns = _load_functions(["infer_lab_subject", "normalize_study_coach_result"])
        result = ns["normalize_study_coach_result"]({
            "high_yield_points": [{"point": "ABO typing vs crossmatch", "subject": "수혈의학"}],
            "predicted_questions": [{"question_type": "ox", "prompt": "CBC는 혈액 검사다", "answer": "O"}],
        })
        self.assertIn("high_yield_points", result)
        self.assertIn("topic_groups", result)
        self.assertIn("predicted_questions", result)
        self.assertEqual(result["predicted_questions"][0]["question_type"], "ox")


if __name__ == "__main__":
    unittest.main()
