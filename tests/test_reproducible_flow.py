import ast
import copy
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_functions(names):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = set(names)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(selected) != len(wanted):
        missing = sorted(wanted - {n.name for n in selected})
        raise RuntimeError(f"required functions not found in app.py: {missing}")
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    return module


class _SessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            return None

    def __setattr__(self, key, value):
        self[key] = value


def _load_namespace(function_names, extra=None):
    module = _load_functions(function_names)
    namespace = {
        "datetime": __import__("datetime").datetime,
        "timezone": __import__("datetime").timezone,
        "uuid": __import__("uuid"),
        "st": __import__("types").SimpleNamespace(session_state=_SessionState()),
        "math": __import__("math"),
        "re": __import__("re"),
        "SequenceMatcher": __import__("difflib").SequenceMatcher,
    }
    namespace.update(extra or {})
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace


class ReproducibleFlowTests(unittest.TestCase):
    def test_detect_term_language_mode_korean(self):
        namespace = _load_namespace(["detect_term_language_mode"])
        mode, pattern = namespace["detect_term_language_mode"]("환자는 복통과 발열로 내원하였다. 진단은 무엇인가?")
        self.assertEqual(mode, "ko")
        self.assertEqual(pattern, "")

    def test_detect_term_language_mode_english(self):
        namespace = _load_namespace(["detect_term_language_mode"])
        mode, pattern = namespace["detect_term_language_mode"]("A 55-year-old man presents with chest pain. Which is the diagnosis?")
        self.assertEqual(mode, "en")
        self.assertEqual(pattern, "")

    def test_detect_term_language_mode_mixed_with_parentheses(self):
        namespace = _load_namespace(["detect_term_language_mode"])
        mode, pattern = namespace["detect_term_language_mode"]("노신경(radial nerve) 손상으로 손목 처짐(wrist drop)이 발생한다.")
        self.assertEqual(mode, "mixed")
        self.assertEqual(pattern, "ko(en)")

    def test_resolve_generation_flavor_basic_subject(self):
        namespace = _load_namespace(["detect_question_flavor_scores", "resolve_generation_flavor"])
        flavor = namespace["resolve_generation_flavor"](
            "자동 판별(Auto)",
            raw_text="세포막의 막전위와 이온 이동 기전을 설명한다.",
            style_text="",
            subject="생리학",
        )
        self.assertEqual(flavor, "basic")

    def test_resolve_generation_flavor_case_subject(self):
        namespace = _load_namespace(["detect_question_flavor_scores", "resolve_generation_flavor"])
        flavor = namespace["resolve_generation_flavor"](
            "자동 판별(Auto)",
            raw_text="55세 환자가 흉통으로 내원하였다.",
            style_text="",
            subject="내과",
        )
        self.assertEqual(flavor, "case")

    def test_build_flavor_instructions_mix_ratio(self):
        namespace = _load_namespace(["build_flavor_instructions"])
        block = namespace["build_flavor_instructions"]("📝 객관식 문제 (Case Study)", "mix", mix_basic_ratio=70)
        self.assertIn("70%", block)
        self.assertIn("30%", block)

    def test_get_configured_admin_users_from_env(self):
        namespace = _load_namespace(
            ["get_configured_admin_users"],
            extra={"os": __import__("os")},
        )
        os_mod = namespace["os"]
        prev = os_mod.environ.get("AXIOMA_ADMIN_USERS")
        os_mod.environ["AXIOMA_ADMIN_USERS"] = "Admin1, admin2@example.com"
        try:
            admins = namespace["get_configured_admin_users"]()
        finally:
            if prev is None:
                del os_mod.environ["AXIOMA_ADMIN_USERS"]
            else:
                os_mod.environ["AXIOMA_ADMIN_USERS"] = prev
        self.assertIn("admin1", admins)
        self.assertIn("admin2@example.com", admins)

    def test_is_admin_user_true_when_email_matches(self):
        namespace = _load_namespace(
            ["get_configured_admin_users", "is_admin_user"],
            extra={"os": __import__("os")},
        )
        os_mod = namespace["os"]
        prev = os_mod.environ.get("AXIOMA_ADMIN_USERS")
        os_mod.environ["AXIOMA_ADMIN_USERS"] = "owner@example.com"
        try:
            state = _SessionState()
            state.auth_user_id = "user1"
            state.auth_email = "owner@example.com"
            namespace["st"].session_state = state
            self.assertTrue(namespace["is_admin_user"]())
        finally:
            if prev is None:
                del os_mod.environ["AXIOMA_ADMIN_USERS"]
            else:
                os_mod.environ["AXIOMA_ADMIN_USERS"] = prev

    def test_estimate_cost_usd_from_summary(self):
        namespace = _load_namespace(
            ["estimate_cost_usd_from_summary"],
            extra={
                "MODEL_PRICING_USD_PER_1M": {
                    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "blended": 0.30}
                }
            },
        )
        total, rows = namespace["estimate_cost_usd_from_summary"](
            {"gpt-4o-mini": {"calls": 2, "tokens": 1000000, "gen_calls": 2, "grade_calls": 0}}
        )
        self.assertAlmostEqual(total, 0.30, places=6)
        self.assertEqual(rows[0]["model"], "gpt-4o-mini")
        self.assertEqual(rows[0]["calls"], 2)
        self.assertEqual(rows[0]["tokens"], 1000000)

    def test_subject_unit_hierarchy_filter(self):
        namespace = _load_namespace(
            [
                "filter_questions_by_subject_unit_hierarchy",
                "get_unit_name",
            ]
        )
        filter_fn = namespace["filter_questions_by_subject_unit_hierarchy"]

        q = [
            {"id": "q1", "subject": "심장", "unit": "판막질환"},
            {"id": "q2", "subject": "심장", "unit": "부정맥"},
            {"id": "q3", "subject": "신경", "unit": "두통"},
            {"id": "q4", "subject": "신경", "unit": "뇌경색"},
        ]
        result = filter_fn(q, ["심장"], {"심장": ["부정맥"]})
        self.assertEqual([x["id"] for x in result], ["q2"])

    def test_start_exam_session_from_items(self):
        namespace = _load_namespace(
            [
                "start_exam_session_from_items",
                "parse_mcq_content",
                "sanitize_mcq_problem_text",
                "build_exam_payload",
                "get_unit_name",
            ]
        )
        start_fn = namespace["start_exam_session_from_items"]

        st_session = _SessionState()
        namespace["st"].session_state = st_session
        count = start_fn(
            [
                {"type": "mcq", "problem": "심근경색의 원인", "options": ["a", "b", "c", "d", "e"], "answer": 2, "subject": "심장"},
                {"type": "mcq", "problem": "심전도상 ST 상승", "options": ["a", "b", "c", "d", "e"], "answer": 1, "subject": "심장"},
            ],
            "객관식",
            "학습모드",
        )
        self.assertEqual(count, 2)
        self.assertTrue(st_session.get("exam_started"))
        self.assertFalse(st_session.get("exam_finished"))
        self.assertEqual(st_session.get("exam_type"), "객관식")
        self.assertEqual(st_session.get("exam_mode"), "학습모드")
        self.assertEqual(len(st_session.get("exam_questions", [])), 2)
        self.assertEqual(st_session.get("current_exam_meta").get("num_questions"), 2)

    def test_parse_mcq_content_trims_hard_concatenated_stem(self):
        namespace = _load_namespace(["parse_mcq_content", "sanitize_mcq_problem_text"])
        parse_mcq_content = namespace["parse_mcq_content"]

        raw = {
            "type": "mcq",
            "problem": "[문제] 모유 수유의 장점으로 가장 적절한 것은?TPN 관련 합병증 원인은?BMI 97백분위수 진단은?",
            "options": ["a", "b", "c", "d", "e"],
            "answer": 1,
        }
        parsed = parse_mcq_content(raw)
        self.assertEqual(parsed["front"], "[문제] 모유 수유의 장점으로 가장 적절한 것은?")

    def test_parse_mcq_content_keeps_quoted_question_sentence(self):
        namespace = _load_namespace(["parse_mcq_content", "sanitize_mcq_problem_text"])
        parse_mcq_content = namespace["parse_mcq_content"]

        raw = {
            "type": "mcq",
            "problem": "부모는 \"아이를 느낄 수 있을까요?\"라고 물었다. 이 요청의 윤리적 근거는?",
            "options": ["a", "b", "c", "d", "e"],
            "answer": 2,
        }
        parsed = parse_mcq_content(raw)
        self.assertEqual(parsed["front"], raw["problem"])

    def test_update_question_by_id_persists(self):
        namespace = _load_namespace(
            [
                "update_question_by_id",
                "load_questions",
                "save_questions",
            ]
        )
        bank_ref = {"text": [{"id": "q1", "subject": "심장", "problem": "old", "options": ["a", "b"], "answer": 1}], "cloze": []}

        def fake_load():
            return copy.deepcopy(bank_ref)

        def fake_save(updated):
            bank_ref.clear()
            bank_ref.update(updated)

        namespace["load_questions"] = fake_load
        namespace["save_questions"] = fake_save

        ok = namespace["update_question_by_id"](
            "q1",
            {
                "subject": "신경",
                "problem": "new stem",
                "options": ["x", "y"],
                "answer": 2,
                "id": "MUST_NOT_CHANGE",
                "explanation": "new explanation",
            },
        )

        self.assertTrue(ok)
        self.assertEqual(bank_ref["text"][0]["subject"], "신경")
        self.assertEqual(bank_ref["text"][0]["problem"], "new stem")
        self.assertEqual(bank_ref["text"][0]["answer"], 2)
        self.assertEqual(bank_ref["text"][0]["id"], "q1")

    def test_update_question_bookmark_persists(self):
        namespace = _load_namespace(
            [
                "update_question_bookmark",
                "load_questions",
                "save_questions",
            ]
        )
        bank_ref = {"text": [{"id": "q1", "bookmarked": False}], "cloze": []}

        def fake_load():
            return copy.deepcopy(bank_ref)

        def fake_save(updated):
            bank_ref.clear()
            bank_ref.update(updated)

        namespace["load_questions"] = fake_load
        namespace["save_questions"] = fake_save

        ok = namespace["update_question_bookmark"]("q1", True)
        self.assertTrue(ok)
        self.assertTrue(bank_ref["text"][0]["bookmarked"])

    def test_get_question_attempt_summary(self):
        namespace = _load_namespace(["get_question_attempt_summary"])
        summary = namespace["get_question_attempt_summary"](
            {
                "stats": {
                    "right": 3,
                    "wrong": 2,
                    "history": [{"time": "2026-02-26T00:00:00+00:00", "correct": False}],
                }
            }
        )
        self.assertEqual(summary["attempts"], 5)
        self.assertEqual(summary["right"], 3)
        self.assertEqual(summary["wrong"], 2)
        self.assertFalse(summary["last_correct"])

    def test_subject_review_summary_without_fsrs(self):
        namespace = _load_namespace(["summarize_subject_review_status", "srs_due"])
        namespace["FSRS_AVAILABLE"] = False
        namespace["datetime"] = __import__("datetime").datetime
        namespace["timezone"] = __import__("datetime").timezone

        summary = namespace["summarize_subject_review_status"]([
            {"id": "q1", "subject": "심장", "stats": {"wrong": 1}, "srs": {"due": ""}},
            {"id": "q2", "subject": "신경", "stats": {"wrong": 0}, "srs": {"due": "2024-01-01T00:00:00+00:00"}},
            {"id": "q3", "subject": "심장", "stats": {"wrong": 0}, "srs": {}},
        ])

        self.assertEqual(summary[0]["분과"], "심장")
        self.assertEqual(summary[0]["총문항"], 2)
        self.assertGreaterEqual(summary[0]["복습대상"], 1)
        self.assertEqual(summary[1]["분과"], "신경")

    def test_safe_dataframe_fallback_markdown(self):
        namespace = _load_namespace(["safe_dataframe", "_to_markdown_table"])
        out = []
        namespace["st"] = _SessionState()
        namespace["st"].dataframe = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("pyarrow missing"))
        namespace["st"].markdown = out.append

        namespace["safe_dataframe"]([{"a": 1, "b": 2}])
        self.assertTrue(len(out) > 0)

    def test_apply_profile_settings_with_invalid_payload_recovers_defaults(self):
        namespace = _load_namespace(["apply_profile_settings"])
        st_session = _SessionState()
        st_session.heatmap_bins = [0, 1, 3, 6, 10]
        st_session.heatmap_colors = ["#ffffff", "#d7f3f0", "#b2e9e3", "#7fd6cc", "#4fc1b6", "#1f8e86"]
        st_session.select_placeholder_exam = "선택하세요"
        st_session.select_placeholder_study = "선택하세요"
        namespace["st"].session_state = st_session

        namespace["load_user_settings"] = lambda: {
            "default": {
                "heatmap_bins": [0, 1],  # invalid: too short
                "heatmap_colors": ["#ffffff", "not-a-color"],  # invalid: too short + bad color
                "select_placeholder_exam": "시험 선택",
                "select_placeholder_study": "학습 선택",
            }
        }

        loaded = namespace["apply_profile_settings"]("default")
        self.assertTrue(loaded)
        self.assertEqual(st_session.heatmap_bins, [0, 1, 3, 6, 10])
        self.assertEqual(len(st_session.heatmap_colors), 6)
        self.assertEqual(st_session.select_placeholder_exam, "시험 선택")
        self.assertEqual(st_session.select_placeholder_study, "학습 선택")


if __name__ == "__main__":
    unittest.main()
