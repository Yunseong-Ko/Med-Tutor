#!/usr/bin/env python3
"""임상의학종합평가 4교시 concept_tags 라벨링."""

import json
from pathlib import Path

TARGET = Path("data_private/course_exams/extracted/COURSE_X_DATE_UNKNOWN_EXAM_4교시.json")

TAGS = {
    1: ["neonatal_jaundice", "physiologic_jaundice"],
    2: ["traumatic_brain_injury", "cerebral_edema", "mannitol"],
    3: ["benign_prostatic_hyperplasia", "urinary_retention"],
    4: ["hypothyroidism_in_pregnancy", "levothyroxine"],
    5: ["hypothyroidism", "secondary_amenorrhea"],
    6: ["acute_liver_failure", "hepatic_encephalopathy"],
    7: ["cardiac_tamponade", "post_ablation"],
    8: ["premature_rupture_of_membranes", "cesarean_delivery"],
    9: ["bacterial_meningitis"],
    10: ["papillary_thyroid_carcinoma"],
    11: ["adjustment_disorder", "adolescent_anxiety"],
    12: ["hyperthyroidism", "tremor"],
    13: ["gastroschisis", "abdominal_wall_defect"],
    14: ["nausea_and_vomiting_of_pregnancy", "hyperemesis_gravidarum"],
    15: ["gallbladder_carcinoma", "incidental_finding"],
    16: ["central_airway_obstruction", "bronchoscopy"],
    17: ["viral_hepatitis", "hepatitis_serology"],
    18: ["lung_abscess", "aspiration_pneumonia"],
    19: ["pulmonary_embolism", "pleuritic_chest_pain"],
    20: ["chronic_cough", "upper_airway_cough_syndrome"],
    21: ["spontaneous_bacterial_peritonitis", "cirrhosis"],
    22: ["chronic_obstructive_pulmonary_disease", "dyspnea"],
    23: ["laryngotracheal_trauma", "airway_management"],
    24: ["esophageal_variceal_bleeding", "cirrhosis"],
    25: ["primary_biliary_cholangitis", "antimitochondrial_antibody"],
    26: ["heart_failure", "type_2_diabetes", "SGLT2_inhibitor"],
    27: ["anal_fissure", "rectal_bleeding_infant"],
    28: ["malaria", "artesunate"],
    29: ["deep_vein_thrombosis", "postoperative"],
    30: ["obesity_in_pregnancy", "maternal_obesity"],
    31: ["acute_urinary_retention", "postrenal_acute_kidney_injury"],
    32: ["toxic_hepatitis", "drug_induced_liver_injury"],
    33: ["multiple_myeloma", "proteinuria"],
    34: ["duodenal_atresia", "polyhydramnios"],
    35: ["malnutrition", "cognitive_impairment"],
    36: ["postpartum_breast_engorgement", "mastitis"],
    37: ["attention_deficit_hyperactivity_disorder", "methylphenidate"],
    38: ["tuberculous_lymphadenitis"],
    39: ["sheehan_syndrome", "hypopituitarism"],
    40: ["ductal_carcinoma_in_situ", "breast"],
    41: ["myasthenia_gravis", "acetylcholine_receptor_antibody"],
    42: ["nephrotic_syndrome", "minimal_change_disease"],
    43: ["vasovagal_syncope", "orthostatic_intolerance"],
    44: ["anorexia_nervosa", "ventricular_arrhythmia"],
    45: ["parkinson_disease", "bradykinesia"],
    46: ["alcohol_withdrawal_delirium", "delirium_tremens"],
    47: ["patent_ductus_arteriosus", "prematurity"],
    48: ["multiple_myeloma", "renal_amyloidosis", "urine_protein_electrophoresis"],
    49: ["recurrent_laryngeal_nerve_injury", "thyroidectomy_complication"],
    50: ["bronchiolitis", "respiratory_syncytial_virus"],
    51: ["active_labor", "normal_labor"],
    52: ["premature_ventricular_complex", "palpitation"],
    53: ["pterygium", "ultraviolet_exposure"],
    54: ["wernicke_korsakoff_syndrome", "confabulation"],
    55: ["eisenmenger_syndrome", "pulmonary_arterial_hypertension"],
    56: ["hepatocellular_carcinoma", "chronic_hepatitis_b"],
    57: ["drug_eruption", "maculopapular_rash"],
    58: ["hypoglycemia", "insulin_overdose"],
    59: ["erythema_toxicum_neonatorum"],
    60: ["severe_fever_with_thrombocytopenia_syndrome", "tick_borne"],
    61: ["cough_variant_asthma", "methacholine_challenge"],
    62: ["fetal_aneuploidy_screening", "nuchal_translucency"],
    63: ["complex_febrile_seizure"],
    64: ["diaphragmatic_injury", "penetrating_thoracoabdominal_trauma"],
    65: ["venous_thromboembolism_prophylaxis_in_pregnancy", "low_molecular_weight_heparin"],
    66: ["complete_atrioventricular_block", "pacemaker"],
    67: ["neonatal_sepsis", "ampicillin_gentamicin"],
    68: ["generalized_anxiety_disorder", "SSRI"],
    69: ["dyslipidemia", "statin"],
    70: ["gynecomastia"],
    71: ["aortic_stenosis", "exertional_dyspnea"],
    72: ["systemic_sclerosis", "raynaud_phenomenon"],
    73: ["paget_disease_of_the_breast"],
    74: ["generalized_anxiety_disorder", "escitalopram"],
    75: ["ventricular_septal_rupture", "myocardial_infarction_complication"],
    76: ["cholinergic_urticaria"],
    77: ["hemorrhagic_shock", "blunt_abdominal_trauma"],
    78: ["tuberculosis", "antituberculous_therapy"],
    79: ["soft_tissue_mass", "excisional_biopsy"],
    80: ["postoperative_delirium", "mixed_delirium"],
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
            labels["labeling_source"] = "manual_comprehensive_4"
            q["labels"] = labels
            n += 1
    TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 4교시 concept_tags 라벨링 {n}/80")


if __name__ == "__main__":
    raise SystemExit(main())
