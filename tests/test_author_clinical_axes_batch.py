import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from scripts import author_clinical_axes_batch as author


def valid_axis(concept_id: str = "asthma") -> dict:
    return {
        "id": concept_id,
        "pathophysiology": {
            "summary": "A concise mechanism summary.",
            "key_steps": ["First mechanism step", "Second mechanism step"],
        },
        "risk_factors": ["Relevant exposure", "Host susceptibility"],
        "prognosis": {
            "factors": ["Response to therapy", "Severity at presentation"],
            "staging_or_grading": "No universal staging system.",
            "natural_history": "Course varies with control and exposure.",
        },
        "treatment": {
            "principles": "Treat the underlying process and prevent recurrence.",
            "indicated_for": ["Appropriate first-line therapy", "Disease-specific supportive care"],
            "contraindicated_for": [],
        },
        "epidemiology": {
            "age": "Occurs across the lifespan",
            "sex": "No consistent predominance",
            "population": "Risk varies by exposure and susceptibility",
            "frequency": "common",
        },
        "uncertainty_notes": ["Details require faculty verification."],
        "needs_review": True,
    }


class ClinicalAxesAuthoringTests(unittest.TestCase):
    def test_candidate_loader_excludes_authored_and_non_grounded_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worklist = root / "worklist.json"
            current = root / "map.json"
            worklist.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "new_disease",
                                "ko": "새 질환",
                                "specialty": "must-not-leave-host",
                                "harrison": {
                                    "chapter": 12,
                                    "title": "Mapped Chapter",
                                    "page": 999,
                                    "part": 2,
                                },
                            },
                            {
                                "id": "already_authored",
                                "ko": "기작성",
                                "harrison": {"chapter": 13, "title": "Other Chapter"},
                            },
                            {
                                "id": "not_grounded",
                                "ko": "미매핑",
                                "harrison": None,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            current.write_text(json.dumps({"axes": {"already_authored": {}}}), encoding="utf-8")

            candidates = author.load_candidates(worklist, current)

            self.assertEqual(
                candidates,
                [
                    {
                        "id": "new_disease",
                        "ko": "새 질환",
                        "harrison": {
                            "chapter": 12,
                            "title": "Mapped Chapter",
                            "page": 999,
                            "part": 2,
                        },
                    }
                ],
            )

    def test_prompt_contains_only_sanitized_metadata(self):
        prompt = author.build_prompt(
            [
                {
                    "id": "new_disease",
                    "ko": "새 질환",
                    "harrison": {
                        "chapter": 12,
                        "title": "Mapped Chapter",
                        "page": 999,
                        "part": 2,
                    },
                }
            ]
        )
        self.assertIn("new_disease", prompt)
        self.assertIn("새 질환", prompt)
        self.assertIn("Mapped Chapter", prompt)
        self.assertNotIn('"page"', prompt)
        self.assertNotIn("999", prompt)
        self.assertNotIn('"part"', prompt)
        self.assertNotIn("specialty", prompt)
        self.assertNotIn("question", prompt.casefold())

    def test_privacy_guard_rejects_unsanitized_prompt_record(self):
        with self.assertRaises(author.BatchError):
            author.build_prompt(
                [
                    {
                        "id": "new_disease",
                        "ko": "새 질환",
                        "harrison": {
                            "chapter": 12,
                            "title": "Mapped Chapter",
                            "page": 999,
                            "part": 2,
                        },
                        "page": 999,
                    }
                ]
            )

    def test_axis_validator_accepts_five_axis_draft(self):
        self.assertEqual(author.validate_axis(valid_axis(), "asthma"), [])

    def test_axis_validator_rejects_precise_epidemiology(self):
        row = valid_axis()
        row["epidemiology"]["age"] = "Most common after age 65"
        errors = author.validate_axis(row, "asthma")
        self.assertTrue(any("qualitative" in error for error in errors))

    def test_structured_output_envelope_is_supported(self):
        expected = {"axes": [valid_axis()]}
        envelope = json.dumps({"type": "result", "structured_output": expected})
        self.assertEqual(author.extract_structured_output(envelope), expected)

    @patch("scripts.author_clinical_axes_batch.subprocess.run")
    def test_cli_call_is_fixed_low_effort_hook_free_and_prompt_sanitized(self, run_mock):
        expected = {"axes": [valid_axis("new_disease")]}
        run_mock.return_value = CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"structured_output": expected}), stderr=""
        )
        record = {
            "id": "new_disease",
            "ko": "새 질환",
            "harrison": {
                "chapter": 12,
                "title": "Mapped Chapter",
                "page": 999,
                "part": 2,
            },
        }

        self.assertEqual(
            author.invoke_claude(
                [record],
                claude_bin="/desktop/claude",
                model="claude-sonnet-4-6",
                timeout_seconds=30,
                max_budget_usd=None,
            ),
            expected,
        )
        command = run_mock.call_args.args[0]
        prompt = run_mock.call_args.kwargs["input"]
        self.assertEqual(command[command.index("--effort") + 1], "low")
        self.assertEqual(command[command.index("--setting-sources") + 1], "")
        self.assertEqual(command[command.index("--model") + 1], "claude-sonnet-4-6")
        self.assertNotIn("999", prompt)
        self.assertNotIn('"part"', prompt)

    def test_batch_keeps_full_local_harrison_reference(self):
        record = {
            "id": "new_disease",
            "ko": "새 질환",
            "harrison": {
                "chapter": 12,
                "title": "Mapped Chapter",
                "page": 999,
                "part": 2,
            },
        }
        args = Namespace(
            model="claude-sonnet-4-6",
            worklist=Path("worklist.json"),
            current_map=Path("map.json"),
            chunk_size=3,
        )
        payload = author.new_payload([record], args, "2.1.205 (Claude Code)")
        self.assertEqual(payload["harrison_refs"]["new_disease"], record["harrison"])

    def test_response_keeps_valid_partial_result_and_reports_missing(self):
        valid, errors = author.validate_response(
            {"axes": [valid_axis("asthma")]}, ["asthma", "copd"]
        )
        self.assertEqual(list(valid), ["asthma"])
        self.assertTrue(any("copd" in error for error in errors))

    def test_id_selection_preserves_explicit_order(self):
        candidates = [
            {"id": "alpha", "ko": "가", "harrison": {"chapter": 1, "title": "A"}},
            {"id": "beta", "ko": "나", "harrison": {"chapter": 2, "title": "B"}},
        ]
        selected = author.select_candidates(candidates, requested_ids=["beta", "alpha"])
        self.assertEqual([row["id"] for row in selected], ["beta", "alpha"])


if __name__ == "__main__":
    unittest.main()
