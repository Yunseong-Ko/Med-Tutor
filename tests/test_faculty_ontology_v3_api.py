import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import api_server


class FacultyOntologyV3ApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.registry = root / "concept_registry.json"
        self.index = root / "registry_index.json"
        self.query_map = root / "ontology_query_map.json"
        self.links = root / "question_links.json"
        self.registry.write_text(
            json.dumps(
                {
                    "concepts": {
                        "multiple_myeloma": {
                            "disease_concept_id": "multiple_myeloma",
                            "node_type": "disease",
                            "aliases": ["plasma cell myeloma"],
                            "specialty": "혈액종양",
                            "assessment_domains": ["diagnosis"],
                            "edges": {"diagnosed_by": [{"id": "bone_marrow_biopsy"}]},
                            "clinical_axes": {"diagnosis": {"summary": "draft"}, "needs_review": True},
                            "evidence": {"harrison": {"chapter": 105}},
                            "needs_review": True,
                            "gen_ready": False,
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.index.write_text(
            json.dumps({"concepts": [{"id": "multiple_myeloma", "title": "Multiple Myeloma", "node_type": "disease"}]}),
            encoding="utf-8",
        )
        self.query_map.write_text(json.dumps({"multiple_myeloma": "multiple myeloma"}), encoding="utf-8")
        self.links.write_text(
            json.dumps(
                {
                    "concept_index": {"multiple_myeloma": ["PRIVATE_Q1"]},
                    "questions": {"PRIVATE_Q1": {"concept": "multiple_myeloma", "label": "다발골수종"}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.patchers = [
            patch.object(api_server, "ONTOLOGY_CONCEPT_REGISTRY_PATH", self.registry),
            patch.object(api_server, "ONTOLOGY_REGISTRY_INDEX_PATH", self.index),
            patch.object(api_server, "ONTOLOGY_QUERY_MAP_PATH", self.query_map),
            patch.object(api_server, "STUDENT_QUESTION_LINKS_PATH", self.links),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client = TestClient(api_server.app)
        self.client.cookies.set("paccine_role", "faculty")

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tempdir.cleanup()

    def test_korean_label_search_returns_review_gated_concept(self):
        response = self.client.get("/api/ontology/search", params={"q": "다발골수종"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["disease_concept_id"], "multiple_myeloma")
        self.assertEqual(payload["results"][0]["label"], "다발골수종")
        self.assertTrue(payload["results"][0]["needs_review"])
        self.assertFalse(payload["results"][0]["gen_ready"])
        self.assertNotIn("PRIVATE_Q1", json.dumps(payload, ensure_ascii=False))

    def test_id_search_returns_relation_and_question_counts(self):
        payload = self.client.get("/api/ontology/search", params={"q": "multiple_myeloma"}).json()
        item = payload["results"][0]
        self.assertEqual(item["relation_count"], 1)
        self.assertEqual(item["axis_count"], 1)
        self.assertEqual(item["question_count"], 1)
        self.assertTrue(item["has_harrison"])

    def test_faculty_default_is_v3_and_legacy_route_redirects_to_current(self):
        current = self.client.get("/faculty-studio-v2/")
        legacy = self.client.get("/faculty-studio-v2/legacy", follow_redirects=False)
        self.assertIn("Ontology 문항 생성 작업실", current.text)
        self.assertEqual(legacy.status_code, 307)
        self.assertEqual(legacy.headers["location"], "/faculty-studio-v2/")

    def test_frontend_does_not_promote_all_axis_candidates_to_explicit_targets(self):
        script = self.client.get("/faculty-studio-v3/app.js").text
        self.assertIn("selectedAxisIds: []", script)
        self.assertIn("return [...state.selectedAxisIds];", script)

    def test_frontend_uses_persistent_multi_question_job_flow(self):
        script = self.client.get("/faculty-studio-v3/app.js").text
        page = self.client.get("/faculty-studio-v3/").text
        self.assertIn('generationJobStorageKey = "paccine.faculty_generation_job.v1"', script)
        self.assertIn('api("/api/generation-jobs"', script)
        self.assertIn("/retry", script)
        self.assertIn("restoreGenerationJob", script)
        self.assertIn("실패 문항만 다시 시도", script)
        self.assertIn("POST /api/generation-jobs", page)
        self.assertIn("generation-job.css", page)

    def test_frontend_integrates_department_intent_flow_without_replacing_manual_mode(self):
        script = self.client.get("/faculty-studio-v3/app.js").text
        page = self.client.get("/faculty-studio-v3/").text
        review_script = self.client.get("/faculty-studio-v2/faculty-workspace.js").text

        self.assertIn("어느 과 문항을 출제하시나요?", page)
        self.assertIn('intentMode: "recommended"', script)
        self.assertIn("selectedIntentIds: new Set()", script)
        self.assertIn('api("/api/faculty/item-intents/departments")', script)
        self.assertIn('api("/api/faculty/item-intents/recommendations"', script)
        self.assertIn('api("/api/faculty/item-intents/generation-jobs"', script)
        self.assertIn("manual-step-2", page)
        self.assertIn("직접 설정에서 첨부", page)
        self.assertNotIn('id="lecture-file"', page)
        self.assertIn("/api/ontology/search?q=", script)
        self.assertIn("선택한 출제 의도", review_script)
        self.assertIn("출제 의도 불일치", review_script)
        self.assertIn("자동 생성 문항 · 교수 검토 필요", review_script)
        self.assertIn("문항 작성 규칙 보완 필요", review_script)
        self.assertIn("feedback_comment", review_script)

    def test_frontend_guards_unfinished_item_set_navigation_and_restores_draft(self):
        script = self.client.get("/faculty-studio-v3/app.js").text
        page = self.client.get("/faculty-studio-v3/").text
        styles = self.client.get("/faculty-studio-v3/app.css").text

        self.assertIn('workflowDraftStorageKey = "paccine.faculty_item_workflow_draft.v1"', script)
        self.assertIn('event.target.closest("a[href]")', script)
        self.assertIn('window.addEventListener("beforeunload"', script)
        self.assertIn("hasUnfinishedWorkflow()", script)
        self.assertIn("saveWorkflowDraft()", script)
        self.assertIn("restoreWorkflowDraft()", script)
        self.assertIn("data-workflow-complete", script)
        self.assertIn('id="leave-guard"', page)
        self.assertIn('id="leave-guard-save"', page)
        self.assertIn('id="leave-guard-discard"', page)
        self.assertIn("임시저장 후 이동", page)
        self.assertIn(".leave-guard", styles)
        self.assertIn("mobile-nav-v1", page)   # 캐시 버스터(2026-09-05 모바일 메뉴 토글 추가로 갱신)

    def test_generation_job_creation_normalizes_ontology_request(self):
        captured = {}

        def fake_create(request):
            captured.update(request)
            return ({"job_id": "gen_20260718T000000Z_123456789abc", "status": "queued"}, False)

        with patch.object(api_server, "create_generation_job", side_effect=fake_create):
            response = self.client.post(
                "/api/generation-jobs",
                json={
                    "topic": "다발골수종 초기 치료",
                    "set_name": "다문항 세트",
                    "num_questions": 40,
                    "target_axis_ids": "axis_1, axis_2",
                    "supporting_axis_types": ["diagnosis", "prognosis"],
                    "selected_media_ids": ["media_1", "media_2"],
                    "reasoning_hops": 9,
                    "faculty_question_intent": {"assessment_claim": "초기 치료 선택"},
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"]["status"], "queued")
        self.assertEqual(captured["num_questions"], 30)
        self.assertEqual(captured["target_axis_ids"], ["axis_1", "axis_2"])
        self.assertEqual(captured["supporting_axis_types"], ["diagnosis", "prognosis"])
        self.assertEqual(captured["selected_media_ids"], ["media_1", "media_2"])
        self.assertEqual(captured["reasoning_hops"], 3)
        self.assertEqual(captured["faculty_question_intent"]["assessment_claim"], "초기 치료 선택")

    def test_generation_job_status_and_retry_not_found(self):
        missing = "gen_20260718T000000Z_123456789abc"
        with patch.object(api_server, "get_generation_job", side_effect=FileNotFoundError):
            self.assertEqual(self.client.get(f"/api/generation-jobs/{missing}").status_code, 404)
        with patch.object(api_server, "retry_failed_generation_job", side_effect=FileNotFoundError):
            self.assertEqual(self.client.post(f"/api/generation-jobs/{missing}/retry").status_code, 404)

    def test_department_catalog_and_item_intent_recommendation_contract(self):
        catalog_response = self.client.get("/api/faculty/item-intents/departments")
        self.assertEqual(catalog_response.status_code, 200)
        catalog = catalog_response.json()
        heme = next(row for row in catalog["departments"] if row["id"] == "hematology_oncology")
        self.assertEqual(heme["concept_count"], 1)

        response = self.client.post(
            "/api/faculty/item-intents/recommendations",
            json={
                "department": "혈액종양내과",
                "requested_item_count": 3,
                "candidate_count": 6,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["exam_profile"], "clinical_comprehensive")
        self.assertEqual(payload["department"]["id"], "hematology_oncology")
        self.assertEqual(payload["candidate_count"], 1)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["target"]["concept_id"], "multiple_myeloma")
        self.assertTrue(candidate["evidence_contract"]["needs_review"])
        self.assertFalse(candidate["evidence_contract"]["claim_evidence_ready"])
        self.assertFalse(payload["selection_rules"]["lecture_required"])

    def test_item_intent_recommendation_rejects_invalid_assignment_count(self):
        response = self.client.post(
            "/api/faculty/item-intents/recommendations",
            json={"department": "혈액종양내과", "requested_item_count": 1},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("2개 또는 3개", response.json()["detail"])

    def test_selected_item_intents_create_one_multi_intent_generation_job(self):
        captured = {}

        def fake_create(request):
            captured.update(request)
            return ({"job_id": "gen_20260720T000000Z_123456789abc", "status": "queued"}, False)

        selected = []
        for index, (concept_id, label, task, axis) in enumerate(
            [
                ("multiple_myeloma", "다발골수종", "first_line_treatment", "treatment"),
                ("acute_myeloid_leukemia", "급성골수성백혈병", "test_selection", "diagnosis"),
                ("tumor_lysis_syndrome", "종양용해증후군", "immediate_management", "treatment"),
            ],
            start=1,
        ):
            selected.append(
                {
                    "intent_id": f"intent:{index}",
                    "title": f"{label} 후보",
                    "target": {"concept_id": concept_id, "label": label},
                    "assessment_claim": {
                        "task": task,
                        "task_label": "평가 과업",
                        "faculty_claim": f"학생이 {label}에서 판단한다.",
                    },
                    "task_model": {"format": "clinical_case", "reasoning_hops": 2},
                    "target_axis_type": axis,
                    "evidence_contract": {"selected_media_ids": [f"media_{index}"]},
                }
            )

        with patch.object(api_server, "create_generation_job", side_effect=fake_create):
            response = self.client.post(
                "/api/faculty/item-intents/generation-jobs",
                json={
                    "department": {"id": "hematology_oncology", "label": "혈액종양내과"},
                    "faculty_id": "faculty_01",
                    "set_name": "혈액종양 임종평 출제",
                    "selected_intents": selected,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["num_questions"], 3)
        self.assertEqual(len(captured["item_intents"]), 3)
        self.assertEqual(captured["item_intents"][0]["disease_concept_id"], "multiple_myeloma")
        self.assertEqual(captured["item_intents"][1]["target_axis_type"], "diagnosis")
        self.assertEqual(captured["item_intents"][0]["selected_media_ids"], ["media_1"])
        self.assertEqual(captured["faculty_assignment"]["faculty_id"], "faculty_01")
        self.assertEqual(captured["faculty_assignment"]["exam_profile"], "clinical_comprehensive")
        self.assertFalse(response.json()["review_contract"]["student_auto_release"])

    def test_multi_intent_generation_job_rejects_duplicate_selection(self):
        item = {
            "intent_id": "intent:same",
            "target": {"concept_id": "multiple_myeloma", "label": "다발골수종"},
            "assessment_claim": {"task": "mechanism", "faculty_claim": "병태생리 기전"},
            "target_axis_type": "pathophysiology",
        }
        response = self.client.post(
            "/api/faculty/item-intents/generation-jobs",
            json={"department": "혈액종양내과", "selected_intents": [item, item]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("중복", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
