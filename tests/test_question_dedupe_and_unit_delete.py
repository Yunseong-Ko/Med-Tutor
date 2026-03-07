import ast
import copy
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_namespace(function_names):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = set(function_names)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(nodes) != len(wanted):
        missing = sorted(wanted - {n.name for n in nodes})
        raise RuntimeError(f"required functions not found: {missing}")
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "datetime": __import__("datetime").datetime,
        "uuid": __import__("uuid"),
        "MODE_MCQ": "📝 객관식 문제 (Case Study)",
    }
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class QuestionDedupeAndUnitDeleteTests(unittest.TestCase):
    def test_add_questions_to_bank_dedupes_identical_mcq_in_single_call(self):
        ns = _load_namespace([
            "_normalize_text_for_dedupe",
            "build_question_dedupe_key",
            "add_questions_to_bank",
        ])
        bank_ref = {"text": [], "cloze": []}

        def fake_load():
            return copy.deepcopy(bank_ref)

        def fake_save(updated):
            bank_ref.clear()
            bank_ref.update(updated)
            return True

        ns["load_questions"] = fake_load
        ns["save_questions"] = fake_save
        ns["parse_generated_text_to_structured"] = lambda text, mode: []

        payload = [
            {
                "type": "mcq",
                "problem": "세포막 전위에 대한 설명으로 옳은 것은?",
                "options": ["A", "B", "C", "D", "E"],
                "answer": 3,
                "explanation": "x",
            },
            {
                "type": "mcq",
                "problem": "  세포막   전위에 대한 설명으로 옳은 것은? ",
                "options": ["A", "B", "C", "D", "E"],
                "answer": 3,
                "explanation": "x",
            },
        ]

        added = ns["add_questions_to_bank"](
            payload,
            "📝 객관식 문제 (Case Study)",
            subject="의총",
            unit="09",
            quality_filter=False,
        )
        self.assertEqual(added, 1)
        self.assertEqual(len(bank_ref["text"]), 1)

    def test_add_questions_to_bank_dedupes_against_existing_bank(self):
        ns = _load_namespace([
            "_normalize_text_for_dedupe",
            "build_question_dedupe_key",
            "add_questions_to_bank",
        ])
        bank_ref = {
            "text": [
                {
                    "id": "q1",
                    "problem": "신경전달물질에 대한 설명으로 옳은 것은?",
                    "options": ["A", "B", "C", "D", "E"],
                    "answer": 2,
                    "subject": "의총",
                    "unit": "09",
                }
            ],
            "cloze": [],
        }

        def fake_load():
            return copy.deepcopy(bank_ref)

        def fake_save(updated):
            bank_ref.clear()
            bank_ref.update(updated)
            return True

        ns["load_questions"] = fake_load
        ns["save_questions"] = fake_save
        ns["parse_generated_text_to_structured"] = lambda text, mode: []

        added = ns["add_questions_to_bank"](
            [
                {
                    "problem": "신경전달물질에 대한 설명으로 옳은 것은?",
                    "options": ["A", "B", "C", "D", "E"],
                    "answer": 2,
                }
            ],
            "📝 객관식 문제 (Case Study)",
            subject="의총",
            unit="09",
            quality_filter=False,
        )
        self.assertEqual(added, 0)
        self.assertEqual(len(bank_ref["text"]), 1)

    def test_delete_questions_by_subject_units_for_both_types(self):
        ns = _load_namespace(["delete_questions_by_subject_units"])
        bank_ref = {
            "text": [
                {"id": "m1", "subject": "의총", "unit": "09"},
                {"id": "m2", "subject": "의총", "unit": "10"},
            ],
            "cloze": [
                {"id": "c1", "subject": "의총", "unit": "09"},
                {"id": "c2", "subject": "해부", "unit": "01"},
            ],
        }

        def fake_load():
            return copy.deepcopy(bank_ref)

        def fake_save(updated):
            bank_ref.clear()
            bank_ref.update(updated)
            return True

        ns["load_questions"] = fake_load
        ns["save_questions"] = fake_save

        deleted = ns["delete_questions_by_subject_units"]({"의총": ["09"]}, mode="all")
        self.assertEqual(deleted, 2)
        self.assertEqual([x["id"] for x in bank_ref["text"]], ["m2"])
        self.assertEqual([x["id"] for x in bank_ref["cloze"]], ["c2"])


if __name__ == "__main__":
    unittest.main()
