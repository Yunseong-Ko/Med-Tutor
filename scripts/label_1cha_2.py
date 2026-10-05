#!/usr/bin/env python3
"""2026 1차 임종평 2교시 concept_tags 라벨링 (Q1~80)."""

import json
from pathlib import Path

TARGET = Path("data_private/course_exams/extracted/COMPREHENSIVE_2026_1CHA_2교시.json")

TAGS = {
    1: ["pyloric_stenosis", "projectile_vomiting"],
    2: ["vasospastic_angina", "chest_pain"],
    3: ["adult_vaccination", "immunization_schedule"],
    4: ["hypomania", "bipolar_disorder"],
    5: ["interstitial_lung_disease", "rheumatoid_arthritis"],
    6: ["mycoplasma_pneumonia", "atypical_pneumonia"],
    7: ["schizophrenia", "auditory_hallucination"],
    8: ["adnexal_mass", "ovarian_cyst"],
    9: ["ischemic_colitis", "hematochezia"],
    10: ["placenta_previa", "antepartum_hemorrhage"],
    11: ["generalized_anxiety_disorder"],
    12: ["acute_ischemic_stroke"],
    13: ["placental_abruption", "antepartum_hemorrhage"],
    14: ["prolonged_grief_disorder", "major_depressive_disorder"],
    15: ["auricular_perichondritis", "piercing"],
    16: ["acute_otitis_media"],
    17: ["type_2_diabetes", "glycemic_control"],
    18: ["failure_to_thrive"],
    19: ["exertional_heat_stroke"],
    20: ["upper_gi_bleeding", "peptic_ulcer"],
    21: ["systemic_lupus_erythematosus"],
    22: ["esophageal_cancer", "dysphagia"],
    23: ["hemoptysis", "bronchiectasis"],
    24: ["complete_av_block", "bradyarrhythmia", "syncope"],
    25: ["ankylosing_spondylitis", "inflammatory_back_pain"],
    26: ["acute_coronary_syndrome", "chest_pain"],
    27: ["infectious_mononucleosis", "pharyngitis"],
    28: ["thyroid_nodule"],
    29: ["peptic_ulcer_disease", "epigastric_pain"],
    30: ["prediabetes", "metabolic_syndrome"],
    31: ["polycystic_ovary_syndrome", "secondary_amenorrhea"],
    32: ["syncope", "micturition_syncope"],
    33: ["chronic_prostatitis"],
    34: ["gastric_outlet_obstruction", "gastric_cancer"],
    35: ["obstructive_jaundice", "choledocholithiasis"],
    36: ["menopause", "vasomotor_symptoms"],
    37: ["spontaneous_bacterial_peritonitis", "cirrhosis"],
    38: ["geriatric_failure_to_thrive", "dehydration"],
    39: ["thrombocytopenia", "leukemia"],
    40: ["heart_murmur", "valvular_heart_disease"],
    41: ["bowel_obstruction", "colon_cancer_history"],
    42: ["lymphoma", "lymphadenopathy"],
    43: ["diabetic_retinopathy"],
    44: ["viral_hepatitis", "hepatitis_b"],
    45: ["preeclampsia"],
    46: ["asthma", "wheezing"],
    47: ["labor", "fetal_monitoring"],
    48: ["pelvic_inflammatory_disease"],
    49: ["hypothyroidism"],
    50: ["hypersensitivity_pneumonitis", "occupational_lung_disease"],
    51: ["pneumonia", "pediatric_respiratory_distress"],
    52: ["digital_ischemia", "peripheral_arterial_disease"],
    53: ["nephrotic_syndrome", "minimal_change_disease"],
    54: ["acute_rhinosinusitis", "bacterial"],
    55: ["lymphedema", "secondary_lymphedema"],
    56: ["familial_hypercholesterolemia"],
    57: ["peripheral_neuropathy"],
    58: ["infantile_spasms", "west_syndrome"],
    59: ["alcoholic_liver_disease", "fatty_liver"],
    60: ["supraventricular_tachycardia"],
    61: ["pulmonary_embolism", "immobilization"],
    62: ["perianal_abscess"],
    63: ["pyelonephritis", "diabetes_mellitus"],
    64: ["delirium", "postoperative"],
    65: ["adjustment_disorder", "insomnia"],
    66: ["subarachnoid_hemorrhage", "thunderclap_headache"],
    67: ["allergic_rhinitis", "seasonal"],
    68: ["abdominal_aortic_aneurysm"],
    69: ["endometritis", "pelvic_inflammatory_disease"],
    70: ["nephrotic_syndrome"],
    71: ["virilizing_ovarian_tumor", "hyperandrogenism"],
    72: ["parapneumonic_effusion", "empyema"],
    73: ["henoch_schonlein_purpura"],
    74: ["ovarian_torsion"],
    75: ["perianal_abscess", "sepsis"],
    76: ["mallory_weiss_syndrome", "hematemesis"],
    77: ["gastric_cancer", "weight_loss"],
    78: ["organophosphate_poisoning", "cholinergic_crisis"],
    79: ["congenital_heart_disease", "infant_heart_failure"],
    80: ["atopic_dermatitis"],
}

UNCERTAIN = {30, 35, 39, 75}


def main():
    d = json.loads(TARGET.read_text(encoding="utf-8"))
    n = 0
    for q in d["questions"]:
        num = q.get("question_number")
        if num in TAGS:
            labels = q.get("labels") or {}
            labels["concept_tags"] = TAGS[num]
            labels["labeling_status"] = "labeled"
            labels["labeling_source"] = "manual_1cha_2"
            if num in UNCERTAIN:
                labels["labeling_uncertain"] = True
            q["labels"] = labels
            n += 1
    TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 2교시 concept_tags 라벨링 {n}/80 (불확실 {sorted(UNCERTAIN)})")


if __name__ == "__main__":
    raise SystemExit(main())
