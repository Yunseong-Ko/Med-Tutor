#!/usr/bin/env python3
"""임상의학종합평가 2교시 concept_tags 라벨링 (Q1~80)."""

import json
from pathlib import Path

TARGET = Path("data_private/course_exams/extracted/COURSE_X_DATE_UNKNOWN_EXAM_2교시.json")

TAGS = {
    1: ["wilson_disease", "24h_urine_copper"],
    2: ["klinefelter_syndrome", "hypogonadism"],
    3: ["legionella_pneumonia", "azithromycin"],
    4: ["stable_angina", "exertional_chest_pain"],
    5: ["reactive_arthritis", "oligoarthritis"],
    6: ["mallory_weiss_syndrome", "hematemesis"],
    7: ["fournier_gangrene", "necrotizing_fasciitis"],
    8: ["transverse_myelitis", "sensory_level"],
    9: ["heart_failure_reduced_ef", "sglt2_inhibitor"],
    10: ["epidural_hematoma", "middle_meningeal_artery"],
    11: ["systemic_lupus_erythematosus", "hydroxychloroquine"],
    12: ["cluster_headache"],
    13: ["alzheimer_dementia", "delusion_of_theft"],
    14: ["cervical_cancer", "chemoradiation"],
    15: ["distal_bile_duct_cancer", "painless_jaundice"],
    16: ["immune_thrombocytopenic_purpura", "ivig"],
    17: ["ards", "lung_protective_ventilation"],
    18: ["ecg_incidental_finding", "observation"],
    19: ["cryptogenic_organizing_pneumonia"],
    20: ["hypoalbuminemia", "diuretic_resistant_edema", "albumin"],
    21: ["silicosis", "occupational_lung_disease"],
    22: ["asherman_syndrome", "secondary_amenorrhea"],
    23: ["ards", "mechanical_ventilation", "pneumonia"],
    24: ["premature_thelarche", "observation"],
    25: ["solitary_pulmonary_nodule", "chest_ct"],
    26: ["autosomal_dominant_polycystic_kidney_disease", "cerebral_aneurysm_screening"],
    27: ["copd", "spirometry"],
    28: ["hypogonadotropic_hypogonadism", "secondary_amenorrhea"],
    29: ["achalasia", "dysphagia"],
    30: ["organic_personality_disorder", "traumatic_brain_injury"],
    31: ["rheumatoid_arthritis", "anti_ccp_antibody"],
    32: ["infertility", "in_vitro_fertilization"],
    33: ["eosinophilic_esophagitis"],
    34: ["small_bowel_obstruction", "adhesive_obstruction"],
    35: ["varicocele", "male_infertility"],
    36: ["acetaminophen_overdose", "n_acetylcysteine"],
    37: ["candida_esophagitis", "fluconazole"],
    38: ["gastrointestinal_bleeding", "anemia"],
    39: ["spontaneous_bacterial_peritonitis", "cefotaxime"],
    40: ["acute_promyelocytic_leukemia", "disseminated_intravascular_coagulation"],
    41: ["heat_exhaustion", "heat_illness"],
    42: ["inflammatory_bowel_disease", "colonoscopy"],
    43: ["volume_depletion", "fluid_resuscitation"],
    44: ["postpartum_thyroiditis", "thyrotoxicosis"],
    45: ["pediatric_dehydration", "fluid_resuscitation"],
    46: ["major_depressive_disorder"],
    47: ["adhd", "methylphenidate"],
    48: ["siadh", "hyponatremia", "hypertonic_saline"],
    49: ["hypertension", "lifestyle_modification"],
    50: ["gastric_outlet_obstruction", "gastrojejunostomy"],
    51: ["lewy_body_dementia", "visual_hallucination"],
    52: ["ovarian_cyst", "observation"],
    53: ["gastric_outlet_obstruction", "pyloric_stent"],
    54: ["asplenia_vaccination", "encapsulated_organisms"],
    55: ["chronic_diarrhea", "fecal_leukocytes"],
    56: ["gonococcal_urethritis", "ceftriaxone_doxycycline"],
    57: ["peptic_ulcer_bleeding", "nsaid", "proton_pump_inhibitor"],
    58: ["developmental_delay", "gross_motor_milestones"],
    59: ["superior_mesenteric_artery_syndrome"],
    60: ["ovarian_fibrothecoma", "benign_ovarian_tumor"],
    61: ["hyperkalemia", "calcium_gluconate"],
    62: ["dyssynergic_defecation", "biofeedback"],
    63: ["mature_cystic_teratoma", "ovarian_mass"],
    64: ["achalasia", "pediatric_dysphagia"],
    65: ["major_depressive_disorder", "ssri"],
    66: ["functional_dyspepsia", "helicobacter_pylori_eradication"],
    67: ["asthma", "inhaled_corticosteroid"],
    68: ["functional_constipation"],
    69: ["hereditary_angioedema", "c4_complement"],
    70: ["bipolar_ii_disorder"],
    71: ["hypocalcemia", "hypoparathyroidism"],
    72: ["cervical_intraepithelial_neoplasia", "conization"],
    73: ["acute_pancreatitis", "abdominal_ct"],
    74: ["acute_abdomen", "exploratory_laparotomy"],
    75: ["hepatocellular_carcinoma", "chronic_hepatitis_c"],
    76: ["aortic_dissection", "ct_angiography"],
    77: ["infective_endocarditis"],
    78: ["atrial_fibrillation", "rate_control"],
    79: ["bipolar_i_disorder", "mania", "valproate"],
    80: ["recurrent_shoulder_dislocation", "hill_sachs_lesion"],
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
            labels["labeling_source"] = "manual_comprehensive_2"
            q["labels"] = labels
            n += 1
    TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 2교시 concept_tags 라벨링 {n}/80")


if __name__ == "__main__":
    raise SystemExit(main())
