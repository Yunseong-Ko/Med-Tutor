#!/usr/bin/env python3
"""Run a repeatable, retrieval-only QA set against the student medical copilot.

The suite deliberately avoids model calls.  It checks the layer that must be
correct before an answer is composed: intent shape, ontology route, Harrison
chapter, and fail-closed behavior for an unsupported topic.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.medical_copilot import build_medical_copilot_response  # noqa: E402


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    expected_template: str
    expected_chapter: int | None
    expected_concept: str | None = None
    expect_safe_block: bool = False


CASES = (
    EvaluationCase("cardio_af_dx", "심방세동의 진단 기준과 주요 감별 포인트는?", "clinical_overview", 258, "atrial_fibrillation"),
    EvaluationCase("pulm_asthma_dx", "천식 진단에서 객관적으로 확인할 검사는?", "clinical_overview", 298, "asthma"),
    EvaluationCase("endo_t2dm_tx", "제2형 당뇨병의 치료 원칙을 설명해줘", "treatment_or_regimen", 416, "type_2_diabetes"),
    EvaluationCase("heme_cml_mech", "만성골수성백혈병의 핵심 병태생리와 기전은?", "mechanism", 110, "chronic_myeloid_leukemia"),
    EvaluationCase("heme_aml_regimen", "AML 3+7 regimen을 설명해줘", "treatment_or_regimen", 109, "acute_myeloid_leukemia"),
    EvaluationCase("heme_hodgkin_stage", "Hodgkin lymphoma staging을 정리해줘", "classification_or_staging", 114, "hodgkin_lymphoma"),
    EvaluationCase("heme_retic_compare", "RPI랑 corrected reticulocyte count 차이를 비교해줘", "comparison", 66),
    EvaluationCase("ob_varicella_mcq", "임신 26주 수두 IgG 음성 임부가 수두에 노출됐다. 처치는? ① 관찰 ② 임신 종결 ③ 항바이러스제 ④ VZIG ⑤ 양수검사", "mcq_vignette", 198, "varicella"),
    EvaluationCase("heme_aplastic_overview", "재생불량성 빈혈을 설명해줘", "clinical_overview", 107, "aplastic_anemia"),
    EvaluationCase("psych_schizophrenia_tx", "조현병의 1차 치료와 2차 치료를 비교해줘", "comparison", 463, "schizophrenia"),
    EvaluationCase("msk_torticollis", "torticollis를 설명해줘", "brief_topic", None, expect_safe_block=True),
    EvaluationCase("onc_crc_egfr", "대장암에서 EGFR amplification이 있으면 치료 옵션이 뭐야?", "treatment_or_regimen", 86, "colorectal_cancer"),
    EvaluationCase("renal_nephrotic_mech", "신증후군의 병태생리를 설명해줘", "mechanism", 326, "nephrotic_syndrome"),
    EvaluationCase("gi_cirrhosis_ascites", "간경변 복수의 치료 원칙은?", "treatment_or_regimen", 355, "cirrhosis"),
    EvaluationCase("renal_aki_dx", "급성신손상의 진단과 초기 평가를 설명해줘", "clinical_overview", 321),
    EvaluationCase("endo_dka_mech", "당뇨병성 케톤산증의 핵심 기전은?", "mechanism", 417, "diabetic_ketoacidosis"),
    EvaluationCase("infect_meningitis_dx", "세균성 수막염의 진단과 감별은?", "clinical_overview", 143, "bacterial_meningitis"),
    EvaluationCase("rheum_sle_dx", "전신홍반루푸스의 진단 기준을 설명해줘", "clinical_overview", 368, "systemic_lupus_erythematosus"),
    EvaluationCase("neuro_parkinson_mech", "파킨슨병의 핵심 병태생리와 기전은?", "mechanism", 446),
    EvaluationCase("onc_breast_stage", "유방암 병기 분류를 정리해줘", "classification_or_staging", 84, "breast_cancer"),
    EvaluationCase("pulm_pe_dx", "폐색전증의 진단 접근을 설명해줘", "clinical_overview", 290, "pulmonary_embolism"),
    EvaluationCase("endo_hyperthyroid_mech", "갑상선기능항진증의 병태생리는?", "mechanism", 396, "hyperthyroidism"),
    EvaluationCase("rheum_ra_tx", "류마티스관절염의 치료 원칙은?", "treatment_or_regimen", 370, "rheumatoid_arthritis"),
    EvaluationCase("cardio_hf_tx", "심부전의 치료 원칙을 설명해줘", "treatment_or_regimen", 265, "heart_failure"),
    EvaluationCase("cardio_acs_dx", "급성관상동맥증후군의 진단 접근은?", "clinical_overview", 284, "acute_coronary_syndrome"),
    EvaluationCase("infect_endocarditis_tx", "감염성 심내막염의 치료 원칙은?", "treatment_or_regimen", 133),
    EvaluationCase("pulm_copd_dx", "COPD의 진단과 중증도 평가는?", "clinical_overview", 303, "chronic_obstructive_pulmonary_disease"),
    EvaluationCase("infect_cap_tx", "지역사회획득폐렴의 치료 원칙은?", "treatment_or_regimen", 131, "community_acquired_pneumonia"),
    EvaluationCase("renal_ckd_stage", "만성콩팥병의 병기와 추적관찰은?", "classification_or_staging", 322, "chronic_kidney_disease"),
    EvaluationCase("renal_hyperk_tx", "고칼륨혈증의 응급 치료 순서는?", "treatment_or_regimen", 56, "hyperkalemia"),
    EvaluationCase("heme_iron_dx", "철결핍성 빈혈의 진단은?", "clinical_overview", 102, "iron_deficiency_anemia"),
    EvaluationCase("heme_itp_tx", "면역혈소판감소증의 치료 원칙은?", "treatment_or_regimen", 121, "immune_thrombocytopenia"),
    EvaluationCase("heme_myeloma_dx", "다발골수종의 진단 기준은?", "clinical_overview", 116, "multiple_myeloma"),
    EvaluationCase("infect_tb_tx", "결핵의 치료 원칙은?", "treatment_or_regimen", 183, "pulmonary_tuberculosis"),
    EvaluationCase("infect_hiv_dx", "HIV 감염의 진단 검사는?", "clinical_overview", 208, "hiv_anonymous_testing"),
    EvaluationCase("critical_sepsis_tx", "패혈증의 초기 평가와 치료는?", "treatment_or_regimen", 315, "sepsis"),
    EvaluationCase("neuro_stroke_tx", "급성 허혈성 뇌졸중의 치료 원칙은?", "treatment_or_regimen", 438, "acute_ischemic_stroke"),
    EvaluationCase("neuro_ich_umbrella_ko", "뇌출혈 분류랑 치료 가이드라인좀", "classification_or_staging", 439, "intracerebral_hemorrhage"),
    EvaluationCase("neuro_ich_umbrella_typo", "Intracrnial hemorrhage 치료 가이드라인좀", "treatment_or_regimen", 439, "intracerebral_hemorrhage"),
    EvaluationCase("neuro_migraine_tx", "편두통의 진단과 치료를 설명해줘", "treatment_or_regimen", 441, "migraine"),
    EvaluationCase("psych_bipolar_tx", "양극성장애의 치료 원칙은?", "treatment_or_regimen", 463, "bipolar_disorder"),
    EvaluationCase("rheum_gout_compare", "통풍의 급성기 치료와 장기 관리 차이는?", "comparison", 384, "gout"),
    EvaluationCase("endo_osteoporosis_tx", "골다공증의 진단과 치료는?", "treatment_or_regimen", 423, "osteoporosis"),
    EvaluationCase("gi_pancreatitis_tx", "급성췌장염의 진단과 초기 치료는?", "treatment_or_regimen", 359, "acute_pancreatitis"),
    EvaluationCase("gi_ibd_compare", "궤양성 대장염과 크론병 차이를 비교해줘", "comparison", 337, "ulcerative_colitis"),
    EvaluationCase("infect_hbv_tx", "만성 B형간염의 치료 원칙은?", "treatment_or_regimen", 352, "hepatitis_b"),
    EvaluationCase("endo_adrenal_tx", "부신기능저하증의 진단과 치료는?", "treatment_or_regimen", 398, "adrenal_insufficiency"),
    EvaluationCase("endo_cushing_dx", "쿠싱증후군의 진단 접근은?", "clinical_overview", 398),
)


def evaluate_case(case: EvaluationCase) -> dict[str, Any]:
    response = build_medical_copilot_response(case.question, generate_answer=False, root=ROOT)
    concepts = [str(row.get("concept_id") or "") for row in response.get("ontology_matches") or []]
    chapters = [int(row["chapter"]) for row in response.get("harrison_sources") or [] if row.get("chapter")]
    checks: dict[str, bool] = {
        "template": response.get("answer_template") == case.expected_template,
    }
    if case.expect_safe_block:
        checks["safe_block"] = (
            response.get("answer_status") == "evidence_insufficient"
            and not chapters
            and not concepts
        )
    else:
        checks["evidence_ready"] = response.get("answer_status") == "retrieval_ready_answer_not_requested"
        checks["chapter"] = bool(chapters) and chapters[0] == case.expected_chapter
        if case.expected_concept:
            checks["primary_concept"] = bool(concepts) and concepts[0] == case.expected_concept
    return {
        **asdict(case),
        "passed": all(checks.values()),
        "checks": checks,
        "actual": {
            "answer_status": response.get("answer_status"),
            "template": response.get("answer_template"),
            "concepts": concepts,
            "chapters": chapters,
            "source_titles": [str(row.get("title") or "") for row in response.get("harrison_sources") or []],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the complete machine-readable result.")
    args = parser.parse_args()
    results = [evaluate_case(case) for case in CASES]
    passed = sum(1 for row in results if row["passed"])
    summary = {"total": len(results), "passed": passed, "failed": len(results) - passed}

    if args.json:
        print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    else:
        for row in results:
            mark = "PASS" if row["passed"] else "FAIL"
            actual = row["actual"]
            details = f"concept={actual['concepts'][:2]} chapter={actual['chapters'][:2]}"
            if not row["passed"]:
                failed_checks = [name for name, ok in row["checks"].items() if not ok]
                details += f" failed={failed_checks}"
            print(f"{mark:4} {row['case_id']:<28} {details}")
        print(f"\nSUMMARY {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
