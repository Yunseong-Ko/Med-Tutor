import copy
import unittest

from scripts.apply_clinical_axes_legacy_safety_fixes_batch2_20260712 import (
    CORRECTIONS,
    apply_corrections,
)
from scripts.audit_clinical_axes_expansion import PRECISE_EPIDEMIOLOGY_PATTERNS, audit_document


REF = {"chapter": 1, "title": "Reviewed disease chapter", "page": 1, "part": 1}


def valid_axis(cid: str) -> dict:
    axis = {
        "id": cid,
        "pathophysiology": {
            "summary": "A disease-specific initiating process activates a defined pathway and produces clinically important organ dysfunction over time.",
            "key_steps": [
                "A disease-specific initiating event activates the relevant pathway",
                "Progressive tissue dysfunction produces the characteristic manifestations",
            ],
        },
        "risk_factors": ["A disease-specific inherited or environmental susceptibility"],
        "prognosis": {
            "factors": ["Extent of organ dysfunction", "Response to disease-specific therapy"],
            "staging_or_grading": "No formal staging system is used",
            "natural_history": "Untreated disease can progress to clinically important complications over time.",
        },
        "treatment": {
            "principles": "Use disease-specific therapy according to clinical severity and organ involvement.",
            "indicated_for": ["Disease-specific therapy for clinically active disease"],
            "contraindicated_for": [],
        },
        "epidemiology": {
            "age": "Varies with the condition",
            "sex": "No clear sex predominance",
            "population": "People with the relevant susceptibility",
            "frequency": "Uncommon",
        },
        "uncertainty_notes": [],
        "needs_review": True,
    }
    correction = CORRECTIONS[cid]
    target = axis
    for key in correction.path[:-1]:
        target = target[key]
    target[correction.path[-1]] = correction.old
    return axis


def draft_document() -> dict:
    return {"total": len(CORRECTIONS), "axes": {cid: valid_axis(cid) for cid in CORRECTIONS}}


def worklist() -> dict:
    return {"items": [{"id": cid, "node_type": "disease", "harrison": REF} for cid in CORRECTIONS]}


class LegacySafetyFixesBatch2Tests(unittest.TestCase):
    def test_exactly_twenty_five_reviewed_records_are_targeted(self):
        self.assertEqual(len(CORRECTIONS), 25)
        self.assertTrue(all(c.source_url.startswith("https://") for c in CORRECTIONS.values()))
        allowed = (
            "cdc.gov",
            "nih.gov",
            "ncbi.nlm.nih.gov",
            "medlineplus.gov",
            "cancer.gov",
            "seer.cancer.gov",
            "who.int",
            "heart.org",
        )
        self.assertTrue(all(any(domain in c.source_url for domain in allowed) for c in CORRECTIONS.values()))

    def test_apply_is_compare_and_set_and_idempotent(self):
        original = draft_document()
        corrected, changed, already, unexpected = apply_corrections(original)

        self.assertEqual(set(changed), set(CORRECTIONS))
        self.assertEqual(already, [])
        self.assertEqual(unexpected, [])
        self.assertNotEqual(corrected, original)
        for cid, correction in CORRECTIONS.items():
            value = corrected["axes"][cid]
            for key in correction.path:
                value = value[key]
            self.assertEqual(value, correction.new)
            self.assertTrue(corrected["axes"][cid]["needs_review"])
            self.assertFalse(any(pattern.search(value) for pattern in PRECISE_EPIDEMIOLOGY_PATTERNS))

        second, second_changed, second_already, second_unexpected = apply_corrections(corrected)
        self.assertEqual(second, corrected)
        self.assertEqual(second_changed, [])
        self.assertEqual(set(second_already), set(CORRECTIONS))
        self.assertEqual(second_unexpected, [])

    def test_drift_is_reported_without_overwrite(self):
        original = draft_document()
        cid = next(iter(CORRECTIONS))
        correction = CORRECTIONS[cid]
        target = original["axes"][cid]
        for key in correction.path[:-1]:
            target = target[key]
        target[correction.path[-1]] = "concurrent reviewed edit"
        snapshot = copy.deepcopy(original)

        corrected, changed, already, unexpected = apply_corrections(original)

        self.assertEqual(original, snapshot)
        self.assertEqual(corrected["axes"][cid], snapshot["axes"][cid])
        self.assertNotIn(cid, changed)
        self.assertNotIn(cid, already)
        self.assertEqual(unexpected[0]["id"], cid)

    def test_audit_blockers_drop_by_twenty_five(self):
        original = draft_document()
        before = audit_document(original, source="legacy-before.json", worklist_data=worklist())
        corrected, _, _, unexpected = apply_corrections(original)
        after = audit_document(corrected, source="legacy-after.json", worklist_data=worklist())

        self.assertEqual(unexpected, [])
        self.assertEqual(before["summary"]["issue_codes"].get("precise_epidemiology_statistic"), 25)
        self.assertNotIn("precise_epidemiology_statistic", after["summary"]["issue_codes"])
        self.assertEqual(before["summary"]["blocking_issues"] - after["summary"]["blocking_issues"], 25)


if __name__ == "__main__":
    unittest.main()
