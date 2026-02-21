import unittest
from pathlib import Path


APP_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py")


class ThemeHomeSafetyTests(unittest.TestCase):
    def test_home_does_not_render_custom_hero_html(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn('<div class="hero">', text)
        self.assertNotIn('<div class="lamp-glow"></div>', text)
        self.assertIn('st.header("Axioma Qbank")', text)
        self.assertIn("전체 정답률", text)


if __name__ == "__main__":
    unittest.main()
