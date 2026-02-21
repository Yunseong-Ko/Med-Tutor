import unittest
from pathlib import Path


APP_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py")


class ObsidianFeatureRemovedTests(unittest.TestCase):
    def test_obsidian_viewer_symbols_removed(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("🗒️ 노트", text)
        self.assertNotIn("Obsidian Vault 경로", text)
        self.assertNotIn("render_obsidian_html", text)
        self.assertNotIn("resolve_obsidian_embeds", text)


if __name__ == "__main__":
    unittest.main()
