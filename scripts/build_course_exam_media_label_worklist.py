#!/usr/bin/env python3
"""Build a deterministic, question-grounded draft media labeling worklist.

This script never edits extracted exam packets and never approves a label.
It inventories every extracted course-exam media occurrence, hashes the binary,
deduplicates repeated question refs, and records candidate semantic labels with
the exact source question fields that produced them.

Outputs are private review artifacts under:
  data_private/course_exams/media_labeling/

The source question is primary provenance for a candidate label. It is not
independent medical validation and it never proves that an image depicts the
question's answer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTRACTED_DIR = ROOT / "data_private" / "course_exams" / "extracted"
DEFAULT_MEDIA_ROOT = ROOT / "data_private" / "course_exams" / "media"
DEFAULT_OUTPUT_DIR = ROOT / "data_private" / "course_exams" / "media_labeling"
DEFAULT_CONCEPT_REGISTRY = ROOT / "data_private" / "concept_registry.json"
DEFAULT_FINDING_REGISTRY = ROOT / "data_private" / "curriculum" / "finding_registry.json"

SCHEMA_VERSION = "course_exam_media_labeling.v1"
RULE_VERSION = "question_grounded_media_candidates.v1"

OUTPUT_NAMES = (
    "media_objects.draft.jsonl",
    "media_occurrences.draft.jsonl",
    "question_media_links.draft.jsonl",
    "media_label_review_worklist.jsonl",
)

IMAGE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
    ".wmf",
}

AXIS_RULES = (
    ("contraindication", ("금기", "사용금지")),
    ("indication", ("적응증",)),
    ("pathophysiology", ("병태생리", "발생기전", "기전")),
    ("risk_factor", ("위험인자", "위험요인")),
    ("epidemiology", ("역학", "발생률", "유병률")),
    ("prognosis", ("예후",)),
    ("etiology", ("원인", "병인")),
    ("symptom", ("증상", "임상소견")),
    (
        "diagnosis",
        (
            "현미경판독",
            "영상판독",
            "병리판독",
            "검사해석",
            "검사선택",
            "진단",
            "검사",
        ),
    ),
    ("treatment", ("치료원칙", "초기처치", "다음처치", "치료", "처치", "수술")),
)

MODALITY_RULES = (
    ("ecg", (r"심전도", r"\bECG\b", r"\bEKG\b")),
    ("eeg", (r"뇌파", r"\bEEG\b")),
    ("mammography", (r"유방촬영", r"mammograph")),
    ("fundus", (r"안저", r"fundus")),
    ("endoscopy", (r"내시경", r"endoscop")),
    ("ultrasound", (r"초음파", r"ultrason", r"\bUS\b")),
    ("mri", (r"자기공명", r"\bMRI\b")),
    (
        "ct",
        (
            r"컴퓨터단층",
            r"전산화단층",
            r"\bCT\b",
        ),
    ),
    ("xray", (r"X[\s-]*선", r"엑스선", r"방사선사진", r"radiograph")),
    (
        "blood_smear",
        (
            r"말초혈액도말",
            r"혈액도말",
            r"peripheral blood smear",
            r"blood smear",
        ),
    ),
    (
        "bone_marrow_microscopy",
        (
            r"골수흡인",
            r"골수도말",
            r"적색골수",
            r"bone marrow",
        ),
    ),
    (
        "microscopy",
        (
            r"현미경",
            r"조직사진",
            r"병리사진",
            r"세포사진",
            r"microscop",
            r"histolog",
        ),
    ),
    ("fluoroscopy", (r"투시", r"fluoroscop")),
    ("clinical_photo", (r"피부병변", r"임상사진", r"clinical photograph")),
)


def stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def digest_json(value: Any) -> str:
    return digest_text(stable_json(value))


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def compact_key(value: Any) -> str:
    text = normalize_text(value).casefold()
    return re.sub(r"[\s._/·,:;()\-]+", "", text)


def nonempty_list(value: Any) -> list[str]:
    if isinstance(value, list):
        source = value
    elif value in (None, "", {}):
        source = []
    else:
        source = [value]
    out: list[str] = []
    for item in source:
        text = normalize_text(item)
        if text and text not in out:
            out.append(text)
    return out


def normalize_answer_keys(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    circled = "①②③④⑤⑥⑦⑧"
    for raw in values:
        text = normalize_text(raw)
        if not text:
            continue
        if text in circled:
            text = str(circled.index(text) + 1)
        if text not in normalized:
            normalized.append(text)
    return normalized


def json_pointer_token(value: Any) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def source_exam_id(record: dict[str, Any], path: Path) -> str:
    exam = record.get("exam") if isinstance(record.get("exam"), dict) else {}
    return normalize_text(
        exam.get("source_exam")
        or record.get("exam_id")
        or record.get("source_exam")
        or path.stem
    )


def question_id(question: dict[str, Any], exam_id: str, index: int) -> str:
    return normalize_text(
        question.get("question_id")
        or f"{exam_id}_Q{int(question.get('question_number') or index):03d}"
    )


def resolve_asset_path(
    asset: dict[str, Any],
    *,
    media_root: Path,
) -> Path:
    raw_path = normalize_text(asset.get("file_path"))
    candidates: list[Path] = []
    if raw_path:
        path = Path(raw_path)
        candidates.append(path if path.is_absolute() else ROOT / path)
    relative = normalize_text(asset.get("relative_path"))
    if relative:
        candidates.append(media_root / relative)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve() if candidates else Path()


def load_concept_index(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    concepts = data.get("concepts") if isinstance(data, dict) else {}
    concepts = concepts if isinstance(concepts, dict) else {}
    alias_index: dict[str, list[str]] = defaultdict(list)
    for concept_id, concept in concepts.items():
        alias_index[normalize_text(concept_id).casefold()].append(concept_id)
        if not isinstance(concept, dict):
            continue
        for alias in concept.get("aliases") or []:
            key = normalize_text(alias).casefold()
            if key and concept_id not in alias_index[key]:
                alias_index[key].append(concept_id)
    return concepts, dict(alias_index)


def load_finding_index(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    findings = data.get("findings") if isinstance(data, dict) else []
    finding_index: dict[str, dict[str, Any]] = {}
    alias_index: dict[str, list[str]] = defaultdict(list)
    for finding in findings if isinstance(findings, list) else []:
        if not isinstance(finding, dict):
            continue
        finding_id = normalize_text(finding.get("finding_id"))
        if not finding_id:
            continue
        finding_index[finding_id] = finding
        for label in (finding_id, finding.get("hpo_label")):
            key = normalize_text(label).casefold()
            if key and finding_id not in alias_index[key]:
                alias_index[key].append(finding_id)
    return finding_index, dict(alias_index)


def question_snapshot(
    question: dict[str, Any],
    *,
    exam_id: str,
    question_id_value: str,
    question_index: int,
    record_path: Path,
) -> dict[str, Any]:
    choices_raw = question.get("choices")
    if isinstance(choices_raw, dict):
        choices = {str(key): normalize_text(value) for key, value in choices_raw.items()}
    elif isinstance(choices_raw, list):
        choices = {str(index + 1): normalize_text(value) for index, value in enumerate(choices_raw)}
    else:
        choices = {}

    answer_keys = normalize_answer_keys(
        question.get("generated_answer") or question.get("answer")
    )
    correct_choice_texts = [
        choices[key]
        for key in answer_keys
        if key in choices and choices[key]
    ]
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    snapshot = {
        "exam_id": exam_id,
        "question_id": question_id_value,
        "question_number": question.get("question_number") or question_index,
        "source_record": relpath(record_path),
        "source_json_pointer": f"/questions/{question_index - 1}",
        "stem": normalize_text(question.get("stem")),
        "stimulus": normalize_text(question.get("stimulus")),
        "choices": choices,
        "answer_keys": answer_keys,
        "correct_choice_texts": correct_choice_texts,
        "original_explanation": normalize_text(question.get("original_explanation")),
        "explanation": normalize_text(question.get("explanation")),
        "answer_rationale": normalize_text(question.get("answer_rationale")),
        "key_info": question.get("key_info") if isinstance(question.get("key_info"), dict) else {},
        "choice_explanations": (
            question.get("choice_explanations")
            if isinstance(question.get("choice_explanations"), dict)
            else {}
        ),
        "labels": labels,
        "disease_concept_id": normalize_text(question.get("disease_concept_id")),
        "ontology_grounding": (
            question.get("ontology_grounding")
            if isinstance(question.get("ontology_grounding"), dict)
            else {}
        ),
        "question_blueprint": (
            question.get("question_blueprint")
            if isinstance(question.get("question_blueprint"), dict)
            else {}
        ),
        "review_status": normalize_text(question.get("review_status")),
        "needs_review": bool(question.get("needs_review", True)),
    }
    snapshot["snapshot_sha256"] = digest_json(snapshot)
    return snapshot


def add_candidate(
    bucket: list[dict[str, Any]],
    *,
    kind: str,
    relation: str,
    label_text: str,
    target_id: str | None,
    resolution: str,
    confidence: float,
    question_id_value: str,
    source_field: str,
    source_value: Any,
    note: str = "",
) -> None:
    payload = {
        "kind": kind,
        "relation": relation,
        "target_id": target_id,
        "label_text": normalize_text(label_text),
        "ontology_resolution": resolution,
        "status": "candidate",
        "confidence": round(max(0.0, min(float(confidence), 1.0)), 3),
        "evidence": {
            "question_id": question_id_value,
            "source_field": source_field,
            "source_value": source_value,
            "rule_version": RULE_VERSION,
        },
        "review_status": "needs_review",
        "medical_approval": False,
    }
    if note:
        payload["note"] = note
    payload["candidate_id"] = "mlabel_" + digest_json(payload)[:24]
    if payload not in bucket:
        bucket.append(payload)


def axis_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    labels = snapshot.get("labels") if isinstance(snapshot.get("labels"), dict) else {}
    raw = normalize_text(labels.get("assessment_domain"))
    if not raw:
        return []
    compact = compact_key(raw)
    candidates: list[dict[str, Any]] = []
    for axis_type, terms in AXIS_RULES:
        if any(compact_key(term) in compact for term in terms):
            add_candidate(
                candidates,
                kind="axis",
                relation="used_to_assess",
                label_text=axis_type,
                target_id=axis_type,
                resolution="resolved",
                confidence=0.9,
                question_id_value=snapshot["question_id"],
                source_field="labels.assessment_domain",
                source_value=raw,
                note="Question assessment context; not a claim about what is visibly depicted.",
            )
            break
    return candidates


def modality_candidates(
    snapshot: dict[str, Any],
    *,
    linked_asset_count: int,
    explicit_modality: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if explicit_modality:
        add_candidate(
            candidates,
            kind="modality",
            relation="has_modality",
            label_text=explicit_modality,
            target_id=None,
            resolution="unresolved",
            confidence=0.95,
            question_id_value=snapshot["question_id"],
            source_field="media_asset.modality",
            source_value=explicit_modality,
        )
        return candidates

    text = " ".join(
        part
        for part in (
            snapshot.get("stem"),
            snapshot.get("stimulus"),
        )
        if part
    )
    for modality, patterns in MODALITY_RULES:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            confidence = 0.9 if linked_asset_count == 1 else 0.55
            note = (
                "Explicit modality in a single-image question."
                if linked_asset_count == 1
                else "Question contains multiple media; candidate is ambiguous across assets."
            )
            add_candidate(
                candidates,
                kind="modality",
                relation="has_modality",
                label_text=modality,
                target_id=None,
                resolution="unresolved",
                confidence=confidence,
                question_id_value=snapshot["question_id"],
                source_field="question.stem_or_stimulus",
                source_value=text,
                note=note,
            )
    return candidates


def semantic_candidates(
    snapshot: dict[str, Any],
    *,
    concepts: dict[str, dict[str, Any]],
    concept_aliases: dict[str, list[str]],
    findings: dict[str, dict[str, Any]],
    finding_aliases: dict[str, list[str]],
    linked_asset_count: int,
    explicit_modality: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    labels = snapshot.get("labels") if isinstance(snapshot.get("labels"), dict) else {}
    source_values: list[tuple[str, str]] = []
    for source_field in ("concept_tags", "topic", "subtopic"):
        for value in nonempty_list(labels.get(source_field)):
            source_values.append((f"labels.{source_field}", value))

    grounding = snapshot.get("ontology_grounding")
    grounding = grounding if isinstance(grounding, dict) else {}
    explicit_concept = normalize_text(
        snapshot.get("disease_concept_id")
        or grounding.get("disease_concept_id")
        or grounding.get("concept_id")
    )
    if explicit_concept:
        source_values.append(("question.ontology_grounding", explicit_concept))

    seen_unresolved: set[tuple[str, str]] = set()
    for source_field, raw_value in source_values:
        value = normalize_text(raw_value)
        casefolded = value.casefold()

        concept_matches: list[str] = []
        if value in concepts:
            concept_matches = [value]
        else:
            concept_matches = concept_aliases.get(casefolded, [])
        for concept_id in concept_matches:
            concept = concepts.get(concept_id) or {}
            add_candidate(
                candidates,
                kind="concept",
                relation="associated_with_question_context",
                label_text=concept_id,
                target_id=concept_id,
                resolution="resolved",
                confidence=0.95 if value == concept_id else 0.8,
                question_id_value=snapshot["question_id"],
                source_field=source_field,
                source_value=raw_value,
                note=(
                    f"Registry node_type={concept.get('node_type') or 'unknown'}. "
                    "Question context does not prove that the image depicts this concept."
                ),
            )

        finding_matches: list[str] = []
        if value in findings:
            finding_matches = [value]
        else:
            finding_matches = finding_aliases.get(casefolded, [])
        for finding_id in finding_matches:
            add_candidate(
                candidates,
                kind="finding",
                relation="may_depict",
                label_text=finding_id,
                target_id=finding_id,
                resolution="resolved",
                confidence=0.7,
                question_id_value=snapshot["question_id"],
                source_field=source_field,
                source_value=raw_value,
                note=(
                    "Exact Finding Registry match from question context. "
                    "Visual confirmation is still required."
                ),
            )

        if not concept_matches and not finding_matches:
            key = (source_field, value)
            if key not in seen_unresolved:
                unresolved.append(
                    {
                        "label_text": value,
                        "source_field": source_field,
                        "source_value": raw_value,
                        "status": "candidate_unresolved",
                        "review_status": "needs_review",
                        "note": "Do not create an Ontology or Finding Registry node automatically.",
                    }
                )
                seen_unresolved.add(key)

    candidates.extend(axis_candidates(snapshot))
    candidates.extend(
        modality_candidates(
            snapshot,
            linked_asset_count=linked_asset_count,
            explicit_modality=explicit_modality,
        )
    )
    candidates.sort(
        key=lambda item: (
            item["kind"],
            item.get("target_id") or "",
            item["label_text"],
            item["candidate_id"],
        )
    )
    unresolved.sort(key=lambda item: (item["source_field"], item["label_text"]))
    return candidates, unresolved


def iter_exam_packets(extracted_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    packets: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(extracted_dir.glob("*.json"), key=lambda item: unicodedata.normalize("NFC", str(item))):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("questions"), list):
            packets.append((path, data))
    return packets


def position_support(
    record: dict[str, Any],
    *,
    question_number: Any,
    asset: dict[str, Any],
) -> bool | None:
    positions = record.get("media_positions")
    if not isinstance(positions, list) or not positions:
        return None
    storage_id = normalize_text(asset.get("storage_id"))
    if not storage_id:
        return None
    question_key = normalize_text(question_number)
    matching = [
        position
        for position in positions
        if isinstance(position, dict)
        and normalize_text(position.get("question_number")) == question_key
        and normalize_text(position.get("storage_id")) == storage_id
    ]
    return bool(matching)


def preferred_occurrence(occurrences: Iterable[dict[str, Any]]) -> str:
    def key(item: dict[str, Any]) -> tuple[int, int, str]:
        exam_id = item.get("source", {}).get("exam_id") or ""
        synthetic = 1 if str(exam_id).startswith("SYNTH_") else 0
        unlinked = 1 if not item.get("question_link_ids") else 0
        return (synthetic, unlinked, item["occurrence_id"])

    return sorted(occurrences, key=key)[0]["occurrence_id"]


def build_outputs(
    *,
    extracted_dir: Path,
    media_root: Path,
    concept_registry_path: Path,
    finding_registry_path: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    concepts, concept_aliases = load_concept_index(concept_registry_path)
    findings, finding_aliases = load_finding_index(finding_registry_path)
    packets = iter_exam_packets(extracted_dir)

    input_files: set[Path] = {
        concept_registry_path.resolve(),
        finding_registry_path.resolve(),
    }
    occurrences: list[dict[str, Any]] = []
    occurrence_by_exam_media: dict[tuple[str, str], dict[str, Any]] = {}
    record_by_exam: dict[str, dict[str, Any]] = {}
    record_path_by_exam: dict[str, Path] = {}
    question_by_exam_id: dict[tuple[str, str], dict[str, Any]] = {}
    question_index_by_exam_id: dict[tuple[str, str], int] = {}
    question_ref_counts: Counter[tuple[str, str, str]] = Counter()
    raw_refs_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)

    for record_path, record in packets:
        input_files.add(record_path.resolve())
        exam_id = source_exam_id(record, record_path)
        record_by_exam[exam_id] = record
        record_path_by_exam[exam_id] = record_path
        for index, question in enumerate(record.get("questions") or [], start=1):
            if not isinstance(question, dict):
                continue
            qid = question_id(question, exam_id, index)
            question_by_exam_id[(exam_id, qid)] = question
            question_index_by_exam_id[(exam_id, qid)] = index
            refs = (
                (question.get("media") or {}).get("media_refs")
                if isinstance(question.get("media"), dict)
                else []
            )
            for ref in refs if isinstance(refs, list) else []:
                if not isinstance(ref, dict):
                    continue
                media_id = normalize_text(ref.get("media_id"))
                if not media_id:
                    continue
                key = (exam_id, qid, media_id)
                question_ref_counts[key] += 1
                raw_refs_by_key[key].append(ref)

        for asset_index, asset in enumerate(record.get("media_assets") or [], start=1):
            if not isinstance(asset, dict):
                continue
            media_id = normalize_text(asset.get("media_id") or asset.get("storage_id"))
            if not media_id:
                media_id = f"{exam_id}_MEDIA_{asset_index:04d}"
            asset_path = resolve_asset_path(asset, media_root=media_root)
            exists = asset_path.exists() and asset_path.is_file()
            if exists:
                input_files.add(asset_path.resolve())
                content_sha256 = file_sha256(asset_path)
                file_size = asset_path.stat().st_size
                suffix = asset_path.suffix.lower()
            else:
                content_sha256 = digest_text(
                    f"missing::{relpath(record_path)}::{media_id}"
                )
                file_size = 0
                suffix = Path(normalize_text(asset.get("file_path"))).suffix.lower()
            object_id = "mediaobj_" + content_sha256
            occurrence_seed = f"{relpath(record_path)}\n{media_id}"
            occurrence_id = "mediaocc_" + digest_text(occurrence_seed)[:24]
            occurrence = {
                "schema_version": SCHEMA_VERSION,
                "record_type": "media_occurrence",
                "occurrence_id": occurrence_id,
                "media_object_id": object_id,
                "legacy_media_id": media_id,
                "source": {
                    "exam_id": exam_id,
                    "record_path": relpath(record_path),
                    "record_sha256": file_sha256(record_path),
                    "source_file": normalize_text(
                        asset.get("source_file")
                        or (record.get("exam") or {}).get("source_file")
                    ),
                    "source_file_status": (
                        "registered_in_workspace"
                        if normalize_text(asset.get("source_file"))
                        and (ROOT / normalize_text(asset.get("source_file"))).exists()
                        else "external_or_unregistered"
                    ),
                    "page_number": asset.get("page_number") or asset.get("source_page"),
                    "bbox": asset.get("bbox"),
                    "storage_id": asset.get("storage_id"),
                    "bindata_id": asset.get("bindata_id"),
                    "block_index": asset.get("block_index"),
                    "paragraph_index": asset.get("paragraph_index"),
                    "extraction_source": asset.get("source"),
                    "match_method": asset.get("match_method"),
                },
                "file": {
                    "path": relpath(asset_path) if asset_path else "",
                    "exists": exists,
                    "suffix": suffix,
                    "size_bytes": file_size,
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                    "web_safe_raster": suffix in {".gif", ".jpeg", ".jpg", ".png", ".webp"},
                },
                "legacy_metadata": {
                    key: asset.get(key)
                    for key in (
                        "relative_path",
                        "caption",
                        "modality",
                        "provenance",
                        "license",
                        "attribution",
                        "linked_question_numbers",
                        "needs_review",
                    )
                    if key in asset
                },
                "rights": {
                    "status": "declared_candidate" if asset.get("license") else "unknown",
                    "license": normalize_text(asset.get("license")),
                    "attribution": normalize_text(asset.get("attribution")),
                    "allowed_uses": [],
                    "review_status": "needs_review",
                },
                "deidentification": {
                    "status": (
                        "passed"
                        if asset.get("deidentified") is True
                        else "failed"
                        if asset.get("deidentified") is False
                        else "unknown"
                    ),
                    "review_status": "needs_review",
                },
                "review": {
                    "review_status": "needs_review",
                    "medical_approval": False,
                    "approved_for_question_use": False,
                    "student_visible": False,
                    "answer_leak_risk": "needs_review",
                },
                "question_link_ids": [],
            }
            occurrences.append(occurrence)
            occurrence_by_exam_media[(exam_id, media_id)] = occurrence

    links: list[dict[str, Any]] = []
    link_by_occurrence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    snapshot_by_link: dict[str, dict[str, Any]] = {}
    raw_ref_total = sum(question_ref_counts.values())

    for key in sorted(question_ref_counts):
        exam_id, qid, media_id = key
        occurrence = occurrence_by_exam_media.get((exam_id, media_id))
        question = question_by_exam_id.get((exam_id, qid))
        if occurrence is None or question is None:
            continue
        record = record_by_exam[exam_id]
        record_path = record_path_by_exam[exam_id]
        qindex = question_index_by_exam_id[(exam_id, qid)]
        snapshot = question_snapshot(
            question,
            exam_id=exam_id,
            question_id_value=qid,
            question_index=qindex,
            record_path=record_path,
        )
        raw_refs = raw_refs_by_key[key]
        ref = raw_refs[0]
        asset = next(
            (
                item
                for item in record.get("media_assets") or []
                if normalize_text(item.get("media_id") or item.get("storage_id")) == media_id
            ),
            {},
        )
        exam_is_1cha = exam_id.startswith("COMPREHENSIVE_2026_1CHA_")
        support = position_support(
            record,
            question_number=question.get("question_number"),
            asset=asset,
        )
        mismatch_flags: list[str] = []
        if question_ref_counts[key] > 1:
            mismatch_flags.append("duplicate_question_media_ref_collapsed")
        if support is False:
            mismatch_flags.append("media_positions_disagrees")
        linked_numbers = [
            normalize_text(value)
            for value in asset.get("linked_question_numbers") or []
        ]
        question_number_value = normalize_text(question.get("question_number"))
        if linked_numbers and question_number_value not in linked_numbers:
            mismatch_flags.append(
                "asset_linked_number_is_photo_label_not_question_fk"
                if exam_is_1cha
                else "asset_linked_question_numbers_disagrees"
            )

        method = normalize_text(
            ref.get("match_method")
            or asset.get("match_method")
            or (
                "literal_photo_reference"
                if exam_is_1cha
                else "question_media_ref"
            )
        )
        confidence_value = ref.get("match_confidence", asset.get("match_confidence"))
        try:
            confidence = float(confidence_value)
        except (TypeError, ValueError):
            confidence = 0.75 if support is True else 0.5
        confidence = round(max(0.0, min(confidence, 1.0)), 3)
        link_id = "qmedia_" + digest_text(f"{qid}\n{occurrence['occurrence_id']}")[:24]
        link = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "question_media_link",
            "link_id": link_id,
            "question_id": qid,
            "exam_id": exam_id,
            "question_number": question.get("question_number") or qindex,
            "occurrence_id": occurrence["occurrence_id"],
            "media_object_id": occurrence["media_object_id"],
            "role": "primary_stimulus" if len(((question.get("media") or {}).get("media_refs") or [])) == 1 else "supporting",
            "display_order": next(
                (
                    index + 1
                    for index, item in enumerate(
                        (question.get("media") or {}).get("media_refs") or []
                    )
                    if isinstance(item, dict)
                    and normalize_text(item.get("media_id")) == media_id
                ),
                1,
            ),
            "link_method": method,
            "match_confidence": confidence,
            "raw_ref_count": question_ref_counts[key],
            "source_position_supported": support,
            "mismatch_flags": sorted(set(mismatch_flags)),
            "confirmation_status": "candidate_unreviewed",
            "visibility": {
                "phase": "before_answer_candidate",
                "caption_visibility": "hidden_until_review",
                "is_required_to_answer": "unknown",
                "answer_leak_risk": "needs_review",
            },
            "question_evidence": {
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "source_record": snapshot["source_record"],
                "source_json_pointer": snapshot["source_json_pointer"],
            },
            "review_status": "needs_review",
        }
        links.append(link)
        link_by_occurrence[occurrence["occurrence_id"]].append(link)
        snapshot_by_link[link_id] = snapshot
        occurrence["question_link_ids"].append(link_id)

    occurrences.sort(key=lambda item: item["occurrence_id"])
    links.sort(key=lambda item: item["link_id"])

    occurrences_by_object: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        occurrence["question_link_ids"] = sorted(set(occurrence["question_link_ids"]))
        occurrences_by_object[occurrence["media_object_id"]].append(occurrence)

    objects: list[dict[str, Any]] = []
    for object_id, object_occurrences in sorted(occurrences_by_object.items()):
        first = object_occurrences[0]
        objects.append(
            {
                "schema_version": SCHEMA_VERSION,
                "record_type": "media_object",
                "media_object_id": object_id,
                "content_sha256": object_id.removeprefix("mediaobj_"),
                "file_size_bytes": first["file"]["size_bytes"],
                "suffixes": sorted(
                    {
                        occurrence["file"]["suffix"]
                        for occurrence in object_occurrences
                        if occurrence["file"]["suffix"]
                    }
                ),
                "occurrence_ids": sorted(
                    occurrence["occurrence_id"]
                    for occurrence in object_occurrences
                ),
                "canonical_occurrence_id": preferred_occurrence(object_occurrences),
                "duplicate_occurrence_count": len(object_occurrences),
                "review_status": "needs_review",
                "approved_for_question_use": False,
                "student_visible": False,
            }
        )

    worklist: list[dict[str, Any]] = []
    heme_pilot_tokens = ("HEMATOLOGY_ONCOLOGY", "혈액종양")
    for occurrence in occurrences:
        occurrence_links = link_by_occurrence.get(occurrence["occurrence_id"], [])
        question_contexts: list[dict[str, Any]] = []
        all_candidates: list[dict[str, Any]] = []
        all_unresolved: list[dict[str, Any]] = []
        review_reasons: set[str] = {
            "visual_content_not_reviewed",
            "semantic_labels_not_confirmed",
            "rights_not_reviewed",
            "deidentification_not_reviewed",
            "answer_leak_not_reviewed",
        }
        if not occurrence_links:
            review_reasons.add("unlinked_media_occurrence")
        if not occurrence["file"]["exists"]:
            review_reasons.add("media_file_missing")
        if not occurrence["file"]["web_safe_raster"]:
            review_reasons.add("web_preview_conversion_required")

        for link in occurrence_links:
            snapshot = snapshot_by_link[link["link_id"]]
            linked_asset_count = len(
                (question_by_exam_id[(link["exam_id"], link["question_id"])].get("media") or {}).get("media_refs") or []
            )
            candidates, unresolved = semantic_candidates(
                snapshot,
                concepts=concepts,
                concept_aliases=concept_aliases,
                findings=findings,
                finding_aliases=finding_aliases,
                linked_asset_count=linked_asset_count,
                explicit_modality=normalize_text(
                    occurrence.get("legacy_metadata", {}).get("modality")
                ),
            )
            question_contexts.append(
                {
                    "link": link,
                    "question": snapshot,
                    "candidate_labels": candidates,
                    "unresolved_context_tags": unresolved,
                }
            )
            all_candidates.extend(candidates)
            all_unresolved.extend(unresolved)
            review_reasons.update(link["mismatch_flags"])
            if not snapshot.get("explanation") and not snapshot.get("original_explanation"):
                review_reasons.add("question_explanation_missing")
            if len(occurrence_links) > 1:
                review_reasons.add("multiple_question_contexts")

        unique_candidates = {
            item["candidate_id"]: item
            for item in all_candidates
        }
        unresolved_keyed = {
            (
                item["source_field"],
                item["label_text"],
            ): item
            for item in all_unresolved
        }
        object_occurrence_count = len(
            occurrences_by_object[occurrence["media_object_id"]]
        )
        if object_occurrence_count > 1:
            review_reasons.add("duplicate_binary_occurrence")
        if not any(item["kind"] == "modality" for item in unique_candidates.values()):
            review_reasons.add("modality_candidate_missing")
        if not any(item["kind"] == "concept" for item in unique_candidates.values()):
            review_reasons.add("ontology_concept_candidate_missing")

        exam_id = occurrence["source"]["exam_id"]
        pilot_priority = 0 if any(token in exam_id for token in heme_pilot_tokens) else 1
        evidence_completeness = sum(
            bool(context["question"].get(field))
            for context in question_contexts
            for field in ("stem", "answer_keys", "explanation", "labels")
        )
        priority_score = (
            pilot_priority * 1000
            + (0 if occurrence_links else 500)
            + len(review_reasons) * 10
            - evidence_completeness
        )
        task = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "media_label_review_task",
            "task_id": "mreview_" + occurrence["occurrence_id"].removeprefix("mediaocc_"),
            "priority_score": priority_score,
            "pilot_group": (
                "hematology_oncology_first"
                if pilot_priority == 0
                else "general_backlog"
            ),
            "media_occurrence": occurrence,
            "duplicate_context": {
                "media_object_id": occurrence["media_object_id"],
                "occurrence_count": object_occurrence_count,
                "canonical_occurrence_id": next(
                    item["canonical_occurrence_id"]
                    for item in objects
                    if item["media_object_id"] == occurrence["media_object_id"]
                ),
            },
            "question_contexts": sorted(
                question_contexts,
                key=lambda item: item["link"]["link_id"],
            ),
            "candidate_labels": sorted(
                unique_candidates.values(),
                key=lambda item: (
                    item["kind"],
                    item.get("target_id") or "",
                    item["label_text"],
                ),
            ),
            "unresolved_context_tags": sorted(
                unresolved_keyed.values(),
                key=lambda item: (item["source_field"], item["label_text"]),
            ),
            "review_reasons": sorted(review_reasons),
            "review_checklist": [
                "Confirm that the media is linked to the correct original question.",
                "Inspect the image and separate depicted findings from question-associated diagnoses.",
                "Confirm modality, specimen/body site, and any image annotations.",
                "Verify rights and permitted educational uses.",
                "Verify deidentification or mark not_applicable with a reason.",
                "Review caption visibility and answer-leak risk.",
                "Confirm, reject, or supersede every candidate label.",
            ],
            "review": {
                "status": "needs_review",
                "reviewer": None,
                "reviewed_at": None,
                "approved_for_question_use": False,
                "student_visible": False,
            },
        }
        worklist.append(task)

    worklist.sort(
        key=lambda item: (
            item["priority_score"],
            item["task_id"],
        )
    )

    duplicate_groups = sum(
        1
        for item in objects
        if item["duplicate_occurrence_count"] > 1
    )
    duplicate_occurrences = sum(
        item["duplicate_occurrence_count"] - 1
        for item in objects
        if item["duplicate_occurrence_count"] > 1
    )
    summary = {
        "exam_packet_count": len(packets),
        "question_count": sum(
            len(record.get("questions") or [])
            for _, record in packets
        ),
        "media_object_count": len(objects),
        "media_occurrence_count": len(occurrences),
        "raw_question_media_ref_count": raw_ref_total,
        "question_media_link_count": len(links),
        "collapsed_duplicate_ref_count": raw_ref_total - len(links),
        "unlinked_media_occurrence_count": sum(
            not occurrence["question_link_ids"]
            for occurrence in occurrences
        ),
        "missing_media_file_count": sum(
            not occurrence["file"]["exists"]
            for occurrence in occurrences
        ),
        "duplicate_binary_group_count": duplicate_groups,
        "duplicate_binary_extra_occurrence_count": duplicate_occurrences,
        "candidate_label_count": sum(
            len(item["candidate_labels"])
            for item in worklist
        ),
        "auto_approved_label_count": 0,
        "approved_for_question_use_count": 0,
        "student_visible_count": 0,
        "worklist_task_count": len(worklist),
    }

    inputs = [
        {
            "path": relpath(path),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(input_files, key=lambda item: unicodedata.normalize("NFC", str(item)))
        if path.exists() and path.is_file()
    ]
    return {
        "media_objects.draft.jsonl": objects,
        "media_occurrences.draft.jsonl": occurrences,
        "question_media_links.draft.jsonl": links,
        "media_label_review_worklist.jsonl": worklist,
    }, {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "summary": summary,
        "inputs": inputs,
    }


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    text = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True)
        for row in rows
    )
    return (text + ("\n" if rows else "")).encode("utf-8")


def manifest_bytes(
    base_manifest: dict[str, Any],
    output_payloads: dict[str, bytes],
) -> bytes:
    manifest = dict(base_manifest)
    manifest["outputs"] = [
        {
            "path": name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "row_count": payload.count(b"\n"),
        }
        for name, payload in sorted(output_payloads.items())
    ]
    return (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def run(args: argparse.Namespace) -> int:
    output_rows, base_manifest = build_outputs(
        extracted_dir=args.extracted_dir,
        media_root=args.media_root,
        concept_registry_path=args.concept_registry,
        finding_registry_path=args.finding_registry,
    )
    payloads = {
        name: jsonl_bytes(output_rows[name])
        for name in OUTPUT_NAMES
    }
    payloads["manifest.json"] = manifest_bytes(base_manifest, payloads)

    if args.dry_run:
        print(
            json.dumps(
                base_manifest["summary"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.check:
        missing: list[str] = []
        changed: list[str] = []
        for name, payload in payloads.items():
            target = args.output_dir / name
            if not target.exists():
                missing.append(name)
                continue
            if target.read_bytes() != payload:
                changed.append(name)
        if missing or changed:
            print(
                json.dumps(
                    {
                        "media_labeling_ok": False,
                        "missing_outputs": missing,
                        "changed_outputs": changed,
                        "summary": base_manifest["summary"],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "media_labeling_ok": True,
                    "summary": base_manifest["summary"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (args.output_dir / name).write_bytes(payload)
    print(
        json.dumps(
            {
                "status": "written",
                "output_dir": relpath(args.output_dir),
                "summary": base_manifest["summary"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build question-grounded draft media labels and a review worklist."
    )
    parser.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)
    parser.add_argument("--media-root", type=Path, default=DEFAULT_MEDIA_ROOT)
    parser.add_argument("--concept-registry", type=Path, default=DEFAULT_CONCEPT_REGISTRY)
    parser.add_argument("--finding-registry", type=Path, default=DEFAULT_FINDING_REGISTRY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
