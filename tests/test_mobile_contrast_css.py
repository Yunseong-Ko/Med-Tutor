import unittest
from pathlib import Path


APP_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py")


class MobileContrastCssTests(unittest.TestCase):
    def test_theme_css_contains_mobile_readability_guards(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertIn("color-scheme:", text)
        self.assertIn("[data-testid=\"stAppViewContainer\"] p,", text)
        self.assertIn("-webkit-text-fill-color: var(--text) !important;", text)
        self.assertIn("[data-testid=\"stSidebar\"] * {", text)


if __name__ == "__main__":
    unittest.main()
