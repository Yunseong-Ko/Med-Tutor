import unittest
from pathlib import Path


REQ_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/requirements.txt")


class WebRequirementsMinimalTests(unittest.TestCase):
    def test_cloud_requirements_keep_ocr_stack_minimal_but_include_hwp_parser(self):
        text = REQ_PATH.read_text(encoding="utf-8")
        self.assertNotIn("easyocr", text)
        self.assertIn("pyhwp", text)


if __name__ == "__main__":
    unittest.main()
