import unittest
from pathlib import Path


ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")


class ExamUnitFilterStateTests(unittest.TestCase):
    def test_no_post_widget_session_state_write_for_unit_filter(self):
        app = ROOT / "app.py"
        self.assertTrue(app.exists(), "app.py missing")
        text = app.read_text(encoding="utf-8")
        self.assertNotIn("st.session_state[unit_key] = selected_units_for_subject", text)
        self.assertIn("if not selected_units_for_subject:", text)
        self.assertIn("selected_units_for_subject = list(units)", text)


if __name__ == "__main__":
    unittest.main()
