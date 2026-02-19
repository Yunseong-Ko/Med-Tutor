import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


APP_PATH = "/Users/goyunseong/Documents/AI Projects/Med-Tutor/app.py"


def _load_functions():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=APP_PATH)
    wanted = {"_openai_usage_tokens", "generate_content_openai"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(nodes) != 2:
        raise RuntimeError("required functions not found in app.py")

    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "PROMPT_MCQ": "MCQ 5문제",
        "PROMPT_CLOZE": "CLOZE",
        "LLM_SEED": 123,
        "LLM_TEMPERATURE": 0.0,
        "PROMPT_VERSION": "v1",
        "_hash_text": lambda t: "hash",
        "build_style_instructions": lambda style_text: "",
        "convert_json_mcq_to_text": lambda txt, n: txt,
    }
    exec(compile(module, APP_PATH, "exec"), namespace)
    return namespace["_openai_usage_tokens"], namespace["generate_content_openai"], namespace


class _UsageObject:
    def __init__(self, total_tokens):
        self.total_tokens = total_tokens


class _FakeOpenAIClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: response
            )
        )


class OpenAIGenerationUsageTest(unittest.TestCase):
    def test_usage_object_does_not_break_generation(self):
        _, generate_content_openai, namespace = _load_functions()
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="generated output"))],
            usage=_UsageObject(total_tokens=77),
        )
        events = []

        namespace["OpenAI"] = lambda api_key: _FakeOpenAIClient(response)
        namespace["append_audit_log"] = lambda event, payload: events.append((event, payload))

        result = generate_content_openai(
            text_content="충분한 강의록 텍스트 " * 10,
            selected_mode="🧠 빈칸 문제",
            num_items=5,
            openai_api_key="sk-test",
            style_text=None,
        )

        self.assertEqual(result, "generated output")
        self.assertTrue(events)
        self.assertEqual(events[0][1]["usage_tokens"], 77)


if __name__ == "__main__":
    unittest.main()
