import unittest

from src.services.faculty_item_intents import (
    build_department_catalog,
    recommend_item_intents,
)


def concept(
    specialty: str,
    *,
    aliases: list[str],
    domains: list[str],
    edges: dict,
    axes: dict | None = None,
    evidence: bool = True,
) -> dict:
    return {
        "specialty": specialty,
        "aliases": aliases,
        "assessment_domains": domains,
        "edges": edges,
        "clinical_axes": axes or {},
        "evidence": {"harrison": {"chapter": 1}} if evidence else {},
        "needs_review": True,
        "gen_ready": False,
    }


class FacultyItemIntentTests(unittest.TestCase):
    def setUp(self):
        self.concepts = {
            "multiple_myeloma": concept(
                "혈액종양",
                aliases=["다발골수종", "multiple myeloma"],
                domains=["treatment_principle", "pathophysiology"],
                edges={
                    "treated_with": [{"id": "therapy"}],
                    "indicated_for": [{"id": "regimen"}],
                    "differential_of": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                    "due_to": [{"id": "light_chain"}],
                    "presents_with": [{"id": "bone_pain"}],
                },
                axes={"treatment": {"summary": "draft"}, "pathophysiology": {"summary": "draft"}},
            ),
            "acute_myeloid_leukemia": concept(
                "혈액종양",
                aliases=["급성골수성백혈병", "AML"],
                domains=["diagnosis"],
                edges={
                    "diagnosed_by": [{"id": "marrow"}, {"id": "flow"}],
                    "differential_of": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                    "presents_with": [{"id": "pancytopenia"}],
                },
                axes={"diagnosis": {"summary": "draft"}},
            ),
            "tumor_lysis_syndrome": concept(
                "혈액종양",
                aliases=["종양용해증후군", "TLS"],
                domains=["emergency_management"],
                edges={
                    "treated_with": [{"id": "rasburicase"}],
                    "indicated_for": [{"id": "hydration"}],
                    "differential_of": [{"id": "a"}, {"id": "b"}],
                },
                axes={"treatment": {"summary": "draft"}},
            ),
            "chronic_myeloid_leukemia": concept(
                "혈액내과",
                aliases=["만성골수성백혈병", "CML"],
                domains=["pharmacotherapy"],
                edges={
                    "treated_with": [{"id": "tki"}],
                    "indicated_for": [{"id": "tki"}],
                    "contraindicated_for": [{"id": "warning"}],
                    "differential_of": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                },
                axes={"treatment": {"summary": "draft"}},
            ),
            "iron_deficiency_anemia": concept(
                "혈액종양",
                aliases=["철결핍성빈혈", "IDA"],
                domains=["test_interpretation"],
                edges={
                    "diagnosed_by": [{"id": "ferritin"}],
                    "differential_of": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                },
                axes={"diagnosis": {"summary": "draft"}},
            ),
            "aplastic_anemia": concept(
                "혈액종양",
                aliases=["재생불량빈혈", "aplastic anemia"],
                domains=["prognosis"],
                edges={"differential_of": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
                axes={"prognosis": {"summary": "draft"}},
            ),
            "colorectal_cancer": concept(
                "소화기",
                aliases=["대장암"],
                domains=["treatment"],
                edges={"treated_with": [{"id": "surgery"}]},
                axes={"treatment": {"summary": "draft"}},
            ),
        }
        self.records = {
            concept_id: {"label": value["aliases"][0], "title": value["aliases"][0]}
            for concept_id, value in self.concepts.items()
        }

    def test_catalog_reports_department_availability(self):
        payload = build_department_catalog(self.concepts)
        heme = next(row for row in payload["departments"] if row["id"] == "hematology_oncology")
        self.assertEqual(heme["concept_count"], 6)
        self.assertEqual(heme["candidate_ready_count"], 6)
        self.assertEqual(heme["availability"], "available")
        self.assertFalse(payload["defaults"].get("lecture_required", False))

    def test_recommendations_are_department_scoped_balanced_and_review_gated(self):
        payload = recommend_item_intents(
            self.concepts,
            self.records,
            department="혈액종양내과",
            requested_item_count=3,
            candidate_count=6,
            question_counts={"multiple_myeloma": 5},
        )
        self.assertEqual(payload["department"]["id"], "hematology_oncology")
        self.assertEqual(payload["requested_item_count"], 3)
        self.assertEqual(payload["candidate_count"], 6)
        self.assertNotIn("colorectal_cancer", {row["target"]["concept_id"] for row in payload["candidates"]})
        self.assertGreaterEqual(
            len({row["assessment_claim"]["task_family"] for row in payload["candidates"]}),
            3,
        )
        for row in payload["candidates"]:
            self.assertTrue(row["evidence_contract"]["needs_review"])
            self.assertFalse(row["evidence_contract"]["gen_ready"])
            self.assertFalse(row["evidence_contract"]["claim_evidence_ready"])
            self.assertEqual(row["task_model"]["format"], "clinical_case")
            self.assertEqual(row["task_model"]["reasoning_hops"], 2)
            self.assertIn("selection_contract", row)
        self.assertFalse(payload["selection_rules"]["lecture_required"])
        self.assertFalse(payload["review_contract"]["student_auto_release"])

    def test_exclusion_and_priority_task_are_applied(self):
        payload = recommend_item_intents(
            self.concepts,
            self.records,
            department="hematology_oncology",
            requested_item_count=2,
            candidate_count=4,
            priority_tasks=["mechanism"],
            exclude_concept_ids=["acute_myeloid_leukemia"],
        )
        ids = {row["target"]["concept_id"] for row in payload["candidates"]}
        self.assertNotIn("acute_myeloid_leukemia", ids)
        myeloma = next(row for row in payload["candidates"] if row["target"]["concept_id"] == "multiple_myeloma")
        self.assertEqual(myeloma["assessment_claim"]["task"], "mechanism")

    def test_requested_count_must_match_faculty_assignment(self):
        with self.assertRaisesRegex(ValueError, "2개 또는 3개"):
            recommend_item_intents(
                self.concepts,
                self.records,
                department="혈액종양내과",
                requested_item_count=1,
            )


if __name__ == "__main__":
    unittest.main()
