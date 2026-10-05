"""Regression tests for the deterministic item-quality gate.

The fixtures are synthetic and contain no private exam text.
"""

from __future__ import annotations

import unittest

from scripts.item_quality_check import apply_generation_quality_gate, scan_item


def make_item(*, choices: dict[str, str], answer: str = "3") -> dict:
    return {
        "stem": (
            "55세 남자가 2일 전부터 심해진 복통으로 내원하였다. "
            "혈압은 118/72 mmHg, 맥박은 92회/분이다. 다음으로 시행할 가장 적절한 검사는?"
        ),
        "choices": choices,
        "answer": answer,
    }


class ItemQualityCheckTests(unittest.TestCase):
    def test_shortest_key_sets_rank_flaws(self):
        item = make_item(
            choices={
                "1": "복부 조영증강 CT 검사",
                "2": "복부 초음파 및 도플러 검사",
                "3": "혈액검사",
                "4": "상부위장관 내시경 검사",
                "5": "복부 단순 방사선 촬영",
            }
        )
        quality = scan_item(item)
        self.assertIn("shortest_is_key", quality["flaws"])
        self.assertIn("key_length_rank", quality["flaws"])
        self.assertEqual(quality["key_length_rank"], 5)

    def test_key_with_most_components_is_flagged(self):
        item = make_item(
            choices={
                "1": "정맥 수액 투여",
                "2": "항생제 투여",
                "3": "정맥 수액 투여 및 응급 수술 협의",
                "4": "진통제 투여",
                "5": "경과 관찰",
            }
        )
        self.assertIn("most_components_is_key", scan_item(item)["flaws"])

    def test_short_atomic_drug_labels_do_not_fail_only_for_lexical_length(self):
        item = make_item(
            choices={
                "1": "와파린 투여",
                "2": "아픽사반 투여",
                "3": "리바록사반 투여",
                "4": "딜티아젬 투여",
                "5": "아미오다론 투여",
            },
            answer="1",
        )
        quality = scan_item(item)
        self.assertNotIn("shortest_is_key", quality["flaws"])
        self.assertNotIn("key_length_rank", quality["flaws"])

    def test_urgency_adverb_only_in_key_is_flagged(self):
        item = make_item(
            choices={
                "1": "생리식염수 투여",
                "2": "경구 항생제 투여",
                "3": "즉시 응급 수술 시행",
                "4": "외래 추적 관찰",
                "5": "추가 영상검사 시행",
            }
        )
        self.assertIn("urgency_adverb_only_in_key", scan_item(item)["flaws"])

    def test_recent_surgery_blocks_unqualified_systemic_thrombolysis_key(self):
        item = make_item(
            choices={
                "1": "아픽사반 경구 투여",
                "2": "미분획 헤파린 투여",
                "3": "전신 혈전용해요법 투여",
                "4": "하대정맥 필터 삽입",
                "5": "카테터 혈전 제거술",
            },
            answer="3",
        )
        item["stem"] = (
            "고관절 치환술 후 4일째 갑작스러운 저혈압과 호흡곤란이 발생했고 "
            "폐색전증이 확인되었다. 가장 적절한 치료는?"
        )
        quality = scan_item(item)
        self.assertIn("answer_contraindicated_by_stem", quality["flaws"])

    def test_generation_gate_attaches_20_rule_checklist_and_review_gate(self):
        item = make_item(
            choices={
                "1": "복부 초음파 검사",
                "2": "복부 CT 영상 검사",
                "3": "상부위장관 내시경 검사",
                "4": "복부 MRI 영상 검사",
                "5": "단순 복부 방사선 검사",
            }
        )
        item.update(
            {
                "reasoning_hops": 2,
                "cognitive_level": "적용",
                "cognitive_model": {"confounders": ["경계치 검사결과"]},
                "choice_explanations": {
                    str(i): ({"rationale": "근거"} if i == 3 else {"misconception": "실제 감별", "why_attractive": "유사한 소견"})
                    for i in range(1, 6)
                },
            }
        )
        gated = apply_generation_quality_gate(item)
        self.assertTrue(gated["needs_review"])
        self.assertFalse(gated["gen_ready"])
        self.assertEqual(gated["item_quality"]["hard_rule_total"], 20)
        self.assertEqual(len(gated["self_check"]), 22)

    def test_numeric_unit_punctuation_is_not_counted_as_multiple_components(self):
        item = make_item(
            choices={
                "1": "저밀도지단백 185 mg/dL",
                "2": "당화혈색소 6.2%",
                "3": "중성지방 1,250 mg/dL",
                "4": "혈청 요산 8.5 mg/dL",
                "5": "혈청 페리틴 600 ng/mL",
            }
        )
        self.assertNotIn("most_components_is_key", scan_item(item)["flaws"])

    def test_real_multistep_does_not_require_confounder(self):
        item = make_item(
            choices={
                "1": "복부 초음파 검사",
                "2": "복부 CT 영상 검사",
                "3": "상부위장관 내시경 검사",
                "4": "복부 MRI 영상 검사",
                "5": "단순 복부 방사선 검사",
            }
        )
        item.update(
            {
                "reasoning_hops": 2,
                "cognitive_level": "적용",
                "cognitive_model": {
                    "decision_cues": ["증상 경과", "활력징후"],
                    "confounders": [],
                    "answer_concept": "다음 검사 선택",
                },
                "evidence_disclosure_plan": {
                    "status": "pass",
                    "selected_for_stem": [{"source_id": "axis:1"}],
                    "target_already_resolved": False,
                    "qc_flags": [],
                },
            }
        )
        gated = apply_generation_quality_gate(item)
        self.assertTrue(gated["self_check"]["reasoning_hops_ge_2_real_not_recognition"])
        self.assertIn("03_real_multistep_not_recognition", gated["item_quality"]["hard_rule_checklist"])

    def test_treatment_item_may_disclose_established_diagnosis(self):
        item = make_item(
            choices={
                "1": "이마티닙",
                "2": "닐로티닙",
                "3": "포나티닙",
                "4": "하이드록시유레아",
                "5": "동종조혈모세포이식",
            },
            answer="1",
        )
        item.update(
            {
                "stem": "BCR-ABL1 양성 만성골수성백혈병으로 진단되었다. QTc가 연장되어 있다. 가장 적절한 초기 치료는?",
                "target_axis_type": "treatment",
                "reveal_specialty": False,
                "evidence_disclosure_plan": {
                    "assessment_task": "treatment",
                    "latent_diagnosis_required": False,
                    "status": "pass",
                    "qc_flags": [],
                },
            }
        )

        flaws = scan_item(item)["flaws"]
        self.assertNotIn("specialty_leak", flaws)
        self.assertNotIn("over_cueing", flaws)
        gated = apply_generation_quality_gate(item)
        self.assertTrue(gated["self_check"]["key_len_ratio_0_8_to_1_2"])

    def test_disclosure_qc_flags_are_scanner_flaws(self):
        item = make_item(
            choices={
                "1": "복부 초음파 검사",
                "2": "복부 CT 영상 검사",
                "3": "상부위장관 내시경 검사",
                "4": "복부 MRI 영상 검사",
                "5": "단순 복부 방사선 검사",
            }
        )
        item["evidence_disclosure_plan"] = {
            "status": "blocked",
            "target_already_resolved": True,
            "qc_flags": ["overdetermined_diagnosis", "malicious_red_herring"],
        }
        flaws = scan_item(item)["flaws"]
        self.assertIn("overdetermined_diagnosis", flaws)
        self.assertIn("malicious_red_herring", flaws)
        self.assertIn("target_already_resolved", flaws)


if __name__ == "__main__":
    unittest.main()
