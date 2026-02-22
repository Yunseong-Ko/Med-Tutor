import unittest
from pathlib import Path


APP_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py")


class TabSelectionStyleTests(unittest.TestCase):
    def test_tab_selected_fill_removed_and_transition_added(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('.stTabs [data-baseweb="tab"] {', text)
        self.assertIn("transition: color 0.22s ease, background-color 0.22s ease;", text)
        self.assertIn('.stTabs [aria-selected="true"] {', text)
        self.assertIn("background: transparent !important;", text)
        self.assertIn("color: var(--accent) !important;", text)


if __name__ == "__main__":
    unittest.main()
