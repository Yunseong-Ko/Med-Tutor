import ast
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_get_main_page_config():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    fn_node = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "get_main_page_config":
            fn_node = node
            break
    if fn_node is None:
        raise RuntimeError("get_main_page_config not found in app.py")
    module = ast.Module(body=[fn_node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace["get_main_page_config"]


class MainNavRoutingTests(unittest.TestCase):
    def test_main_pages_without_admin(self):
        get_main_page_config = _load_get_main_page_config()
        pages = get_main_page_config(False)
        self.assertEqual(
            pages,
            [
                ("home", "🏠 홈"),
                ("generate", "📚 문제 생성"),
                ("convert", "🧾 기출문제 변환"),
                ("exam", "🎯 실전 시험"),
            ],
        )

    def test_main_pages_with_admin(self):
        get_main_page_config = _load_get_main_page_config()
        pages = get_main_page_config(True)
        self.assertEqual(pages[-1], ("admin", "🛠️ 운영"))
        self.assertEqual(len(pages), 5)

    def test_main_nav_uses_single_page_radio_key(self):
        source = Path(APP_PATH).read_text(encoding="utf-8")
        self.assertIn('key="main_nav_label"', source)


if __name__ == "__main__":
    unittest.main()
