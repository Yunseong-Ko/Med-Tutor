import unittest
from pathlib import Path


ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")


class LauncherScriptTests(unittest.TestCase):
    def test_macos_launcher_contains_bootstrap_steps(self):
        path = ROOT / "start_axioma_qbank.command"
        self.assertTrue(path.exists(), "start_axioma_qbank.command missing")
        text = path.read_text(encoding="utf-8")
        self.assertIn(".venv", text)
        self.assertIn("-m venv .venv", text)
        self.assertIn("-m pip install -r requirements.txt", text)
        self.assertIn("-m streamlit run app.py", text)

    def test_windows_launcher_contains_bootstrap_steps(self):
        path = ROOT / "start_axioma_qbank.bat"
        self.assertTrue(path.exists(), "start_axioma_qbank.bat missing")
        text = path.read_text(encoding="utf-8")
        self.assertIn(".venv", text)
        self.assertIn("-m venv .venv", text)
        self.assertIn("-m pip install -r requirements.txt", text)
        self.assertIn("-m streamlit run app.py", text)


if __name__ == "__main__":
    unittest.main()
