#!/usr/bin/env python3
"""2026 1차 임종평 3교시 concept_tags 라벨링 (Q1~80)."""

import json
from pathlib import Path

TARGET = Path("data_private/course_exams/extracted/COMPREHENSIVE_2026_1CHA_3교시.json")

TAGS = {
    1: ["inguinal_hernia"],
    2: ["acute_myocardial_infarction", "ecg"],
    3: ["carpal_tunnel_syndrome"],
    4: ["hepatocellular_carcinoma", "hepatitis_b"],
    5: ["hemobilia", "hepatic_trauma"],
    6: ["asthma_exacerbation", "pediatric"],
    7: ["anaphylaxis", "food_allergy"],
    8: ["endobronchial_tumor", "hemoptysis"],
    9: ["esophageal_variceal_bleeding", "cirrhosis"],
    10: ["bronchopulmonary_dysplasia", "prematurity"],
    11: ["panic_disorder"],
    12: ["obstructive_jaundice", "pancreatic_cancer"],
    13: ["obesity", "cushing_syndrome"],
    14: ["asymptomatic_hematuria", "iga_nephropathy"],
    15: ["petechiae", "immune_thrombocytopenia"],
    16: ["labor", "fetal_monitoring"],
    17: ["pneumonia", "productive_cough"],
    18: ["central_precocious_puberty"],
    19: ["autosomal_dominant_polycystic_kidney_disease"],
    20: ["clostridioides_difficile_colitis", "dehydration"],
    21: ["hyperprolactinemia", "galactorrhea"],
    22: ["cardiac_arrest", "ventricular_fibrillation"],
    23: ["stable_angina", "coronary_artery_disease"],
    24: ["upper_airway_cough_syndrome", "postnasal_drip"],
    25: ["neonatal_fever", "neonatal_sepsis"],
    26: ["prenatal_care", "fetal_lie"],
    27: ["postpartum_psychosis"],
    28: ["legionella_pneumonia", "atypical_pneumonia"],
    29: ["uterine_fibroid", "menorrhagia"],
    30: ["crohn_disease"],
    31: ["anastomotic_leak", "postoperative_complication"],
    32: ["gastrointestinal_bleeding", "nsaid"],
    33: ["hyperkalemia", "chronic_kidney_disease"],
    34: ["obsessive_compulsive_disorder"],
    35: ["diabetic_nephropathy", "proteinuria"],
    36: ["chest_trauma", "pneumothorax"],
    37: ["hypoglycemia", "fasting"],
    38: ["imperforate_hymen", "hematocolpos"],
    39: ["pneumonia", "pleurisy"],
    40: ["anaphylaxis", "perioperative_drug_allergy"],
    41: ["apnea_of_prematurity"],
    42: ["drug_reaction", "dress_syndrome"],
    43: ["migraine"],
    44: ["vulvar_hematoma"],
    45: ["nephrotic_syndrome", "diabetic_nephropathy"],
    46: ["endometriosis", "dysmenorrhea"],
    47: ["heart_failure", "exertional_dyspnea"],
    48: ["cardiogenic_shock", "acute_myocardial_infarction"],
    49: ["roseola_infantum"],
    50: ["suicide_attempt", "major_depressive_disorder"],
    51: ["kawasaki_disease"],
    52: ["breast_mass", "breast_cancer"],
    53: ["gastric_stump_cancer", "postgastrectomy"],
    54: ["death_certificate", "forensic_medicine"],
    55: ["travel_fever", "febrile_illness"],
    56: ["achalasia"],
    57: ["metabolic_bone_disease_of_prematurity", "fracture"],
    58: ["anorexia_nervosa", "osteoporosis"],
    59: ["placental_abruption"],
    60: ["small_bowel_obstruction", "strangulation"],
    61: ["vitamin_b12_deficiency", "subacute_combined_degeneration"],
    62: ["malnutrition", "preoperative_nutrition"],
    63: ["abnormal_uterine_bleeding"],
    64: ["turner_syndrome"],
    65: ["febrile_infant", "sepsis"],
    66: ["pheochromocytoma"],
    67: ["choledocholithiasis", "cholangitis"],
    68: ["emergency_contraception"],
    69: ["neck_mass", "thyroid_nodule"],
    70: ["carbon_monoxide_poisoning"],
    71: ["obstructive_sleep_apnea"],
    72: ["hepatitis_b", "hepatocellular_carcinoma"],
    73: ["caustic_ingestion", "corrosive_injury"],
    74: ["acute_cholecystitis", "choledocholithiasis"],
    75: ["severe_preeclampsia", "hellp_syndrome"],
    76: ["osteoarthritis", "hand"],
    77: ["diabetic_ketoacidosis"],
    78: ["idiopathic_pulmonary_fibrosis"],
    79: ["hyperthyroidism", "graves_disease"],
    80: ["vibrio_vulnificus", "necrotizing_fasciitis"],
}

UNCERTAIN = {13, 15, 55}


def main():
    d = json.loads(TARGET.read_text(encoding="utf-8"))
    n = 0
    for q in d["questions"]:
        num = q.get("question_number")
        if num in TAGS:
            labels = q.get("labels") or {}
            labels["concept_tags"] = TAGS[num]
            labels["labeling_status"] = "labeled"
            labels["labeling_source"] = "manual_1cha_3"
            if num in UNCERTAIN:
                labels["labeling_uncertain"] = True
            q["labels"] = labels
            n += 1
    TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 3교시 concept_tags 라벨링 {n}/80 (불확실 {sorted(UNCERTAIN)})")


if __name__ == "__main__":
    raise SystemExit(main())
