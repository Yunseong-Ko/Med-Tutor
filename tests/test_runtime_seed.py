import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.seed_runtime_data import REQUIRED_FILES, REQUIRED_GLOBS, seed_runtime, verify_runtime


class RuntimeSeedTests(unittest.TestCase):
    def _build_seed(self, root: Path) -> None:
        qbank_bytes = json.dumps({"questions": [{"id": "demo"}]}).encode("utf-8")
        qbank_sha = hashlib.sha256(qbank_bytes).hexdigest()
        for relative in REQUIRED_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative == "student/qbank.json":
                path.write_bytes(qbank_bytes)
            elif relative == "student/qbank_enrichment.draft.json":
                path.write_text(json.dumps({
                    "schema_version": "paccine.qbank_enrichment.draft.v1",
                    "built_against_sha256": qbank_sha,
                    "drafts": {"demo": {"explanation": "seed draft", "needs_review": True}},
                }), encoding="utf-8")
            elif relative == "student/qbank_enrichment.releases.json":
                path.write_text(json.dumps({
                    "schema_version": "paccine.qbank_enrichment.releases.v1",
                    "built_against_sha256": qbank_sha,
                    "releases": {},
                }), encoding="utf-8")
            else:
                path.write_text("{}", encoding="utf-8")
        examples = {
            "studio/question_bank/demo.question_set.json": "{}",
            "course_exams/extracted/demo.json": "{}",
            "course_exams/media/demo/image.png": "image",
            "medlegal/cases/demo.case.json": "{}",
        }
        for relative, value in examples.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")

    def test_seed_copies_missing_files_and_verifies(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            seed = base / "seed"
            data = base / "data"
            self._build_seed(seed)
            marker = seed_runtime(seed, data)
            status = verify_runtime(data)
            self.assertGreater(marker["copied_files"], 0)
            self.assertTrue(status["ready"])
            self.assertEqual(status["question_count"], 1)

    def test_seed_does_not_overwrite_persistent_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            seed = base / "seed"
            data = base / "data"
            self._build_seed(seed)
            seed_runtime(seed, data)
            release_path = data / "studio/student_releases.json"
            release_path.write_text('{"preserved": true}', encoding="utf-8")
            seed_runtime(seed, data)
            self.assertEqual(json.loads(release_path.read_text(encoding="utf-8")), {"preserved": True})

    def test_seed_refreshes_drafts_but_preserves_real_server_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            seed = base / "seed"
            data = base / "data"
            self._build_seed(seed)
            seed_runtime(seed, data)

            qbank_sha = hashlib.sha256((data / "student/qbank.json").read_bytes()).hexdigest()
            release_path = data / "student/qbank_enrichment.releases.json"
            release_path.write_text(json.dumps({
                "schema_version": "paccine.qbank_enrichment.releases.v1",
                "built_against_sha256": qbank_sha,
                "releases": {
                    "demo": {
                        "approved": True,
                        "medical_approval": True,
                        "demo_release": False,
                        "needs_real_faculty_review": False,
                        "review_status": "faculty_approved",
                        "reviewer_id": "faculty@example.edu",
                        "reviewed_at": "2026-07-23T12:00:00+00:00",
                        "explanation": "server-approved explanation",
                    }
                },
            }), encoding="utf-8")

            draft_path = seed / "student/qbank_enrichment.draft.json"
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            draft["drafts"]["demo"]["explanation"] = "new deployed draft"
            draft_path.write_text(json.dumps(draft), encoding="utf-8")
            seed_release_path = seed / "student/qbank_enrichment.releases.json"
            seed_release_path.write_text(json.dumps({
                "schema_version": "paccine.qbank_enrichment.releases.v1",
                "built_against_sha256": qbank_sha,
                "releases": {
                    "demo": {
                        "approved": True,
                        "demo_release": True,
                        "needs_real_faculty_review": True,
                        "explanation": "unsafe demo replacement",
                    }
                },
            }), encoding="utf-8")

            marker = seed_runtime(seed, data)
            stored_draft = json.loads((data / "student/qbank_enrichment.draft.json").read_text(encoding="utf-8"))
            stored_release = json.loads(release_path.read_text(encoding="utf-8"))
            self.assertEqual(stored_draft["drafts"]["demo"]["explanation"], "new deployed draft")
            self.assertEqual(
                stored_release["releases"]["demo"]["explanation"],
                "server-approved explanation",
            )
            self.assertGreaterEqual(marker["synced_overlays"], 1)

    def test_seed_rejects_overlay_for_another_qbank(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            seed = base / "seed"
            data = base / "data"
            self._build_seed(seed)
            draft_path = seed / "student/qbank_enrichment.draft.json"
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            draft["built_against_sha256"] = "0" * 64
            draft_path.write_text(json.dumps(draft), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                seed_runtime(seed, data)

    def test_verify_fails_when_a_required_group_is_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._build_seed(root)
            for path in root.glob(REQUIRED_GLOBS[0]):
                path.unlink()
            with self.assertRaises(RuntimeError):
                verify_runtime(root)


if __name__ == "__main__":
    unittest.main()
