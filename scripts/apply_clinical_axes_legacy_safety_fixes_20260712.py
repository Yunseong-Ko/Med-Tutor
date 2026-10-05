#!/usr/bin/env python3
"""Remove unsafe glucose-delay wording from legacy clinical-axis drafts."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data_private" / "curriculum" / "clinical_axes_map.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    data = json.loads(PATH.read_text(encoding="utf-8"))
    axes = deepcopy(data["axes"])
    changed: list[str] = []

    alcohol = axes["alcohol_use_disorder"]["treatment"]
    if "before glucose" in alcohol["indicated_for"][1].casefold():
        alcohol["indicated_for"][1] = (
            "Prompt parenteral thiamine for patients at risk of deficiency; administer urgently indicated glucose "
            "without waiting for thiamine, using either order or concurrent administration."
        )
        alcohol["contraindicated_for"] = [
            value for value in alcohol["contraindicated_for"] if "glucose before thiamine" not in value.casefold()
        ]
        changed.append("alcohol_use_disorder")

    malnutrition = axes["malnutrition"]
    if "thiamine before glucose" in malnutrition["treatment"]["indicated_for"][3].casefold():
        malnutrition["treatment"]["indicated_for"][3] = (
            "Prompt micronutrient and vitamin repletion, including thiamine for patients at risk of deficiency; do "
            "not delay urgent glucose treatment."
        )
        malnutrition["treatment"]["contraindicated_for"] = [
            value
            for value in malnutrition["treatment"]["contraindicated_for"]
            if "loading before thiamine" not in value.casefold()
        ]
        malnutrition.setdefault("uncertainty_notes", []).append(
            "Plan thiamine with carbohydrate during controlled refeeding, but never delay treatment of urgent hypoglycemia."
        )
        changed.append("malnutrition")

    pregnancy = axes["nausea_and_vomiting_of_pregnancy"]
    if "before dextrose" in pregnancy["treatment"]["indicated_for"][4].casefold():
        pregnancy["treatment"]["indicated_for"][4] = (
            "Prompt parenteral thiamine in prolonged vomiting or deficiency risk; give urgently indicated dextrose "
            "without waiting for thiamine."
        )
        pregnancy["treatment"]["contraindicated_for"] = [
            value
            for value in pregnancy["treatment"]["contraindicated_for"]
            if "dextrose given before thiamine" not in value.casefold()
        ]
        changed.append("nausea_and_vomiting_of_pregnancy")

    wernicke = axes["wernicke_encephalopathy"]["treatment"]
    if "before any glucose" in wernicke["principles"].casefold():
        wernicke["principles"] = (
            "Give immediate parenteral thiamine and correct magnesium. Do not delay urgently indicated glucose; "
            "thiamine and glucose may be given in either order or concurrently."
        )
        wernicke["indicated_for"][0] = "Immediate empiric high-dose parenteral thiamine."
        wernicke["indicated_for"][2] = "Urgently indicated glucose without delay, with prompt thiamine treatment."
        wernicke["contraindicated_for"] = []
        changed.append("wernicke_encephalopathy")

    if args.apply and changed:
        data["axes"] = axes
        PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "check",
                "records_corrected": len(changed),
                "ids": changed,
                "medical_approval": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
