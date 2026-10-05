#!/usr/bin/env python3
"""임상의학종합평가 1교시 concept_tags 라벨링 (Q21~60)."""

import json
from pathlib import Path

TARGET = Path("data_private/course_exams/extracted/COURSE_4_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_1교시.json")

TAGS = {
    21: ["chylous_fistula", "pancreaticoduodenectomy", "mct_diet"],
    22: ["major_depressive_disorder", "serotonin"],
    23: ["acute_pancreatitis", "epigastric_pain"],
    24: ["neonatal_hepatitis_b_prophylaxis", "hbsag_unknown"],
    25: ["fetal_growth_restriction", "immediate_delivery"],
    26: ["pulmonary_embolism", "dyspnea"],
    27: ["labor_induction", "decreased_fetal_movement"],
    28: ["idiopathic_pulmonary_fibrosis", "antifibrotic"],
    29: ["menorrhagia", "hysterectomy"],
    30: ["congenital_cytomegalovirus", "sensorineural_hearing_loss"],
    31: ["reactive_lymphadenitis", "cervical_lymphadenopathy"],
    32: ["massive_transfusion_protocol", "hemorrhagic_shock"],
    33: ["child_abuse", "failure_to_thrive"],
    34: ["septic_shock", "fluid_resuscitation"],
    35: ["diabetes_mellitus", "polyuria"],
    36: ["gastric_cancer", "upper_endoscopy"],
    37: ["lung_abscess", "purulent_sputum"],
    38: ["oropharyngeal_dysphagia", "videofluoroscopic_swallow_study"],
    39: ["multiple_myeloma", "urine_protein_electrophoresis"],
    40: ["kikuchi_disease", "histiocytic_necrotizing_lymphadenitis"],
    41: ["diabetic_ketoacidosis", "cerebral_edema", "mannitol"],
    42: ["trauma_airway_management", "polytrauma"],
    43: ["st_elevation_myocardial_infarction"],
    44: ["infertility", "hysterosalpingography"],
    45: ["atrial_fibrillation", "anticoagulation", "edoxaban"],
    46: ["burn_injury", "escharotomy"],
    47: ["chronic_spontaneous_urticaria", "antihistamine"],
    48: ["trichomonas_vaginitis"],
    49: ["tension_pneumothorax", "needle_thoracostomy"],
    50: ["nephrotic_syndrome"],
    51: ["renal_abscess", "percutaneous_drainage"],
    52: ["delirium", "hospitalized_elderly"],
    53: ["gastrointestinal_bleeding", "hematochezia"],
    54: ["medical_record_soap_note", "clinical_documentation"],
    55: ["anterior_mediastinal_mass", "thymoma"],
    56: ["gout", "xanthine_oxidase_inhibitor", "tophi"],
    57: ["abnormal_uterine_bleeding", "gnrh_agonist"],
    58: ["sheehan_syndrome", "hypopituitarism"],
    59: ["infectious_mononucleosis", "cervical_lymphadenopathy"],
    60: ["major_depressive_disorder", "suicidality"],
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
            labels["labeling_source"] = "manual_comprehensive_1"
            q["labels"] = labels
            n += 1
    TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 1교시 concept_tags 라벨링 {n}/40")


if __name__ == "__main__":
    raise SystemExit(main())
