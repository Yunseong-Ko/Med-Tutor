import ast
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


class _FakeStreamlit:
    def __init__(self):
        self.last_markdown = ""

    def markdown(self, text, unsafe_allow_html=False):
        self.last_markdown = text


def _load_theme_functions():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = {"apply_theme", "should_apply_custom_theme"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(nodes) != len(wanted):
        raise RuntimeError("theme functions not found in app.py")
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    fake_st = _FakeStreamlit()
    namespace = {"st": fake_st}
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace["apply_theme"], namespace["should_apply_custom_theme"], fake_st


class ThemeToggleSafetyTests(unittest.TestCase):
    def test_dark_mode_enables_theme_even_if_custom_toggle_off(self):
        _, should_apply, _ = _load_theme_functions()
        self.assertTrue(should_apply(False, "Dark"))
        self.assertFalse(should_apply(False, "Light"))
        self.assertTrue(should_apply(True, "Light"))

    def test_theme_css_does_not_use_broad_class_selector_that_can_break_layout(self):
        apply_theme, _, fake_st = _load_theme_functions()
        apply_theme("Dark", "Gradient")
        css = fake_st.last_markdown
        self.assertIn(".stApp", css)
        self.assertNotIn('[class*="css"]', css)
        self.assertNotIn("display: none", css.lower())


if __name__ == "__main__":
    unittest.main()
