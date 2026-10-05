#!/usr/bin/env python3
"""임상의학종합평가 3교시 concept_tags 라벨링 (근거·검색의 전제).

stem + 정답을 근거로 각 문항의 주 질환/개념을 첫 태그로 부여한다(영문 표준명 우선).
정답은 원본에 있던 것(유출본)을 그대로 사용하며 임의 추론하지 않는다.
"""

import json
from pathlib import Path

TARGET = Path("data_private/course_exams/extracted/COURSE_X_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_3교시.json")

TAGS = {
    1: ["herpes_zoster_vaccination", "immunosuppression", "recombinant_zoster_vaccine"],
    2: ["chronic_pulmonary_aspergillosis", "hemoptysis", "cavitary_lung_lesion"],
    3: ["diverticulitis", "left_lower_quadrant_pain"],
    4: ["shoulder_dystocia", "mcroberts_maneuver"],
    5: ["catatonia", "schizophrenia", "lorazepam"],
    6: ["ventricular_fibrillation", "defibrillation", "cardiac_arrest"],
    7: ["schizophrenia", "antipsychotics"],
    8: ["acute_decompensated_heart_failure", "furosemide", "pulmonary_edema"],
    9: ["osteoporosis", "fracture_risk"],
    10: ["type_1_diabetes_mellitus", "polyuria"],
    11: ["ankylosing_spondylitis", "inflammatory_back_pain"],
    12: ["acute_mesenteric_ischemia", "SMA_embolism"],
    13: ["pancreatic_cancer", "chronic_pancreatitis", "EUS_biopsy"],
    14: ["threatened_abortion", "first_trimester_bleeding"],
    15: ["nephrotic_syndrome", "minimal_change_disease", "corticosteroid"],
    16: ["colorectal_cancer", "bowel_habit_change"],
    17: ["COPD_exacerbation", "noninvasive_ventilation"],
    18: ["premature_rupture_of_membranes", "labor_induction", "oxytocin"],
    19: ["tuberculosis", "fever_of_unknown_origin"],
    20: ["anaplastic_thyroid_carcinoma", "rapidly_enlarging_goiter"],
    21: ["ethambutol_optic_neuropathy", "drug_induced_color_vision_defect"],
    22: ["juvenile_idiopathic_arthritis", "uveitis"],
    23: ["tuberculosis", "antituberculous_therapy"],
    24: ["late_life_depression", "suicidality", "SSRI"],
    25: ["pneumonia", "sputum_gram_stain"],
    26: ["ischemic_colitis", "hematochezia"],
    27: ["malignant_mesothelioma", "asbestos_exposure"],
    28: ["chronic_hypertension_in_pregnancy"],
    29: ["henoch_schonlein_purpura", "IgA_vasculitis"],
    30: ["iron_deficiency_anemia", "chronic_kidney_disease", "hemodialysis"],
    31: ["sinonasal_malignancy", "maxillary_sinus", "unilateral_epistaxis"],
    32: ["acute_cholecystitis", "right_upper_quadrant_pain"],
    33: ["somatic_symptom_disorder", "chest_pain"],
    34: ["primary_sclerosing_cholangitis", "ulcerative_colitis"],
    35: ["amniotic_fluid_embolism", "obstetric_collapse"],
    36: ["toxic_shock_syndrome"],
    37: ["toxoplasmosis", "cervical_lymphadenopathy"],
    38: ["vitamin_K_deficiency", "coagulopathy", "post_gastrectomy"],
    39: ["renal_abscess", "pyelonephritis"],
    40: ["lymphoma", "inguinal_lymphadenopathy", "lactate_dehydrogenase"],
    41: ["intellectual_disability", "learning_difficulty"],
    42: ["acute_cholangitis", "biliary_obstruction", "percutaneous_transhepatic_biliary_drainage"],
    43: ["vasovagal_syncope", "orthostatic_syncope"],
    44: ["inguinal_hernia", "reducible_groin_mass"],
    45: ["pancreatic_cystic_lesion", "surveillance"],
    46: ["hyperthyroidism", "graves_disease", "methimazole"],
    47: ["colonic_inertia", "chronic_constipation", "defecation_disorder"],
    48: ["hepatocellular_carcinoma", "hepatic_resection"],
    49: ["syphilis_in_pregnancy", "penicillin_desensitization"],
    50: ["acute_diverticulitis", "abdominal_ct"],
    51: ["campylobacter_enteritis", "bloody_diarrhea"],
    52: ["attention_deficit_hyperactivity_disorder", "initial_assessment"],
    53: ["acute_myocardial_infarction", "cardiogenic_shock", "primary_pci"],
    54: ["bacterial_meningitis", "complex_febrile_seizure", "lumbar_puncture"],
    55: ["cushing_syndrome", "adrenal_imaging"],
    56: ["preterm_labor", "tocolysis"],
    57: ["diabetic_ketoacidosis"],
    58: ["patent_ductus_arteriosus", "preterm_murmur"],
    59: ["panic_disorder", "panic_attack"],
    60: ["benign_paroxysmal_positional_vertigo", "gufoni_maneuver"],
    61: ["hypokalemia", "metabolic_alkalosis", "vomiting"],
    62: ["anal_cancer", "HIV", "chemoradiotherapy"],
    63: ["acute_angle_closure_glaucoma", "laser_iridotomy"],
    64: ["spinal_cord_injury", "spinal_shock", "bulbocavernosus_reflex"],
    65: ["allergic_rhinitis", "aeroallergen"],
    66: ["labor_induction", "antenatal_assessment"],
    67: ["perforated_peptic_ulcer", "pneumoperitoneum"],
    68: ["primary_aldosteronism", "resistant_hypertension", "saline_infusion_test"],
    69: ["acute_mesenteric_ischemia", "acute_abdomen"],
    70: ["premature_ovarian_insufficiency", "secondary_amenorrhea"],
    71: ["mitral_regurgitation", "valve_repair"],
    72: ["opioid_overdose", "naloxone"],
    73: ["intestinal_obstruction", "acute_abdomen"],
    74: ["mitral_stenosis", "rheumatic_heart_disease"],
    75: ["infertility", "in_vitro_fertilization"],
    76: ["allergic_contact_dermatitis", "nickel"],
    77: ["acute_ischemic_stroke", "intravenous_thrombolysis", "alteplase"],
    78: ["aortic_stenosis", "exertional_dizziness"],
    79: ["infantile_spasms", "west_syndrome", "vigabatrin"],
    80: ["juvenile_myoclonic_epilepsy", "levetiracetam"],
}


def main():
    d = json.loads(TARGET.read_text(encoding="utf-8"))
    n = 0
    for q in d["questions"]:
        num = q.get("question_number")
        if num in TAGS:
            labels = q.get("labels") or {}
            labels["concept_tags"] = TAGS[num]
            labels["labeling_status"] = "labeled"
            labels["labeling_source"] = "manual_comprehensive_3"
            q["labels"] = labels
            n += 1
    TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 3교시 concept_tags 라벨링 {n}/80")


if __name__ == "__main__":
    raise SystemExit(main())
