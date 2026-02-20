import unittest
from pathlib import Path
from unittest.mock import patch

import launcher


class LauncherArgsTest(unittest.TestCase):
    def test_main_forces_development_mode_off(self):
        with patch("launcher.resolve_app_path", return_value=Path("/tmp/app.py")), patch(
            "launcher.stcli.main", return_value=0
        ) as mock_main:
            with self.assertRaises(SystemExit) as ctx:
                launcher.main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertTrue(mock_main.called)
        self.assertIn("--global.developmentMode=false", launcher.sys.argv)


if __name__ == "__main__":
    unittest.main()
