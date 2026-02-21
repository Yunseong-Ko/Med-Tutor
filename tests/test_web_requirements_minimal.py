import unittest
from pathlib import Path


REQ_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/requirements.txt")


class WebRequirementsMinimalTests(unittest.TestCase):
    def test_cloud_requirements_do_not_force_heavy_optional_ocr_packages(self):
        text = REQ_PATH.read_text(encoding="utf-8")
        self.assertNotIn("easyocr", text)
        self.assertNotIn("pyhwp", text)


if __name__ == "__main__":
    unittest.main()
