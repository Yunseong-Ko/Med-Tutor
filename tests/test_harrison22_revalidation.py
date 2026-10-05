from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from scripts import build_axis_layer
from scripts.build_harrison22_snapshot import heading_offset
from scripts.revalidate_ontology_harrison22 import ChapterRetriever, chunks_for_page


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data_private" / "harrison" / "22e"


def test_shared_page_chapter_boundaries_are_separable() -> None:
    text = (
        "Palpitations\nJoseph Loscalzo\n45\nPalpitations body.\n"
        "Exercise Intolerance\nJoseph Loscalzo\n46\nExercise body."
    )
    start_45, _ = heading_offset(text, 45, "Palpitations")
    start_46, _ = heading_offset(text, 46, "Exercise Intolerance")
    assert start_45 is not None
    assert start_46 is not None
    assert start_45 < start_46
    assert "Exercise body" not in text[start_45:start_46]


def test_chunking_and_retrieval_are_deterministic_and_unapproved() -> None:
    text = "Acute leukemia is diagnosed using bone marrow findings. " * 40
    assert chunks_for_page(text) == chunks_for_page(text)
    retriever = ChapterRetriever(
        109,
        [
            {
                "inside_chapter_boundary": True,
                "segment_text": text,
                "source_file": "109_Acute Myeloid Leukemia.pdf",
                "source_file_sha256": "a" * 64,
                "pdf_page": 1,
                "printed_page": 825,
            }
        ],
    )
    candidate = retriever.search("acute leukemia bone marrow diagnosis")
    assert candidate is not None
    assert candidate["entailment_status"] == "needs_human_review"
    assert candidate["scope"] == "claim_level_candidate_not_entailment"
    assert candidate == retriever.search("acute leukemia bone marrow diagnosis")


def test_snapshot_is_complete_and_repairs_known_toc_gaps() -> None:
    manifest_path = SNAPSHOT / "snapshot_manifest.json"
    chapter_path = SNAPSHOT / "chapter_index.json"
    if not manifest_path.exists() or not chapter_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_schema = json.loads(
        (ROOT / "schemas" / "harrison_source_snapshot.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(manifest, snapshot_schema)
    chapters = json.loads(chapter_path.read_text(encoding="utf-8"))["chapters"]
    assert manifest["summary"]["pdf_files"] == 507
    assert manifest["summary"]["clinical_chapters"] == 505
    assert manifest["integrity"]["missing_numbered_files"] == []
    by_number = {row["chapter"]: row for row in chapters}
    assert set(by_number) == set(range(1, 506))
    assert by_number[354]["toc_printed_page"] == 2700
    assert by_number[373]["title"] == "Sjögren’s Disease"
    assert by_number[376]["title"] == "Behçet Syndrome"
    assert by_number[412]["toc_printed_page"] == 3178
    assert by_number[458]["toc_printed_page"] == 3617


def test_generated_claim_overlay_is_fail_closed_and_schema_valid() -> None:
    overlay_path = SNAPSHOT / "validation" / "claim_support_overlay.json"
    if not overlay_path.exists():
        return
    payload = json.loads(overlay_path.read_text(encoding="utf-8"))
    schema = json.loads(
        (ROOT / "schemas" / "harrison22_claim_revalidation.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(payload, schema)
    assert payload["summary"]["automatic_medical_approvals"] == 0
    assert payload["summary"]["student_visible_claims"] == 0
    assert payload["summary"]["verified_entailment_claims"] == 0
    axis = json.loads(
        (ROOT / "data_private" / "curriculum" / "axis_registry.json").read_text(encoding="utf-8")
    )
    assert len(payload["claims"]) == len(axis["nodes"]) + len(axis["relationships"])
    assert all(row["needs_review"] for row in payload["claims"].values())
    assert not any(row["medical_approval"] for row in payload["claims"].values())
    candidate_scores = [
        candidate["retrieval_score"]
        for row in payload["claims"].values()
        for candidate in row.get("candidates", [])
    ]
    assert candidate_scores
    assert min(candidate_scores) >= 0


def test_claim_lineage_is_stable_but_revision_changes_with_assertion() -> None:
    lineage = build_axis_layer.claim_lineage_id("axis_node", "risk_factor", "smoking")
    assert lineage == build_axis_layer.claim_lineage_id("axis_node", "risk_factor", "smoking")
    first = build_axis_layer.claim_revision_id(lineage, "Smoking", build_axis_layer.default_qualifiers())
    second = build_axis_layer.claim_revision_id(lineage, "Heavy smoking", build_axis_layer.default_qualifiers())
    assert first != second
