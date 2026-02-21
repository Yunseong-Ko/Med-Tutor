import ast
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_function(name):
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if not selected:
        raise RuntimeError(f"required function not found in app.py: {name}")
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace[name]


class MobileThemeQueryTests(unittest.TestCase):
    def test_resolve_theme_mode_from_query_dark(self):
        resolver = _load_function("resolve_theme_mode_from_query")
        self.assertEqual(resolver("dark"), "Dark")

    def test_resolve_theme_mode_from_query_light(self):
        resolver = _load_function("resolve_theme_mode_from_query")
        self.assertEqual(resolver("light"), "Light")

    def test_resolve_theme_mode_from_query_default(self):
        resolver = _load_function("resolve_theme_mode_from_query")
        self.assertEqual(resolver("unknown", default="Light"), "Light")

    def test_resolve_mobile_flag_from_query_true_values(self):
        resolver = _load_function("resolve_mobile_flag_from_query")
        self.assertTrue(resolver("1"))
        self.assertTrue(resolver("true"))
        self.assertTrue(resolver("mobile"))

    def test_resolve_mobile_flag_from_query_false_values(self):
        resolver = _load_function("resolve_mobile_flag_from_query")
        self.assertFalse(resolver("0"))
        self.assertFalse(resolver("desktop"))


if __name__ == "__main__":
    unittest.main()
