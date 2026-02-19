import ast
import io
import re
import unittest
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_docx_builder():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = {"format_explanation_text", "_set_row_cant_split", "build_docx_question_sheet"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(nodes) != len(wanted):
        raise RuntimeError("required docx functions not found in app.py")
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "Document": Document,
        "OxmlElement": OxmlElement,
        "io": io,
        "re": re,
    }
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace["build_docx_question_sheet"]


class DocxLayoutReadabilityTests(unittest.TestCase):
    def test_docx_has_blank_line_between_stem_and_options(self):
        build_docx = _load_docx_builder()
        items = [
            {
                "type": "mcq",
                "problem": "증례 기반 문항",
                "options": ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"],
                "answer": 1,
                "explanation": "정답 이유 | 오답 이유",
            }
        ]
        docx_bytes = build_docx(items, title="테스트 문제집")
        self.assertTrue(docx_bytes)

        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")

        self.assertIn("문항 1", xml)
        self.assertIn("정답", xml)
        self.assertIn("해설", xml)
        self.assertRegex(xml, r"증례 기반 문항.*?</w:p><w:p/>\s*<w:p>.*?A\. Alpha")


if __name__ == "__main__":
    unittest.main()
