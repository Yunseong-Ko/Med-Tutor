import sys
import tempfile
import unittest
from pathlib import Path

APP_ROOT = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor")
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.repositories.prewarm_cache_store import load_prewarm_cache_file, save_prewarm_cache_file


class PrewarmCacheStoreTests(unittest.TestCase):
    def test_load_returns_empty_dict_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "prewarm_cache.json"
            self.assertEqual(load_prewarm_cache_file(path), {})

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "prewarm_cache.json"
            payload = {"raw:file-a": "lecture text", "style:file-b": "style text"}
            self.assertTrue(save_prewarm_cache_file(path, payload))
            self.assertEqual(load_prewarm_cache_file(path), payload)

    def test_non_dict_payload_is_normalized_to_empty_dict(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "prewarm_cache.json"
            self.assertTrue(save_prewarm_cache_file(path, ["unexpected"]))
            self.assertEqual(load_prewarm_cache_file(path), {})


if __name__ == "__main__":
    unittest.main()
