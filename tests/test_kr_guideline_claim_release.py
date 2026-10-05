import json
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]


def test_empty_guideline_claim_release_registry_is_default_deny_and_valid():
    schema = json.loads(
        (ROOT / "schemas" / "kr_guideline_claim_release.schema.json").read_text(
            encoding="utf-8"
        )
    )
    registry = json.loads(
        (ROOT / "data_private" / "kr_guidelines" / "claim_releases.json").read_text(
            encoding="utf-8"
        )
    )

    jsonschema.Draft202012Validator(schema).validate(registry)
    assert registry["policy"]["default_deny"] is True
    assert registry["releases"] == []
