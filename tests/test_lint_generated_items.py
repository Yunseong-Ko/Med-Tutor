import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from item_quality_check import scan_item  # noqa: E402
from lint_generated_items import (  # noqa: E402
    analyze_case_quality,
    classify_item_kind,
    lint_batch,
    rebalance_answer_positions,
)


def _item(answer: int, choices: dict, stem: str = "45세 남자가 피로로 왔다. 가장 적절한 진단은?") -> dict:
    return {
        "topic": "t",
        "stem": stem,
        "choices": {str(k): v for k, v in choices.items()},
        "answer": answer,
        "choice_explanations": {str(k): f"해설{k}" for k in choices},
    }


class ScanTests(unittest.TestCase):
    def test_longest_answer_is_flagged(self):
        q = _item(3, {
            1: "빈혈", 2: "감염", 3: "철결핍성 빈혈로 페리틴 감소와 총철결합능 증가를 동반한 상태",
            4: "출혈", 5: "용혈",
        })
        flaws = scan_item(q)["flaws"]
        self.assertIn("longest_is_key", flaws)

    def test_negative_stem_is_flagged(self):
        q = _item(5, {1: "간", 2: "비장", 3: "골수", 4: "난황낭", 5: "흉선"},
                  stem="정상 발생 조혈 부위가 아닌 것은?")
        self.assertIn("negative_stem", scan_item(q)["flaws"])

    def _grounded_item(self):
        item = _item(
            1,
            {1: "철결핍빈혈", 2: "만성질환빈혈", 3: "지중해빈혈", 4: "철적혈모구빈혈", 5: "용혈빈혈"},
            stem="45세 여자가 피로로 병원에 왔다. 혈압 118/72 mmHg였다. 가장 적절한 진단은?",
        )
        item["disease_concept_id"] = "iron_deficiency_anemia"
        item["pma_solution"] = {"correct_reason": "철 결핍 소견에 합당하다. H1", "source_anchor": "H1 · 22e · Ch.96 · p.702"}
        item["harrison_sources"] = [
            {
                "source_id": "H1",
                "chapter": 96,
                "printed_page": 702,
                "locator": "22e · Ch.96 · p.702",
                "entailment_status": "verified",
            }
        ]
        item["grounding_trace"] = {
            "all_distractors_in_scope": True,
            "answer_concept_level": "disease",
            "answer_evidence_in_scope": True,
        }
        item["choice_explanations"] = {
            "1": {"verdict": "정답", "model_verdict": "정답", "rationale": "H1", "concept_level": "disease"},
            **{
                str(index): {
                    "verdict": "오답",
                    "model_verdict": "오답",
                    "rationale": "감별 근거",
                    "misconception": "유사한 빈혈",
                    "source_id": f"disease_{index}",
                    "concept_level": "disease",
                }
                for index in range(2, 6)
            },
        }
        return item

    def test_answer_key_explanation_mismatch_is_high_integrity_flaw(self):
        item = self._grounded_item()
        item["choice_explanations"]["1"]["model_verdict"] = "오답"
        item["choice_explanations"]["2"]["model_verdict"] = "정답"
        flaws = scan_item(item)["flaws"]
        self.assertIn("answer_key_explanation_mismatch", flaws)
        report = lint_batch([item])
        self.assertEqual(report["ontology_rag_flag_distribution"]["answer_key_explanation_mismatch"], 1)

    def test_circled_answer_declaration_mismatch_is_flagged(self):
        item = self._grounded_item()
        item["explanation"] = "풀이 후 정답: ② 만성질환빈혈"
        self.assertIn("answer_key_explanation_mismatch", scan_item(item)["flaws"])

    def test_distractor_not_ontology_grounded_is_flagged(self):
        item = self._grounded_item()
        item["grounding_trace"]["all_distractors_in_scope"] = False
        self.assertIn("distractor_not_ontology_grounded", scan_item(item)["flaws"])

    def test_explanation_missing_source_is_flagged(self):
        item = self._grounded_item()
        item["harrison_sources"] = []
        item["pma_solution"]["source_anchor"] = "출처 없음"
        self.assertIn("explanation_missing_source", scan_item(item)["flaws"])

    def test_syndrome_and_disease_choice_levels_are_flagged(self):
        item = self._grounded_item()
        item["choice_explanations"]["3"]["concept_level"] = "syndrome"
        self.assertIn("syndrome_vs_disease_heterogeneous", scan_item(item)["flaws"])


