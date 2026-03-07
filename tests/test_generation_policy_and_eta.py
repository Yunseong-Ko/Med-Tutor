import ast
import unittest
from pathlib import Path


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


class GenerationPolicyAndEtaTests(unittest.TestCase):
    def test_generate_page_contains_policy_and_faq_text(self):
        text = Path(APP_PATH).read_text(encoding="utf-8")
        self.assertIn("데이터 처리/보안 안내", text)
        self.assertIn("다른 사용자 계정의 문제 생성에 업로드 원문이 재사용되지 않습니다.", text)
        self.assertIn("자주 묻는 질문 (베타)", text)
        self.assertIn("예상 처리 시간(대기열 추가+생성)", text)

    def test_estimate_generation_runtime_minutes_increases_with_load(self):
        source = Path(APP_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=APP_PATH)
        target = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "estimate_generation_runtime_minutes":
                target = node
                break
        if target is None:
            self.fail("estimate_generation_runtime_minutes not found")
        module = ast.Module(body=[target], type_ignores=[])
        ast.fix_missing_locations(module)
        ns = {}
        exec(compile(module, APP_PATH, "exec"), ns)
        fn = ns["estimate_generation_runtime_minutes"]
        small = fn(total_bytes=1_000_000, num_files=1, num_items=10, has_style_file=False)
        large = fn(total_bytes=50_000_000, num_files=4, num_items=30, has_style_file=True)
        self.assertGreaterEqual(small, 1.0)
        self.assertGreater(large, small)


if __name__ == "__main__":
    unittest.main()
