import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from scripts.merge_media_visual_review_candidates import (
    build_outputs,
    manifest_bytes,
    normalize_label_key,
    records_bytes,
)


class MediaVisualReviewCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.batch_dir = self.root / "batches"
        self.batch_dir.mkdir()
        self.worklist = self.root / "worklist.jsonl"
        self.finding_registry = self.root / "finding_registry.json"
        self.schema = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "media_visual_review_candidate.schema.json"
        )
        self.output = self.root / "candidates.jsonl"
        self.manifest = self.root / "manifest.json"
        self.finding_registry.write_text(
            json.dumps(
                {
                    "findings": [
                        {
                            "finding_id": "left_shift",
                            "node_type": "finding",
                            "needs_review": True,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def task(self, suffix: str = "1"):
        fill = suffix[-1]
        image_path = self.root / f"image_{suffix}.png"
        image_payload = f"stable-fixture-image-{suffix}".encode("utf-8")
        image_path.write_bytes(image_payload)
        image_sha256 = hashlib.sha256(image_payload).hexdigest()
        return {
            "task_id": "mreview_" + fill * 24,
            "pilot_group": "hematology_oncology_first",
            "media_occurrence": {
                "occurrence_id": "mediaocc_" + fill * 24,
                "media_object_id": "mediaobj_" + image_sha256,
                "file": {"path": str(image_path)},
            },
            "question_contexts": [
                {
                    "question": {
                        "question_id": f"HEME_Q{suffix}",
                        "stem": "말초혈액도말에서 left shift를 보인다.",
                        "answer_keys": ["1"],
                        "correct_choice_texts": ["만성 골수성 백혈병"],
                    }
                }
            ],
            "candidate_labels": [
                {
                    "kind": "concept",
                    "label_text": "chronic_myeloid_leukemia",
                    "target_id": "chronic_myeloid_leukemia",
                    "confidence": 0.8,
                },
                {
                    "kind": "axis",
                    "label_text": "diagnosis",
                    "target_id": "diagnosis",
                    "confidence": 0.7,
                },
            ],
        }

    def decision(self, suffix: str = "1"):
        fill = suffix[-1]
        return {
            "task_id": "mreview_" + fill * 24,
            "image_readability": "readable",
            "visual_description": "성숙 호중구와 미성숙 과립구가 보이는 도말 후보",
            "modality_labels": [
                {
                    "label_text": "blood_smear_microscopy",
                    "confidence": 0.95,
                    "basis": "visual_only",
                }
            ],
            "specimen_labels": [
                {
                    "label_text": "peripheral_blood",
                    "confidence": 0.85,
                    "basis": "visual_and_question",
                }
            ],
            "finding_labels": [
                {
                    "label_text": "left_shift",
                    "confidence": 0.75,
                    "basis": "visual_and_question",
                },
                {
                    "label_text": "chronic_myeloid_leukemia",
                    "confidence": 0.6,
                    "basis": "question_only",
                },
            ],
            "visible_annotations": [],
            "embedded_text": [],
            "visual_confidence": 0.8,
            "alignment_status": "supported",
            "answer_leak_risk": "low",
            "deidentification_risk_observed": "unknown",
            "alignment_notes": "이미지와 문항 맥락이 일치하지만 진단은 확정하지 않음.",
        }

    def args(self, *, allow_incomplete=False, selection=None):
        return argparse.Namespace(
            worklist=self.worklist,
            selection=selection,
            batch_dir=self.batch_dir,
            output=self.output,
            manifest=self.manifest,
            schema=self.schema,
            finding_registry=self.finding_registry,
            allow_incomplete=allow_incomplete,
            check=False,
        )

    def write_worklist(self, tasks):
        self.worklist.write_text(
            "".join(json.dumps(task, ensure_ascii=False) + "\n" for task in tasks),
            encoding="utf-8",
        )

    def write_batch(self, name, decisions):
        (self.batch_dir / name).write_text(
            json.dumps(decisions, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_normalizes_visual_and_question_context_without_approval(self):
        self.write_worklist([self.task()])
        self.write_batch("batch_01.json", [self.decision()])

        records, manifest = build_outputs(self.args())
        self.assertEqual(len(records), 1)
        record = records[0]
        jsonschema.validate(
            record,
            json.loads(self.schema.read_text(encoding="utf-8")),
        )

        findings = {
            item["label_text"]: item
            for item in record["visual_assessment"]["depicted_finding_candidates"]
        }
        self.assertEqual(findings["left_shift"]["target_id"], "left_shift")
        self.assertEqual(
            findings["left_shift"]["status"],
            "visually_supported_candidate",
        )
        self.assertEqual(
            findings["chronic_myeloid_leukemia"]["status"],
            "question_context_candidate",
        )
        self.assertEqual(
            record["question_alignment"]["associated_concept_candidates"][0]["basis"],
            "question_only",
        )
        self.assertFalse(record["safety"]["medical_approval"])
        self.assertTrue(record["safety"]["rights_review_required"])
        self.assertTrue(record["safety"]["deidentification_review_required"])
        self.assertEqual(
            record["safety"]["deidentification_risk_observed"],
            "unknown",
        )
        self.assertFalse(record["safety"]["approved_for_question_use"])
        self.assertFalse(record["safety"]["student_visible"])
        self.assertEqual(record["review_status"], "human_review_required")
        self.assertEqual(manifest["summary"]["missing_task_count"], 0)
        self.assertEqual(manifest["review_queues"]["conflict_task_ids"], [])
        self.assertEqual(
            manifest["review_queues"]["deidentification_risk_task_ids"],
            [],
        )
        self.assertEqual(
            normalize_label_key("Peripheral blood-smear microscopy"),
            "peripheral_blood_smear_microscopy",
        )

    def test_requires_complete_unique_pilot_coverage(self):
        self.write_worklist([self.task("1"), self.task("2")])
        self.write_batch("batch_01.json", [self.decision("1")])
        with self.assertRaisesRegex(ValueError, "Missing 1 selected decisions"):
            build_outputs(self.args())

        records, manifest = build_outputs(self.args(allow_incomplete=True))
        self.assertEqual(len(records), 1)
        self.assertEqual(manifest["summary"]["missing_task_count"], 1)

        self.write_batch("batch_02.json", [self.decision("1")])
        with self.assertRaisesRegex(ValueError, "duplicate decision"):
            build_outputs(self.args(allow_incomplete=True))

    def test_cumulative_selection_can_include_general_backlog(self):
        first = self.task("1")
        second = self.task("2")
        second["pilot_group"] = "general_backlog"
        self.write_worklist([first, second])
        self.write_batch(
            "batch_01.json",
            [self.decision("1"), self.decision("2")],
        )
        selection = self.root / "selection.json"
        selection.write_text(
            json.dumps(
                {
                    "worklist": {
                        "sha256": hashlib.sha256(
                            self.worklist.read_bytes()
                        ).hexdigest()
                    },
                    "rounds": [
                        {
                            "round_id": "cumulative",
                            "task_ids": [first["task_id"], second["task_id"]],
                        }
                    ],
                    "selected_task_ids": [
                        first["task_id"],
                        second["task_id"],
                    ],
                }
            ),
            encoding="utf-8",
        )

        records, manifest = build_outputs(self.args(selection=selection))
        self.assertEqual(len(records), 2)
        self.assertEqual(manifest["summary"]["selected_task_count"], 2)
        self.assertEqual(
            manifest["selection"]["rounds"],
            [{"round_id": "cumulative", "task_count": 2}],
        )
        self.assertEqual(
            manifest["round_summary"]["cumulative"],
            {
                "selected_task_count": 2,
                "record_count": 2,
                "missing_task_count": 0,
            },
        )

    def test_rejects_changed_or_missing_source_image(self):
        task = self.task()
        self.write_worklist([task])
        self.write_batch("batch_01.json", [self.decision()])
        Path(task["media_occurrence"]["file"]["path"]).write_bytes(b"tampered")

        with self.assertRaisesRegex(ValueError, "image SHA-256 mismatch"):
            build_outputs(self.args())

    def test_output_and_manifest_are_deterministic_and_use_requested_path(self):
        self.write_worklist([self.task()])
        self.write_batch("batch_01.json", [self.decision()])
        first_records, first_manifest = build_outputs(self.args())
        second_records, second_manifest = build_outputs(self.args())
        self.assertEqual(first_records, second_records)
        self.assertEqual(first_manifest, second_manifest)

        payload = records_bytes(first_records)
        rendered = json.loads(
            manifest_bytes(first_manifest, payload, self.output).decode("utf-8")
        )
        self.assertEqual(rendered["output"]["path"], str(self.output.resolve()))
        self.assertEqual(rendered["output"]["row_count"], 1)


if __name__ == "__main__":
    unittest.main()
