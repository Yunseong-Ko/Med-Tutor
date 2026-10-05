import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from scripts.build_course_exam_media_label_worklist import (
    SCHEMA_VERSION,
    build_outputs,
    jsonl_bytes,
)


class CourseExamMediaLabelWorklistTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.extracted_dir = self.root / "extracted"
        self.media_root = self.root / "media"
        self.extracted_dir.mkdir()
        self.media_root.mkdir()
        self.concept_registry = self.root / "concept_registry.json"
        self.finding_registry = self.root / "finding_registry.json"
        self.concept_registry.write_text(
            json.dumps(
                {
                    "concepts": {
                        "chronic_myeloid_leukemia": {
                            "disease_concept_id": "chronic_myeloid_leukemia",
                            "node_type": "disease",
                            "aliases": ["CML"],
                            "needs_review": True,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        self.finding_registry.write_text(
            json.dumps(
                {
                    "findings": [
                        {
                            "finding_id": "left_shift",
                            "node_type": "finding",
                            "hpo_label": "Left shift",
                            "needs_review": True,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_packet(
        self,
        *,
        filename="exam.json",
        exam_id="HEME_EXAM",
        media_id="MEDIA_1",
        file_name="image.png",
        duplicate_refs=2,
        linked_question_numbers=None,
    ):
        image_path = self.media_root / file_name
        image_path.write_bytes(b"not-a-real-png-but-stable-for-hash")
        packet = {
            "exam": {
                "source_exam": exam_id,
                "source_file": "source.hwp",
            },
            "media_assets": [
                {
                    "media_id": media_id,
                    "storage_id": "BIN0001",
                    "file_path": str(image_path),
                    "relative_path": file_name,
                    "linked_question_numbers": linked_question_numbers or [1],
                    "needs_review": True,
                }
            ],
            "media_positions": [
                {
                    "question_number": 1,
                    "storage_id": "BIN0001",
                    "paragraph_index": 10,
                }
            ],
            "questions": [
                {
                    "question_id": f"{exam_id}_Q001",
                    "question_number": 1,
                    "stem": "말초혈액도말 현미경 사진에서 left shift를 보인다.",
                    "choices": {
                        "1": "만성 골수성 백혈병",
                        "2": "다른 질환",
                    },
                    "answer": "1",
                    "original_explanation": "이미지는 left shift를 보이며 문항은 CML을 다룬다.",
                    "labels": {
                        "concept_tags": [
                            "chronic_myeloid_leukemia",
                            "left_shift",
                            "unresolved_tag",
                        ],
                        "assessment_domain": "현미경 판독",
                    },
                    "media": {
                        "media_refs": [
                            {
                                "media_id": media_id,
                                "match_method": "hwp_xml_paragraph_flow",
                                "match_confidence": 0.75,
                            }
                            for _ in range(duplicate_refs)
                        ]
                    },
                    "needs_review": True,
                }
            ],
        }
        (self.extracted_dir / filename).write_text(
            json.dumps(packet, ensure_ascii=False),
            encoding="utf-8",
        )
        return image_path

    def build(self):
        return build_outputs(
            extracted_dir=self.extracted_dir,
            media_root=self.media_root,
            concept_registry_path=self.concept_registry,
            finding_registry_path=self.finding_registry,
        )

    def test_builds_question_grounded_candidates_without_approving(self):
        self.write_packet()
        outputs, manifest = self.build()

        self.assertEqual(manifest["summary"]["media_object_count"], 1)
        self.assertEqual(manifest["summary"]["media_occurrence_count"], 1)
        self.assertEqual(manifest["summary"]["raw_question_media_ref_count"], 2)
        self.assertEqual(manifest["summary"]["question_media_link_count"], 1)
        self.assertEqual(manifest["summary"]["collapsed_duplicate_ref_count"], 1)
        self.assertEqual(manifest["summary"]["auto_approved_label_count"], 0)

        task = outputs["media_label_review_worklist.jsonl"][0]
        self.assertEqual(task["schema_version"], SCHEMA_VERSION)
        self.assertEqual(task["review"]["status"], "needs_review")
        self.assertFalse(task["review"]["approved_for_question_use"])
        self.assertFalse(task["review"]["student_visible"])

        snapshot = task["question_contexts"][0]["question"]
        self.assertEqual(snapshot["answer_keys"], ["1"])
        self.assertEqual(snapshot["correct_choice_texts"], ["만성 골수성 백혈병"])
        self.assertIn("left shift", snapshot["original_explanation"])

        candidates = task["candidate_labels"]
        by_kind = {kind: [item for item in candidates if item["kind"] == kind] for kind in {
            "axis", "concept", "finding", "modality"
        }}
        self.assertEqual(by_kind["concept"][0]["target_id"], "chronic_myeloid_leukemia")
        self.assertEqual(by_kind["concept"][0]["relation"], "associated_with_question_context")
        self.assertEqual(by_kind["finding"][0]["target_id"], "left_shift")
        self.assertEqual(by_kind["finding"][0]["relation"], "may_depict")
        self.assertEqual(by_kind["axis"][0]["target_id"], "diagnosis")
        self.assertTrue(any(item["label_text"] == "blood_smear" for item in by_kind["modality"]))
        self.assertFalse(any(item["relation"] == "depicts" for item in candidates))
        self.assertTrue(
            any(
                item["label_text"] == "unresolved_tag"
                for item in task["unresolved_context_tags"]
            )
        )

    def test_same_binary_forms_one_object_and_two_occurrences(self):
        self.write_packet(
            filename="a.json",
            exam_id="EXAM_A",
            media_id="MEDIA_A",
            file_name="shared.png",
            duplicate_refs=1,
        )
        second_packet_path = self.extracted_dir / "b.json"
        packet = json.loads((self.extracted_dir / "a.json").read_text(encoding="utf-8"))
        packet["exam"]["source_exam"] = "EXAM_B"
        packet["media_assets"][0]["media_id"] = "MEDIA_B"
        packet["questions"][0]["question_id"] = "EXAM_B_Q001"
        packet["questions"][0]["media"]["media_refs"][0]["media_id"] = "MEDIA_B"
        second_packet_path.write_text(json.dumps(packet), encoding="utf-8")

        outputs, manifest = self.build()
        self.assertEqual(manifest["summary"]["media_object_count"], 1)
        self.assertEqual(manifest["summary"]["media_occurrence_count"], 2)
        self.assertEqual(manifest["summary"]["duplicate_binary_group_count"], 1)
        self.assertEqual(manifest["summary"]["duplicate_binary_extra_occurrence_count"], 1)
        media_object = outputs["media_objects.draft.jsonl"][0]
        self.assertEqual(media_object["duplicate_occurrence_count"], 2)
        self.assertEqual(len(media_object["occurrence_ids"]), 2)

    def test_comprehensive_photo_number_mismatch_is_explicit(self):
        self.write_packet(
            exam_id="COMPREHENSIVE_2026_1CHA_1교시",
            linked_question_numbers=[99],
            duplicate_refs=1,
        )
        outputs, _ = self.build()
        link = outputs["question_media_links.draft.jsonl"][0]
        self.assertIn(
            "asset_linked_number_is_photo_label_not_question_fk",
            link["mismatch_flags"],
        )
        self.assertEqual(link["link_method"], "hwp_xml_paragraph_flow")
        self.assertEqual(link["review_status"], "needs_review")

    def test_rows_validate_and_second_build_is_deterministic(self):
        self.write_packet(duplicate_refs=1)
        first_outputs, first_manifest = self.build()
        second_outputs, second_manifest = self.build()
        self.assertEqual(first_manifest, second_manifest)
        for name in first_outputs:
            self.assertEqual(
                jsonl_bytes(first_outputs[name]),
                jsonl_bytes(second_outputs[name]),
            )

        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "course_exam_media_labeling.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for rows in first_outputs.values():
            for row in rows:
                jsonschema.validate(row, schema)


if __name__ == "__main__":
    unittest.main()
