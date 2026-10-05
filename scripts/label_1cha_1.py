#!/usr/bin/env python3
"""2026 1차 임종평 1교시 concept_tags 라벨링 (Q1~80). 법규·임상·예방 혼합."""

import json
from pathlib import Path

TARGET = Path("data_private/course_exams/extracted/COMPREHENSIVE_2026_1CHA_1교시.json")

TAGS = {
    1: ["hiv_anonymous_testing", "aids_prevention_act", "notifiable_disease_reporting"],
    2: ["vaccine_injury_compensation", "infectious_disease_control_act", "adverse_event_reporting"],
    3: ["quarantine_act", "ebola", "monitoring_period"],
    4: ["national_health_insurance", "benefit_types", "cpap"],
    5: ["narcotics_control_act", "temporary_narcotic_designation"],
    6: ["blood_management_act", "emergency_transfusion"],
    7: ["regional_public_health_act", "health_screening_notification"],
    8: ["medical_act", "medical_record_retention", "clinic_closure"],
    9: ["medical_liability", "robotic_surgery"],
    10: ["life_sustaining_treatment_decision_act", "end_of_life"],
    11: ["framework_act_on_health", "rare_disease_support"],
    12: ["emergency_medical_service_act", "patient_transfer"],
    13: ["infectious_disease_control_act", "mandatory_hospitalization", "mers"],
    14: ["medical_act", "license_disqualification"],
    15: ["medical_kickback", "administrative_disposition"],
    16: ["medical_record_access", "third_party_disclosure"],
    17: ["clinical_trial_ethics", "informed_consent"],
    18: ["medical_act", "practice_substitution"],
    19: ["narcotics_control_act", "opioid_prescription"],
    20: ["health_promotion_act", "health_promotion_fund"],
    21: ["hypokalemia", "thiazide", "periodic_paralysis"],
    22: ["ectopic_pregnancy", "hemoperitoneum"],
    23: ["pyometra", "postmenopausal", "diabetes_mellitus"],
    24: ["dry_gangrene", "toe_ischemia", "thermal_injury"],
    25: ["copd", "chronic_bronchitis", "smoking"],
    26: ["insomnia", "sedative_hypnotic_use", "alcohol"],
    27: ["nephritic_syndrome", "glomerulonephritis", "edema"],
    28: ["pediatric_abdominal_mass", "neuroblastoma"],
    29: ["acute_myocardial_infarction", "chest_pain", "ecg"],
    30: ["bipolar_disorder", "mood_swing"],
    31: ["atrial_fibrillation", "heart_failure"],
    32: ["appendicitis"],
    33: ["sexual_assault", "post_exposure_prophylaxis", "emergency_contraception"],
    34: ["stable_angina", "coronary_ct"],
    35: ["septic_arthritis", "acute_monoarthritis"],
    36: ["breast_cancer", "mammography", "family_history"],
    37: ["febrile_illness_in_pregnancy", "scrub_typhus", "eschar"],
    38: ["deep_vein_thrombosis", "immobilization"],
    39: ["febrile_illness_with_bleeding", "thrombocytopenia"],
    40: ["alcohol_use_disorder", "naltrexone"],
    41: ["pulmonary_tuberculosis", "hemoptysis"],
    42: ["chronic_cough", "cough_variant_asthma"],
    43: ["white_coat_hypertension", "ambulatory_bp_monitoring"],
    44: ["mania", "bipolar_disorder"],
    45: ["precocious_puberty"],
    46: ["acute_urinary_retention", "benign_prostatic_hyperplasia"],
    47: ["cardiogenic_shock", "acute_myocardial_infarction"],
    48: ["fatigue", "pancytopenia", "acute_leukemia"],
    49: ["copd", "emphysema", "spirometry"],
    50: ["preeclampsia", "preterm_labor"],
    51: ["heart_failure", "exertional_dyspnea"],
    52: ["prenatal_care", "fetal_ultrasound"],
    53: ["obstructive_jaundice", "pancreatic_cancer", "weight_loss"],
    54: ["neonatal_jaundice"],
    55: ["acute_pancreatitis", "alcohol"],
    56: ["meningitis", "pediatric"],
    57: ["altered_mental_status", "sepsis", "diabetes_mellitus"],
    58: ["dementia", "alzheimer_disease"],
    59: ["thyroid_nodule", "thyroid_cancer"],
    60: ["acute_otitis_media"],
    61: ["lalonde_report", "health_field_concept", "determinants_of_health"],
    62: ["healthcare_delivery_system", "referral_system"],
    63: ["emergency_medical_underserved_area", "quality_of_care", "access"],
    64: ["provider_payment_system", "fee_for_service"],
    65: ["causal_inference_criteria", "consistency"],
    66: ["basic_reproduction_number", "herd_immunity"],
    67: ["screening_test_validity", "sensitivity_specificity"],
    68: ["acute_mountain_sickness", "high_altitude"],
    69: ["silicosis", "occupational_lung_disease"],
    70: ["raynaud_phenomenon"],
    71: ["epidemiologic_bias", "study_design"],
    72: ["attack_rate", "outbreak_investigation"],
    73: ["relative_risk", "attributable_risk", "air_pollution"],
    74: ["mosquito_borne_disease", "malaria", "travel"],
    75: ["risk_assessment", "nitrate", "methemoglobinemia"],
    76: ["systematic_review", "meta_analysis"],
    77: ["lead_poisoning", "occupational_exposure"],
    78: ["healthcare_cost_containment"],
    79: ["roemer_law", "supplier_induced_demand", "bed_supply"],
    80: ["antigenic_shift", "zoonosis", "emerging_infectious_disease"],
}

UNCERTAIN = {37, 39, 48, 74}  # 사진/제한정보로 추정 — 검토 필요


def main():
    d = json.loads(TARGET.read_text(encoding="utf-8"))
    n = 0
    for q in d["questions"]:
        num = q.get("question_number")
        if num in TAGS:
            labels = q.get("labels") or {}
            labels["concept_tags"] = TAGS[num]
            labels["labeling_status"] = "labeled"
            labels["labeling_source"] = "manual_1cha_1"
            if num in UNCERTAIN:
                labels["labeling_uncertain"] = True
            q["labels"] = labels
            n += 1
    TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 1교시 concept_tags 라벨링 {n}/80 (불확실 {len(UNCERTAIN)}: {sorted(UNCERTAIN)})")


if __name__ == "__main__":
    raise SystemExit(main())
