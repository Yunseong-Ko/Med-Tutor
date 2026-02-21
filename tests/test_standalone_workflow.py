import unittest
from pathlib import Path


ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")


class StandaloneWorkflowTests(unittest.TestCase):
    def test_workflow_exists_and_has_build_matrix(self):
        wf = ROOT / ".github" / "workflows" / "build-standalone.yml"
        self.assertTrue(wf.exists(), "build-standalone workflow missing")
        text = wf.read_text(encoding="utf-8")
        self.assertIn('python-version: "3.12"', text)
        self.assertIn("macos-latest", text)
        self.assertIn("windows-latest", text)
        self.assertIn("--collect-all streamlit", text)
        self.assertIn("--copy-metadata streamlit", text)
        self.assertIn("--copy-metadata importlib_metadata", text)
        self.assertIn("softprops/action-gh-release@v2", text)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", text)
        self.assertIn("actions/download-artifact@v4", text)
        self.assertIn("cp -R release_artifacts/AxiomaQbank-macos release_payload/AxiomaQbank.app", text)
        self.assertIn("chmod +x release_payload/AxiomaQbank.app/Contents/MacOS/AxiomaQbank", text)
        self.assertIn("zip -r ../AxiomaQbank-macos.zip AxiomaQbank.app", text)
        self.assertIn("Smoke test Windows bundle", text)
        self.assertIn("continue-on-error: true", text)
        self.assertIn('Start-Process -FilePath "dist/AxiomaQbank/AxiomaQbank.exe"', text)
        self.assertIn("http://127.0.0.1:8501/_stcore/health", text)
        self.assertIn("launcher_error.log", text)

    def test_readme_mentions_python_free_distribution(self):
        readme = ROOT / "README.md"
        self.assertTrue(readme.exists(), "README.md missing")
        text = readme.read_text(encoding="utf-8")
        self.assertIn("Python 없이 실행하는 배포 방법", text)
        self.assertIn(".github/workflows/build-standalone.yml", text)
        self.assertIn("releases/latest", text)
        self.assertIn("AxiomaQbank-macos.zip", text)
        self.assertIn("AxiomaQbank-windows.zip", text)
        self.assertIn("Source code (zip)", text)
        self.assertIn('chmod +x "/경로/AxiomaQbank.app/Contents/MacOS/AxiomaQbank"', text)
        self.assertIn("launcher_error.log", text)


if __name__ == "__main__":
    unittest.main()
