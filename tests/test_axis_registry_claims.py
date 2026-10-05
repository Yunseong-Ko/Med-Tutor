from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from scripts import build_axis_layer


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "axis_registry.schema.json"


@pytest.fixture(scope="module")
def draft_payload(tmp_path_factory: pytest.TempPathFactory) -> dict:
    missing = tmp_path_factory.mktemp("axis-review") / "missing-overrides.json"
    return build_axis_layer.build(review_overrides_path=missing)


def write_override(path: Path, row: dict) -> Path:
    sections = {"concepts": [], "axis_nodes": [], "axis_relationships": []}
    claim = str(row.get("claim_id") or "")
    if claim.startswith("c:axis_node:"):
        sections["axis_nodes"].append(row)
    elif claim.startswith("c:axis_relation:"):
        sections["axis_relationships"].append(row)
    elif row.get("concept_id"):
        sections["concepts"].append(row)
    else:
        sections["axis_nodes"].append(row)
    path.write_text(
        json.dumps(
            {
                "schema_version": build_axis_layer.REVIEW_OVERRIDE_SCHEMA_VERSION,
                **sections,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_registry_schema_and_default_claim_safety(draft_payload: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(draft_payload), key=lambda error: list(error.path))
    assert not errors, [f"{list(error.path)}: {error.message}" for error in errors[:10]]

    claims = [*draft_payload["nodes"], *draft_payload["relationships"]]
    claim_ids = [row["claim_id"] for row in claims]
    assert len(claim_ids) == len(set(claim_ids))
    assert all(row["review_status"] == "draft_unreviewed" for row in claims)
    assert all(row["review"]["status"] == "draft_unreviewed" for row in claims)
    assert all(row["needs_review"] is True for row in claims)
    assert all(row["medical_approval"] is False for row in claims)
    assert all(row["applicability"] == "unknown" for row in claims)
    assert all(row["review"]["flags"] == [] for row in claims)
    assert {
        row["provenance"]["claim_entailment"] for row in claims
    } <= {"unverified", "needs_human_review"}
    assert not any(
        row["provenance"]["claim_entailment"] in {"verified", "contradicted"}
        for row in claims
    )
    assert draft_payload["stats"]["medical_approval_claims"] == 0
    assert draft_payload["stats"]["review_decisions_applied"] == 0


def test_claim_ids_are_stable_and_match_the_documented_hash_contract() -> None:
    aid = build_axis_layer.axis_id("risk_factor", "Smoking")
    assert aid == "a:risk_factor:a61e0c3ee83110"
    assert build_axis_layer.claim_id("axis_node", aid) == "c:axis_node:1f62c9b35b8d0459"
    assert (
        build_axis_layer.claim_id(
            "axis_relation",
            "target_disease",
            "has_risk_factor",
            aid,
        )
        == "c:axis_relation:cc91614cb51c2eb6"
    )
    assert build_axis_layer.axis_id("risk_factor", "  smoking  ") == aid


def test_missing_review_override_file_is_a_safe_noop(tmp_path: Path) -> None:
    overrides, meta = build_axis_layer.load_review_overrides(tmp_path / "missing.json")
    assert overrides == {}
    assert meta["status"] == "not_found_no_overrides_applied"
    assert meta["decision_counts"] == {
        "concepts": 0,
        "axis_nodes": 0,
        "axis_relationships": 0,
    }
    assert meta["applied_count"] == 0


def test_unified_decision_contract_accepts_concept_section_without_axis_application(
    tmp_path: Path,
) -> None:
    decision = {
        "schema_version": build_axis_layer.REVIEW_DECISION_SCHEMA_VERSION,
        "concepts": [
            {
                "concept_id": "acute_pancreatitis",
                "review_status": "reviewed_not_approved",
                "medical_approval": False,
                "applicability": "applicable",
                "review_flags": ["specialist_followup"],
                "reviewer_id": "faculty:test-reviewer",
                "reviewed_at": "2026-07-12T12:00:00+09:00",
                "claim_entailment": "needs_human_review"
            }
        ],
        "axis_nodes": [],
        "axis_relationships": [],
    }
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    decision_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$ref": "#/definitions/ontologyReviewDecisions",
        "definitions": schema["definitions"],
    }
    jsonschema.validate(
        decision,
        decision_schema,
        format_checker=jsonschema.FormatChecker(),
    )
    path = tmp_path / "ontology_review_decisions.json"
    path.write_text(json.dumps(decision), encoding="utf-8")
    overrides, meta = build_axis_layer.load_review_overrides(path)
    assert overrides == {}
    assert meta["decision_counts"] == {
        "concepts": 1,
        "axis_nodes": 0,
        "axis_relationships": 0,
    }


def test_explicit_human_override_can_approve_one_claim_only(
    draft_payload: dict,
    tmp_path: Path,
) -> None:
    nodes = copy.deepcopy(draft_payload["nodes"][:2])
    relationships = copy.deepcopy(draft_payload["relationships"][:2])
    target = relationships[0]
    path = write_override(
        tmp_path / "overrides.json",
        {
            "claim_id": target["claim_id"],
            "review_status": "approved",
            "medical_approval": True,
            "applicability": "applicable",
            "review_flags": ["faculty_verified", "high_yield"],
            "reviewer_id": "faculty:test-reviewer",
            "reviewed_at": "2026-07-12T12:00:00+09:00",
            "claim_entailment": "verified",
            "note": "Synthetic explicit human-review decision.",
            "qualifiers": {
                "population": ["adult"],
                "clinical_context": ["stable patient"],
                "certainty": "confirmed"
            },
            "evidence_refs": [
                {
                    "ref_id": "review:test-source",
                    "source_type": "faculty_review_packet",
                    "scope": "claim_review",
                    "entailment_status": "verified"
                }
            ]
        },
    )
    overrides, meta = build_axis_layer.load_review_overrides(path)
    applied = build_axis_layer.apply_review_overrides(
        nodes,
        relationships,
        overrides,
        source_path=meta["path"],
    )

    assert applied == 1
    assert target["review_status"] == "approved"
    assert target["medical_approval"] is True
    assert target["needs_review"] is False
    assert target["applicability"] == "applicable"
    assert target["review"]["flags"] == ["faculty_verified", "high_yield"]
    assert target["provenance"]["claim_entailment"] == "verified"
    assert target["provenance"]["status"] == "human_review_override"
    assert target["qualifiers"]["population"] == ["adult"]
    assert target["qualifiers"]["certainty"] == "confirmed"
    assert relationships[1]["review_status"] == "draft_unreviewed"
    assert all(node["review_status"] == "draft_unreviewed" for node in nodes)


def test_not_applicable_override_stays_unapproved_and_flagged(
    draft_payload: dict,
    tmp_path: Path,
) -> None:
    nodes = copy.deepcopy(draft_payload["nodes"][:1])
    target = nodes[0]
    path = write_override(
        tmp_path / "not-applicable.json",
        {
            "claim_id": target["claim_id"],
            "review_status": "reviewed_not_approved",
            "medical_approval": False,
            "applicability": "not_applicable",
            "review_flags": ["scope_mismatch"],
            "reviewer_id": "faculty:test-reviewer",
            "reviewed_at": "2026-07-12T12:00:00+09:00",
            "claim_entailment": "not_supported"
        },
    )
    overrides, meta = build_axis_layer.load_review_overrides(path)
    build_axis_layer.apply_review_overrides(nodes, [], overrides, source_path=meta["path"])

    assert target["applicability"] == "not_applicable"
    assert target["review"]["flags"] == ["scope_mismatch"]
    assert target["medical_approval"] is False
    assert target["needs_review"] is True


def test_loader_rejects_unsafe_approval(tmp_path: Path, draft_payload: dict) -> None:
    target = draft_payload["nodes"][0]
    path = write_override(
        tmp_path / "unsafe.json",
        {
            "claim_id": target["claim_id"],
            "review_status": "approved",
            "medical_approval": True,
            "applicability": "unknown",
            "reviewer_id": "faculty:test-reviewer",
            "reviewed_at": "2026-07-12T12:00:00+09:00",
            "claim_entailment": "unverified"
        },
    )
    with pytest.raises(ValueError, match="approved claim requires"):
        build_axis_layer.load_review_overrides(path)


def test_unknown_claim_override_fails_closed(tmp_path: Path) -> None:
    path = write_override(
        tmp_path / "unknown.json",
        {
            "claim_id": "c:axis_node:0000000000000000",
            "review_status": "reviewed_not_approved",
            "medical_approval": False,
            "applicability": "unknown",
            "review_flags": ["manual_followup"],
            "reviewer_id": "faculty:test-reviewer",
            "reviewed_at": "2026-07-12T12:00:00+09:00",
            "claim_entailment": "needs_human_review"
        },
    )
    overrides, meta = build_axis_layer.load_review_overrides(path)
    with pytest.raises(ValueError, match="unknown claim_id"):
        build_axis_layer.apply_review_overrides([], [], overrides, source_path=meta["path"])
