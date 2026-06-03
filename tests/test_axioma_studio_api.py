import io
import json
import unittest

from fastapi.testclient import TestClient

from api_server import app
from src.services.lecture_studio import (
    MEDIA_ASSET_DIR,
    MEDIA_INDEX_PATH,
    QUESTION_BANK_DIR,
    REVIEW_SET_DIR,
    archive_question_set,
    attach_visual_refs,
    visual_candidate_priority,
)


class AxiomaStudioApiTests(unittest.TestCase):
    def test_health(self):
        client = TestClient(app)
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_models_catalog_includes_claude_and_openai(self):
        client = TestClient(app)
        response = client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        providers = {item["id"]: item for item in response.json()["providers"]}
        self.assertIn("claude-cli", providers)
        self.assertIn("anthropic", providers)
        self.assertIn("openai", providers)
        self.assertIn("gpt-5.2", [model["id"] for model in providers["openai"]["models"]])
        self.assertIn("claude-sonnet-4-6", [model["id"] for model in providers["anthropic"]["models"]])

    def test_prompt_only_generation_from_txt(self):
        client = TestClient(app)
        lecture = (
            "소장폐색은 복부 수술 후 유착이 흔한 원인이다. "
            "구토, 복부팽만, 산통성 복통, air-fluid level이 중요하다. "
            "교수 검수 전에는 생성 문항을 초안으로만 사용한다."
        )
        response = client.post(
            "/api/generate",
            data={
                "subject": "외과",
                "unit": "소장폐색",
                "num_questions": "2",
                "difficulty": "보통",
                "question_type": "clinical_case",
                "reference_policy": "local_open",
                "provider": "prompt-only",
                "model": "prompt-only",
            },
            files={
                "lecture_file": ("demo_lecture.txt", io.BytesIO(lecture.encode("utf-8")), "text/plain")
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "prompt_ready")
        self.assertEqual(payload["provider"], "prompt-only")
        self.assertIn("prompt", payload["paths"])
        self.assertIn("image_candidates", payload)

    def test_media_bank_upload_and_list(self):
        client = TestClient(app)
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
            b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT"
            b"\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA"
            b"\xe2&\xb8\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        asset = {}
        try:
            response = client.post(
                "/api/media",
                data={
                    "asset_type": "radiology",
                    "modality": "CT",
                    "subject": "신경과",
                    "unit": "뇌혈관질환",
                    "diagnosis": "test hemorrhage",
                    "caption": "test media asset",
                    "key_findings": "CT, hemorrhage",
                    "deidentified": "true",
                    "approved_for_question_use": "true",
                },
                files={"media_file": ("test.png", io.BytesIO(png), "image/png")},
            )
            self.assertEqual(response.status_code, 200)
            asset = response.json()["asset"]
            self.assertEqual(asset["modality"], "CT")
            self.assertTrue(asset["approved_for_question_use"])

            list_response = client.get("/api/media")
            self.assertEqual(list_response.status_code, 200)
            asset_ids = [item["asset_id"] for item in list_response.json()["assets"]]
            self.assertIn(asset["asset_id"], asset_ids)

            delete_response = client.delete(f"/api/media/{asset['asset_id']}")
            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.json()["deleted"]["asset_id"], asset["asset_id"])

            list_after_delete = client.get("/api/media")
            asset_ids_after_delete = [item["asset_id"] for item in list_after_delete.json()["assets"]]
            self.assertNotIn(asset["asset_id"], asset_ids_after_delete)
        finally:
            if asset.get("stored_name"):
                (MEDIA_ASSET_DIR / asset["stored_name"]).unlink(missing_ok=True)
            if asset.get("asset_id") and MEDIA_INDEX_PATH.exists():
                rows = json.loads(MEDIA_INDEX_PATH.read_text(encoding="utf-8"))
                rows = [row for row in rows if row.get("asset_id") != asset["asset_id"]]
                MEDIA_INDEX_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_question_sets_endpoint(self):
        client = TestClient(app)
        response = client.get("/api/question-sets?limit=5")
        self.assertEqual(response.status_code, 200)
        self.assertIn("sets", response.json())

    def test_question_set_detail_edit_and_approve_flow(self):
        client = TestClient(app)
        set_id = "unit_review_flow"
        try:
            archive_question_set(
                set_id,
                {
                    "source_name": "unit_lecture.txt",
                    "provider": "prompt-only",
                    "model": "prompt-only",
                    "subject": "신경과",
                    "unit": "뇌혈관질환",
                    "question_type": "clinical_case",
                    "reference_policy": "local_open",
                    "image_policy": "none",
                },
                [
                    {
                        "question_id": "Q_REVIEW_001",
                        "problem": "초안 문제",
                        "options": ["A", "B", "C", "D", "E"],
                        "answer": 1,
                        "explanation": "초안 해설",
                        "review_status": "draft",
                        "needs_review": True,
                        "review_reasons": ["reference_needed"],
                        "reference_notes": [
                            {"ref_no": 1, "source": "unit_lecture.txt", "basis": "테스트 근거"}
                        ],
                    }
                ],
            )

            detail = client.get(f"/api/question-sets/{set_id}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["summary"]["question_count"], 1)

            edited = client.patch(
                f"/api/question-sets/{set_id}/questions/Q_REVIEW_001",
                json={
                    "updates": {
                        "problem": "수정된 문제",
                        "options": ["가", "나", "다", "라", "마"],
                        "answer": 2,
                        "explanation": "수정된 해설",
                        "review_status": "needs_revision",
                        "review_reasons": "wording_check",
                    }
                },
            )
            self.assertEqual(edited.status_code, 200)
            self.assertEqual(edited.json()["question"]["problem"], "수정된 문제")
            self.assertEqual(edited.json()["question"]["answer"], 2)
            self.assertTrue(edited.json()["question"]["needs_review"])

            approved = client.post(f"/api/question-sets/{set_id}/questions/Q_REVIEW_001/approve", json={})
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(approved.json()["question"]["review_status"], "approved")
            self.assertFalse(approved.json()["question"]["needs_review"])
            self.assertEqual(approved.json()["summary"]["approved_count"], 1)
        finally:
            (QUESTION_BANK_DIR / f"{set_id}.question_set.json").unlink(missing_ok=True)
            (REVIEW_SET_DIR / f"{set_id}.review_set.json").unlink(missing_ok=True)

    def test_image_candidates_prioritize_clinical_and_pathology_visuals(self):
        ct_candidate = {
            "type": "slide_snapshot",
            "source_name": "lecture.pptx",
            "locator_label": "slide 7",
            "text_preview": "흉부 CT 영상에서 보이는 병변",
        }
        pathology_candidate = {
            "type": "slide_snapshot",
            "source_name": "lecture.pptx",
            "locator_label": "slide 8",
            "text_preview": "병리 슬라이드 조직병리 현미경 소견",
        }
        summary_candidate = {
            "type": "slide_snapshot",
            "source_name": "lecture.pptx",
            "locator_label": "slide 1",
            "text_preview": "학습목표 및 요약",
        }

        self.assertGreaterEqual(visual_candidate_priority(ct_candidate), 0.45)
        self.assertGreaterEqual(visual_candidate_priority(pathology_candidate), 0.35)
        self.assertLess(visual_candidate_priority(summary_candidate), 0.2)

    def test_image_based_force_attaches_high_value_visual_candidate(self):
        records = [
            {
                "problem": "다음 자료를 보고 가장 적절한 진단을 고르시오.",
                "pma_solution": {"source_anchor": "slide 7 CT 영상"},
                "needs_review": False,
            }
        ]
        candidates = [
            {
                "id": "slide_1",
                "type": "slide_snapshot",
                "source_name": "lecture.pptx",
                "page": 1,
                "locator_label": "slide 1",
                "url": "/api/studio/images/slide_1.png",
                "text_preview": "학습목표 및 요약",
                "_tokens": {"학습목표", "요약"},
            },
            {
                "id": "slide_7",
                "type": "slide_snapshot",
                "source_name": "lecture.pptx",
                "page": 7,
                "locator_label": "slide 7",
                "url": "/api/studio/images/slide_7.png",
                "text_preview": "흉부 CT 영상",
                "_tokens": {"흉부", "ct", "영상"},
            },
        ]

        attached = attach_visual_refs(records, candidates, force=True)
        self.assertEqual(attached[0]["image_refs"][0]["id"], "slide_7")
        self.assertGreaterEqual(attached[0]["image_refs"][0]["visual_priority"], 0.45)

    def test_image_based_can_attach_multiple_selected_visuals(self):
        records = [
            {
                "problem": "다음 CT와 병리 슬라이드를 함께 보고 진단을 고르시오.",
                "pma_solution": {"source_anchor": "CT pathology"},
                "needs_review": False,
            }
        ]
        candidates = [
            {
                "id": "ct_1",
                "type": "media_bank_asset",
                "source_name": "ct.png",
                "locator_label": "CT",
                "url": "/api/media/assets/ct.png",
                "text_preview": "CT hemorrhage",
                "visual_priority": 0.45,
                "_tokens": {"ct", "hemorrhage"},
            },
            {
                "id": "path_1",
                "type": "media_bank_asset",
                "source_name": "path.png",
                "locator_label": "Pathology",
                "url": "/api/media/assets/path.png",
                "text_preview": "pathology biopsy",
                "visual_priority": 0.45,
                "_tokens": {"pathology", "biopsy"},
            },
            {
                "id": "pbs_1",
                "type": "media_bank_asset",
                "source_name": "pbs.png",
                "locator_label": "PBS",
                "url": "/api/media/assets/pbs.png",
                "text_preview": "peripheral blood smear",
                "visual_priority": 0.45,
                "_tokens": {"pbs", "blood", "smear"},
            },
        ]

        attached = attach_visual_refs(records, candidates, force=True, max_refs_per_question=3)
        self.assertEqual(len(attached[0]["image_refs"]), 3)
        self.assertEqual({ref["id"] for ref in attached[0]["image_refs"]}, {"ct_1", "path_1", "pbs_1"})


if __name__ == "__main__":
    unittest.main()
