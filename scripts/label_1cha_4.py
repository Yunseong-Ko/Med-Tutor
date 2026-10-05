#!/usr/bin/env python3
"""2026 1차 임종평 4교시 concept_tags 라벨링 (Q1~80). Q3은 동영상 문항."""

import json
from pathlib import Path

TARGET = Path("data_private/course_exams/extracted/COMPREHENSIVE_2026_1CHA_4교시.json")

TAGS = {
    1: ["shoulder_dystocia", "macrosomia", "brachial_plexus_injury"],
    2: ["idiopathic_pulmonary_fibrosis", "dyspnea"],
    3: ["anxiety_disorder", "video_based"],
    4: ["lower_gastrointestinal_bleeding", "hematochezia"],
    5: ["acute_pericarditis"],
    6: ["febrile_neutropenia"],
    7: ["ulcerative_colitis"],
    8: ["eclampsia"],
    9: ["asherman_syndrome"],
    10: ["hepatocellular_carcinoma", "hepatic_mass"],
    11: ["gout", "tophi"],
    12: ["leptospirosis", "pulmonary_hemorrhage"],
    13: ["congenital_heart_disease", "heart_murmur"],
    14: ["urge_incontinence", "overactive_bladder"],
    15: ["gastric_outlet_obstruction", "gastric_cancer"],
    16: ["labor", "post_term_pregnancy"],
    17: ["biliary_colic", "cholelithiasis"],
    18: ["major_depressive_disorder"],
    19: ["autoimmune_hepatitis"],
    20: ["hypertension", "diabetes_mellitus"],
    21: ["vibrio_vulnificus", "necrotizing_fasciitis"],
    22: ["type_1_diabetes", "diabetic_ketoacidosis"],
    23: ["hirschsprung_disease", "delayed_meconium"],
    24: ["guillain_barre_syndrome"],
    25: ["post_streptococcal_glomerulonephritis"],
    26: ["atrial_fibrillation"],
    27: ["gastric_cancer", "peptic_ulcer"],
    28: ["premature_rupture_of_membranes", "labor"],
    29: ["cervical_radiculopathy"],
    30: ["peripheral_arterial_disease", "intermittent_claudication"],
    31: ["gambling_disorder"],
    32: ["hepatocellular_carcinoma", "alcoholic_cirrhosis"],
    33: ["prenatal_care", "screening"],
    34: ["abdominal_aortic_aneurysm"],
    35: ["breast_cancer", "family_history"],
    36: ["hepatitis_c"],
    37: ["meconium_aspiration_syndrome"],
    38: ["labor", "gestational_diabetes"],
    39: ["influenza_vaccine", "vaccination_in_pregnancy"],
    40: ["pelvic_inflammatory_disease", "cervicitis"],
    41: ["allergic_conjunctivitis"],
    42: ["bacterial_meningitis", "meningococcal"],
    43: ["nephrotic_syndrome"],
    44: ["varicella"],
    45: ["liver_abscess"],
    46: ["acute_cholecystitis"],
    47: ["acromegaly"],
    48: ["midgut_volvulus", "malrotation"],
    49: ["social_anxiety_disorder"],
    50: ["electrical_injury", "high_voltage_burn"],
    51: ["angioedema", "nsaid_hypersensitivity"],
    52: ["anal_fissure"],
    53: ["cutaneous_vasculitis", "palpable_purpura"],
    54: ["asthma", "allergic"],
    55: ["atopic_dermatitis"],
    56: ["pulmonary_tuberculosis"],
    57: ["silicosis", "occupational_lung_disease"],
    58: ["tension_pneumothorax", "chest_trauma"],
    59: ["neonatal_hyperbilirubinemia", "kernicterus"],
    60: ["acute_cholecystitis", "cholangitis"],
    61: ["hepatic_encephalopathy"],
    62: ["copd"],
    63: ["schizophrenia"],
    64: ["hypokalemia", "renal_tubular_acidosis", "sjogren_syndrome"],
    65: ["intellectual_disability", "learning_disorder"],
    66: ["malaria", "travel"],
    67: ["hyperthyroidism", "postpartum_thyroiditis"],
    68: ["alcohol_withdrawal", "wernicke_encephalopathy"],
    69: ["antidepressant_induced_mania", "bipolar_disorder"],
    70: ["lung_cancer", "malignant_pleural_effusion"],
    71: ["precocious_puberty"],
    72: ["respiratory_distress_syndrome", "prematurity"],
    73: ["vertebral_metastasis", "malignancy"],
    74: ["restless_legs_syndrome"],
    75: ["tetanus"],
    76: ["congenital_heart_disease", "infant_heart_failure"],
    77: ["postmenopausal_bleeding", "endometrial_cancer"],
    78: ["coagulopathy", "disseminated_intravascular_coagulation"],
    79: ["acute_bacterial_sinusitis"],
    80: ["hemoptysis", "lung_mass"],
}

UNCERTAIN = {2, 22, 66, 73}


def main():
    d = json.loads(TARGET.read_text(encoding="utf-8"))
    n = 0
    for q in d["questions"]:
        num = q.get("question_number")
        if num in TAGS:
            labels = q.get("labels") or {}
            labels["concept_tags"] = TAGS[num]
            labels["labeling_status"] = "labeled"
            labels["labeling_source"] = "manual_1cha_4"
            if num in UNCERTAIN:
                labels["labeling_uncertain"] = True
            q["labels"] = labels
            n += 1
    TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 4교시 concept_tags 라벨링 {n}/80 (불확실 {sorted(UNCERTAIN)})")


if __name__ == "__main__":
    raise SystemExit(main())
