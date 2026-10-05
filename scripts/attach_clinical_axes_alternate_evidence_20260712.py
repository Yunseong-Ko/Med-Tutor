#!/usr/bin/env python3
"""Attach explicit authority-scoped evidence pointers to legacy non-Harrison axes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data_private" / "curriculum" / "clinical_axes_map.json"
VERIFIED_ON = "2026-07-12"


def ref(ref_id: str, source_type: str, authority: str, title: str, url: str, scope: str) -> dict:
    return {
        "ref_id": ref_id,
        "source_type": source_type,
        "authority": authority,
        "title": title,
        "url": url,
        "verified_on": VERIFIED_ON,
        "scope": scope,
        "entailment_status": "needs_human_review",
    }


SOURCES = {
    "anorectal_malformation": [
        ref(
            "apsa:nat-anorectal-malformations-2026",
            "professional_society_educational_review",
            "American Pediatric Surgical Association",
            "Anorectal Malformations",
            "https://www.pedsurglibrary.com/apsa/view/Pediatric-Surgery-NaT/829049/all/Anorectal_Malformations",
            "definition, anatomy, associated abnormalities, evaluation, and surgical-management overview",
        )
    ],
    "biliary_atresia": [
        ref(
            "niddk:biliary-atresia-treatment",
            "government_patient_guidance",
            "National Institute of Diabetes and Digestive and Kidney Diseases",
            "Treatment for Biliary Atresia",
            "https://www.niddk.nih.gov/health-information/liver-disease/biliary-atresia/treatment",
            "Kasai procedure, cholangitis, progressive liver disease, and transplant overview",
        )
    ],
    "electrical_injury": [
        ref(
            "cdc:electrical-hazards-first-aid-2024",
            "government_clinical_reference",
            "Centers for Disease Control and Prevention",
            "What to Do to Protect Yourself From Electrical Hazards",
            "https://www.cdc.gov/natural-disasters/response/what-to-do-protect-yourself-from-electrical-hazards.html",
            "hazard removal, emergency activation, resuscitation, and initial burn precautions only",
        )
    ],
    "food_protein_induced_enterocolitis_syndrome": [
        ref(
            "aaaai:international-fpies-guideline-2017",
            "professional_society_guideline",
            "American Academy of Allergy, Asthma & Immunology",
            "International consensus guidelines for the diagnosis and management of food protein-induced enterocolitis syndrome",
            "https://education.aaaai.org/sites/default/files/International%20FPIES%20Guidelines.pdf",
            "FPIES definition, diagnosis, acute management, long-term management, and oral food challenge",
        )
    ],
    "motor_developmental_delay": [
        ref(
            "doi:10.1542/peds.2013-1056",
            "professional_society_clinical_report",
            "American Academy of Pediatrics",
            "Motor Delays: Early Identification and Evaluation",
            "https://publications.aap.org/pediatrics/article-abstract/131/6/e2016/31072",
            "developmental surveillance, motor-delay evaluation, diagnostic workup, and early-intervention referral",
        )
    ],
    "neuroblastoma": [
        ref(
            "nci:pdq-neuroblastoma-treatment",
            "government_evidence_review",
            "National Cancer Institute",
            "Neuroblastoma Treatment (PDQ) - Health Professional Version",
            "https://www.cancer.gov/types/neuroblastoma/hp/neuroblastoma-treatment-pdq",
            "biology, INRG staging, risk stratification, prognosis, and treatment",
        )
    ],
    "sexual_assault": [
        ref(
            "cdc:sti-guideline-sexual-assault-2021",
            "government_clinical_guideline",
            "Centers for Disease Control and Prevention",
            "Sexual Assault and Abuse and STIs",
            "https://www.cdc.gov/std/treatment-guidelines/sexual-assault.htm",
            "STI evaluation, prophylaxis, treatment, vaccination, and HIV postexposure assessment only",
        )
    ],
    "wilms_tumor": [
        ref(
            "nci:pdq-wilms-treatment",
            "government_evidence_review",
            "National Cancer Institute",
            "Wilms Tumor and Other Childhood Kidney Tumors Treatment (PDQ) - Health Professional Version",
            "https://www.cancer.gov/types/kidney/hp/wilms-treatment-pdq",
            "biology, staging, prognosis, multidisciplinary care, and treatment",
        )
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    data = json.loads(PATH.read_text(encoding="utf-8"))
    changed: list[str] = []
    conflicts: list[str] = []
    for cid, refs in SOURCES.items():
        axis = data["axes"][cid]
        current = axis.get("evidence_refs")
        if current is None:
            axis["evidence_refs"] = refs
            changed.append(cid)
        elif current != refs:
            conflicts.append(cid)
    if conflicts:
        raise SystemExit("unexpected existing evidence_refs: " + ", ".join(conflicts))
    if args.apply and changed:
        PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": "apply" if args.apply else "check", "changed": changed, "conflicts": conflicts}))


if __name__ == "__main__":
    main()
