#!/usr/bin/env python3
"""Remove over-precise epidemiology statistics from 25 legacy axis drafts.

This batch deliberately does not change diagnosis or treatment content.  It
replaces exact prevalence, proportion, or sex-ratio wording with qualitative
statements whose direction is supported by the authoritative references below.
Every record remains ``needs_review=true`` and this script does not grant
medical approval.

The patch is compare-and-set and idempotent: a value is changed only when it
exactly matches the reviewed legacy text.  An unexpected value is reported as
drift and blocks ``--apply`` so concurrent edits are never overwritten.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data_private" / "curriculum" / "clinical_axes_map.json"


@dataclass(frozen=True)
class Correction:
    path: tuple[str, ...]
    old: str
    new: str
    source_url: str
    transition_values: tuple[str, ...] = ()


# Sources are public-health agencies, NIH/NCI resources, or a professional
# society.  They support the direction of the qualitative replacement; the
# numerical estimates themselves are intentionally not retained in an
# auto-authored draft.
CORRECTIONS: dict[str, Correction] = {
    "abdominal_aortic_aneurysm": Correction(
        ("epidemiology", "sex"),
        "Strong male predominance (~4-6:1)",
        "Abdominal aortic aneurysm is more common among men than women",
        "https://www.ncbi.nlm.nih.gov/books/NBK441574/",
        ("More common among men than women",),
    ),
    "autism_spectrum_disorder": Correction(
        ("epidemiology", "sex"),
        "Strong male predominance (roughly 4:1)",
        "More commonly identified among boys than girls",
        "https://www.cdc.gov/autism/data-research/index.html",
    ),
    "congenital_hypothyroidism": Correction(
        ("epidemiology", "sex"),
        "Female predominance (thyroid dysgenesis ~2:1 F:M)",
        "More common among female than male newborns",
        "https://medlineplus.gov/genetics/condition/congenital-hypothyroidism/",
    ),
    "juvenile_myelomonocytic_leukemia": Correction(
        ("epidemiology", "sex"),
        "Male predominance (about 2:1)",
        "More common among boys than girls",
        "https://www.cancer.gov/types/leukemia/hp/child-aml-treatment-pdq/childhood-jmml-treatment-pdq",
    ),
    "kawasaki_disease": Correction(
        ("epidemiology", "sex"),
        "Male predominance (~1.5:1)",
        "More common among boys than girls",
        "https://www.heart.org/en/health-topics/kawasaki-disease",
    ),
    "major_depressive_disorder": Correction(
        ("epidemiology", "sex"),
        "Female predominance (~2:1)",
        "More commonly diagnosed among women than men",
        "https://www.nimh.nih.gov/health/publications/depression",
    ),
    "panic_disorder": Correction(
        ("epidemiology", "sex"),
        "Female predominance (roughly 2:1)",
        "More common among women than men",
        "https://www.nimh.nih.gov/health/publications/panic-disorder-when-fear-overwhelms",
    ),
    "polycythemia_vera": Correction(
        ("epidemiology", "population"),
        "JAK2 V617F mutation present in over 95% of cases",
        "JAK2 alterations are present in nearly all cases",
        "https://staging.seer.cancer.gov/eod_public/input/3.2/hemeretic/jak2/",
    ),
    "schizophrenia": Correction(
        ("epidemiology", "population"),
        "Worldwide ~1% lifetime prevalence; higher in urban and migrant populations",
        "Occurs worldwide and is less common than many other mental disorders",
        "https://www.who.int/news-room/fact-sheets/detail/schizophrenia",
    ),
    "chronic_lymphocytic_leukemia": Correction(
        ("epidemiology", "sex"),
        "Male predominance (~2:1)",
        "Chronic lymphocytic leukemia is more common among men than women",
        "https://seer.cancer.gov/statfacts/html/cllsll.html",
        ("More common among men than women",),
    ),
    "chronic_myeloid_leukemia": Correction(
        ("epidemiology", "population"),
        "Accounts for roughly 15% of adult leukemias; no strong geographic clustering",
        "A relatively rare leukemia that occurs mainly in middle-aged and older adults",
        "https://seer.cancer.gov/statfacts/html/cmyl.html",
    ),
    "chronic_myelomonocytic_leukemia": Correction(
        ("epidemiology", "sex"),
        "Male predominance (~2:1)",
        "Chronic myelomonocytic leukemia is more common among men than women",
        "https://www.cancer.gov/types/myeloproliferative/patient/mds-mpd-treatment-pdq",
        ("More common among men than women",),
    ),
    "familial_adenomatous_polyposis": Correction(
        ("epidemiology", "population"),
        "Autosomal dominant inheritance worldwide; ~25% arise from de novo mutation",
        "Autosomal dominant inheritance worldwide; some cases result from a de novo APC pathogenic variant",
        "https://www.ncbi.nlm.nih.gov/books/NBK1345/",
    ),
    "gastric_cancer": Correction(
        ("epidemiology", "sex"),
        "Male predominance (about 2:1)",
        "More common among males than females",
        "https://www.cancer.gov/types/stomach/causes-risk-factors",
    ),
    "hemophilia_a": Correction(
        ("epidemiology", "population"),
        "All ethnic groups; accounts for ~80-85% of hemophilia cases",
        "Affects all racial and ethnic groups and is more common than hemophilia B",
        "https://www.cdc.gov/hemophilia/about/index.html",
    ),
    "hemophilia_b": Correction(
        ("epidemiology", "population"),
        "All ethnic groups; accounts for ~15-20% of hemophilia cases",
        "Affects all racial and ethnic groups and is less common than hemophilia A",
        "https://www.cdc.gov/hemophilia/about/index.html",
    ),
    "hepatocellular_carcinoma": Correction(
        ("epidemiology", "sex"),
        "Male predominance (roughly 2-4:1)",
        "Hepatocellular carcinoma is more common among men than women",
        "https://www.cancer.gov/types/liver/what-is-liver-cancer/causes-risk-factors",
        ("More common among men than women",),
    ),
    "hirschsprung_disease": Correction(
        ("epidemiology", "sex"),
        "Male predominance (about 4:1, less marked in long-segment disease)",
        "Male predominance overall, with less sex disparity in long-segment disease",
        "https://medlineplus.gov/genetics/condition/hirschsprung-disease/",
    ),
    "hyperthyroidism": Correction(
        ("epidemiology", "sex"),
        "Strong female predominance (roughly 5-10:1)",
        "More common among women than men",
        "https://www.niddk.nih.gov/health-information/endocrine-diseases/hyperthyroidism",
    ),
    "iga_nephropathy": Correction(
        ("epidemiology", "sex"),
        "Male predominance (~2:1)",
        "IgA nephropathy is more common among men than women",
        "https://www.niddk.nih.gov/health-information/kidney-disease/iga-nephropathy",
        ("More common among men than women",),
    ),
    "migraine": Correction(
        ("epidemiology", "sex"),
        "Female predominance (roughly 3:1)",
        "More common among adult women than adult men",
        "https://www.ninds.nih.gov/health-information/disorders/migraine",
    ),
    "rheumatoid_arthritis": Correction(
        ("epidemiology", "sex"),
        "Female predominance (roughly 2-3:1)",
        "More common among women than men",
        "https://www.niams.nih.gov/health-topics/rheumatoid-arthritis",
    ),
    "systemic_lupus_erythematosus": Correction(
        ("epidemiology", "sex"),
        "Strong female predominance (~9:1)",
        "Markedly more common among women than men",
        "https://www.niams.nih.gov/health-topics/lupus",
    ),
    "non_small_cell_lung_cancer": Correction(
        ("epidemiology", "population"),
        "Smokers; ~85% of all lung cancers are NSCLC; EGFR mutations enriched in East Asian never-smoking women",
        "The most common main type of lung cancer; associated with smoking, while some subtypes also occur in never-smokers",
        "https://www.cancer.gov/publications/dictionaries/cancer-terms/def/non-small-cell-lung-cancer",
    ),
    "wilms_tumor": Correction(
        ("epidemiology", "population"),
        "Most common primary renal malignancy of childhood; bilateral in a minority (~5-10%), often syndrome-associated",
        "The most common primary renal malignancy of childhood; bilateral disease occurs in a minority and is often syndrome-associated",
        "https://seer.cancer.gov/archive/publications/childhood/childhood-monograph.pdf",
    ),
}


def _get_path(record: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = record
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _set_path(record: dict[str, Any], path: tuple[str, ...], value: str) -> None:
    parent: Any = record
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value


def apply_corrections(data: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str], list[dict[str, Any]]]:
    """Return a corrected deep copy plus changed/already/drift reports."""
    result = deepcopy(data)
    axes = result.get("axes")
    if not isinstance(axes, dict):
        raise ValueError("input must contain an axes object")

    changed: list[str] = []
    already_applied: list[str] = []
    unexpected: list[dict[str, Any]] = []
    for cid, correction in CORRECTIONS.items():
        record = axes.get(cid)
        if not isinstance(record, dict):
            unexpected.append({"id": cid, "path": ".".join(correction.path), "actual": None, "reason": "missing_record"})
            continue
        actual = _get_path(record, correction.path)
        if actual == correction.new:
            already_applied.append(cid)
            continue
        if actual != correction.old and actual not in correction.transition_values:
            unexpected.append(
                {
                    "id": cid,
                    "path": ".".join(correction.path),
                    "actual": actual,
                    "reason": "unexpected_value",
                }
            )
            continue
        _set_path(record, correction.path, correction.new)
        # Automated correction never clears the clinical review gate.
        record["needs_review"] = True
        changed.append(cid)
    return result, changed, already_applied, unexpected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--apply", action="store_true", help="write reviewed corrections to --input")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    result, changed, already_applied, unexpected = apply_corrections(data)
    if args.apply and unexpected:
        raise SystemExit("refusing to apply because one or more reviewed source values drifted")
    if args.apply and changed:
        args.input.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "check",
                "target_records": len(CORRECTIONS),
                "records_corrected": len(changed),
                "already_applied": len(already_applied),
                "unexpected": unexpected,
                "ids": changed,
                "medical_approval": False,
                "needs_review_preserved": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
