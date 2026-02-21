import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")


def load_launcher_module():
    launcher_path = ROOT / "launcher.py"
    spec = importlib.util.spec_from_file_location("medtutor_launcher", launcher_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackagedLauncherResolutionTests(unittest.TestCase):
    def test_resolves_windows_bundle_internal_app(self):
        launcher = load_launcher_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe_dir = root / "AxiomaQbank"
            internal_dir = exe_dir / "_internal"
            internal_dir.mkdir(parents=True, exist_ok=True)
            app_path = internal_dir / "app.py"
            app_path.write_text("# app", encoding="utf-8")

            resolved = launcher.resolve_app_path(
                file_path=exe_dir / "launcher.py",
                executable_path=exe_dir / "AxiomaQbank.exe",
                cwd_path=root,
                frozen=True,
            )
            self.assertEqual(resolved, app_path)

    def test_resolves_cwd_app_in_source_mode(self):
        launcher = load_launcher_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app_path = root / "app.py"
            app_path.write_text("# app", encoding="utf-8")

            resolved = launcher.resolve_app_path(
                file_path=root / "launcher.py",
                executable_path=root / "python",
                cwd_path=root,
                frozen=False,
            )
            self.assertEqual(resolved, app_path)

    def test_missing_app_raises_checked_paths(self):
        launcher = load_launcher_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(FileNotFoundError) as ctx:
                launcher.resolve_app_path(
                    file_path=root / "launcher.py",
                    executable_path=root / "AxiomaQbank.exe",
                    cwd_path=root,
                    frozen=True,
                )
            self.assertIn("_internal", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
