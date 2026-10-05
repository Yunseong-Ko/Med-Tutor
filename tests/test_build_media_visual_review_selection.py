import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from scripts.build_media_visual_review_selection import (
    PHOTO_RICH_MODALITIES,
    build_selection,
    render,
)


class MediaVisualReviewSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.worklist = self.root / "worklist.jsonl"
        self.schema = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "media_visual_review_selection.schema.json"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def task(task_hex, pilot_group, modalities, priority=1000):
        return {
            "task_id": "mreview_" + task_hex * 24,
            "pilot_group": pilot_group,
            "priority_score": priority,
            "question_contexts": [{"question": {"question_id": task_hex}}],
            "candidate_labels": [
                {"kind": "modality", "label_text": label}
                for label in modalities
            ],
        }

    def write(self, rows):
        self.worklist.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_selects_heme_and_photo_rich_modalities_deterministically(self):
        rows = [
            self.task("a", "hematology_oncology_first", []),
            self.task("b", "general_backlog", ["endoscopy"], priority=900),
            self.task("c", "general_backlog", ["clinical_photo"], priority=1100),
            self.task("d", "general_backlog", ["xray"], priority=800),
        ]
        self.write(rows)
        first = build_selection(self.worklist)
        second = build_selection(self.worklist)
        self.assertEqual(first, second)
        self.assertEqual(render(first), render(second))

        rounds = {item["round_id"]: item for item in first["rounds"]}
        self.assertEqual(
            rounds["hematology_oncology_first"]["task_ids"],
            ["mreview_" + "a" * 24],
        )
        self.assertEqual(
            rounds["photo_rich_modalities_second"]["task_ids"],
            ["mreview_" + "c" * 24, "mreview_" + "b" * 24],
        )
        self.assertNotIn("mreview_" + "d" * 24, first["selected_task_ids"])
        self.assertIn("clinical_photo", PHOTO_RICH_MODALITIES)
        self.assertEqual(first["summary"]["selected_task_count"], 3)
        self.assertEqual(first["summary"]["remaining_unselected_task_count"], 1)

        jsonschema.validate(
            first,
            json.loads(self.schema.read_text(encoding="utf-8")),
        )


if __name__ == "__main__":
    unittest.main()
