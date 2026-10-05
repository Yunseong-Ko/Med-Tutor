import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_axis_layer import claim_id as materialized_claim_id
from scripts.build_clinical_axis_review_worklist import build_review_worklist, main


CONCEPT_ID = "example_disease"


def axis_registry(*, include_relationship_claim_ids: bool = True) -> dict:
    nodes = [
        {
            "axis_id": "a:treatment:principle",
            "axis_type": "treatment",
            "label": "Use definitive treatment for every patient.",
            "dimension": "principle",
        },
        {
            "axis_id": "a:indication:drug",
            "axis_type": "indication",
            "label": "Example drug for biomarker-positive disease",
            "dimension": "",
        },
        {
            "axis_id": "a:contraindication:drug",
            "axis_type": "contraindication",
            "label": "Example drug with a documented severe hypersensitivity reaction",
            "dimension": "",
        },
    ]
    relationships = [
        {
            "disease_concept_id": CONCEPT_ID,
            "axis_id": "a:treatment:principle",
            "relation": "has_treatment_principle",
        },
        {
            "disease_concept_id": CONCEPT_ID,
            "axis_id": "a:indication:drug",
            "relation": "has_indication",
        },
        {
            "disease_concept_id": CONCEPT_ID,
            "axis_id": "a:contraindication:drug",
            "relation": "has_contraindication",
        },
    ]
    if include_relationship_claim_ids:
        for index, row in enumerate(relationships):
            row["claim_id"] = f"c:axis_relation:stored{index}"
    return {
        "schema_version": "1.2.0",
        "nodes": nodes,
        "relationships": relationships,
    }


def audit_report() -> dict:
    return {
        "generated_at": "2026-07-12T00:00:00+00:00",
        "source": "data_private/curriculum/clinical_axes_map.json",
        "issues": [
            {
                "code": "dangerous_absolute_expression",
                "severity": "warning",
                "blocking": False,
                "message": "Potentially unsafe absolute wording requires human medical review.",
                "id": CONCEPT_ID,
                "path": "treatment.principles",
                "evidence": "Use definitive treatment for every patient.",
            },
            {
                "code": "potential_indication_contraindication_overlap",
                "severity": "warning",
                "blocking": False,
                "message": "Conditions require human review.",
                "id": CONCEPT_ID,
                "path": "treatment.indicated_for.0|treatment.contraindicated_for.0",
                "evidence": (
                    "INDICATED: Example drug for biomarker-positive disease | "
                    "CONTRAINDICATED: Example drug with a documented severe hypersensitivity reaction"
                ),
            },
            {
                "code": "staging_or_grading_unresolved",
                "severity": "warning",
                "blocking": False,
                "message": "No staging or grading statement is authored.",
                "id": CONCEPT_ID,
                "path": "prognosis.staging_or_grading",
            },
        ],
    }


class ClinicalAxisReviewWorklistTests(unittest.TestCase):
    def build(self, audit=None, registry=None):
        return build_review_worklist(
            audit or audit_report(),
            registry or axis_registry(),
            audit_path="audit.json",
            axis_registry_path="axis_registry.json",
        )

    def test_maps_warning_to_stored_relationship_claim_and_keeps_review_pending(self):
        payload = self.build()
        item = next(row for row in payload["items"] if row["warning_code"] == "dangerous_absolute_expression")

        self.assertEqual(item["priority"], "P0")
        self.assertEqual(item["claim_id"], "c:axis_relation:stored0")
        self.assertEqual(item["axis_id"], "a:treatment:principle")
        self.assertEqual(
            item["source_path"],
            "data_private/curriculum/clinical_axes_map.json#/axes/example_disease/treatment/principles",
        )
        self.assertEqual(item["claims"][0]["mapping_status"], "exact_label")
        self.assertEqual(
            item["claims"][0]["source_path"],
            "data_private/curriculum/clinical_axes_map.json#/axes/example_disease/treatment/principles",
        )
        self.assertEqual(item["review_decision"]["status"], "pending")
        self.assertIsNone(item["review_decision"]["decision"])
        self.assertFalse(item["medical_approval"])
        self.assertFalse(payload["medical_approval"])
        self.assertFalse(payload["automatic_medical_approval_performed"])

    def test_overlap_warning_maps_both_claims_and_unresolved_path_gets_stable_fallback(self):
        payload = self.build()
        overlap = next(
            row for row in payload["items"] if row["warning_code"] == "potential_indication_contraindication_overlap"
        )
        unresolved = next(row for row in payload["items"] if row["warning_code"] == "staging_or_grading_unresolved")

        self.assertEqual(overlap["priority"], "P1")
        self.assertEqual(overlap["claim_ids"], ["c:axis_relation:stored1", "c:axis_relation:stored2"])
        self.assertEqual(overlap["axis_ids"], ["a:contraindication:drug", "a:indication:drug"])
        self.assertIsNone(overlap["claim_id"])
        self.assertEqual(unresolved["priority"], "P2")
        self.assertIsNone(unresolved["axis_id"])
        self.assertEqual(unresolved["claims"][0]["mapping_status"], "not_materialized")
        self.assertEqual(
            unresolved["claim_id"],
            materialized_claim_id("unmaterialized_axis", CONCEPT_ID, "prognosis.staging_or_grading"),
        )

    def test_missing_relationship_claim_id_uses_axis_layer_fallback_rule(self):
        payload = self.build(registry=axis_registry(include_relationship_claim_ids=False))
        item = next(row for row in payload["items"] if row["warning_code"] == "dangerous_absolute_expression")

        self.assertEqual(
            item["claim_id"],
            materialized_claim_id(
                "axis_relation",
                CONCEPT_ID,
                "has_treatment_principle",
                "a:treatment:principle",
            ),
        )

    def test_output_is_independent_of_audit_and_registry_row_order(self):
        audit_a = audit_report()
        registry_a = axis_registry()
        audit_b = copy.deepcopy(audit_a)
        registry_b = copy.deepcopy(registry_a)
        audit_b["issues"].reverse()
        registry_b["nodes"].reverse()
        registry_b["relationships"].reverse()

        self.assertEqual(self.build(audit=audit_a, registry=registry_a), self.build(audit=audit_b, registry=registry_b))

    def test_cli_writes_identical_bytes_for_identical_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit_path = root / "audit.json"
            registry_path = root / "axis_registry.json"
            output_a = root / "review_a.json"
            output_b = root / "review_b.json"
            audit_path.write_text(json.dumps(audit_report()), encoding="utf-8")
            registry_path.write_text(json.dumps(axis_registry()), encoding="utf-8")

            args = ["--audit", str(audit_path), "--axis-registry", str(registry_path)]
            self.assertEqual(main([*args, "--output", str(output_a)]), 0)
            self.assertEqual(main([*args, "--output", str(output_b)]), 0)
            self.assertEqual(output_a.read_bytes(), output_b.read_bytes())


if __name__ == "__main__":
    unittest.main()
