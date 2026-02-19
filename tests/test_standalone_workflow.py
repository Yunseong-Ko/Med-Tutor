import unittest
from pathlib import Path


ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")


class StandaloneWorkflowTests(unittest.TestCase):
    def test_workflow_exists_and_has_build_matrix(self):
        wf = ROOT / ".github" / "workflows" / "build-standalone.yml"
        self.assertTrue(wf.exists(), "build-standalone workflow missing")
        text = wf.read_text(encoding="utf-8")
        self.assertIn("macos-latest", text)
        self.assertIn("windows-latest", text)
        self.assertIn("--collect-all streamlit", text)
        self.assertIn("--copy-metadata streamlit", text)
        self.assertIn("--copy-metadata importlib_metadata", text)

    def test_readme_mentions_python_free_distribution(self):
        readme = ROOT / "README.md"
        self.assertTrue(readme.exists(), "README.md missing")
        text = readme.read_text(encoding="utf-8")
        self.assertIn("Python 없이 실행하는 배포 방법", text)
        self.assertIn(".github/workflows/build-standalone.yml", text)


if __name__ == "__main__":
    unittest.main()
