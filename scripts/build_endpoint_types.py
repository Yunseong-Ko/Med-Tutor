#!/usr/bin/env python3
"""Coarse-type the out-of-registry edge endpoints (disorder|finding|test_procedure|drug_substance|
organism_agent) — the prerequisite the reference feedback named. High-precision heuristics first;
the rest go to an LLM pass. Edge-type context (diagnosed_by/treated_with/caused_by) is kept per
endpoint so the LLM typer has a strong prior.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data_private" / "curriculum" / "endpoint_typing_worklist.json"
OUT_TYPED = ROOT / "data_private" / "curriculum" / "endpoint_types_heuristic.json"
OUT_UNRES = ROOT / "data_private" / "curriculum" / "endpoint_types_unresolved.json"

TEST = re.compile(r"(biopsy|endoscopy|colonoscopy|gastroscopy|sigmoidoscopy|bronchoscopy|cystoscopy|"
                  r"laryngoscopy|otoscopy|ophthalmoscopy|fundoscopy|colposcopy|laparoscopy|laparotomy|"
                  r"_ct$|_ct_|computed_tomography|_mri$|_mri_|magnetic_resonance|ultrasound|ultrasonography|"
                  r"sonograph|echocardiogra|_scan$|scintigraphy|radiograph|x_ray|xray|angiograph|venograph|"
                  r"_ecg$|electrocardiogram|electroencephalogram|_eeg$|_emg$|manometry|spirometry|audiometry|"
                  r"urinalysis|culture$|_culture_|gram_stain|smear|cytology|histolog|serolog|_pcr$|_assay$|"
                  r"_titer$|_panel$|_test$|_testing$|screening|mammograph|tomography|aspiration|_lavage$|"
                  r"dexa|densitometry|paracentesis|thoracentesis|lumbar_puncture|examination|auscultation|"
                  r"palpation|electrophoresis|immunohistochem|karyotyp|blood_smear|bone_marrow_biopsy|"
                  r"skin_prick|patch_test|fine_needle)", re.I)
ORG = re.compile(r"(_virus$|_virus_|virus$|bacteri|_coli|aureus|pylori|pneumoniae|tuberculosis|mycobacter|"
                 r"candida|aspergillus|plasmodium|_species$|streptococc|staphylococc|clostrid|salmonella|"
                 r"shigella|helicobacter|treponema|neisseria|klebsiella|pseudomonas|enterococc|rotavirus|"
                 r"cytomegalovirus|epstein_barr|parvovirus|toxin$|_toxin_|endotoxin|venom)", re.I)
DISORDER = re.compile(r"(_syndrome$|_disease$|_disorder$|itis$|_carcinoma|_sarcoma|lymphoma$|leukemia$|"
                      r"_oma$|osis$|_pathy$|nephropathy|myopathy|neuropathy|_failure$|_infection$|infection$|"
                      r"_deficiency$|stenosis$|insufficiency$|thrombosis$|embolism$|ischemia$|infarction$|"
                      r"malformation$|atresia$|hyperplasia$|dysplasia$|hernia$|abscess$|ulcer$|fistula$|"
                      r"aneurysm$|obstruction$|perforation$|cirrhosis$|fibrosis$|anemia$|cancer$)", re.I)
FINDING = re.compile(r"(pain$|_pain_|fever$|bleeding$|hemorrhage$|edema$|jaundice$|uria$|rrhea$|diarrhea|"
                     r"cough$|dyspnea$|nausea$|vomiting$|weight_loss$|fatigue$|rash$|pruritus$|_mass$|"
                     r"lesion$|murmur$|effusion$|ascites$|splenomegaly$|hepatomegaly$|lymphadenopathy$|"
                     r"cyanosis$|pallor$|hypotension$|tachycardia$|bradycardia$|leukocytosis$|thrombocytopenia$|"
                     r"eosinophilia$|neutropenia$|hypoxemia$|hypoxia$|elevated_|decreased_|increased_|"
                     r"positive_|palpable_|_deviation$|distension$|tenderness$|swelling$|weakness$|numbness$)", re.I)
DRUG = re.compile(r"(cillin$|mycin$|micin$|_pril$|sartan$|statin$|_zole$|_dipine$|_olol$|_pam$|_lam$|"
                  r"cycline$|floxacin$|_mab$|_nib$|_tinib$|prazole$|_parin$|warfarin|heparin|aspirin|"
                  r"insulin|steroid$|corticosteroid|dexamethasone|prednisolone|prednisone|metformin|"
                  r"furosemide|antibiotic|chemotherap|immunotherap|vaccine$|_ig$|immunoglobulin|"
                  r"transfusion$|supplementation$|replacement_therapy$|_diet$)", re.I)


def heuristic(eid: str, edge_types: dict) -> str | None:
    # order matters: procedure/organism/drug are distinctive; disorder vs finding last
    if TEST.search(eid):
        return "test_procedure"
    if ORG.search(eid):
        return "organism_agent"
    if DRUG.search(eid):
        return "drug_substance"
    if DISORDER.search(eid):
        return "disorder"
    if FINDING.search(eid):
        return "finding"
    return None


def main() -> None:
    work = json.loads(WORK.read_text(encoding="utf-8"))["items"]
    typed, unresolved = {}, []
    for w in work:
        t = heuristic(w["id"], w["edge_types"])
        if t:
            typed[w["id"]] = t
        else:
            unresolved.append(w)
    OUT_TYPED.write_text(json.dumps({"total": len(typed), "types": typed}, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_UNRES.write_text(json.dumps({"total": len(unresolved), "items": unresolved}, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(f"heuristic-typed: {len(typed)}/{len(work)} ({len(typed)/len(work)*100:.0f}%)  {dict(Counter(typed.values()))}")
    print(f"unresolved -> LLM: {len(unresolved)}")


if __name__ == "__main__":
    main()
