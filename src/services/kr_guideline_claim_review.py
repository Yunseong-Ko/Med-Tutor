from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
WORKLIST_RELATIVE_PATH = Path("data_private/kr_guidelines/claim_extraction_worklist.json")
SOURCE_REGISTRY_RELATIVE_PATH = Path("data_private/kr_guidelines/verified_latest_registry.json")
REVIEW_RECORDS_RELATIVE_PATH = Path("data_private/kr_guidelines/claim_review_records.json")
RELEASES_RELATIVE_PATH = Path("data_private/kr_guidelines/claim_releases.json")
RELEASE_SCHEMA_RELATIVE_PATH = Path("schemas/kr_guideline_claim_release.schema.json")
LOCK_RELATIVE_PATH = Path("data_private/kr_guidelines/.claim_review.lock")

CURRENT_SOURCE_STATUSES = {
    "verified_latest_on_official_source",
    "living_guideline_current",
}
ALLOWED_RELATIONS = {
    "recommends",
    "suggests",
    "requires",
    "permits",
    "contraindicates",
    "does_not_recommend",
    "defines",
}
ALLOWED_SURFACES = {
    "library_summary",
    "study_qa",
    "case_presentation",
    "anki",
    "item_generation",
}


def _root(root: Path | None) -> Path:
    return (root or DEFAULT_ROOT).resolve()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        if default is not None:
            return default
        raise FileNotFoundError(f"가이드라인 claim 자산을 찾을 수 없습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _claim_hash_payload(claim: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "source_id",
        "source_file_sha256",
        "page",
        "verbatim_locator_hash",
        "clinical_axis",
        "subject_concept_id",
        "relation",
        "object_text",
        "polarity",
        "population",
        "recommendation_strength",
        "evidence_grade",
        "effective_version",
    )
    return {key: claim.get(key) for key in keys}


