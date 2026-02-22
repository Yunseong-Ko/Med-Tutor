import unittest
from pathlib import Path


APP_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py")


class AuthLandingUiTests(unittest.TestCase):
    def test_auth_landing_symbols_exist(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertIn("def render_auth_landing_page()", text)
        self.assertIn("auth_login_form_main", text)
        self.assertIn("auth_signup_form_main", text)
        self.assertIn("Axioma Qbank", text)


if __name__ == "__main__":
    unittest.main()
