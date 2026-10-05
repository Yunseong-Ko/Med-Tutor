#!/usr/bin/env python3
"""Apply reviewed safety corrections to the 2026-07-12 clinical-axis drafts.

The source batches remain medical-review drafts.  This script only encodes
specific corrections identified by an independent manual review; it does not
grant medical approval.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "data_private" / "curriculum" / "clinical_axes_batches"
FILES = {
    "pilot": BATCH_DIR / "codex_batch_002_pilot_20260712.json",
    "a": BATCH_DIR / "codex_batch_003a_20260712.json",
    "b": BATCH_DIR / "codex_batch_003b_20260712.json",
    "c": BATCH_DIR / "codex_batch_003c_20260712.json",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require_contains(value: object, needle: str, label: str) -> None:
    if needle.casefold() not in str(value).casefold():
        raise SystemExit(f"stale correction target {label}: expected {needle!r}")


def replace_list_item(values: list[str], index: int, needle: str, replacement: str, label: str) -> None:
    require_contains(values[index], needle, label)
    values[index] = replacement


def remove_list_item(values: list[str], index: int, needle: str, label: str) -> None:
    require_contains(values[index], needle, label)
    del values[index]


def apply_fixes(documents: dict[str, dict]) -> list[str]:
    changed: list[str] = []

    pilot = documents["pilot"]["axes"]
    ampullary = pilot["ampullary_carcinoma"]
    require_contains(ampullary["pathophysiology"]["summary"], "at or around", "ampullary scope")
    ampullary["pathophysiology"]["summary"] = (
        "Ampullary carcinoma arises from epithelium within the ampulla of Vater. "
        "Distal cholangiocarcinoma, pancreatic ductal adenocarcinoma, and non-ampullary "
        "duodenal carcinoma are distinct periampullary cancers and should not be grouped under this concept."
    )
    for index, needle in ((6, "biliary tract inflammatory"), (4, "Choledochal"), (3, "Chronic pancreatitis")):
        remove_list_item(ampullary["risk_factors"], index, needle, f"ampullary risk_factors[{index}]")
    changed.append("ampullary_carcinoma")

    cirrhosis = pilot["alcoholic_cirrhosis"]
    require_contains(cirrhosis["treatment"]["principles"], "sobriety criteria", "alcoholic cirrhosis principle")
    cirrhosis["treatment"]["principles"] = (
        "The cornerstone is sustained alcohol abstinence with addiction treatment and nutritional rehabilitation. "
        "Manage portal-hypertension and hepatic-insufficiency complications, and consider transplantation for "
        "selected end-stage disease after individualized multidisciplinary medical, psychosocial, and addiction assessment."
    )
    remove_list_item(
        cirrhosis["treatment"]["contraindicated_for"],
        3,
        "sobriety",
        "alcoholic cirrhosis transplant exclusion",
    )
    cirrhosis["uncertainty_notes"].append(
        "Transplant candidacy requires individualized multidisciplinary medical, psychosocial, and addiction assessment; "
        "a fixed abstinence interval alone should not be treated as a universal exclusion criterion."
    )
    changed.append("alcoholic_cirrhosis")

    rhinitis = pilot["allergic_rhinitis"]
    replace_list_item(
        rhinitis["treatment"]["indicated_for"],
        3,
        "Leukotriene receptor",
        "Montelukast only when alternative allergic-rhinitis therapies are ineffective or not tolerated, or when a "
        "coexisting indication supports use, after counseling about serious neuropsychiatric adverse effects.",
        "allergic rhinitis montelukast",
    )
    changed.append("allergic_rhinitis")

    batch_a_doc = documents["a"]
    batch_a = batch_a_doc["axes"]
    angioedema = batch_a["angioedema"]
    angioedema["treatment"]["principles"] = (
        "Prioritize airway assessment and protection. Use epinephrine for anaphylaxis or histaminergic disease and "
        "established on-demand therapy for hereditary angioedema. For ACE-inhibitor angioedema, stop the ACE "
        "inhibitor and provide airway-focused supportive care; off-label bradykinin-directed treatment has "
        "inconsistent evidence and must not delay airway management."
    )
    remove_list_item(
        angioedema["treatment"]["contraindicated_for"],
        1,
        "Antihistamines as sole therapy",
        "angioedema ineffective antihistamine entry",
    )
    angioedema["uncertainty_notes"].append(
        "Antihistamines are ineffective as sole therapy for bradykinin-mediated angioedema; this is lack of "
        "indication or efficacy rather than a true contraindication."
    )
    changed.append("angioedema")

    asthma = batch_a["asthma_exacerbation"]
    replace_list_item(
        asthma["treatment"]["indicated_for"],
        5,
        "ventilatory support",
        "A closely monitored noninvasive-ventilation trial may be considered only in selected cooperative patients; "
        "evidence is weak and it must not delay intubation. Use invasive ventilation for impending or established "
        "respiratory failure.",
        "asthma ventilatory support",
    )
    changed.append("asthma_exacerbation")

    atypical = batch_a["atypical_pneumonia"]
    atypical["pathophysiology"]["summary"] = (
        "Atypical pneumonia is a historical, imprecise syndrome label for selected bacterial and viral causes of "
        "community-acquired pneumonia; no single clinical, inflammatory, or radiographic pattern reliably "
        "distinguishes it from other community-acquired pneumonia."
    )
    atypical["treatment"]["principles"] = (
        "Beta-lactams lack activity against confirmed Mycoplasma, Chlamydia pneumoniae, and Legionella, but "
        "beta-lactam monotherapy is not a universal community-acquired-pneumonia contraindication. Select empiric "
        "therapy by care setting, severity, comorbidity, resistance risk, and microbiologic evidence."
    )
    remove_list_item(
        atypical["treatment"]["contraindicated_for"],
        0,
        "Beta-lactam monotherapy",
        "atypical pneumonia beta-lactam entry",
    )
    changed.append("atypical_pneumonia")

    adpkd = batch_a["autosomal_dominant_polycystic_kidney_disease"]
    replace_list_item(
        adpkd["treatment"]["contraindicated_for"],
        0,
        "Tolvaptan",
        "Tolvaptan in planned pregnancy, pregnancy or breastfeeding; significant non-polycystic liver disease; "
        "inability to perceive or respond to thirst or manage aquaresis; high volume-depletion risk; uncorrected "
        "hypernatremia; urinary tract obstruction; or concurrent strong CYP3A inhibitors.",
        "ADPKD tolvaptan",
    )
    changed.append("autosomal_dominant_polycystic_kidney_disease")

    bph = batch_a["benign_prostatic_hyperplasia"]
    for index, needle in ((2, "Anticholinergic"), (1, "Alpha-blockers"), (0, "reductase inhibitors")):
        remove_list_item(bph["treatment"]["contraindicated_for"], index, needle, f"BPH contraindication {index}")
    bph["uncertainty_notes"].extend(
        [
            "When fertility is a priority, counsel patients taking a five-alpha-reductase inhibitor about possible "
            "sexual or semen effects; paternal use is not itself a fetal-malformation contraindication.",
            "Choose alpha blockers according to blood-pressure effects and use anticholinergics cautiously after "
            "post-void-residual assessment; these are individualized precautions rather than class-wide absolute contraindications.",
        ]
    )
    changed.append("benign_prostatic_hyperplasia")

    arrest = batch_a["cardiac_arrest"]
    replace_list_item(
        arrest["treatment"]["indicated_for"],
        4,
        "temperature management",
        "Deliberate protocolized temperature control, including fever prevention, for adults who remain unresponsive "
        "to verbal commands after return of spontaneous circulation.",
        "cardiac arrest temperature control",
    )
    replace_list_item(
        arrest["treatment"]["indicated_for"],
        5,
        "coronary angiography",
        "Emergency coronary angiography for persistent ST elevation or selected patients with shock, recurrent "
        "ventricular arrhythmia, or significant ongoing ischemia; do not use routine emergent angiography in stable "
        "post-arrest patients without these features.",
        "cardiac arrest angiography",
    )
    remove_list_item(
        arrest["treatment"]["contraindicated_for"],
        0,
        "Prolonged resuscitation",
        "cardiac arrest termination rule",
    )
    arrest["uncertainty_notes"].append(
        "Termination of resuscitation must follow a validated BLS, ALS, or universal termination-of-resuscitation "
        "rule, local protocol and law, and the full clinical context; unwitnessed arrest or a non-shockable rhythm "
        "alone is not a contraindication to continued resuscitation."
    )
    changed.append("cardiac_arrest")

    shock = batch_a["cardiogenic_shock"]
    replace_list_item(
        shock["treatment"]["indicated_for"],
        3,
        "Mechanical circulatory support",
        "Consider temporary mechanical circulatory support only in carefully selected refractory shock after "
        "phenotype and hemodynamic assessment by an experienced shock team; device choice is cause- and "
        "patient-specific, and routine intra-aortic balloon-pump use in unselected infarct-related shock is not supported.",
        "cardiogenic shock MCS",
    )
    changed.append("cardiogenic_shock")

    cough = batch_a["chronic_cough"]
    cough["treatment"]["principles"] = (
        "Evaluate red flags and patient-specific treatable traits rather than assuming a fixed diagnostic triad. "
        "Use acid-suppressive therapy only when typical reflux symptoms or objective acid reflux support the "
        "indication; do not routinely prescribe a proton-pump inhibitor for chronic cough alone."
    )
    replace_list_item(
        cough["treatment"]["indicated_for"],
        2,
        "Proton pump inhibitor",
        "Acid-suppressive therapy when typical reflux symptoms or objective acid reflux supports a causal role, not "
        "for chronic cough alone.",
        "chronic cough PPI",
    )
    changed.append("chronic_cough")

    prostatitis = batch_a["chronic_prostatitis"]
    replace_list_item(
        prostatitis["risk_factors"],
        3,
        "Psychological stress",
        "Psychological distress, catastrophizing, and central pain amplification may coexist with chronic "
        "prostatitis or chronic pelvic pain syndrome and influence symptom burden and treatment needs; they should "
        "not be labeled as proven causal disease risk factors.",
        "chronic prostatitis psychosocial factor",
    )
    changed.append("chronic_prostatitis")

    cough_asthma = batch_a["cough_variant_asthma"]
    replace_list_item(
        cough_asthma["treatment"]["indicated_for"],
        1,
        "Short-acting beta",
        "Use an inhaled-corticosteroid-containing asthma regimen; if a short-acting beta agonist is used as a "
        "reliever, it should not be presented as stand-alone long-term anti-inflammatory treatment.",
        "cough-variant asthma SABA",
    )
    remove_list_item(
        cough_asthma["treatment"]["contraindicated_for"],
        1,
        "ACE inhibitors",
        "cough-variant asthma ACE inhibitor",
    )
    cough_asthma["uncertainty_notes"].append(
        "Evaluate ACE-inhibitor cough as an alternative or contributing diagnosis and discontinue or substitute the "
        "ACE inhibitor when clinically implicated; this does not belong in the disease-treatment contraindication axis."
    )
    changed.append("cough_variant_asthma")

    vasculitis = batch_a["cutaneous_vasculitis"]
    replace_list_item(
        vasculitis["pathophysiology"]["key_steps"],
        0,
        "immune complexes",
        "Mechanism varies by subtype; immune-complex deposition is common in cutaneous leukocytoclastic vasculitis, "
        "but pauci-immune and other vascular inflammatory patterns also occur.",
        "cutaneous vasculitis mechanism",
    )
    replace_list_item(
        vasculitis["treatment"]["indicated_for"],
        2,
        "Systemic corticosteroids",
        "Consider a short systemic corticosteroid course for severe, painful, ulcerative, recurrent, or refractory "
        "skin-limited disease after evaluating infection; systemic organ involvement requires urgent subtype-specific "
        "specialist treatment rather than corticosteroid monotherapy.",
        "cutaneous vasculitis steroids",
    )
    changed.append("cutaneous_vasculitis")

    diabetes = batch_a["diabetes_mellitus"]
    replace_list_item(
        diabetes["treatment"]["indicated_for"],
        2,
        "Metformin",
        "Metformin is an appropriate foundational option for many people with type two diabetes, but initial therapy "
        "is person-centered; use SGLT2 inhibitors or GLP-one-based therapy for relevant cardiovascular, kidney, "
        "heart-failure, or obesity indications independent of metformin.",
        "diabetes metformin",
    )
    replace_list_item(
        diabetes["treatment"]["contraindicated_for"],
        2,
        "SGLT",
        "Apply agent-specific kidney-function thresholds; glycemic efficacy declines as kidney function falls but "
        "cardiorenal benefit may persist. Avoid or hold SGLT2 inhibitors in active ketoacidosis or high-risk acute "
        "fasting, surgery, or severe-illness contexts.",
        "diabetes SGLT2",
    )
    changed.append("diabetes_mellitus")

    ectopic_pregnancy = batch_a["ectopic_pregnancy"]
    ectopic_pregnancy["prognosis"]["natural_history"] = (
        "An ectopic pregnancy may regress spontaneously, undergo tubal abortion, persist, or rupture; carefully "
        "selected stable patients may undergo monitored expectant management, but rupture can occur and requires "
        "reliable follow-up and emergency access."
    )
    replace_list_item(
        ectopic_pregnancy["treatment"]["indicated_for"],
        3,
        "laparotomy",
        "Immediate operative management and hemorrhage resuscitation for rupture with hemodynamic instability; the "
        "surgical approach is chosen according to instability, bleeding, anatomy, expertise, and available resources.",
        "ectopic pregnancy surgery",
    )
    changed.append("ectopic_pregnancy")

    febrile = batch_a["febrile_illness"]
    febrile["prognosis"]["staging_or_grading"] = (
        "Fever has no universal severity stage. Fever of unknown origin is a duration-and-diagnostic category, not a "
        "severity grade; sepsis is suspected infection with organ dysfunction and should be assessed separately "
        "rather than presented as fever staging."
    )
    replace_list_item(
    febrile["treatment"]["indicated_for"],
        1,
        "Empirical broad-spectrum antibiotics",
        "Give prompt empiric antibiotics for defined high-risk syndromes such as suspected sepsis or septic shock, "
        "febrile neutropenia, suspected bacterial meningitis, or another serious bacterial infection, using syndrome- "
        "and local-resistance-specific therapy; immunocompromised status alone does not define one universal regimen.",
        "febrile illness empiric antibiotics",
    )
    changed.append("febrile_illness")

    febrile_pregnancy = batch_a["febrile_illness_in_pregnancy"]
    replace_list_item(
        febrile_pregnancy["treatment"]["contraindicated_for"],
        0,
        "NSAIDs",
        "Avoid NSAIDs from about twenty weeks unless specifically necessary because of fetal renal dysfunction and "
        "oligohydramnios risk; avoid at about thirty weeks or later because of premature ductus arteriosus closure.",
        "febrile pregnancy NSAID timing",
    )
    remove_list_item(
        febrile_pregnancy["treatment"]["contraindicated_for"],
        2,
        "Fluoroquinolones",
        "febrile pregnancy fluoroquinolone",
    )
    febrile_pregnancy["uncertainty_notes"].append(
        "Fluoroquinolones are not an absolute class contraindication in pregnancy; reserve them for infections in "
        "which expected benefit outweighs risk and preferred alternatives are unsuitable."
    )
    changed.append("febrile_illness_in_pregnancy")

    hp = batch_a["hypersensitivity_pneumonitis"]
    hp["prognosis"]["staging_or_grading"] = (
        "Classify hypersensitivity pneumonitis primarily as nonfibrotic or fibrotic using clinical, high-resolution-CT, "
        "and pathologic findings; acute, subacute, and chronic labels are historical categories with imprecise "
        "diagnostic and prognostic correlation."
    )
    hp["treatment"]["principles"] = (
        "Antigen identification and avoidance are central. Corticosteroids may be considered for selected severe or "
        "symptomatic nonfibrotic disease; other immunosuppression is specialist-directed because evidence is limited. "
        "Consider antifibrotic therapy only when a non-IPF fibrotic interstitial lung disease meets progressive "
        "pulmonary-fibrosis criteria despite appropriate management."
    )
    changed.append("hypersensitivity_pneumonitis")

    hypoglycemia_general = batch_a["hypoglycemia"]
    hypoglycemia_general["prognosis"]["staging_or_grading"] = (
        "For diabetes-related hypoglycemia, Level 1 is glucose below 70 but at least 54 mg/dL, Level 2 is below "
        "54 mg/dL, and Level 3 is altered mental or physical functioning requiring assistance regardless of glucose "
        "value. Whipple's triad confirms a hypoglycemic disorder in people without diabetes and is not a severity grade."
    )
    changed.append("hypoglycemia")

    ild = batch_a["interstitial_lung_disease"]
    replace_list_item(
        ild["treatment"]["indicated_for"],
        1,
        "Systemic corticosteroids",
        "Systemic corticosteroids only for selected inflammatory or steroid-responsive interstitial lung disease "
        "after subtype confirmation; do not generalize their use to all connective-tissue-disease-associated ILD, "
        "and do not use glucocorticoids as first-line ILD treatment in systemic sclerosis.",
        "ILD corticosteroids",
    )
    changed.append("interstitial_lung_disease")

    legionella = batch_a["legionella_pneumonia"]
    for index, needle in ((1, "Aminoglycoside"), (0, "Beta-lactam")):
        remove_list_item(
            legionella["treatment"]["contraindicated_for"],
            index,
            needle,
            f"Legionella ineffective monotherapy {index}",
        )
    legionella["treatment"]["principles"] += (
        " Do not use beta-lactam or aminoglycoside monotherapy as definitive treatment for confirmed Legionella "
        "pneumonia because these agents lack reliable intracellular activity."
    )
    changed.append("legionella_pneumonia")

    leptospirosis = batch_a["leptospirosis"]
    replace_list_item(
        leptospirosis["treatment"]["indicated_for"],
        0,
        "Doxycycline",
        "Doxycycline for selected mild leptospirosis when appropriate. Chemoprophylaxis is a separate prevention "
        "decision and may be considered only for selected adults with high-risk, short-term exposure because "
        "supporting evidence is limited.",
        "leptospirosis doxycycline",
    )
    changed.append("leptospirosis")

    lgib = batch_a["lower_gastrointestinal_bleeding"]
    lgib["pathophysiology"]["summary"] = (
        "Acute lower gastrointestinal bleeding originates from the colon or rectum; small-bowel bleeding is a "
        "distinct middle-gastrointestinal bleeding entity with a different diagnostic pathway."
    )
    remove_list_item(
        lgib["treatment"]["indicated_for"],
        2,
        "Tagged red cell",
        "lower GI bleeding localization test",
    )
    lgib["uncertainty_notes"].append(
        "CT angiography is the initial localization test for ongoing hemodynamically significant hematochezia; "
        "radionuclide scintigraphy is reserved for selected intermittent bleeding when endoscopy and CT angiography "
        "do not localize the source. These belong in a diagnostic or localization axis, not treatment."
    )
    changed.append("lower_gastrointestinal_bleeding")

    lymphedema = batch_a["lymphedema"]
    remove_list_item(
        lymphedema["treatment"]["contraindicated_for"],
        0,
        "Diuretics",
        "lymphedema diuretics",
    )
    lymphedema["treatment"]["principles"] += (
        " Long-term diuretics are discouraged as routine lymphedema treatment because benefit is marginal and fluid "
        "or electrolyte imbalance may occur; short courses may be appropriate for specific comorbid conditions or effusions."
    )
    changed.append("lymphedema")

    meningococcal = batch_a["meningococcal"]
    replace_list_item(
        meningococcal["treatment"]["indicated_for"],
        2,
        "corticosteroids",
        "Give dexamethasone with or before antibiotics when bacterial meningitis is strongly suspected, but "
        "discontinue it if Neisseria meningitidis is confirmed. Do not routinely give corticosteroids for "
        "meningococcal septicemia; consider replacement-dose corticosteroids only for refractory septic shock when indicated.",
        "meningococcal corticosteroids",
    )
    replace_list_item(
        meningococcal["treatment"]["contraindicated_for"],
        1,
        "Lumbar puncture",
        "Do not perform lumbar puncture during shock, uncontrolled seizures, significant bleeding risk, extensive or "
        "rapidly spreading purpura, or signs suggesting raised intracranial pressure or an evolving space-occupying "
        "lesion; obtain blood samples, start antibiotics, stabilize, and image when indicated without delaying treatment.",
        "meningococcal lumbar puncture",
    )
    changed.append("meningococcal")

    metabolic = batch_a["metabolic_syndrome"]
    remove_list_item(
        metabolic["treatment"]["contraindicated_for"],
        0,
        "Fibrates",
        "metabolic syndrome fibrate interaction",
    )
    metabolic["uncertainty_notes"].append(
        "Avoid gemfibrozil with most statins because of increased myopathy risk; other fibrate-statin combinations "
        "may be used selectively with interaction review and monitoring."
    )
    changed.append("metabolic_syndrome")

    micturition = batch_a["micturition_syncope"]
    remove_list_item(
        micturition["treatment"]["contraindicated_for"],
        0,
        "Vasodilatory medications",
        "micturition syncope medication precaution",
    )
    micturition["treatment"]["principles"] += (
        " Review medications that lower blood pressure or impair compensatory vasoconstriction individually because "
        "they may increase susceptibility; this is a modifiable risk or precaution, not an absolute contraindication."
    )
    changed.append("micturition_syncope")

    occupational = batch_a["occupational_lung_disease"]
    replace_list_item(
        occupational["treatment"]["indicated_for"],
        2,
        "Antifibrotic",
        "Nintedanib may be considered for eligible non-IPF interstitial lung disease that meets progressive pulmonary "
        "fibrosis criteria despite appropriate disease-specific management; an IPF-like imaging pattern alone is not "
        "the indication.",
        "occupational lung disease antifibrotic",
    )
    remove_list_item(
        occupational["treatment"]["contraindicated_for"],
        1,
        "corticosteroid monotherapy",
        "occupational lung disease steroid precaution",
    )
    occupational["treatment"]["principles"] += (
        " Establish the occupational-lung-disease subtype and evaluate active infection before initiating "
        "corticosteroid or other immunosuppressive therapy."
    )
    changed.append("occupational_lung_disease")

    # The unqualified concept id conflates pleural empyema with intracranial
    # subdural/epidural empyema.  Quarantine it instead of merging unsafe axes.
    if "empyema" in batch_a:
        del batch_a["empyema"]
        batch_a_doc.get("harrison_refs", {}).pop("empyema", None)
        progress = batch_a_doc.get("_progress") or {}
        progress["selected_ids"] = [cid for cid in progress.get("selected_ids", []) if cid != "empyema"]
        progress["completed_ids"] = [cid for cid in progress.get("completed_ids", []) if cid != "empyema"]
        batch_a_doc.get("_meta", {})["batch_size"] = len(progress.get("selected_ids", []))
        changed.append("empyema_quarantined")

    batch_b = documents["b"]["axes"]
    felty = batch_b["felty_syndrome"]
    replace_list_item(
        felty["treatment"]["indicated_for"],
        3,
        "Biologic DMARDs",
        "Rituximab may be considered for refractory Felty syndrome after conventional DMARD therapy, with "
        "infection-risk assessment and specialist oversight.",
        "Felty biologic therapy",
    )
    changed.append("felty_syndrome")

    ectopic = batch_b["ectopic_acth_cushing_syndrome"]
    replace_list_item(
        ectopic["treatment"]["indicated_for"],
        3,
        "Pasireotide",
        "Somatostatin-receptor-directed therapy may be considered only for selected receptor-positive neuroendocrine "
        "tumors under specialist care; pasireotide is not routine therapy for ectopic ACTH syndrome.",
        "ectopic ACTH pasireotide",
    )
    replace_list_item(
        ectopic["treatment"]["contraindicated_for"],
        0,
        "fertility preservation",
        "Mifepristone is contraindicated in pregnancy and requires specialist monitoring because cortisol "
        "concentrations do not reliably measure treatment response.",
        "ectopic ACTH mifepristone",
    )
    changed.append("ectopic_acth_cushing_syndrome")

    prca = batch_b["pure_red_cell_aplasia"]
    replace_list_item(
        prca["prognosis"]["factors"],
        0,
        "antiviral therapy",
        "Identification and successful treatment of an underlying cause, such as thymoma management or intravenous "
        "immunoglobulin for chronic parvovirus B19-associated PRCA in an immunocompromised host.",
        "PRCA underlying cause",
    )
    changed.append("pure_red_cell_aplasia")

    hypoglycemia = batch_b["tumor_induced_hypoglycemia"]
    require_contains(hypoglycemia["pathophysiology"]["summary"], "Insulinoma", "tumor hypoglycemia scope")
    hypoglycemia["pathophysiology"]["summary"] = (
        "In this paraneoplastic axis, tumor-induced hypoglycemia refers to non-islet-cell tumor hypoglycemia, "
        "usually mediated by incompletely processed IGF-II; insulinoma is a distinct endogenous hyperinsulinemic "
        "tumor and should be modeled separately."
    )
    replace_list_item(
        hypoglycemia["treatment"]["indicated_for"],
        3,
        "Growth hormone",
        "Recombinant growth hormone as a specialist-directed adjunct when glucocorticoids and nutritional support "
        "are insufficient or produce unacceptable toxicity.",
        "tumor hypoglycemia growth hormone",
    )
    changed.append("tumor_induced_hypoglycemia")

    osteomalacia = batch_b["tumor_induced_osteomalacia"]
    remove_list_item(
        osteomalacia["treatment"]["indicated_for"],
        3,
        "Functional imaging",
        "TIO diagnostic imaging in treatment axis",
    )
    remove_list_item(
        osteomalacia["treatment"]["contraindicated_for"],
        0,
        "Native vitamin D",
        "TIO native vitamin D non-contraindication",
    )
    osteomalacia["treatment"]["principles"] += (
        " Native vitamin D may correct coexisting deficiency but is not adequate as sole therapy for FGF23-mediated "
        "phosphate wasting; use active vitamin D with phosphate or burosumab according to specialist guidance."
    )
    changed.append("tumor_induced_osteomalacia")

    hemorrhagic = batch_b["hemorrhagic_cystitis"]
    replace_list_item(
        hemorrhagic["treatment"]["indicated_for"],
        2,
        "alum or formalin",
        "Intravesical alum irrigation after complete clot clearance; use particular caution in renal impairment.",
        "hemorrhagic cystitis alum",
    )
    hemorrhagic["treatment"]["indicated_for"].insert(
        3,
        "Reserve low-concentration formalin for life-threatening bleeding refractory to less invasive measures, "
        "under anesthesia and only after cystography excludes perforation or vesicoureteral reflux.",
    )
    changed.append("hemorrhagic_cystitis")

    thrombophlebitis = batch_b["paraneoplastic_thrombophlebitis"]
    thrombophlebitis["treatment"]["principles"] = (
        "Treat the underlying malignancy and use a direct oral anticoagulant or low-molecular-weight heparin according "
        "to cancer site, gastrointestinal or genitourinary bleeding risk, drug interactions, kidney function, and "
        "patient preference. Vitamin K antagonists are generally less preferred, not universally contraindicated, "
        "when these options cannot be used."
    )
    remove_list_item(
        thrombophlebitis["treatment"]["contraindicated_for"],
        0,
        "Vitamin K antagonists",
        "cancer thrombosis vitamin K antagonist",
    )
    changed.append("paraneoplastic_thrombophlebitis")

    enterocolitis = batch_b["neutropenic_enterocolitis"]
    replace_list_item(
        enterocolitis["treatment"]["indicated_for"],
        3,
        "Granulocyte colony",
        "Do not use granulocyte colony-stimulating factor routinely; consider it selectively for severe febrile "
        "neutropenia with high-risk features such as sepsis, profound or prolonged neutropenia, or other guideline-defined risk.",
        "neutropenic enterocolitis G-CSF",
    )
    replace_list_item(
        enterocolitis["treatment"]["contraindicated_for"],
        2,
        "Opioid",
        "Avoid antidiarrheal or other bowel-motility-suppressing agents when ileus or toxic colitis is present; do "
        "not categorically prohibit carefully titrated analgesia.",
        "neutropenic enterocolitis motility agents",
    )
    changed.append("neutropenic_enterocolitis")

    sclc = batch_b["small_cell_lung_cancer"]
    sclc["treatment"]["principles"] = (
        "Platinum-etoposide chemotherapy is central. Concurrent thoracic radiation is used for limited-stage disease. "
        "Platinum-etoposide plus atezolizumab or durvalumab is an established first-line option for extensive-stage "
        "disease, and durvalumab consolidation is approved for adults with limited-stage disease without progression "
        "after concurrent chemoradiation."
    )
    replace_list_item(
        sclc["treatment"]["indicated_for"],
        2,
        "Prophylactic cranial",
        "Consider prophylactic cranial irradiation after a complete or very good response in patients with suitable "
        "performance and cognitive status after brain MRI; for extensive-stage disease, discuss irradiation versus "
        "scheduled MRI surveillance.",
        "SCLC cranial irradiation",
    )
    changed.append("small_cell_lung_cancer")

    gist = batch_b["gastrointestinal_stromal_tumor"]
    gist["treatment"]["principles"] = (
        "Surgical resection is central for resectable localized disease. Perform mutational testing before neoadjuvant, "
        "adjuvant, or metastatic tyrosine-kinase-inhibitor selection, because drug sensitivity differs by genotype."
    )
    replace_list_item(
        gist["treatment"]["indicated_for"],
        2,
        "Adjuvant imatinib",
        "Adjuvant imatinib only for high-risk resected gastrointestinal stromal tumor with an imatinib-sensitive genotype.",
        "GIST adjuvant imatinib",
    )
    replace_list_item(
        gist["treatment"]["indicated_for"],
        5,
        "Third-line",
        "Regorafenib after imatinib and sunitinib; ripretinib after progression or intolerance to at least three prior "
        "tyrosine kinase inhibitors.",
        "GIST later-line therapy",
    )
    if any("Sporadic somatic" in value for value in gist["risk_factors"]):
        gist["risk_factors"] = [value for value in gist["risk_factors"] if "Sporadic somatic" not in value]
    changed.append("gastrointestinal_stromal_tumor")

    dlbcl = batch_b["diffuse_large_b_cell_lymphoma"]
    replace_list_item(
        dlbcl["treatment"]["indicated_for"],
        1,
        "CNS prophylaxis",
        "Use individualized CNS-relapse assessment; a high CNS-IPI score alone does not make intrathecal or high-dose "
        "methotrexate universally indicated. Reserve prophylaxis for selected high-risk anatomic or biologic settings "
        "after hematology review.",
        "DLBCL CNS prophylaxis",
    )
    replace_list_item(
        dlbcl["treatment"]["indicated_for"],
        3,
        "CAR-T",
        "Use axicabtagene ciloleucel or lisocabtagene maraleucel as second-line therapy for eligible primary-refractory "
        "disease or relapse within twelve months; use later-line CD19 CAR-T products according to product indication "
        "and prior therapy.",
        "DLBCL CAR-T timing",
    )
    replace_list_item(
        dlbcl["treatment"]["indicated_for"],
        4,
        "EPOCH",
        "Consider dose-adjusted EPOCH-R only after specialist review for a precisely molecularly classified high-grade "
        "B-cell lymphoma; do not present it as proven superior for every MYC/BCL2- or BCL6-altered case.",
        "DLBCL EPOCH-R",
    )
    changed.append("diffuse_large_b_cell_lymphoma")

    lymphoblastic = batch_b["lymphoblastic_lymphoma"]
    lymphoblastic["risk_factors"] = [
        "A defined inherited predisposition syndrome with evidence for lymphoblastic neoplasia; risk is subtype-specific "
        "and requires hematology or genetics review."
    ]
    replace_list_item(
        lymphoblastic["treatment"]["indicated_for"],
        1,
        "Intrathecal",
        "Use protocol-defined intrathecal and CNS-penetrant systemic therapy for prophylaxis; reserve cranial radiation "
        "for overt CNS disease or exceptional protocol-defined high-risk settings.",
        "lymphoblastic lymphoma CNS therapy",
    )
    changed.append("lymphoblastic_lymphoma")

    rms = batch_b["rhabdomyosarcoma"]
    rms["risk_factors"] = [rms["risk_factors"][0]]
    rms["uncertainty_notes"].append(
        "Age belongs in epidemiology, while PAX-FOXO1 fusion and primary anatomic site belong in classification or "
        "prognosis rather than antecedent risk factors."
    )
    changed.append("rhabdomyosarcoma")

    osteosarcoma = batch_b["osteosarcoma"]
    replace_list_item(
        osteosarcoma["treatment"]["indicated_for"],
        2,
        "Adjuvant chemotherapy",
        "Continue protocol-defined postoperative chemotherapy; use histologic necrosis primarily for prognosis and "
        "do not imply routine regimen intensification solely because of poor necrosis.",
        "osteosarcoma postoperative chemotherapy",
    )
    remove_list_item(
        osteosarcoma["treatment"]["contraindicated_for"],
        0,
        "Primary radiation",
        "osteosarcoma radiotherapy",
    )
    osteosarcoma["uncertainty_notes"].append(
        "Surgery is preferred when feasible; consider definitive or postoperative radiotherapy for unresectable axial "
        "disease, unacceptable surgical morbidity, or inadequate margins."
    )
    changed.append("osteosarcoma")

    ewing = batch_b["ewing_sarcoma"]
    replace_list_item(
        ewing["treatment"]["indicated_for"],
        3,
        "High-dose chemotherapy",
        "Do not list high-dose chemotherapy with stem-cell rescue as routine treatment for high-risk or relapsed "
        "disease; restrict it to selected protocol-defined populations or clinical trials.",
        "Ewing high-dose chemotherapy",
    )
    replace_list_item(
        ewing["treatment"]["indicated_for"],
        4,
        "Pulmonary irradiation",
        "Consider whole-lung irradiation for selected pulmonary metastatic disease according to protocol, response, "
        "prior radiation, age, and competing toxicity; do not imply automatic use in every patient.",
        "Ewing whole-lung irradiation",
    )
    changed.append("ewing_sarcoma")

    retinoblastoma = batch_b["retinoblastoma"]
    remove_list_item(
        retinoblastoma["risk_factors"],
        2,
        "somatic RB1",
        "retinoblastoma somatic mechanism",
    )
    retinoblastoma["uncertainty_notes"].append(
        "Biallelic somatic RB1 inactivation is a tumor mechanism in sporadic unilateral disease, not an antecedent risk factor."
    )
    changed.append("retinoblastoma")

    for cid in (
        "neoplastic_meningitis",
        "mesothelioma",
        "anaplastic_large_cell_lymphoma",
        "glioma",
    ):
        if cid not in batch_b:
            continue
        del batch_b[cid]
        documents["b"].get("harrison_refs", {}).pop(cid, None)
        progress = documents["b"].get("_progress") or {}
        progress["selected_ids"] = [value for value in progress.get("selected_ids", []) if value != cid]
        progress["completed_ids"] = [value for value in progress.get("completed_ids", []) if value != cid]
        documents["b"].get("_meta", {})["batch_size"] = len(progress.get("selected_ids", []))
        changed.append(f"{cid}_quarantined")

    batch_c = documents["c"]["axes"]
    delirium = batch_c["delirium_tremens"]
    delirium["treatment"]["principles"] = (
        "Benzodiazepines are the pharmacologic mainstay. Give parenteral thiamine promptly to patients at risk of "
        "deficiency, but do not delay urgently needed glucose; thiamine and glucose may be administered in either "
        "order or concurrently."
    )
    replace_list_item(
        delirium["treatment"]["indicated_for"],
        1,
        "thiamine prior",
        "Prompt parenteral thiamine for patients at risk of deficiency; administer glucose immediately when indicated "
        "without waiting for thiamine.",
        "delirium thiamine sequence",
    )
    delirium["prognosis"]["staging_or_grading"] = (
        "CIWA-Ar may help grade uncomplicated alcohol withdrawal before delirium develops, but it should not be used "
        "to monitor alcohol-withdrawal delirium because it relies on patient-reported symptoms; use an objective "
        "delirium or agitation scale and close clinical monitoring."
    )
    replace_list_item(
        delirium["treatment"]["indicated_for"],
        4,
        "Antipyretics",
        "External cooling and treatment of severe agitation or other contributors to hyperthermia; antipyretics do "
        "not correct withdrawal-related hyperthermia.",
        "delirium hyperthermia",
    )
    changed.append("delirium_tremens")

    rubella = batch_c["rubella"]
    rubella["pathophysiology"]["summary"] = (
        "Rubella is caused by rubella virus, an enveloped positive-sense single-stranded RNA virus in the family "
        "Matonaviridae and genus Rubivirus. Respiratory infection followed by viremia produces the postnatal illness; "
        "transplacental infection can disrupt fetal organ development and cause congenital rubella syndrome."
    )
    replace_list_item(
        rubella["treatment"]["contraindicated_for"],
        1,
        "relative contraindication",
        "MMR vaccination in patients with severe immunocompromise; determine vaccine eligibility using current "
        "immunization guidance.",
        "rubella immunocompromise",
    )
    changed.append("rubella")

    dlb = batch_c["dementia_with_lewy_bodies"]
    replace_list_item(
        dlb["treatment"]["indicated_for"],
        2,
        "Clonazepam or melatonin",
        "Melatonin for REM sleep behavior disorder; consider clonazepam only after assessing fall, cognitive, "
        "respiratory, and sedation risk.",
        "DLB REM sleep behavior disorder",
    )
    changed.append("dementia_with_lewy_bodies")

    molar = batch_c["molar_pregnancy"]
    replace_list_item(
        molar["treatment"]["indicated_for"],
        0,
        "for all",
        "Suction evacuation as the preferred uterine evacuation method when fertility preservation is desired; "
        "hysterectomy is an alternative for selected patients who have completed childbearing.",
        "molar pregnancy evacuation",
    )
    remove_list_item(
        molar["treatment"]["contraindicated_for"],
        1,
        "Empiric chemotherapy",
        "molar prophylactic chemotherapy",
    )
    molar["uncertainty_notes"].append(
        "Routine prophylactic chemotherapy is not recommended; exceptional use may be considered under specialist "
        "protocols when reliable hCG follow-up is not feasible."
    )
    changed.append("molar_pregnancy")

    torsion = batch_c["ovarian_torsion"]
    torsion["treatment"]["principles"] = (
        "Urgent laparoscopy with detorsion and ovarian preservation is preferred. Grossly blue, black, or edematous "
        "appearance does not reliably indicate nonviability; oophorectomy should be reserved for an ovary that "
        "cannot be preserved because the tissue disintegrates or malignancy is strongly suspected."
    )
    replace_list_item(
        torsion["treatment"]["indicated_for"],
        3,
        "Oophorectomy",
        "Oophorectomy only when ovarian preservation is technically impossible or malignancy is strongly suspected; "
        "ischemic appearance alone is not an indication.",
        "ovarian torsion oophorectomy",
    )
    torsion["prognosis"]["staging_or_grading"] = (
        "No formal staging system exists; intraoperative color or immediate reperfusion does not reliably determine "
        "ovarian viability, so preservation after detorsion is favored."
    )
    changed.append("ovarian_torsion")

    urticaria = batch_c["urticaria"]
    replace_list_item(
        urticaria["risk_factors"],
        1,
        "culprit drugs",
        "Exposure to medications that can provoke urticaria, including NSAIDs and selected antibiotics; "
        "ACE-inhibitor-associated bradykinin angioedema is a distinct condition.",
        "urticaria medication exposure",
    )
    replace_list_item(
        urticaria["treatment"]["contraindicated_for"],
        1,
        "ACE inhibitors",
        "Re-exposure to a medication with a convincing history of drug-induced urticaria, pending allergy evaluation "
        "when appropriate.",
        "urticaria drug re-exposure",
    )
    changed.append("urticaria")

    obstruction = batch_c["bowel_obstruction"]
    obstruction["pathophysiology"]["summary"] = (
        "Mechanical bowel obstruction is interruption of intestinal transit by a physical blockage, causing proximal "
        "distension and possible ischemia or perforation. Adynamic ileus is a distinct functional disorder and should "
        "be modeled separately."
    )
    remove_list_item(
        obstruction["risk_factors"],
        5,
        "adynamic ileus",
        "bowel obstruction ileus risk factor",
    )
    replace_list_item(
        obstruction["treatment"]["indicated_for"],
        2,
        "Urgent surgical",
        "Urgent surgery for peritonitis, suspected strangulation or ischemia, perforation, closed-loop obstruction, "
        "or clinical deterioration; complete obstruction alone requires etiologic and surgical assessment rather "
        "than an automatic operation.",
        "bowel obstruction surgery",
    )
    changed.append("bowel_obstruction")

    broca = batch_c["broca_aphasia"]
    replace_list_item(
        broca["treatment"]["indicated_for"],
        4,
        "Pharmacological adjuncts",
        "No pharmacologic agent is established for routine aphasia rehabilitation; medication adjuncts should be "
        "limited to specialist-directed research or separate comorbid indications.",
        "Broca aphasia pharmacology",
    )
    changed.append("broca_aphasia")

    liver_abscess = batch_c["liver_abscess"]
    liver_abscess["treatment"]["principles"] = (
        "Treatment is etiology-specific: pyogenic abscess usually requires antibiotics plus source control or drainage "
        "when indicated; amebic abscess usually receives a tissue amebicide followed by a luminal agent, with drainage "
        "reserved for selected complications, nonresponse, or diagnostic uncertainty."
    )
    replace_list_item(
        liver_abscess["treatment"]["indicated_for"],
        3,
        "Antiparasitic therapy",
        "Metronidazole or tinidazole for confirmed or strongly suspected amebic abscess, followed by a luminal "
        "amebicide such as paromomycin to eradicate intestinal carriage.",
        "liver abscess amebic therapy",
    )
    changed.append("liver_abscess")

    fibrocystic = batch_c["fibrocystic_change"]
    fibrocystic["prognosis"]["staging_or_grading"] = (
        "Fibrocystic breast change is a benign nonproliferative clinical and pathologic pattern with no staging system; "
        "proliferative lesions and atypical ductal or lobular hyperplasia should be represented as separate diagnoses "
        "with distinct cancer risk."
    )
    replace_list_item(
        fibrocystic["treatment"]["indicated_for"],
        2,
        "Enhanced breast surveillance",
        "Routine age- and risk-appropriate breast screening; enhanced surveillance only when a separate high-risk "
        "lesion is confirmed.",
        "fibrocystic surveillance",
    )
    remove_list_item(
        fibrocystic["treatment"]["indicated_for"],
        4,
        "Hormonal risk-reduction",
        "fibrocystic hormonal risk reduction",
    )
    changed.append("fibrocystic_change")

    vitamin_k = batch_c["vitamin_k_deficiency"]
    replace_list_item(
        vitamin_k["risk_factors"],
        3,
        "Warfarin",
        "Vitamin K antagonist exposure causes pharmacologic antagonism and should be represented separately from "
        "nutritional or malabsorptive vitamin K deficiency.",
        "vitamin K antagonist scope",
    )
    vitamin_k["treatment"]["principles"] = (
        "Replete vitamin K by an appropriate route and treat the cause. For life-threatening bleeding or urgent "
        "vitamin K antagonist reversal, provide rapid factor replacement, preferably four-factor prothrombin complex "
        "concentrate when indicated and available, with intravenous vitamin K; use plasma when concentrate is "
        "unavailable or unsuitable."
    )
    replace_list_item(
        vitamin_k["treatment"]["indicated_for"],
        1,
        "Parenteral",
        "Slow intravenous vitamin K for significant bleeding or urgent reversal when a rapid and reliable effect is "
        "required; do not present subcutaneous administration as equivalent because absorption is less predictable.",
        "vitamin K parenteral route",
    )
    changed.append("vitamin_k_deficiency")

    aspiration = batch_c["aspiration_pneumonia"]
    aspiration["pathophysiology"]["summary"] = (
        "Aspiration pneumonia is a bacterial lower respiratory infection after aspiration of colonized oropharyngeal "
        "material; chemical pneumonitis after aspiration of sterile gastric contents is a distinct syndrome and may "
        "not require antibiotics."
    )
    aspiration["treatment"]["principles"] = (
        "Address aspiration risk and select a standard community- or hospital-acquired pneumonia regimen according "
        "to care setting and resistance risk; do not routinely add anaerobic coverage unless lung abscess, empyema, "
        "or another strong anaerobic indication is suspected."
    )
    replace_list_item(
        aspiration["treatment"]["indicated_for"],
        0,
        "anaerobic coverage",
        "Standard pneumonia antimicrobial therapy selected by acquisition setting and resistance risk; add specific "
        "anaerobic coverage only when lung abscess, empyema, or necrotizing infection is suspected.",
        "aspiration pneumonia antibiotics",
    )
    changed.append("aspiration_pneumonia")

    hydronephrosis = batch_c["hydronephrosis"]
    hydronephrosis["pathophysiology"]["summary"] = (
        "Hydronephrosis is dilation of the renal collecting system and does not by itself prove active obstruction; "
        "physiologic pregnancy-related dilation, reflux, prior obstruction, and imaging mimics must be distinguished."
    )
    hydronephrosis["treatment"]["principles"] = (
        "Confirm clinically significant obstruction and assess infection and renal function. Decompress urgently for "
        "infected obstruction, threatened renal function, bilateral or solitary-kidney obstruction, or uncontrolled "
        "symptoms; observe selected nonobstructive or physiologic cases."
    )
    remove_list_item(
        hydronephrosis["risk_factors"],
        5,
        "Pregnancy",
        "hydronephrosis pregnancy physiology",
    )
    hydronephrosis["uncertainty_notes"].append(
        "Pregnancy commonly causes physiologic collecting-system dilation and should not automatically be interpreted "
        "as pathologic obstruction."
    )
    changed.append("hydronephrosis")

    gh_deficiency = batch_c["growth_hormone_deficiency"]
    gh_deficiency["pathophysiology"]["summary"] = (
        "Growth hormone deficiency is inadequate growth-hormone secretion caused by hypothalamic-pituitary "
        "dysfunction; growth-hormone resistance or insensitivity is a separate disorder."
    )
    remove_list_item(
        gh_deficiency["treatment"]["indicated_for"],
        2,
        "underlying cause",
        "growth hormone deficiency tumor therapy",
    )
    gh_deficiency["uncertainty_notes"].append(
        "Treat pituitary or hypothalamic tumors according to independent oncologic or neurosurgical indications; "
        "surgery or radiotherapy is not a treatment for growth hormone deficiency and may further impair pituitary function."
    )
    changed.append("growth_hormone_deficiency")

    strep = batch_c["streptococcal_pharyngitis"]
    strep["prognosis"]["staging_or_grading"] = (
        "No formal staging system exists; Centor or McIsaac criteria estimate the likelihood of group A streptococcal "
        "infection and may guide testing, but they do not grade severity or replace microbiologic confirmation."
    )
    replace_list_item(
        strep["treatment"]["indicated_for"],
        2,
        "Macrolide antibiotics",
        "For penicillin allergy, select a guideline-supported alternative according to immediate versus non-immediate "
        "allergy history and local resistance; reserve macrolides for appropriate allergy scenarios because resistance varies.",
        "streptococcal pharyngitis allergy therapy",
    )
    changed.append("streptococcal_pharyngitis")

    influenza = batch_c["influenza"]
    replace_list_item(
        influenza["treatment"]["indicated_for"],
        0,
        "Neuraminidase inhibitors",
        "Start oseltamivir promptly for suspected or confirmed influenza in hospitalized, severe or progressive, "
        "pregnant or postpartum, and other high-risk patients without waiting for test results and regardless of "
        "symptom duration; early treatment provides the greatest benefit.",
        "influenza antiviral timing",
    )
    changed.append("influenza")

    hdn = batch_c["hemolytic_disease_of_newborn"]
    replace_list_item(
        hdn["pathophysiology"]["key_steps"],
        0,
        "Fetomaternal hemorrhage",
        "RhD and other non-ABO alloantibodies generally follow maternal sensitization to foreign red-cell antigens; "
        "ABO hemolytic disease can occur in a first pregnancy from pre-existing maternal IgG anti-A or anti-B.",
        "HDN sensitization",
    )
    hdn["prognosis"]["staging_or_grading"] = (
        "Risk of fetal anemia is assessed using maternal antibody specificity and level, fetal antigen status, and "
        "serial middle cerebral artery peak systolic velocity; amniotic-fluid Liley or Queenan charts are not routine "
        "contemporary monitoring."
    )
    replace_list_item(
        hdn["treatment"]["indicated_for"],
        0,
        "Rh immunoglobulin",
        "Rh immunoglobulin prophylaxis for an unsensitized RhD-negative pregnant patient when fetal or neonatal RhD "
        "exposure is possible; it is not useful after immune anti-D has developed.",
        "HDN Rh immunoglobulin",
    )
    replace_list_item(
        hdn["treatment"]["indicated_for"],
        4,
        "Exchange transfusion",
        "Urgent exchange transfusion when bilirubin reaches the gestational-age and neurotoxicity-risk-adjusted "
        "exchange threshold or signs of acute bilirubin encephalopathy are present; treat clinically significant "
        "anemia with appropriately matched red-cell transfusion rather than phototherapy.",
        "HDN exchange transfusion",
    )
    replace_list_item(
        hdn["treatment"]["indicated_for"],
        5,
        "Intravenous immunoglobulin",
        "Consider intravenous immunoglobulin only for direct-antiglobulin-test-positive isoimmune hemolytic disease "
        "when bilirubin has reached the escalation-of-care threshold and continues to rise despite intensive "
        "phototherapy, particularly when timely exchange transfusion may be difficult; benefit is uncertain and "
        "potential harm must be weighed.",
        "HDN IVIG",
    )
    changed.append("hemolytic_disease_of_newborn")

    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    original = {key: load(path) for key, path in FILES.items()}
    if all(
        isinstance((document.get("_meta") or {}).get("manual_safety_review"), dict)
        for document in original.values()
    ):
        print(
            json.dumps(
                {
                    "mode": "already_applied",
                    "files": len(original),
                    "medical_approval": False,
                },
                ensure_ascii=False,
            )
        )
        return
    updated = deepcopy(original)
    changed = apply_fixes(updated)
    if args.apply:
        for key, path in FILES.items():
            meta = updated[key].setdefault("_meta", {})
            meta["manual_safety_review"] = {
                "status": "reviewed_corrections_applied_not_medically_approved",
                "review_date": "2026-07-12",
                "needs_review": True,
            }
            path.write_text(json.dumps(updated[key], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "check",
                "records_corrected": len(changed),
                "ids": sorted(changed),
                "medical_approval": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
