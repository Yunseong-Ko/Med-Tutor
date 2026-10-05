"""Tests for scripts/generate_lecture_questions.py.

No API calls, no network I/O.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Allow import from scripts/ without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_lecture_questions import (
    build_generation_prompt,
    check_gitignore,
    extract_json_payload,
    normalize_question,
    normalize_evidence_disclosure_plan,
)


def _make_item(**overrides) -> dict:
    """Return a minimal valid raw question dict for normalize_question."""
    base: dict = {
        "problem": "65세 남성이 갑작스러운 복통으로 응급실에 내원하였다. 문진 상 3일 전 복부 수술력이 있다.",
        "options": ["소장폐색", "충수염", "담석증", "췌장염", "위천공"],
        "answer": 1,
        "explanation": "소장폐색 풀이: 수술 후 유착이 가장 흔한 원인이다.",
        "pma_solution": {
            "reasoning_summary": "수술 후 유착에 의한 소장폐색",
            "correct_reason": "복부단순촬영에서 air-fluid level과 소장 확장 소견",
            "choice_explanations": {
                "1": "정답: 수술 유착 SBO",
                "2": "오답: 충수염은 우하복부 국소통",
                "3": "오답: 담석증은 식후 유발",
                "4": "오답: 췌장염은 혈청 아밀라아제 상승",
                "5": "오답: 위천공은 free air 소견",
            },
            "high_yield_point": "SBO에서 closed-loop → 즉각 수술",
            "trap": "대장폐색과 혼동하지 말 것",
            "source_anchor": "강의록 p.12 소장폐색 진단 기준",
        },
        "evidence_refs": [],
        "evidence_tier": "lecture_only",
        "needs_review": False,
    }
    base.update(overrides)
    return base


class GenerateLectureQuestionsTests(unittest.TestCase):
    def test_disclosure_aliases_normalize_without_false_task_mismatch(self):
        plan = normalize_evidence_disclosure_plan(
            {
                "status": "pass",
                "assessment_task": "treatment",
                "latent_diagnosis_required": False,
                "retrieved_axis_ids": ["a:treatment:one"],
                "selected_for_stem": [
                    {
                        "source_id": "a:diagnosis:one",
                        "role": "discriminating_cue",
                        "strength": "moderate",
                        "evidence_family": "lab_result",
                        "surface_form": "검사 양성",
                    },
                    {
                        "source_id": "a:symptom:one",
                        "role": "confirmatory_cue",
                        "strength": "strong",
                        "evidence_family": "morphology",
                        "surface_form": "형태학적 소견",
                    },
                    {
                        "source_id": "a:symptom:two",
                        "role": "prerequisite_cue",
                        "strength": "moderate",
                        "evidence_family": "symptom",
                        "surface_form": "피로",
                    },
                ],
                "withheld": ["a:indication:two"],
                "qc_flags": [],
            },
            assessment_task="treatment",
        )

        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["qc_flags"], [])
        self.assertEqual(plan["selected_for_stem"][0]["role"], "decision_modifier")
        self.assertEqual(plan["selected_for_stem"][0]["evidence_family"], "general_laboratory")
        self.assertEqual(plan["selected_for_stem"][1]["role"], "target_data")
        self.assertEqual(plan["selected_for_stem"][1]["evidence_family"], "pathology_genetics")
        self.assertEqual(plan["selected_for_stem"][2]["evidence_family"], "symptom_course")
        self.assertIn("a:diagnosis:one", plan["retrieved_axis_ids"])
        self.assertEqual(
            plan["withheld"],
            [{"source_id": "a:indication:two", "reason": "unspecified_review"}],
        )

    def test_normalize_question_happy_path(self):
        item = _make_item()
        result = normalize_question(
            item, idx=1, source_name="demo.txt", subject="외과", unit="소장"
        )
        self.assertEqual(result["answer"], 1)
        self.assertTrue(result["needs_review"])
        self.assertIn("automated_generation_requires_human_review", result["review_reasons"])
        self.assertTrue(result["question_id"].startswith("LECTURE_demo_Q001"))
        self.assertEqual(len(result["options"]), 5)
        self.assertEqual(result["source_type"], "lecture_material")
        self.assertEqual(result["evidence_tier"], "lecture_only")
        self.assertFalse(result["gen_ready"])
        self.assertEqual(result["reasoning_hops"], 2)
        self.assertFalse(result["reveal_specialty"])
        self.assertIn("item_quality", result)
        self.assertEqual(result["item_quality"]["hard_rule_total"], 20)
        self.assertIn("cognitive_model", result)
        self.assertEqual(len(result["choice_explanations"]), 5)
        self.assertIn("misconception", result["choice_explanations"]["2"])

    def test_disclosure_common_model_synonyms_do_not_create_false_mismatch(self):
        plan = normalize_evidence_disclosure_plan(
            {
                "status": "pass",
                "assessment_task": "treatment",
                "selected_for_stem": [
                    {
                        "source_id": "a:prognosis:vitals",
                        "role": "informative_cue",
                        "strength": "moderate",
                        "evidence_family": "vital_sign",
                        "surface_form": "저혈압과 빈맥",
                    },
                    {
                        "source_id": "a:treatment:frame",
                        "role": "task_frame",
                        "strength": "weak",
                        "evidence_family": "clinical_context",
                        "surface_form": "즉시 치료가 필요한 상황",
                    },
                    {
                        "source_id": "a:diagnosis:ecg",
                        "role": "prerequisite_cue",
                        "strength": "moderate",
                        "evidence_family": "ecg_finding",
                        "surface_form": "불규칙 RR 간격",
                    },
                    {
                        "source_id": "a:risk:risk",
                        "role": "neutral_context",
                        "strength": "weak",
                        "evidence_family": "risk_factor",
                        "surface_form": "고혈압 병력",
                    },
                ],
                "withheld": [],
                "qc_flags": [],
            },
            assessment_task="treatment",
        )

        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["qc_flags"], [])
        self.assertEqual(plan["selected_for_stem"][0]["role"], "decision_modifier")
        self.assertEqual(plan["selected_for_stem"][0]["evidence_family"], "physical_exam")
        self.assertEqual(plan["selected_for_stem"][1]["role"], "prerequisite_cue")
        self.assertEqual(plan["selected_for_stem"][1]["evidence_family"], "care_context")
        self.assertEqual(plan["selected_for_stem"][2]["evidence_family"], "special_laboratory")

        synonym_plan = normalize_evidence_disclosure_plan(
            {
                "status": "pass",
                "assessment_task": "treatment",
                "selected_for_stem": [
                    {
                        "source_id": "a:diagnosis:test",
                        "role": "prerequisite_cue",
                        "strength": "moderate",
                        "evidence_family": "diagnostic_test",
                        "surface_form": "심전도 소견",
                    },
                    {
                        "source_id": "a:diagnosis:finding",
                        "role": "prerequisite_cue",
                        "strength": "moderate",
                        "evidence_family": "diagnostic_finding",
                        "surface_form": "QRS 연장",
                    },
                    {
                        "source_id": "a:lab:value",
                        "role": "prerequisite_cue",
                        "strength": "moderate",
                        "evidence_family": "lab_value",
                        "surface_form": "칼륨 상승",
                    },
                ],
                "qc_flags": [],
            },
            assessment_task="treatment",
        )
        self.assertEqual(synonym_plan["status"], "pass")
        self.assertEqual(synonym_plan["qc_flags"], [])
        self.assertEqual(
            [cue["evidence_family"] for cue in synonym_plan["selected_for_stem"]],
            ["special_laboratory", "special_laboratory", "general_laboratory"],
        )

        confirmatory_plan = normalize_evidence_disclosure_plan(
            {
                "status": "pass",
                "assessment_task": "indication",
                "selected_for_stem": [
                    {
                        "source_id": "a:imaging:one",
                        "role": "confirmatory",
                        "strength": "strong",
                        "evidence_family": "imaging",
                        "surface_form": "혈전 확인",
                    }
                ],
                "qc_flags": [],
            },
            assessment_task="indication",
        )
        self.assertEqual(confirmatory_plan["status"], "pass")
        self.assertEqual(confirmatory_plan["selected_for_stem"][0]["role"], "target_data")

    def test_prompt_contains_nbme_contract_and_self_check(self):
        prompt = build_generation_prompt(
            "승인된 강의 요약",
            source_name="demo.txt",
            subject="내과",
            unit="임상추론",
            num_questions=2,
            difficulty="중",
            max_chars=1000,
        )
        self.assertIn("reveal_specialty: false", prompt)
        self.assertIn("reasoning_hops: 2", prompt)
        self.assertIn("self_check 22항목", prompt)
        self.assertIn("urgency_adverb_not_key_only", prompt)

    def test_normalize_question_empty_problem(self):
        item = _make_item(problem="")
        result = normalize_question(
            item, idx=2, source_name="demo.txt", subject="외과", unit="소장"
        )
        self.assertTrue(result["needs_review"])
        self.assertIn("empty_problem", result["review_reasons"])

    def test_normalize_question_bad_answer_needs_review(self):
        item = _make_item(answer="잘못된값")
        result = normalize_question(
            item, idx=3, source_name="demo.txt", subject="외과", unit="소장"
        )
        self.assertEqual(result["answer"], 1)
        self.assertTrue(result["needs_review"])
        self.assertIn("invalid_answer", result["review_reasons"])

    def test_normalize_question_short_options(self):
        item = _make_item(options=["선지1", "선지2"])
        result = normalize_question(
            item, idx=4, source_name="demo.txt", subject="외과", unit="소장"
        )
        self.assertEqual(len(result["options"]), 5)
        self.assertIn("choice_count_lt_5", result["review_reasons"])
        self.assertTrue(result["needs_review"])

    def test_normalize_question_missing_source_anchor(self):
        pma = _make_item()["pma_solution"].copy()
        pma["source_anchor"] = ""
        item = _make_item(pma_solution=pma)
        result = normalize_question(
            item, idx=5, source_name="demo.txt", subject="외과", unit="소장"
        )
        self.assertIn("missing_source_anchor", result["review_reasons"])
        self.assertTrue(result["needs_review"])

    def test_normalize_question_sanitizes_evidence_source_type(self):
        item = _make_item(evidence_refs=[{"source": "x", "basis": "y", "source_type": "bad"}])
        result = normalize_question(
            item, idx=6, source_name="demo.txt", subject="외과", unit="소장"
        )
        self.assertEqual(result["evidence_refs"][0]["source_type"], "other")

    def test_normalize_question_preserves_model_verdict_for_mismatch_lint(self):
        item = _make_item(
            choice_explanations={
                "1": {"verdict": "오답", "rationale": "모델이 잘못 표시"},
                "2": {"verdict": "정답", "rationale": "모델이 잘못 표시"},
            }
        )
        result = normalize_question(item, idx=8, source_name="demo.txt", subject="내과", unit="혈액")
        self.assertEqual(result["choice_explanations"]["1"]["model_verdict"], "오답")
        self.assertIn("answer_key_explanation_mismatch", result["item_quality"]["flaws"])

    def test_normalize_question_preserves_exact_harrison_locator(self):
        item = _make_item(
            evidence_refs=[
                {
                    "source_id": "H1",
                    "source": "Harrison 22e",
                    "locator": "22e · Ch.120 · p.924",
                    "chapter": 120,
                    "printed_page": 924,
                    "basis": "ITP 진단 원리",
                    "source_type": "textbook",
                    "retrieval_method": "chapter_routed_scored_page",
                    "entailment_status": "needs_human_review",
                }
            ]
        )
        result = normalize_question(item, idx=9, source_name="demo.txt", subject="내과", unit="ITP")
        ref = result["evidence_refs"][0]
        self.assertEqual(ref["source_id"], "H1")
        self.assertEqual(ref["locator"], "22e · Ch.120 · p.924")
        self.assertEqual(ref["printed_page"], "924")

    def test_normalize_question_preserves_data_table(self):
        item = _make_item(
            data_table={
                "title": "응급실 초기 활력징후",
                "columns": ["항목", "수치", "참고치"],
                "rows": [
                    {"항목": "혈압", "수치": "82/50 mmHg", "참고치": "저혈압"},
                    {"항목": "맥박", "수치": "128/min", "참고치": "빈맥"},
                ],
            }
        )
        result = normalize_question(
            item, idx=7, source_name="demo.txt", subject="외과", unit="외상"
        )
        self.assertEqual(result["data_table"]["title"], "응급실 초기 활력징후")
        self.assertEqual(result["data_table"]["columns"], ["항목", "수치", "참고치"])
        self.assertEqual(result["data_table"]["rows"][0], ["혈압", "82/50 mmHg", "저혈압"])

    def test_extract_json_payload_bare(self):
        raw = '[{"problem": "test question", "answer": 1}]'
        result = extract_json_payload(raw)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["answer"], 1)

    def test_extract_json_payload_code_fence(self):
        raw = '```json\n[{"problem": "fenced question", "answer": 3}]\n```'
        result = extract_json_payload(raw)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["answer"], 3)

    def test_extract_json_payload_empty(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            extract_json_payload("")

    def test_check_gitignore_exits_when_data_private_missing(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".gitignore").write_text("node_modules/\n.env\nbuild/\n", encoding="utf-8")
            try:
                import os

                os.chdir(tmp_path)
                with self.assertRaises(SystemExit):
                    check_gitignore()
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
