import unittest
from pathlib import Path

from src.services.medical_copilot import COPILOT_VERIFIED_EXAMPLES


APP_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/frontend/student-v3/app.js")
INDEX_PATH = Path("/Users/goyunseong/Documents/AI Projects/Med-Tutor/frontend/student-v3/index.html")

VERIFIED_EXAMPLES = (
    "만성골수성백혈병의 핵심 병태생리와 기전은?",
    "용혈성빈혈의 핵심 병태생리와 검사 소견을 설명해줘",
    "재생불량성빈혈의 핵심 병태생리와 진단 원리를 설명해줘",
)

RETIRED_EXAMPLES = (
    "심방세동의 핵심 진단 원리를 설명해줘",
    "호흡곤란을 감별할 때 어떤 평가 축을 확인해야 할까?",
    "당뇨병을 Harrison과 국내 가이드라인 관점에서 어떻게 공부하면 좋을까?",
)


class StudentCopilotExampleTests(unittest.TestCase):
    def test_welcome_screen_uses_only_live_api_verified_examples(self):
        text = APP_PATH.read_text(encoding="utf-8")

        self.assertIn("검증된 예시 질문", text)
        self.assertIn("state.copilotStatus?.verified_examples", text)
        self.assertIn('verification_status === "passed"', text)
        self.assertIn('expected_answer_status === "grounded_learning_draft"', text)
        for prompt in VERIFIED_EXAMPLES:
            self.assertIn(prompt, [item["prompt"] for item in COPILOT_VERIFIED_EXAMPLES])
        for prompt in RETIRED_EXAMPLES:
            self.assertNotIn(prompt, text)
            self.assertNotIn(prompt, [item["prompt"] for item in COPILOT_VERIFIED_EXAMPLES])

    def test_verified_examples_have_expiry_model_and_locator_metadata(self):
        for item in COPILOT_VERIFIED_EXAMPLES:
            self.assertEqual(item["verification_status"], "passed")
            self.assertEqual(item["expected_answer_status"], "grounded_learning_draft")
            self.assertTrue(item["verified_at"])
            self.assertTrue(item["expires_at"])
            self.assertTrue(item["provider"])
            self.assertTrue(item["model"])
            self.assertTrue(item["evidence_chapters"])

    def test_student_bundle_cache_key_changes_with_example_release(self):
        html = INDEX_PATH.read_text(encoding="utf-8")

        self.assertIn("/student-v3/app.js?v=20260722-verified-registry-v7", html)


if __name__ == "__main__":
    unittest.main()