def claim_content_sha256(claim: dict[str, Any]) -> str:
    return _sha256_text(
        json.dumps(_claim_hash_payload(claim), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _empty_review_records() -> dict[str, Any]:
    return {
        "schema_version": "kr_guideline_claim_review_records.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "human_medical_review_required": True,
            "automatic_approval": False,
            "verbatim_text_stored": False,
        },
        "claims": [],
    }


def _review_records(root: Path) -> dict[str, Any]:
    payload = _read_json(root / REVIEW_RECORDS_RELATIVE_PATH, _empty_review_records())
    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        raise ValueError("가이드라인 claim 검토 기록 형식이 올바르지 않습니다.")
    return payload


def _releases(root: Path) -> dict[str, Any]:
    payload = _read_json(root / RELEASES_RELATIVE_PATH)
    if not isinstance(payload, dict) or not isinstance(payload.get("releases"), list):
        raise ValueError("가이드라인 claim release 형식이 올바르지 않습니다.")
    return payload


def _worklist(root: Path) -> dict[str, Any]:
    payload = _read_json(root / WORKLIST_RELATIVE_PATH)
    if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
        raise ValueError("가이드라인 claim 작업 목록 형식이 올바르지 않습니다.")
    return payload


def _source_registry(root: Path) -> dict[str, Any]:
    payload = _read_json(root / SOURCE_REGISTRY_RELATIVE_PATH)
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("가이드라인 source registry 형식이 올바르지 않습니다.")
    return payload


def _validate_release_registry(payload: dict[str, Any], root: Path) -> None:
    schema = _read_json(root / RELEASE_SCHEMA_RELATIVE_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        detail = "; ".join(f"{list(error.path)}: {error.message}" for error in errors[:8])
        raise ValueError(f"claim release 검증 실패: {detail}")


def _task_by_id(root: Path, task_id: str) -> dict[str, Any]:
    task = next(
        (row for row in _worklist(root).get("tasks") or [] if row.get("task_id") == task_id),
        None,
    )
    if not isinstance(task, dict):
        raise ValueError("claim 추출 작업을 찾을 수 없습니다.")
    return task


def _source_by_id(root: Path, source_id: str) -> dict[str, Any]:
    source = next(
        (row for row in _source_registry(root).get("sources") or [] if row.get("source_id") == source_id),
        None,
    )
    if not isinstance(source, dict):
        raise ValueError("가이드라인 source를 찾을 수 없습니다.")
    return source


def list_claim_review_tasks(
    *,
    query: str = "",
    priority: str = "",
    readiness: str = "",
    clinical_axis: str = "",
    offset: int = 0,
    limit: int = 30,
    root: Path | None = None,
) -> dict[str, Any]:
    resolved_root = _root(root)
    worklist = _worklist(resolved_root)
    records = _review_records(resolved_root)
    releases = _releases(resolved_root)
    drafts_by_task: dict[str, list[dict[str, Any]]] = {}
    for claim in records.get("claims") or []:
        drafts_by_task.setdefault(str(claim.get("task_id") or ""), []).append(claim)
    needle = _clean(query).lower()
    rows = []
    for task in worklist.get("tasks") or []:
        if priority and task.get("priority") != priority:
            continue
        if readiness and task.get("readiness") != readiness:
            continue
        if clinical_axis and task.get("clinical_axis") != clinical_axis:
            continue
        haystack = " ".join(
            [
                str(task.get("source_title") or ""),
                str(task.get("source_id") or ""),
                " ".join(task.get("concept_candidates") or []),
            ]
        ).lower()
        if needle and needle not in haystack:
            continue
        task_claims = drafts_by_task.get(str(task.get("task_id") or ""), [])
        rows.append(
            {
                "task_id": task.get("task_id"),
                "source_id": task.get("source_id"),
                "source_title": task.get("source_title"),
                "priority": task.get("priority"),
                "latest_status": task.get("latest_status"),
                "clinical_axis": task.get("clinical_axis"),
                "readiness": task.get("readiness"),
                "concept_candidates": task.get("concept_candidates") or [],
                "specialty_agent_ids": task.get("specialty_agent_ids") or [],
                "source_documents": [
                    {
                        "attachment_id": item.get("attachment_id"),
                        "role": item.get("role"),
                        "page_count": item.get("pdf_pages"),
                    }
                    for item in task.get("source_files") or []
                ],
                "draft_count": len(task_claims),
                "released_count": sum(claim.get("status") == "released" for claim in task_claims),
                "review_status": (
                    "released"
                    if any(claim.get("status") == "released" for claim in task_claims)
                    else "drafted"
                    if task_claims
                    else "not_started"
                ),
            }
        )
    rows.sort(
        key=lambda item: (
            {"P0": 0, "P1": 1, "P2": 2}.get(str(item.get("priority")), 3),
            0 if item.get("readiness") == "ready_for_candidate_extraction" else 1,
            str(item.get("source_title") or ""),
            str(item.get("clinical_axis") or ""),
        )
    )
    safe_offset = max(0, int(offset or 0))
    safe_limit = max(1, min(100, int(limit or 30)))
    selected = rows[safe_offset : safe_offset + safe_limit]
    return {
        "status": "ready",
        "summary": {
            "tasks": len(worklist.get("tasks") or []),
            "matching_tasks": len(rows),
            "claim_drafts": len(records.get("claims") or []),
            "released_claims": sum(item.get("status") == "released" for item in releases.get("releases") or []),
            "automatic_medical_approvals": 0,
        },
        "filters": {
            "query": query or None,
            "priority": priority or None,
            "readiness": readiness or None,
            "clinical_axis": clinical_axis or None,
        },
        "offset": safe_offset,
        "limit": safe_limit,
        "total": len(rows),
        "items": selected,
        "safety": {
            "candidate_extraction_is_medical_approval": False,
            "human_attestation_required_for_release": True,
            "default_deny": True,
        },
    }


def list_claim_drafts(*, task_id: str = "", root: Path | None = None) -> list[dict[str, Any]]:
    records = _review_records(_root(root))
    return [
        dict(claim)
        for claim in records.get("claims") or []
        if not task_id or claim.get("task_id") == task_id
    ]


def get_claim_source_document(
    task_id: str,
    attachment_id: str,
    *,
    root: Path | None = None,
) -> Path:
    resolved_root = _root(root)
    task = _task_by_id(resolved_root, _clean(task_id))
    source_file = next(
        (
            item
            for item in task.get("source_files") or []
            if item.get("attachment_id") == _clean(attachment_id)
        ),
        None,
    )
    if not isinstance(source_file, dict):
        raise ValueError("선택한 원문 파일을 찾을 수 없습니다.")
    return _resolved_source_path(resolved_root, source_file)


def _resolved_source_path(resolved_root: Path, source_file: dict[str, Any]) -> Path:
    relative_path = Path(str(source_file.get("relative_path") or ""))
    if relative_path.is_absolute():
        raise ValueError("원문 파일 경로가 올바르지 않습니다.")
    target = (resolved_root / relative_path).resolve()
    allowed_root = (resolved_root / "data_private" / "kr_guidelines").resolve()
    if target != allowed_root and allowed_root not in target.parents:
        raise ValueError("허용되지 않은 원문 파일 경로입니다.")
    if not target.is_file():
        raise FileNotFoundError(f"가이드라인 원문 파일을 찾을 수 없습니다: {target}")
    return target


def create_claim_draft(payload: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    resolved_root = _root(root)
    task_id = _clean(payload.get("task_id"))
    task = _task_by_id(resolved_root, task_id)
    if task.get("readiness") == "source_file_unavailable":
        raise ValueError("원문 파일이 없어 claim 후보를 만들 수 없습니다.")
    files = task.get("source_files") or []
    if not files:
        raise ValueError("검토할 원문 파일이 없습니다.")
    attachment_id = _clean(payload.get("attachment_id"))
    source_file = next(
        (item for item in files if item.get("attachment_id") == attachment_id),
        files[0] if not attachment_id else None,
    )
    if not isinstance(source_file, dict):
        raise ValueError("선택한 원문 파일을 찾을 수 없습니다.")
    source_path = _resolved_source_path(resolved_root, source_file)
    actual_source_hash = _sha256_file(source_path)
    if actual_source_hash != source_file.get("sha256"):
        raise ValueError("원문 파일 hash가 작업 목록과 달라 최신 상태를 다시 확인해야 합니다.")
    page = int(payload.get("page") or 0)
    if page < 1 or (source_file.get("pdf_pages") and page > int(source_file["pdf_pages"])):
        raise ValueError("page가 원문 범위를 벗어났습니다.")
    subject_concept_id = _clean(payload.get("subject_concept_id"))
    if not subject_concept_id:
        raise ValueError("subject_concept_id가 필요합니다.")
    concept_candidates = set(task.get("concept_candidates") or [])
    if concept_candidates and subject_concept_id not in concept_candidates and not _clean(payload.get("concept_override_reason")):
        raise ValueError("작업 후보 밖의 concept를 사용하려면 concept_override_reason이 필요합니다.")
    relation = _clean(payload.get("relation"))
    if relation not in ALLOWED_RELATIONS:
        raise ValueError("지원하지 않는 relation입니다.")
    object_text = _clean(payload.get("object_text"))
    population = _clean(payload.get("population"))
    locator_note = _clean(payload.get("locator_note"))
    if not 20 <= len(object_text) <= 2000:
        raise ValueError("object_text는 20~2000자여야 합니다.")
    if not 3 <= len(population) <= 1000:
        raise ValueError("population은 3~1000자여야 합니다.")
    if not locator_note:
        raise ValueError("권고 번호·표·문단 위치를 나타내는 locator_note가 필요합니다.")
    effective_version = _clean(payload.get("effective_version"))
    if not effective_version:
        raise ValueError("effective_version이 필요합니다.")
    created_at = datetime.now(timezone.utc).isoformat()
    draft = {
        "task_id": task_id,
        "source_id": task.get("source_id"),
        "source_title": task.get("source_title"),
        "source_file_sha256": source_file.get("sha256"),
        "attachment_id": source_file.get("attachment_id"),
        "page": page,
        "locator_note": locator_note,
        "verbatim_locator_hash": _sha256_text(locator_note),
        "clinical_axis": task.get("clinical_axis"),
        "subject_concept_id": subject_concept_id,
        "concept_override_reason": _clean(payload.get("concept_override_reason")) or None,
        "relation": relation,
        "object_text": object_text,
        "polarity": _clean(payload.get("polarity")) or "positive",
        "population": population,
        "recommendation_strength": _clean(payload.get("recommendation_strength")) or "not_reported",
        "evidence_grade": _clean(payload.get("evidence_grade")) or "not_reported",
        "effective_version": effective_version,
        "review_notes": _clean(payload.get("review_notes")) or None,
        "created_by": _clean(payload.get("created_by")) or "local_reviewer",
        "created_at": created_at,
        "updated_at": created_at,
        "status": "draft",
        "needs_review": True,
        "medical_approval": False,
        "student_visible": False,
        "decision": None,
    }
    draft["claim_content_sha256"] = claim_content_sha256(draft)
    draft["claim_id"] = f"kr-claim:{draft['claim_content_sha256'][:24]}"
    lock_path = resolved_root / LOCK_RELATIVE_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        records = _review_records(resolved_root)
        existing = next(
            (item for item in records.get("claims") or [] if item.get("claim_id") == draft["claim_id"]),
            None,
        )
        if existing:
            return dict(existing)
        records["claims"].append(draft)
        records["generated_at"] = created_at
        _write_json_atomic(resolved_root / REVIEW_RECORDS_RELATIVE_PATH, records)
    return draft


def decide_claim(
    claim_id: str,
    payload: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    resolved_root = _root(root)
    action = _clean(payload.get("action")).lower()
    if action not in {"release", "reject", "revoke"}:
        raise ValueError("action은 release, reject, revoke 중 하나여야 합니다.")
    reviewer = _clean(payload.get("reviewer"))
    if not reviewer:
        raise ValueError("실명 또는 검토자 식별값이 필요합니다.")
    if payload.get("attestation") is not True:
        raise ValueError("원문·대상군·예외·근거수준을 확인했다는 attestation이 필요합니다.")
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    lock_path = resolved_root / LOCK_RELATIVE_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        records = _review_records(resolved_root)
        releases = _releases(resolved_root)
        claim = next(
            (item for item in records.get("claims") or [] if item.get("claim_id") == claim_id),
            None,
        )
        if not isinstance(claim, dict):
            raise ValueError("claim 후보를 찾을 수 없습니다.")
        task = _task_by_id(resolved_root, str(claim.get("task_id") or ""))
        source = _source_by_id(resolved_root, str(claim.get("source_id") or ""))
        release = next(
            (item for item in releases.get("releases") or [] if item.get("claim_id") == claim_id),
            None,
        )
        if action == "release":
            if task.get("readiness") != "ready_for_candidate_extraction":
                raise ValueError("최신성과 원문 준비가 확인된 작업만 release할 수 있습니다.")
            if source.get("latest_status") not in CURRENT_SOURCE_STATUSES:
                raise ValueError("현재판 확인이 끝난 source만 release할 수 있습니다.")
            surfaces = list(dict.fromkeys(_clean(item) for item in payload.get("surfaces") or [] if _clean(item)))
            if not surfaces or not set(surfaces).issubset(ALLOWED_SURFACES):
                raise ValueError("하나 이상의 유효한 release surface가 필요합니다.")
            review_due_at = _clean(payload.get("review_due_at"))
            try:
                due = datetime.fromisoformat(review_due_at.replace("Z", "+00:00"))
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
            except ValueError as exc:
                raise ValueError("review_due_at은 timezone이 포함된 ISO datetime이어야 합니다.") from exc
            if due <= now:
                raise ValueError("review_due_at은 현재보다 이후여야 합니다.")
            current_hash = claim_content_sha256(claim)
            if current_hash != claim.get("claim_content_sha256"):
                raise ValueError("claim 내용 hash가 바뀌어 다시 검토해야 합니다.")
            source_file = next(
                (
                    item
                    for item in task.get("source_files") or []
                    if item.get("attachment_id") == claim.get("attachment_id")
                ),
                None,
            )
            if not isinstance(source_file, dict):
                raise ValueError("검토한 원문 파일을 작업 목록에서 찾을 수 없습니다.")
            actual_source_hash = _sha256_file(_resolved_source_path(resolved_root, source_file))
            if actual_source_hash != claim.get("source_file_sha256"):
                raise ValueError("검토 이후 원문 파일 hash가 바뀌어 다시 검토해야 합니다.")
            release_record = {
                "release_id": f"kr-release:{claim_id.split(':')[-1]}",
                "claim_id": claim_id,
                "status": "released",
                "surfaces": surfaces,
                "claim_content_sha256": current_hash,
                "source_snapshot_sha256": claim.get("source_file_sha256"),
                "concept_ids": [claim.get("subject_concept_id")],
                "jurisdiction": "KR",
                "approved_by": reviewer,
                "reviewed_at": now_text,
                "review_due_at": due.astimezone(timezone.utc).isoformat(),
                "valid_from": now_text,
                "revoked_at": None,
                "revocation_reason": None,
            }
            if release:
                releases["releases"][releases["releases"].index(release)] = release_record
            else:
                releases["releases"].append(release_record)
            release = release_record
            claim.update(
                {
                    "status": "released",
                    "needs_review": False,
                    "medical_approval": True,
                    "student_visible": bool(set(surfaces).intersection({"study_qa", "case_presentation", "anki"})),
                    "updated_at": now_text,
                    "decision": {
                        "action": "release",
                        "reviewer": reviewer,
                        "reviewed_at": now_text,
                        "surfaces": surfaces,
                    },
                }
            )
        elif action == "reject":
            if release and release.get("status") == "released":
                raise ValueError("현재 release된 claim은 reject 대신 revoke해야 합니다.")
            reason = _clean(payload.get("reason"))
            if not reason:
                raise ValueError("reject reason이 필요합니다.")
            claim.update(
                {
                    "status": "rejected",
                    "needs_review": False,
                    "medical_approval": False,
                    "student_visible": False,
                    "updated_at": now_text,
                    "decision": {
                        "action": "reject",
                        "reviewer": reviewer,
                        "reviewed_at": now_text,
                        "reason": reason,
                    },
                }
            )
        else:
            reason = _clean(payload.get("reason"))
            if not reason:
                raise ValueError("revocation reason이 필요합니다.")
            if not release or release.get("status") != "released":
                raise ValueError("현재 released 상태인 claim만 revoke할 수 있습니다.")
            release.update(
                {
                    "status": "revoked",
                    "revoked_at": now_text,
                    "revocation_reason": reason,
                }
            )
            claim.update(
                {
                    "status": "revoked",
                    "needs_review": True,
                    "medical_approval": False,
                    "student_visible": False,
                    "updated_at": now_text,
                    "decision": {
                        "action": "revoke",
                        "reviewer": reviewer,
                        "reviewed_at": now_text,
                        "reason": reason,
                    },
                }
            )
        records["generated_at"] = now_text
        releases["generated_at"] = now_text
        _validate_release_registry(releases, resolved_root)
        _write_json_atomic(resolved_root / REVIEW_RECORDS_RELATIVE_PATH, records)
        _write_json_atomic(resolved_root / RELEASES_RELATIVE_PATH, releases)
    return {"claim": dict(claim), "release": dict(release) if release else None}


def list_valid_released_claims(
    *,
    surface: str,
    concept_ids: list[str] | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    if surface not in ALLOWED_SURFACES:
        raise ValueError("지원하지 않는 release surface입니다.")
    resolved_root = _root(root)
    records = _review_records(resolved_root)
    releases = _releases(resolved_root)
    sources = {item.get("source_id"): item for item in _source_registry(resolved_root).get("sources") or []}
    tasks = {item.get("task_id"): item for item in _worklist(resolved_root).get("tasks") or []}
    claims = {item.get("claim_id"): item for item in records.get("claims") or []}
    wanted = set(concept_ids or [])
    now = datetime.now(timezone.utc)
    valid: list[dict[str, Any]] = []
    for release in releases.get("releases") or []:
        if release.get("status") != "released" or surface not in (release.get("surfaces") or []):
            continue
        claim = claims.get(release.get("claim_id"))
        if not isinstance(claim, dict) or claim.get("status") != "released" or not claim.get("medical_approval"):
            continue
        if claim_content_sha256(claim) != release.get("claim_content_sha256"):
            continue
        if claim.get("source_file_sha256") != release.get("source_snapshot_sha256"):
            continue
        task = tasks.get(claim.get("task_id")) or {}
        source_file = next(
            (
                item
                for item in task.get("source_files") or []
                if item.get("attachment_id") == claim.get("attachment_id")
            ),
            None,
        )
        if not isinstance(source_file, dict):
            continue
        try:
            if _sha256_file(_resolved_source_path(resolved_root, source_file)) != release.get("source_snapshot_sha256"):
                continue
        except (FileNotFoundError, ValueError, OSError):
            continue
        try:
            due = datetime.fromisoformat(str(release.get("review_due_at") or "").replace("Z", "+00:00"))
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if due <= now:
            continue
        release_concepts = set(release.get("concept_ids") or [])
        if wanted and not wanted.intersection(release_concepts):
            continue
        source = sources.get(claim.get("source_id")) or {}
        if source.get("latest_status") not in CURRENT_SOURCE_STATUSES:
            continue
        valid.append(
            {
                "claim_id": claim.get("claim_id"),
                "source_id": claim.get("source_id"),
                "source_title": claim.get("source_title"),
                "official_landing_url": source.get("official_landing_url"),
                "clinical_axis": claim.get("clinical_axis"),
                "subject_concept_id": claim.get("subject_concept_id"),
                "relation": claim.get("relation"),
                "object_text": claim.get("object_text"),
                "polarity": claim.get("polarity"),
                "population": claim.get("population"),
                "recommendation_strength": claim.get("recommendation_strength"),
                "evidence_grade": claim.get("evidence_grade"),
                "effective_version": claim.get("effective_version"),
                "page": claim.get("page"),
                "release": {
                    "release_id": release.get("release_id"),
                    "surfaces": release.get("surfaces") or [],
                    "reviewed_at": release.get("reviewed_at"),
                    "review_due_at": release.get("review_due_at"),
                },
            }
        )
    valid.sort(key=lambda item: (str(item.get("subject_concept_id")), str(item.get("clinical_axis")), str(item.get("claim_id"))))
    return valid
