from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from scripts import ingest_us_guideline_sources as ingest


ROOT = Path(__file__).resolve().parents[1]


def private_artifact(relative_path: str) -> Path:
    path = ROOT / relative_path
    if not path.exists():
        pytest.skip(f"private guideline artifact is not present: {relative_path}")
    return path


def test_us_registry_schema_and_release_defaults_are_fail_closed() -> None:
    schema = json.loads((ROOT / "schemas" / "us_guideline_source_registry.schema.json").read_text())
    payload = json.loads(
        private_artifact("data_private/us_guidelines/verified_latest_registry.json").read_text()
    )
    assert list(Draft7Validator(schema).iter_errors(payload)) == []

    payload["sources"][0]["generation_eligible"] = True
    errors = list(Draft7Validator(schema).iter_errors(payload))
    assert errors
    assert any("False was expected" in error.message for error in errors)


def test_copyright_metadata_only_attachment_never_calls_network(tmp_path: Path) -> None:
    registry = json.loads(
        private_artifact("data_private/us_guidelines/verified_latest_registry.json").read_text()
    )
    source = next(row for row in registry["sources"] if row["source_id"] == "us-cpg:ada-standards-2026")
    result = ingest.download_attachment(
        object(),
        source,
        source["attachments"][0],
        files_dir=tmp_path,
        overwrite=False,
    )
    assert result["download_status"] == "metadata_only"
    assert result["error"] == "source_or_rights_policy_metadata_only"
    assert list(tmp_path.rglob("*")) == []


def test_current_us_base_counts_rights_and_checksums() -> None:
    registry = json.loads(
        private_artifact("data_private/us_guidelines/verified_latest_registry.json").read_text()
    )
    sources = registry["sources"]
    attachments = [attachment for source in sources for attachment in source["attachments"]]
    downloaded = [attachment for attachment in attachments if attachment["download_status"] == "downloaded"]

    assert len(sources) == 16
    assert sum(source["priority"] == "P0" for source in sources) == 12
    assert len(attachments) == 16
    assert len(downloaded) == 3
    assert sum(attachment["download_status"] == "metadata_only" for attachment in attachments) == 13
    assert registry["summary"]["downloaded_bytes"] == 809_875
    assert registry["summary"]["runtime_ingest_allowed_sources"] == 0
    assert registry["jurisdiction_policy"]["primary_for_korean_care"] is False
    assert registry["jurisdiction_policy"]["silent_merge_allowed"] is False
    assert all(source["jurisdiction"] == "US" for source in sources)
    assert all(source["needs_review"] is True for source in sources)
    assert all(source["medical_approval"] is False for source in sources)
    assert all(source["student_visible"] is False for source in sources)
    assert all(source["generation_eligible"] is False for source in sources)
    assert all(source["rights"]["runtime_ingest_allowed"] is False for source in sources)

    for attachment in downloaded:
        path = private_artifact(attachment["relative_path"])
        assert path.stat().st_size == attachment["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == attachment["sha256"]
        assert attachment["pdf_pages"] and attachment["pdf_pages"] > 0
        assert attachment["pdf_text_chars"] and attachment["pdf_text_chars"] > 0


def test_jurisdiction_policy_preserves_kr_primary_and_conflict_display() -> None:
    policy = json.loads(
        private_artifact("data_private/us_guidelines/jurisdiction_policy.json").read_text()
    )
    korean_mode = policy["modes"]["korean_clinical_learning"]
    research_mode = policy["modes"]["research_comparison"]
    release = policy["release_defaults"]

    assert korean_mode["primary_jurisdiction"] == "KR"
    assert korean_mode["us_roles"] == ["gap_fill", "comparison"]
    assert research_mode["show_parallel_recommendations"] is True
    assert policy["conflict_policy"]["silent_merge_allowed"] is False
    assert policy["conflict_policy"]["automatic_majority_vote_allowed"] is False
    assert release == {
        "needs_review": True,
        "medical_approval": False,
        "student_visible": False,
        "generation_eligible": False,
        "runtime_ingest_enabled": False,
    }
