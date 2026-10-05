#!/usr/bin/env python3
"""Audit and repair known-bad Harrison mappings using the local 22e TOC.

The original lexical matcher can assign high confidence to a single shared word
(for example, "tumor" or "prolapse").  This script applies a small, reviewable
curation table, refuses to invent pages, synchronizes the clinical-axis
worklist, and writes an audit report under data_private/.

No question text is read and no network service is used.
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
TOC_PATH = DP / "curriculum" / "harrison_toc_index.json"
SEED_PATH = DP / "harrison" / "concept_to_harrison.json"
EXPANSION_PATH = DP / "curriculum" / "expansion_harrison_map.json"
WORKLIST_PATH = DP / "curriculum" / "clinical_axes_worklist.json"
AXES_PATH = DP / "curriculum" / "clinical_axes_map.json"
REPORT_PATH = DP / "curriculum" / "harrison_mapping_audit_20260711.json"

ACCESSMED = "https://accessmedicine.mhmedical.com"
BOOKID = "3541"  # 22e. 2026-09-27 확인: 3095는 21e이며 sectionid 체계가 전혀 다르다(로컬 pages.jsonl은 22e).

# Direct chapter assignments are limited to cases for which the local TOC has a
# clearly relevant home.  Values are (chapter, confidence, reason).
SEED_CORRECTIONS = {
    "acute_coronary_syndrome": (
        284, "high", "Broad acute coronary syndrome needs the ischemic-heart-disease chapter rather than a STEMI-only chapter."
    ),
    "acute_myocardial_infarction": (
        284, "high", "Broad acute myocardial infarction spans STEMI and NSTEMI; use the parent ischemic-heart-disease chapter."
    ),
    "allergic_conjunctivitis": (
        34, "medium", "Ocular allergic disease belongs with disorders of the eye rather than a rhinitis-focused allergy chapter."
    ),
    "antidepressant_induced_mania": (
        463, "medium", "Medication-associated mania is a psychiatric syndrome; prior toxic-hepatitis match was unrelated."
    ),
    "carbon_monoxide_poisoning": (
        470, "high", "Carbon monoxide poisoning belongs with poisoning and drug overdose, not heavy-metal poisoning."
    ),
    "dry_gangrene": (
        292, "high", "Ischemic dry gangrene belongs with arterial disease of the extremities, not clostridial gas gangrene."
    ),
    "endobronchial_tumor": (
        83, "medium", "Endobronchial neoplasia belongs with lung neoplasms; prior pituitary-tumor match was unrelated."
    ),
    "exertional_heat_stroke": (
        478, "high", "Dedicated heat-related-illness chapter; prior ischemic-stroke match was a token collision."
    ),
    "familial_hypercholesterolemia": (
        419, "high", "Inherited hypercholesterolemia belongs with lipoprotein-metabolism disorders."
    ),
    "idiopathic_pulmonary_fibrosis": (
        304, "high", "Idiopathic pulmonary fibrosis belongs with interstitial lung disease, not cystic fibrosis."
    ),
    "ischemic_colitis": (
        340, "high", "Ischemic colitis belongs with mesenteric vascular insufficiency, not infectious colitis."
    ),
    "learning_disorder": (
        463, "medium", "Neurodevelopmental learning disorder belongs with psychiatric disorders; prior machine-learning match was unrelated."
    ),
    "malignant_pleural_effusion": (
        305, "high", "Pleural malignant effusion belongs with disorders of the pleura."
    ),
    "metabolic_bone_disease_of_prematurity": (
        421, "medium", "Metabolic bone disease belongs with bone and mineral metabolism, not metabolic syndrome."
    ),
    "post_term_pregnancy": (
        491, "medium", "Post-term pregnancy belongs with pregnancy disorders; prior cancer-survivorship match was unrelated."
    ),
    "prolonged_grief_disorder": (
        463, "medium", "Prolonged grief is a psychiatric disorder; prior assisted-circulation match was a token collision."
    ),
    "stable_angina": (
        284, "high", "Stable angina belongs with ischemic heart disease rather than the NSTEMI/unstable-angina chapter."
    ),
    "vasospastic_angina": (
        284, "medium", "Vasospastic angina belongs with ischemic heart disease rather than the NSTEMI/unstable-angina chapter."
    ),
    "virilizing_ovarian_tumor": (
        94, "medium", "Ovarian virilizing tumor belongs with gynecologic malignancies; prior pituitary-tumor match was unrelated."
    ),
    "polycystic_ovary_syndrome": (
        405, "medium", "Reproductive/menstrual disorder; prior match was polycystic kidney disease."
    ),
    "vasomotor_symptoms": (
        407, "high", "Menopausal vasomotor symptoms; prior match was upper respiratory symptoms."
    ),
}

# A null assignment is safer than claiming Harrison coverage that is not in the
# local TOC.  The concept remains in the registry and remains needs_review=true.
SEED_UNMAP = {
    "apnea_of_prematurity": "Sleep apnea is not apnea of prematurity; the local Harrison TOC has no neonatal-apnea chapter.",
    "chest_trauma": "Chest Discomfort is a symptom chapter, not a thoracic-trauma source; no general chest-trauma chapter exists in the local TOC.",
    "electrical_injury": "No corresponding electrical/lightning injury chapter in the local Harrison 22e TOC; prior match was an arrhythmia chapter.",
    "febrile_illness_with_bleeding": "The general acute-febrile chapter does not establish a discrete hemorrhagic febrile syndrome.",
    "hepatic_trauma": "Cardiac Trauma is an unrelated organ-specific chapter and the local TOC has no hepatic-trauma chapter.",
    "nsaid_hypersensitivity": "Hypersensitivity pneumonitis is a different disease and does not support NSAID hypersensitivity.",
    "pediatric_respiratory_distress": "The adult ARDS chapter does not support a broad pediatric respiratory-distress concept.",
    "sexual_assault": "No corresponding sexual-assault care chapter in the local Harrison 22e TOC; prior match was Sexual Dysfunction.",
}

EXPANSION_CORRECTIONS = {
    "abusive_head_trauma": (454, "medium", "Traumatic brain injury; prior match was Head and Neck Cancer."),
    "cervical_intraepithelial_neoplasia": (94, "high", "Cervical premalignancy belongs with gynecologic malignancies."),
    "chronic_myeloid_leukemia": (110, "high", "Dedicated Chronic Myeloid Leukemia chapter."),
    "delirium_tremens": (464, "high", "Alcohol-withdrawal syndrome; prior match was a symptom chapter."),
    "erb_palsy": (457, "medium", "Brachial plexus injury belongs with peripheral neuropathy, not cranial nerve palsy."),
    "familial_adenomatous_polyposis": (86, "high", "Hereditary colorectal neoplasia; prior match was familial Mediterranean fever."),
    "febrile_seizure": (436, "medium", "Seizure disorder; prior match was the acutely ill febrile patient chapter."),
    "fetal_growth_restriction": (491, "medium", "Pregnancy disorder; prior match was polycystic kidney disease."),
    "gastrointestinal_stromal_tumor": (85, "medium", "Gastrointestinal neoplasm; prior match was pituitary tumor syndromes."),
    "granulosa_cell_tumor": (94, "high", "Ovarian sex-cord stromal tumor."),
    "growth_hormone_deficiency": (391, "high", "Pituitary hormone deficiency belongs with hypopituitarism."),
    "hereditary_spherocytosis": (105, "high", "Inherited hemolytic anemia; prior match was familial Mediterranean fever."),
    "hodgkin_lymphoma": (114, "high", "Dedicated Hodgkin lymphoma chapter; prior match was non-Hodgkin lymphoma."),
    "internal_hernia": (341, "medium", "Mechanical intestinal obstruction; prior match was skin manifestations of internal disease."),
    "klumpke_palsy": (457, "medium", "Brachial plexus injury belongs with peripheral neuropathy, not cranial nerve palsy."),
    "mature_cystic_teratoma": (94, "high", "Ovarian germ-cell tumor; prior match was cystic fibrosis."),
    "molar_pregnancy": (94, "high", "Gestational trophoblastic neoplasia."),
    "ovulatory_dysfunction": (405, "high", "Menstrual/ovulatory disorder; prior match was sexual dysfunction."),
    "paroxysmal_nocturnal_hemoglobinuria": (105, "high", "Hemolytic anemia; prior match was paroxysmal supraventricular tachycardia."),
    "pelvic_organ_prolapse": (404, "medium", "Female reproductive disorder; prior match was mitral valve prolapse."),
    "phrenic_nerve_injury": (457, "medium", "Peripheral nerve injury; prior match was a cranial nerve chapter."),
    "radiation_pneumonitis": (304, "high", "Radiation pneumonitis belongs with interstitial lung disease rather than hypersensitivity pneumonitis."),
    "post_traumatic_stress_disorder": (463, "high", "Psychiatric disorder; prior match was traumatic brain injury."),
    "posterior_fossa_tumor": (95, "high", "Central nervous system tumor; prior match was pituitary tumor syndromes."),
    "premature_ovarian_insufficiency": (404, "high", "Female reproductive endocrine disorder; prior match was ventricular ectopy."),
    "premature_thelarche": (404, "medium", "Female reproductive/puberty disorder; prior match was ventricular ectopy."),
    "somatic_symptom_disorder": (463, "high", "Psychiatric disorder; prior match was cancer symptom control."),
    "thrombotic_thrombocytopenic_purpura": (120, "high", "Platelet/vessel-wall thrombotic microangiopathy."),
    "twin_to_twin_transfusion_syndrome": (491, "medium", "Pregnancy-specific disorder; prior match was transfusion therapy."),
    "tumor_induced_hypoglycemia": (98, "high", "Endocrinologic paraneoplastic syndrome; prior match was toxic hepatitis."),
    "tumor_induced_osteomalacia": (98, "high", "Endocrinologic paraneoplastic syndrome; prior match was toxic hepatitis."),
    "tumor_lysis_syndrome": (80, "high", "Oncologic emergency; prior match was pituitary tumor syndromes."),
    "urinary_tract_infection": (140, "high", "Dedicated urinary tract infection chapter; prior match was urinary tract cancer."),
    "uterine_prolapse": (404, "medium", "Female reproductive disorder; prior match was mitral valve prolapse."),
    "yolk_sac_tumor": (94, "high", "Registry specialty is gynecologic oncology; prior match was pituitary tumor syndromes."),
}

EXPANSION_UNMAP = {
    "anorectal_malformation": "No congenital anorectal-malformation chapter in the local Harrison 22e TOC; prior match was an adult anorectal-disorders chapter.",
    "biliary_atresia": "No biliary-atresia chapter in the local Harrison 22e TOC; prior match was liver/biliary cancer.",
    "food_protein_induced_enterocolitis_syndrome": "No FPIES chapter in the local Harrison 22e TOC; prior match was infectious diarrhea/food poisoning.",
    "gastroenteritis": "Generic gastroenteritis is broader than the viral-only chapter and should be split by etiology before remapping.",
    "germ_cell_tumor": "Generic concept is not site-specific enough to select Testicular Cancer versus Gynecologic Malignancies.",
    "legg_calve_perthes_disease": "Systemic-disease-associated arthritis is not Legg-Calve-Perthes disease; no disease-specific chapter exists in the local TOC.",
    "leukemia": "Generic leukemia spans multiple dedicated acute/chronic and myeloid/lymphoid chapters and must be split before mapping.",
    "lipoma": "A sarcoma and bone-metastasis chapter is not a defensible primary source for benign lipoma.",
    "motor_developmental_delay": "No pediatric developmental-delay chapter in the local Harrison 22e TOC; prior match was motor neuron disease.",
    "neuroblastoma": "No neuroblastoma chapter in the local Harrison 22e TOC; prior match was pheochromocytoma based only on lineage similarity.",
    "wilms_tumor": "No Wilms tumor chapter in the local Harrison 22e TOC; prior match was pituitary tumor syndromes.",
}

MAPPING_NOTE_IDS = {
    "abusive_head_trauma", "cervical_intraepithelial_neoplasia",
    "chronic_myeloid_leukemia", "electrical_injury", "erb_palsy",
    "familial_adenomatous_polyposis", "internal_hernia",
    "fetal_growth_restriction",
    "mature_cystic_teratoma", "motor_developmental_delay", "neuroblastoma",
    "paroxysmal_nocturnal_hemoglobinuria", "pelvic_organ_prolapse",
    "polycystic_ovary_syndrome", "post_traumatic_stress_disorder",
    "posterior_fossa_tumor", "sexual_assault", "tumor_lysis_syndrome",
    "vasomotor_symptoms", "wilms_tumor",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def accessmed_url(title: str) -> str:
    return f"{ACCESSMED}/SearchResults.aspx?q={urllib.parse.quote(title)}&searchType=1&book={BOOKID}"


def chapter_ref(toc: dict[int, dict], chapter: int, confidence: str, reason: str, *, seed: bool) -> dict:
    ch = toc[chapter]
    ref = {
        "chapter": ch["ch"],
        "title": ch["title"],
        "page": ch["page"],
        "part": ch["part"],
        "match_score": None,
        "confidence": confidence,
        "accessmedicine": accessmed_url(ch["title"]),
        "status": "audited_curated_20260711",
        "audit_reason": reason,
    }
    if seed:
        ref["needs_review"] = True
    return ref


def unmapped_ref(reason: str, *, seed: bool):
    if not seed:
        return None
    return {
        "chapter": None,
        "title": None,
        "page": None,
        "part": None,
        "match_score": None,
        "confidence": "none",
        "accessmedicine": None,
        "status": "audited_unmapped_20260711",
        "audit_reason": reason,
        "needs_review": True,
    }


def is_mapping_note(note: object) -> bool:
    text = str(note).lower()
    source = any(word in text for word in ("worklist", "harrison", "chapter", "citation", "reference"))
    problem = any(word in text for word in ("mis-map", "mismatch", "mislabeled", "incorrect", "does not match", "does not correspond"))
    return source and problem


def build_changes(before: dict, after: dict, ids: set[str], source: str) -> list[dict]:
    changes = []
    for cid in sorted(ids):
        if before.get(cid) != after.get(cid):
            changes.append({"id": cid, "source": source, "before": before.get(cid), "after": after.get(cid)})
    return changes


def validate_map_refs(mapping: dict, toc: dict[int, dict], label: str) -> list[str]:
    errors = []
    for cid, ref in mapping.items():
        if not ref or ref.get("chapter") is None:
            continue
        chapter = ref.get("chapter")
        ch = toc.get(chapter)
        if not ch:
            errors.append(f"{label}:{cid}: chapter {chapter!r} absent from local TOC")
            continue
        for key, toc_key in (("title", "title"), ("page", "page"), ("part", "part")):
            if ref.get(key) != ch.get(toc_key):
                errors.append(f"{label}:{cid}: {key}={ref.get(key)!r}, TOC={ch.get(toc_key)!r}")
    return errors


def run(apply: bool) -> dict:
    toc_data = load_json(TOC_PATH)
    toc = {row["ch"]: row for row in toc_data["chapters"]}
    if len(toc) != toc_data.get("total"):
        raise SystemExit("TOC total does not match unique chapter count")

    seed_data = load_json(SEED_PATH)
    expansion_data = load_json(EXPANSION_PATH)
    axes_data = load_json(AXES_PATH)
    worklist_data = load_json(WORKLIST_PATH)

    seed_before = deepcopy(seed_data["concept_to_harrison"])
    expansion_before = deepcopy(expansion_data["map"])
    seed_map = seed_data["concept_to_harrison"]
    expansion_map = expansion_data["map"]

    for cid, (chapter, confidence, reason) in SEED_CORRECTIONS.items():
        if cid not in seed_map:
            raise SystemExit(f"seed correction target missing: {cid}")
        seed_map[cid] = chapter_ref(toc, chapter, confidence, reason, seed=True)
    for cid, reason in SEED_UNMAP.items():
        if cid not in seed_map:
            raise SystemExit(f"seed unmap target missing: {cid}")
        seed_map[cid] = unmapped_ref(reason, seed=True)

    for cid, (chapter, confidence, reason) in EXPANSION_CORRECTIONS.items():
        if cid not in expansion_map:
            raise SystemExit(f"expansion correction target missing: {cid}")
        expansion_map[cid] = chapter_ref(toc, chapter, confidence, reason, seed=False)
    for cid, reason in EXPANSION_UNMAP.items():
        if cid not in expansion_map:
            raise SystemExit(f"expansion unmap target missing: {cid}")
        expansion_map[cid] = unmapped_ref(reason, seed=False)

    # Keep the downstream worklist aligned with the repaired sources.
    targeted = set(SEED_CORRECTIONS) | set(SEED_UNMAP) | set(EXPANSION_CORRECTIONS) | set(EXPANSION_UNMAP)
    synchronized = []
    for item in worklist_data.get("items", []):
        cid = item.get("id")
        if cid not in targeted:
            continue
        ref = seed_map.get(cid) if cid in seed_map else expansion_map.get(cid)
        item["harrison"] = None if not ref or ref.get("chapter") is None else {
            "chapter": ref["chapter"], "title": ref["title"], "page": ref["page"], "part": ref["part"]
        }
        synchronized.append(cid)

    removed_notes = []
    for cid in sorted(MAPPING_NOTE_IDS):
        axes = axes_data.get("axes", {}).get(cid)
        if not axes:
            continue
        kept = []
        for note in axes.get("uncertainty_notes", []):
            if is_mapping_note(note):
                removed_notes.append({"id": cid, "note": note})
            else:
                kept.append(note)
        axes["uncertainty_notes"] = kept

    errors = []
    errors.extend(validate_map_refs(seed_map, toc, "seed"))
    errors.extend(validate_map_refs(expansion_map, toc, "expansion"))
    if len(expansion_map) != expansion_data.get("total"):
        errors.append("expansion total does not match map size")
    if (set(SEED_CORRECTIONS) | set(SEED_UNMAP)) - set(seed_map):
        errors.append("one or more seed targets are absent")
    if (set(EXPANSION_CORRECTIONS) | set(EXPANSION_UNMAP)) - set(expansion_map):
        errors.append("one or more expansion targets are absent")

    risky_remaining = []
    for source, mapping in (("seed", seed_map), ("expansion", expansion_map)):
        for cid, ref in mapping.items():
            if not ref or ref.get("chapter") is None:
                continue
            score = ref.get("match_score")
            if ref.get("confidence") == "low" or (isinstance(score, (int, float)) and score < 5.0):
                risky_remaining.append({
                    "source": source, "id": cid, "chapter": ref.get("chapter"),
                    "title": ref.get("title"), "confidence": ref.get("confidence"), "match_score": score,
                })

    changes = build_changes(seed_before, seed_map, set(SEED_CORRECTIONS) | set(SEED_UNMAP), "seed")
    changes += build_changes(
        expansion_before, expansion_map,
        set(EXPANSION_CORRECTIONS) | set(EXPANSION_UNMAP), "expansion"
    )
    previous = load_json(REPORT_PATH) if apply and REPORT_PATH.exists() else {}
    previous_changes = previous.get("changes", [])
    merged_changes = {
        (row["source"], row["id"]): row
        for row in previous_changes + changes
    }
    previous_notes = previous.get("stale_mapping_notes_removed", [])
    merged_notes = {
        (row["id"], row["note"]): row
        for row in previous_notes + removed_notes
    }
    report = {
        "generated_by": "scripts/audit_harrison_mappings.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if apply else "check",
        "privacy": "Local TOC and ontology metadata only; no question text read; no network used.",
        "toc_source": str(TOC_PATH.relative_to(ROOT)),
        "toc_chapters": len(toc),
        "changes": sorted(merged_changes.values(), key=lambda x: (x["source"], x["id"])),
        "changed_count": len(merged_changes),
        "run_changed_count": len(changes),
        "worklist_synchronized": sorted(synchronized),
        "stale_mapping_notes_removed": sorted(merged_notes.values(), key=lambda x: (x["id"], x["note"])),
        "remaining_low_or_single_token_mappings": sorted(risky_remaining, key=lambda x: (x["source"], x["id"])),
        "validation_errors": errors,
        "needs_review": True,
    }

    if errors:
        raise SystemExit("\n".join(errors))
    if apply:
        dump_json(SEED_PATH, seed_data)
        dump_json(EXPANSION_PATH, expansion_data)
        dump_json(WORKLIST_PATH, worklist_data)
        dump_json(AXES_PATH, axes_data)
        dump_json(REPORT_PATH, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write corrected maps, worklist, axes notes, and audit report")
    args = parser.parse_args()
    report = run(apply=args.apply)
    print(f"mode={report['mode']} changed={report['changed_count']} remaining_risky={len(report['remaining_low_or_single_token_mappings'])}")
    print(f"validation_errors={len(report['validation_errors'])}")
    if args.apply:
        print(REPORT_PATH.relative_to(ROOT))


if __name__ == "__main__":
    main()
