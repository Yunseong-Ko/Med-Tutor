import unittest

from scripts.audit_clinical_axes_expansion import audit_document


REF = {"chapter": 1, "title": "A Disease Chapter", "page": 10, "part": 1}


def valid_axis(cid: str) -> dict:
    return {
        "id": cid,
        "pathophysiology": {
            "summary": "A disease-specific initiating injury activates a defined pathway and produces clinically important organ dysfunction over time.",
            "key_steps": [
                "An initiating exposure activates the disease pathway",
                "Tissue dysfunction produces the characteristic manifestations",
            ],
        },
        "risk_factors": ["Defined inherited susceptibility", "A disease-specific environmental exposure"],
        "prognosis": {
            "factors": ["Extent of organ dysfunction", "Response to disease-specific therapy"],
            "staging_or_grading": "No formal staging system is used",
            "natural_history": "Untreated disease can progress from limited dysfunction to clinically important complications.",
        },
        "treatment": {
            "principles": "Remove the initiating exposure and use disease-specific therapy according to organ severity.",
            "indicated_for": ["Targeted inhibitor for clinically active disease"],
            "contraindicated_for": ["Targeted inhibitor during a documented severe hypersensitivity reaction"],
        },
        "epidemiology": {
            "age": "Most often recognized in adulthood",
            "sex": "No clear sex predominance",
            "population": "People with the relevant inherited or environmental susceptibility",
            "frequency": "Uncommon",
        },
        "uncertainty_notes": [],
        "needs_review": True,
    }


def worklist(*ids: str, node_type: str = "disease", ref: dict | None = REF) -> dict:
    return {"items": [{"id": cid, "node_type": node_type, "harrison": ref} for cid in ids]}


class ClinicalAxesExpansionAuditTests(unittest.TestCase):
    def test_valid_batch_passes_draft_gate_but_never_medical_approval(self):
        cid = "example_disease"
        report = audit_document(
            {
                "_meta": {"needs_review": True},
                "harrison_refs": {cid: REF},
                "axes": {cid: valid_axis(cid)},
            },
            source="batch.json",
            worklist_data=worklist(cid),
        )

        self.assertTrue(report["quality_gate_passed"])
        self.assertFalse(report["medical_approval"])
        self.assertFalse(report["automatic_medical_approval_performed"])
        self.assertTrue(report["review_required"])
        self.assertEqual(report["summary"]["harrison_refs_exact_or_worklist_grounded"], 1)

    def test_requested_quality_signals_are_reported(self):
        ids = ["screening", "example_disease_1", "example_disease_2", "example_disease_3", "example_disease_4"]
        axes = {}
        refs = {}
        for cid in ids:
            axis = valid_axis(cid)
            axis["pathophysiology"]["summary"] = "TBD"
            axis["treatment"] = {
                "principles": "Supportive care",
                "indicated_for": ["Supportive care", "Aspirin for active disease"],
                "contraindicated_for": ["Aspirin for active disease"],
            }
            axis["epidemiology"]["sex"] = "Always affects women, about 52% of cases"
            axis["risk_factors"][0] = "Identical inherited susceptibility phrase used by every generated disease"
            axes[cid] = axis
            refs[cid] = dict(REF)
        axes[ids[0]]["needs_review"] = False
        refs[ids[0]]["page"] = 999

        report = audit_document(
            {"_meta": {"needs_review": True}, "harrison_refs": refs, "axes": axes},
            source="bad_batch.json",
            worklist_data=worklist(*ids),
            max_identical_phrase_uses=4,
        )
        codes = set(report["summary"]["issue_codes"])

        self.assertFalse(report["quality_gate_passed"])
        self.assertTrue(
            {
                "placeholder_content",
                "generic_treatment_principle",
                "generic_treatment_entry",
                "harrison_ref_mismatch",
                "indication_contraindication_exact_overlap",
                "needs_review_not_true",
                "non_disease_concept_candidate",
                "over_replicated_phrase",
                "precise_epidemiology_statistic",
                "dangerous_absolute_expression",
            }.issubset(codes)
        )

    def test_merged_map_uses_worklist_grounding_and_flags_non_disease_type(self):
        cid = "example_concept"
        report = audit_document(
            {"total": 1, "axes": {cid: valid_axis(cid)}},
            source="clinical_axes_map.json",
            worklist_data=worklist(cid, node_type="procedure"),
        )

        self.assertEqual(report["source_kind"], "merged_map")
        self.assertIn("non_disease_node_type", report["summary"]["issue_codes"])
        self.assertFalse(report["quality_gate_passed"])

    def test_high_risk_withdrawal_wording_is_blocked(self):
        cid = "delirium_tremens"
        axis = valid_axis(cid)
        axis["prognosis"]["staging_or_grading"] = (
            "CIWA-Ar is used to monitor alcohol-withdrawal delirium and guide treatment."
        )
        axis["treatment"]["principles"] = (
            "Give high-dose thiamine before glucose to prevent Wernicke encephalopathy."
        )

        report = audit_document(
            {
                "_meta": {"needs_review": True},
                "harrison_refs": {cid: REF},
                "axes": {cid: axis},
            },
            source="withdrawal_batch.json",
            worklist_data=worklist(cid),
        )

        codes = set(report["summary"]["issue_codes"])
        self.assertIn("unsafe_thiamine_glucose_sequence", codes)
        self.assertIn("ciwa_used_for_active_delirium", codes)
        self.assertFalse(report["quality_gate_passed"])

    def test_authority_scoped_alternate_source_batch_is_grounded_but_not_approved(self):
        cid = "example_unmapped_disease"
        axis = valid_axis(cid)
        refs = [
            {
                "ref_id": "doi:10.0000/example",
                "source_type": "professional_society_guideline",
                "authority": "Example Society",
                "title": "Example guideline",
                "url": "https://example.org/guideline",
                "verified_on": "2026-07-12",
                "scope": "whole_record",
                "entailment_status": "needs_human_review",
            }
        ]
        axis["evidence_refs"] = refs
        report = audit_document(
            {"_meta": {"needs_review": True}, "source_refs": {cid: refs}, "axes": {cid: axis}},
            source="alternate_batch.json",
            worklist_data=worklist(cid, ref=None),
        )

        self.assertEqual(report["source_kind"], "alternate_batch")
        self.assertTrue(report["quality_gate_passed"])
        self.assertEqual(report["summary"]["alternate_source_refs_exact_or_embedded"], 1)
        self.assertFalse(report["medical_approval"])

    def test_unmapped_merged_axis_without_alternate_source_remains_blocked(self):
        cid = "example_unmapped_disease"
        report = audit_document(
            {"total": 1, "axes": {cid: valid_axis(cid)}},
            source="clinical_axes_map.json",
            worklist_data=worklist(cid, ref=None),
        )

        self.assertIn("not_harrison_grounded", report["summary"]["issue_codes"])
        self.assertFalse(report["quality_gate_passed"])

    def test_empty_staging_is_review_warning_not_a_blocker(self):
        cid = "example_disease"
        axis = valid_axis(cid)
        axis["prognosis"]["staging_or_grading"] = ""
        report = audit_document(
            {"total": 1, "axes": {cid: axis}},
            source="clinical_axes_map.json",
            worklist_data=worklist(cid),
        )

        self.assertIn("staging_or_grading_unresolved", report["summary"]["issue_codes"])
        self.assertEqual(report["summary"]["blocking_issues"], 0)


if __name__ == "__main__":
    unittest.main()
