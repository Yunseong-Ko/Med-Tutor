import ast
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_helper(name):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if not body:
        raise RuntimeError(f"Missing function in app.py: {name}")
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace[name]


class PageLazyHelperTests(unittest.TestCase):
    def test_should_render_exam_setup_for_new_session(self):
        helper = _load_helper("should_render_exam_setup")
        self.assertTrue(helper(False, []))
        self.assertTrue(helper(False, [{}]))

    def test_should_hide_exam_setup_for_live_session(self):
        helper = _load_helper("should_render_exam_setup")
        self.assertFalse(helper(True, [{"id": "q1"}]))


if __name__ == "__main__":
    unittest.main()
