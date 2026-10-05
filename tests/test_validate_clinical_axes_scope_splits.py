import copy
import json
import unittest
from pathlib import Path

from scripts.validate_clinical_axes_scope_splits import validate_documents


ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "data_private" / "curriculum"


def load(name: str) -> dict:
    return json.loads((CURRICULUM / name).read_text(encoding="utf-8"))


class ScopeSplitValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quarantine = load("clinical_axes_scope_quarantine_20260712.json")
        cls.concepts = load("clinical_axes_scope_split_concepts_20260712.json")
        cls.batch = load("clinical_axes_scope_split_batch_20260712.json")

    def test_real_candidate_patch_passes_without_medical_approval(self):
        report = validate_documents(self.quarantine, self.concepts, self.batch)
        self.assertTrue(report["quality_gate_passed"])
        self.assertFalse(report["medical_approval"])
        self.assertTrue(report["review_required"])
        self.assertEqual(report["summary"]["quarantined_parents"], 5)
        self.assertEqual(report["summary"]["new_concepts"], 25)
        self.assertEqual(report["summary"]["classification_nodes"], 4)
        self.assertEqual(report["summary"]["clinical_axis_leaves"], 21)
        self.assertIn("low_evidence_source", report["summary"]["issue_codes"])

    def test_classification_node_cannot_receive_axes(self):
        batch = copy.deepcopy(self.batch)
        batch["axes"]["hematologic_malignancy_cns_involvement"] = copy.deepcopy(batch["axes"]["cns_leukemia"])
        batch["axes"]["hematologic_malignancy_cns_involvement"]["id"] = "hematologic_malignancy_cns_involvement"
        report = validate_documents(self.quarantine, self.concepts, batch)
        codes = {issue["code"] for issue in report["issues"] if issue["blocking"]}
        self.assertIn("non_leaf_has_axes", codes)
        self.assertIn("axis_without_leaf", codes)

    def test_missing_source_and_orphan_parent_are_blocked(self):
        concepts = copy.deepcopy(self.concepts)
        concepts["concepts"]["pleural_empyema"]["source_pointers"] = []
        concepts["concepts"]["pleural_empyema"]["parent_id"] = "unknown_parent"
        report = validate_documents(self.quarantine, concepts, self.batch)
        codes = {issue["code"] for issue in report["issues"] if issue["blocking"]}
        self.assertIn("missing_concept_source", codes)
        self.assertIn("orphan_parent", codes)

    def test_original_umbrella_parent_cannot_receive_axes(self):
        batch = copy.deepcopy(self.batch)
        batch["axes"]["glioma"] = copy.deepcopy(batch["axes"]["glioblastoma_idh_wildtype"])
        batch["axes"]["glioma"]["id"] = "glioma"
        report = validate_documents(self.quarantine, self.concepts, batch)
        codes = {issue["code"] for issue in report["issues"] if issue["blocking"]}
        self.assertIn("non_leaf_has_axes", codes)


if __name__ == "__main__":
    unittest.main()
