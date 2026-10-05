from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.build_ontology_hardening_worklist import build, write_or_check


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_separates_quarantined_and_groundable_gaps() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        registry = root / "registry.json"
        axes = root / "axes.json"
        typed = root / "typed.json"
        endpoints = root / "endpoints.json"
        audit = root / "audit.json"
        write(
            registry,
            {
                "_meta": {},
                "concepts": {
                    "covered": {
                        "node_type": "disease",
                        "aliases": ["Covered"],
                        "edges": {
                            "differential_of": [
                                {"id": "d1"}, {"id": "d2"}, {"id": "d3"}, {"id": "d4"}
                            ]
                        },
                        "evidence": {"harrison": {"chapter": 1, "page": 2}},
                    },
                    "missing": {"node_type": "disease", "aliases": ["Missing"], "edges": {}, "evidence": {}},
                    "umbrella": {
                        "node_type": "syndrome",
                        "aliases": ["Umbrella"],
                        "generation_grounding_status": "quarantined_scope_ambiguous",
                        "edges": {},
                        "evidence": {},
                    },
                    **{
                        cid: {"node_type": "disease", "aliases": [cid], "edges": {}, "evidence": {}}
                        for cid in ("d1", "d2", "d3", "d4")
                    },
                },
            },
        )
        write(typed, {"entities": {}})
        write(
            axes,
            {
                "nodes": [
                    {"axis_id": "a:diagnosis:x", "axis_type": "diagnosis", "review_status": "draft_unreviewed"}
                ],
                "relationships": [
                    {
                        "disease_concept_id": "covered",
                        "axis_id": "a:diagnosis:x",
                        "provenance": {"claim_entailment": "unverified"},
                    }
                ],
            },
        )
        write(endpoints, {"total": 1, "items": [{"id": "test", "total": 2}]})
        write(audit, {"summary": {"warnings": 1}, "issues": [{"code": "thin_content"}]})

        payload = build(
            registry_path=registry,
            axis_registry_path=axes,
            typed_entity_registry_path=typed,
            endpoint_unresolved_path=endpoints,
            clinical_audit_path=audit,
        )

        summary = payload["summary"]
        assert summary["generation_quarantined_concepts"] == 1
        assert summary["axis_missing_generation_groundable"] == 5
        missing_rows = payload["worklists"]["axis_missing"]
        umbrella = next(row for row in missing_rows if row["disease_concept_id"] == "umbrella")
        assert umbrella["disposition"] == "retain_generation_quarantine_and_review_scope_split"
        assert summary["distractor_pool_lt_4"] == 5
        assert summary["unresolved_endpoint_ids"] == 1
        assert summary["axis_relationships_entailment_not_verified"] == 1


def test_write_or_check_is_deterministic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "worklist.json"
        payload = {"schema_version": "test", "rows": [1, 2]}
        assert write_or_check(payload, output, check=False)
        assert write_or_check(payload, output, check=True)
        output.write_text("{}\n", encoding="utf-8")
        assert not write_or_check(payload, output, check=True)