class RebalanceTests(unittest.TestCase):
    def test_positions_are_spread_and_semantics_preserved(self):
        # 10 items all keyed to option 1 -> should spread across 1..5.
        items = []
        for _ in range(10):
            items.append(_item(1, {1: "정답옵션", 2: "b", 3: "c", 4: "d", 5: "e"}))
        fixed, changed = rebalance_answer_positions(items)
        self.assertEqual(len(fixed), 10)
        self.assertGreater(changed, 0)
        positions = [f["answer"] for f in fixed]
        # every position 1..5 should be used at least once across 10 items
        self.assertEqual(set(positions), {1, 2, 3, 4, 5})
        # semantics preserved: the correct answer's text still "정답옵션"
        for f in fixed:
            self.assertEqual(f["choices"][str(f["answer"])], "정답옵션")
            # the explanation that moved with the answer stays the answer's explanation
            self.assertEqual(f["choice_explanations"][str(f["answer"])], "해설1")

    def test_clean_position_is_left_unchanged(self):
        items = [_item(1, {1: "a", 2: "b", 3: "c", 4: "d", 5: "e"})]  # idx0 target=1 == answer
        fixed, changed = rebalance_answer_positions(items)
        self.assertEqual(changed, 0)
        self.assertEqual(fixed[0]["answer"], 1)

    def test_lint_batch_reports_position_chi2(self):
        items = [_item(1, {1: "a", 2: "b", 3: "c", 4: "d", 5: "e"}) for _ in range(10)]
        report = lint_batch(items)
        self.assertEqual(report["n_items"], 10)
        # all answers at position 1 -> strong chi2
        self.assertIsNotNone(report["answer_position_chi2_vs_uniform"])
        self.assertGreater(report["answer_position_chi2_vs_uniform"], 20)


class CaseCheckTests(unittest.TestCase):
    GOOD = {
        "stem": "34세 여자가 3개월 전부터 피로로 병원에 왔다. 진찰에서 결막이 창백하였다. "
                "혈압 112/70 mmHg였다. 검사에서 Hb 8.1 g/dL(정상 12–16), 페리틴 6 ng/mL(정상 15–150)이었다.",
        "choices": {"1": "지중해빈혈 소인", "2": "철결핍빈혈", "3": "만성질환빈혈", "4": "철적혈모구빈혈", "5": "거대적혈모구빈혈"},
        "answer": 2, "lead_in": "가장 적절한 진단은?",
    }

    def test_polished_case_is_clean(self):
        r = analyze_case_quality(self.GOOD)
        self.assertEqual(r["item_kind"], "case")
        self.assertEqual(r["case_flags"], [])

    def test_stem_fact_repeat_is_flagged(self):
        it = {
            "stem": "45세 남자가 피로로 병원에 왔다. 혈압 128/78 mmHg였다. HFE 유전자 과오돌연변이가 확인되었다. 페리틴 1850 ng/mL(정상 30-300)였다.",
            "choices": {"1": "HFE 변이에 의한 철 과잉", "2": "글로빈 합성 장애", "3": "HFE 변이로 인한 헵시딘 감소", "4": "염증 반응", "5": "미토콘드리아 장애"},
            "answer": 3, "lead_in": "가장 적절한 기전은?",
        }
        self.assertIn("stem_fact_repeat_in_option", analyze_case_quality(it)["case_flags"])

    def test_case_negative_leadin_flagged_but_concept_relaxed(self):
        case_neg = dict(self.GOOD, lead_in="빈혈의 원인으로 옳지 않은 것은?")
        self.assertIn("negative_or_open_leadin_in_case", analyze_case_quality(case_neg)["case_flags"])
        case_content_neg = dict(self.GOOD, lead_in="관련이 가장 적은 것은?")
        self.assertIn("negative_or_open_leadin_in_case", analyze_case_quality(case_content_neg)["case_flags"])
        # concept item (no age/clinical) with a negative lead-in is NOT flagged as case-negative
        concept = {"stem": "거대적혈모구빈혈에서 옳지 않은 것은?", "choices": {str(k): x for k, x in enumerate("abcde", 1)}, "answer": 1}
        self.assertEqual(classify_item_kind(concept), "concept")
        self.assertNotIn("negative_or_open_leadin_in_case", analyze_case_quality(concept)["case_flags"])

    def test_nonstandard_terminology_and_missing_ref_range(self):
        it = dict(self.GOOD, stem="60세 남자가 피로로 병원에 왔다. 혈압 130/80 mmHg였다. 도말에서 대소부동이 보였다. Hb가 감소되어 있었다.")
        flags = analyze_case_quality(it)["case_flags"]
        self.assertIn("nonstandard_terminology", flags)
        self.assertIn("lab_value_without_reference_range", flags)


if __name__ == "__main__":
    unittest.main()
