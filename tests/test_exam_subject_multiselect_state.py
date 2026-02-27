import unittest
from pathlib import Path


ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")


class ExamSubjectMultiselectStateTests(unittest.TestCase):
    def test_no_default_param_for_exam_subject_multi_widget(self):
        app = ROOT / "app.py"
        self.assertTrue(app.exists(), "app.py missing")
        text = app.read_text(encoding="utf-8")
        self.assertIn('key="exam_subject_multi"', text)
        self.assertNotIn('default=[s for s in st.session_state.exam_subject_multi', text)

    def test_no_post_widget_write_to_exam_subject_multi(self):
        app = ROOT / "app.py"
        text = app.read_text(encoding="utf-8")
        self.assertNotIn('st.session_state.exam_subject_multi = all_subjects', text)


if __name__ == "__main__":
    unittest.main()
