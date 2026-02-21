import unittest
from pathlib import Path


APP_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py")


class ThemeControlsRemovedTests(unittest.TestCase):
    def test_sidebar_theme_toggles_removed_and_theme_default_enabled(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("커스텀 테마 사용", text)
        self.assertNotIn("다크 모드", text)
        self.assertIn('st.session_state.theme_enabled = True if safe_param is None else LOCK_THEME', text)


if __name__ == "__main__":
    unittest.main()
