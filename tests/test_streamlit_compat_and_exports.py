import unittest
from pathlib import Path


ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")


class StreamlitCompatAndExportTests(unittest.TestCase):
    def test_generation_recovery_panel_uses_container_without_border_arg(self):
        app = ROOT / "app.py"
        self.assertTrue(app.exists(), "app.py missing")
        text = app.read_text(encoding="utf-8")
        self.assertIn("def render_generation_recovery_panel()", text)
        self.assertNotIn("st.container(border=True)", text)
        self.assertIn("with st.container():", text)

    def test_free_response_modes_and_docx_export_are_present(self):
        app = ROOT / "app.py"
        text = app.read_text(encoding="utf-8")
        self.assertIn("🧠 단답형 문제", text)
        self.assertIn("🧾 서술형 문제", text)
        self.assertIn("def parse_free_response_items", text)
        self.assertIn("def grade_essay_answer_ai", text)
        self.assertIn("def build_docx_question_sheet", text)
        self.assertIn("w:cantSplit", text)
        self.assertIn("📤 시험지/문제집 내보내기", text)


if __name__ == "__main__":
    unittest.main()
