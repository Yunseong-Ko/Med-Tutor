"""Tests for deterministic QuestionBlueprint educational overlays."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import jsonschema

from scripts.question_blueprint import build_question_blueprint


ROOT = Path(__file__).resolve().parents[1]


def synthetic_grounding() -> dict:
    return {
        "review_policy": "faculty_draft",
        "blocked": False,
        "pack": {
            "disease_concept_id": "target_disease",
            "axis_context": {
                "types": {
                    "treatment": [
                        {"axis_id": "a:treatment:two", "label": "Drug B", "relation": "treated_with"},
                        {"axis_id": "a:treatment:one", "label": "Drug A", "relation": "treated_with"},
                        {"axis_id": "a:treatment:four", "label": "Procedure D", "relation": "treated_with"},
                        {"axis_id": "a:treatment:three", "label": "Drug C", "relation": "treated_with"},
                    ],
                    "diagnosis": [
                        {"axis_id": "a:diagnosis:two", "label": "not used by overlay"},
                        {"axis_id": "a:diagnosis:one", "label": "not used by overlay"},
                    ],
                    "symptom": [
                        {"axis_id": "a:symptom:one", "label": "not used by overlay"}
                    ],
                }
            },
            "distractor_pool": [
                {
                    "id": "disease_d",
                    "provenance": "differential_of",
                    "in_registry": True,
                    "label": "not used by overlay",
                },
                {"id": "disease_b", "provenance": "is_a_sibling", "in_registry": True},
                {"id": "disease_e", "provenance": "differential_of", "in_registry": False},
                {"id": "disease_c", "provenance": "shared_finding_bridge", "in_registry": True},
            ],
        },
    }


class QuestionBlueprintTests(unittest.TestCase):
    def test_explicit_axis_type_overrides_question_type_and_builds_review_only_overlay(self):
        blueprint = build_question_blueprint(
            synthetic_grounding(),
            question_type="management",
            target_axis_type="diagnosis",
        )

        self.assertEqual(blueprint["status"], "draft_blueprint")
        self.assertEqual(blueprint["selection"]["target_axis_source"], "explicit_axis_type")
        self.assertEqual(blueprint["target"]["axis_type"], "diagnosis")
        self.assertEqual(
            blueprint["target"]["axis_ids"],
            ["a:diagnosis:one", "a:diagnosis:two"],
        )
        self.assertEqual(blueprint["option_domain"], "diagnosis")
        self.assertTrue(blueprint["needs_review"])
        self.assertFalse(blueprint["medical_approval"])
        self.assertFalse(blueprint["gen_ready"])
        self.assertEqual(len(blueprint["misconceptions"]), 4)
        self.assertTrue(all(row["needs_review"] for row in blueprint["misconceptions"]))
        self.assertTrue(all(not row["medical_approval"] for row in blueprint["misconceptions"]))

    def test_unambiguous_question_type_maps_axis_without_random_selection(self):
        blueprint = build_question_blueprint(synthetic_grounding(), question_type="management")

        self.assertEqual(blueprint["selection"]["target_axis_source"], "question_type_mapping")
        self.assertEqual(blueprint["target"]["axis_type"], "treatment")
        self.assertEqual(blueprint["option_domain"], "intervention")
        self.assertEqual(blueprint["status"], "draft_blueprint")
        self.assertEqual(
            blueprint["distractor_source_ids"],
            [
                "a:treatment:four",
                "a:treatment:one",
                "a:treatment:three",
                "a:treatment:two",
            ],
        )
        self.assertTrue(
            all(row["source_id"].startswith("a:treatment:") for row in blueprint["distractor_sources"])
        )
        self.assertNotIn("disease_b", blueprint["distractor_source_ids"])

    def test_generic_or_missing_question_type_never_selects_first_available_axis(self):
        for question_type in (None, "clinical_case", "mixed", "image_based"):
            with self.subTest(question_type=question_type):
                blueprint = build_question_blueprint(
                    synthetic_grounding(),
                    question_type=question_type,
                )
                self.assertEqual(blueprint["status"], "blocked")
                self.assertIsNone(blueprint["target"]["axis_type"])
                self.assertEqual(blueprint["target"]["axis_ids"], [])
                self.assertEqual(blueprint["supporting_axes"], [])
                self.assertIn("target_axis_type_missing", blueprint["block_reasons"])

    def test_explicit_axis_ids_determine_one_axis_type_and_are_canonicalized(self):
        blueprint = build_question_blueprint(
            synthetic_grounding(),
            question_type="management",
            target_axis_ids=["a:diagnosis:two", "a:diagnosis:one", "a:diagnosis:two"],
        )

        self.assertEqual(blueprint["selection"]["target_axis_source"], "explicit_axis_ids")
        self.assertEqual(blueprint["target"]["axis_type"], "diagnosis")
        self.assertEqual(
            blueprint["target"]["axis_ids"],
            ["a:diagnosis:one", "a:diagnosis:two"],
        )

    def test_unknown_or_cross_type_explicit_axis_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "not present"):
            build_question_blueprint(
                synthetic_grounding(),
                target_axis_ids=["a:diagnosis:missing"],
            )
        with self.assertRaisesRegex(ValueError, "exactly one axis type"):
            build_question_blueprint(
                synthetic_grounding(),
                target_axis_ids=["a:diagnosis:one", "a:treatment:one"],
            )

    def test_unavailable_explicit_axis_type_is_blocked_without_fallback(self):
        blueprint = build_question_blueprint(
            synthetic_grounding(),
            question_type="diagnostic",
            target_axis_type="prognosis",
        )

        self.assertEqual(blueprint["target"]["axis_type"], "prognosis")
        self.assertEqual(blueprint["target"]["axis_ids"], [])
        self.assertIn("target_axis_ids_missing", blueprint["block_reasons"])
        self.assertEqual(blueprint["status"], "blocked")

    def test_ids_and_output_are_stable_across_grounding_row_order(self):
        original = synthetic_grounding()
        shuffled = copy.deepcopy(original)
        shuffled["pack"]["axis_context"]["types"] = dict(
            reversed(list(shuffled["pack"]["axis_context"]["types"].items()))
        )
        for rows in shuffled["pack"]["axis_context"]["types"].values():
            rows.reverse()
        shuffled["pack"]["distractor_pool"].reverse()

        first = build_question_blueprint(original, target_axis_type="diagnosis")
        second = build_question_blueprint(shuffled, target_axis_type="diagnosis")

        self.assertEqual(first, second)
        self.assertRegex(first["blueprint_id"], r"^qb:[0-9a-f]{16}$")
        self.assertEqual(
            [row["misconception_id"] for row in first["misconceptions"]],
            [row["misconception_id"] for row in second["misconceptions"]],
        )

    def test_explicit_option_domain_and_supporting_axes_are_preserved(self):
        blueprint = build_question_blueprint(
            synthetic_grounding(),
            target_axis_type="diagnosis",
            supporting_axis_types=["symptom"],
            option_domain="test_selection",
        )

        self.assertEqual(blueprint["option_domain"], "test_selection")
        self.assertEqual(blueprint["selection"]["option_domain_source"], "explicit")
        self.assertEqual(
            blueprint["supporting_axes"],
            [{"axis_type": "symptom", "axis_ids": ["a:symptom:one"]}],
        )

    def test_mechanism_support_alias_uses_pathophysiology_axis(self):
        grounding = synthetic_grounding()
        grounding["pack"]["axis_context"]["types"]["pathophysiology"] = [
            {"axis_id": "a:pathophysiology:one", "label": "mechanism"}
        ]
        blueprint = build_question_blueprint(
            grounding,
            target_axis_type="diagnosis",
            supporting_axis_types=["mechanism"],
        )

        self.assertNotIn("supporting_axis_type_missing:mechanism", blueprint["block_reasons"])
        self.assertEqual(blueprint["supporting_axes"][0]["axis_type"], "pathophysiology")

    def test_grounding_policy_block_is_propagated(self):
        grounding = synthetic_grounding()
        grounding["blocked"] = True
        blueprint = build_question_blueprint(grounding, target_axis_type="diagnosis")

        self.assertEqual(blueprint["status"], "blocked")
        self.assertIn("grounding_policy_blocked", blueprint["block_reasons"])
        self.assertTrue(blueprint["source_contract"]["grounding_blocked"])

    def test_schema_validates_ready_and_blocked_blueprints(self):
        schema = json.loads(
            (ROOT / "schemas" / "question_blueprint.schema.json").read_text(encoding="utf-8")
        )
        for blueprint in (
            build_question_blueprint(synthetic_grounding(), target_axis_type="diagnosis"),
            build_question_blueprint(synthetic_grounding(), question_type="clinical_case"),
        ):
            jsonschema.validate(instance=blueprint, schema=schema)


if __name__ == "__main__":
    unittest.main()
