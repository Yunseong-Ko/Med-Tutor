from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.services.lecture_studio import (
    SavedUpload,
    archive_question_set,
    generate_studio_questions,
)
from src.services.kr_guideline_claim_review import list_valid_released_claims


GENERATION_JOB_DIR = Path("data_private/studio/generation_jobs")
ACTIVE_JOB_STATUSES = {"queued", "running", "retrying", "partial"}
_JOB_ID_PATTERN = re.compile(r"^gen_[0-9TZ]+_[0-9a-f]{12}$")
_LOCK = threading.RLock()
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paccine-studio-generation")
_FUTURES: dict[str, Future] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ensure_job_dir() -> None:
    GENERATION_JOB_DIR.mkdir(parents=True, exist_ok=True)


def _job_path(job_id: str) -> Path:
    value = str(job_id or "").strip()
    if not _JOB_ID_PATTERN.fullmatch(value):
        raise FileNotFoundError("invalid generation job id")
    return GENERATION_JOB_DIR / f"{value}.json"


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as temp_file:
        json.dump(payload, temp_file, ensure_ascii=False, indent=2)
        temp_name = temp_file.name
    os.replace(temp_name, path)


def _load_job_unlocked(job_id: str) -> dict[str, Any]:
    path = _job_path(job_id)
    if not path.exists():
        raise FileNotFoundError(job_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("generation job payload must be an object")
    return payload


def _save_job_unlocked(job: dict[str, Any]) -> dict[str, Any]:
    job["updated_at"] = _now()
    _write_json_atomic(_job_path(str(job.get("job_id") or "")), job)
    return job


def load_generation_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        return _load_job_unlocked(job_id)


def _fingerprint_request(request: dict[str, Any]) -> str:
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _refresh_counts(job: dict[str, Any]) -> None:
    items = job.get("items") if isinstance(job.get("items"), list) else []
    done = sum(1 for item in items if item.get("status") == "done")
    failed = sum(1 for item in items if item.get("status") == "failed")
    cancelled = sum(1 for item in items if item.get("status") == "cancelled")
    job["success_count"] = done
    job["failed_count"] = failed
    job["completed_count"] = done + failed + cancelled
    total = max(1, int(job.get("requested_count") or len(items) or 1))
    job["progress_percent"] = min(100, round((job["completed_count"] / total) * 100))


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "AI 문항 생성 시간이 초과되었습니다. 실패 문항만 다시 시도할 수 있습니다."
    text = str(exc or "문항 생성 실패").strip()
    if "timed out" in text.lower() or "time out" in text.lower():
        return "AI 문항 생성 시간이 초과되었습니다. 실패 문항만 다시 시도할 수 있습니다."
    return text[:500] or "문항 생성에 실패했습니다."


def public_generation_job(job: dict[str, Any]) -> dict[str, Any]:
    _refresh_counts(job)
    future = _FUTURES.get(str(job.get("job_id") or ""))
    worker_alive = bool(future and not future.done())
    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "set_name": (job.get("request") or {}).get("set_name"),
        "requested_count": job.get("requested_count"),
        "completed_count": job.get("completed_count"),
        "success_count": job.get("success_count"),
        "failed_count": job.get("failed_count"),
        "progress_percent": job.get("progress_percent"),
        "result_set_id": job.get("result_set_id") if job.get("success_count") else None,
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "updated_at": job.get("updated_at"),
        "cancel_requested": bool(job.get("cancel_requested")),
        "recoverable": job.get("status") == "running" and not worker_alive,
        "error": job.get("error"),
        "items": [
            {
                "index": item.get("index"),
                "intent_id": item.get("intent_id"),
                "intent_title": item.get("intent_title"),
                "status": item.get("status"),
                "attempts": item.get("attempts", 0),
                "error": item.get("error"),
                "started_at": item.get("started_at"),
                "completed_at": item.get("completed_at"),
            }
            for item in (job.get("items") or [])
        ],
    }


def get_generation_job(job_id: str) -> dict[str, Any]:
    return public_generation_job(load_generation_job(job_id))


def _active_duplicate_unlocked(fingerprint: str) -> dict[str, Any] | None:
    _ensure_job_dir()
    for path in sorted(GENERATION_JOB_DIR.glob("gen_*.json"), reverse=True):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if job.get("request_fingerprint") == fingerprint and job.get("status") in ACTIVE_JOB_STATUSES:
            return job
    return None


def create_generation_job(request: dict[str, Any], *, auto_submit: bool = True) -> tuple[dict[str, Any], bool]:
    item_intents = request.get("item_intents") if isinstance(request.get("item_intents"), list) else []
    requested_count = len(item_intents) if item_intents else max(1, min(30, int(request.get("num_questions") or 1)))
    normalized_request = dict(request)
    normalized_request["num_questions"] = requested_count
    fingerprint = _fingerprint_request(normalized_request)
    with _LOCK:
        duplicate = _active_duplicate_unlocked(fingerprint)
        if duplicate is not None:
            if auto_submit and duplicate.get("status") in {"queued", "retrying"}:
                submit_generation_job(str(duplicate["job_id"]))
            return public_generation_job(duplicate), True

        token = uuid.uuid4().hex[:12]
        job_id = f"gen_{_timestamp_id()}_{token}"
        result_set_id = f"{_timestamp_id()}_queue_{token}"
        now = _now()
        job = {
            "schema_version": "paccine.studio_generation_job.v1",
            "job_id": job_id,
            "status": "queued",
            "request_fingerprint": fingerprint,
            "request": normalized_request,
            "requested_count": requested_count,
            "completed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "progress_percent": 0,
            "result_set_id": result_set_id,
            "cancel_requested": False,
            "created_at": now,
            "updated_at": now,
            "items": [
                {
                    "index": index,
                    "intent_id": (
                        str(item_intents[index - 1].get("intent_id") or "").strip() or None
                        if item_intents and isinstance(item_intents[index - 1], dict)
                        else None
                    ),
                    "intent_title": (
                        str(item_intents[index - 1].get("intent_title") or "").strip() or None
                        if item_intents and isinstance(item_intents[index - 1], dict)
                        else None
                    ),
                    "status": "queued",
                    "attempts": 0,
                    "error": None,
                }
                for index in range(1, requested_count + 1)
            ],
        }
        _save_job_unlocked(job)
    if auto_submit:
        submit_generation_job(job_id)
    return public_generation_job(job), False


def _read_item_records(item: dict[str, Any]) -> list[dict[str, Any]]:
    path_value = str(item.get("output_path") or "").strip()
    if not path_value:
        return []
    path = Path(path_value)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _prior_problem_summaries(job: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for item in job.get("items") or []:
        if item.get("status") != "done":
            continue
        for record in _read_item_records(item)[:1]:
            problem = str(record.get("problem") or "").strip().replace("\n", " ")
            if problem:
                rows.append(problem[:240])
    return rows[-8:]


def _effective_item_request(job: dict[str, Any], item_index: int) -> dict[str, Any]:
    request = job.get("request") if isinstance(job.get("request"), dict) else {}
    base = {key: value for key, value in request.items() if key != "item_intents"}
    item_intents = request.get("item_intents") if isinstance(request.get("item_intents"), list) else []
    if 1 <= item_index <= len(item_intents) and isinstance(item_intents[item_index - 1], dict):
        base.update(item_intents[item_index - 1])
    return base


def _build_item_source(job: dict[str, Any], item_index: int) -> tuple[SavedUpload, str]:
    request = _effective_item_request(job, item_index)
    topic = str(request.get("topic") or "").strip()
    subject = str(request.get("subject") or "General").strip() or "General"
    unit = str(request.get("unit") or topic or "미분류").strip() or "미분류"
    teaching_points = str(request.get("teaching_points") or "").strip()
    textbook_reference = str(request.get("textbook_reference") or "").strip()
    concept_id = str(request.get("disease_concept_id") or "").strip()
    approved_claims: list[dict[str, Any]] = []
    if concept_id:
        try:
            approved_claims = list_valid_released_claims(
                surface="item_generation",
                concept_ids=[concept_id],
            )
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            approved_claims = []
    total = int(job.get("requested_count") or 1)
    prior = _prior_problem_summaries(job)
    lines = [
        f"# 출제 주제: {topic}",
        f"과목: {subject} / 단원: {unit}",
        f"세트 내 문항 위치: {item_index}/{total}",
        "",
    ]
    if teaching_points:
        lines += ["## 교수 강조점 / 출제 의도", teaching_points, ""]
    if textbook_reference:
        lines += ["## 참고 위치 — 원문 직접 근거 여부는 교수 검수 필요", textbook_reference, ""]
    if approved_claims:
        lines += [
            "## 교수 검토 후 문항 생성용으로 release된 국내 가이드라인 claim",
            "아래 단일 claim의 문구·대상군·임상 축을 벗어나 확대 해석하지 않는다. 생성 결과는 여전히 교수 검토용 초안이다.",
            *[
                (
                    f"- [{claim.get('claim_id')}] {claim.get('object_text')} "
                    f"| 대상: {claim.get('population')} | 축: {claim.get('clinical_axis')} "
                    f"| 출처: {claim.get('source_title')} p.{claim.get('page')}"
                )
                for claim in approved_claims
            ],
            "",
        ]
    lines += [
        "제공된 범위만 사용해 KMLE/임상종합평가형 5지선다 검토용 초안을 한 문항 작성한다.",
        "같은 세트의 다른 문항과 임상 상황, 핵심 소견 조합, 정답 표현을 중복하지 않는다.",
    ]
    if prior:
        lines += ["", "## 앞서 생성된 문두 — 아래와 겹치지 말 것", *[f"- {value}" for value in prior]]
    item_dir = GENERATION_JOB_DIR / str(job.get("job_id"))
    item_dir.mkdir(parents=True, exist_ok=True)
    path = item_dir / f"item_{item_index:02d}.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    variant = (
        f"이 문항은 전체 {total}개 중 {item_index}번이다. 앞선 문항과 환자 연령·성별·주호소·검사 배열·정답 문구를 "
        "되풀이하지 말고, 이 문항에 선택된 교수 출제 의도와 Ontology 축에 맞는 임상 판단 장면을 사용한다."
    )
    return SavedUpload(path=path, original_name=f"queue_{job.get('job_id')}_item_{item_index:02d}.txt", kind="lecture"), variant


def _generation_kwargs(request: dict[str, Any], variant: str) -> dict[str, Any]:
    return {
        "set_name": str(request.get("set_name") or "새 Ontology 문항 세트"),
        "subject": str(request.get("subject") or "General"),
        "unit": str(request.get("unit") or "미분류"),
        "num_questions": 1,
        "difficulty": str(request.get("difficulty") or "보통"),
        "question_type": str(request.get("question_type") or "clinical_case"),
        "item_type": str(request.get("item_type") or "A"),
        "reveal_specialty": bool(request.get("reveal_specialty", False)),
        "reasoning_hops": int(request.get("reasoning_hops") or 2),
        "grounding_topic": str(request.get("topic") or request.get("unit") or ""),
        "grounding_concept_id": str(request.get("disease_concept_id") or ""),
        "ontology_review_policy": str(request.get("ontology_review_policy") or "faculty_draft"),
        "target_axis_type": str(request.get("target_axis_type") or ""),
        "target_axis_ids": list(request.get("target_axis_ids") or []),
        "supporting_axis_types": list(request.get("supporting_axis_types") or []),
        "option_domain": str(request.get("option_domain") or ""),
        "selected_media_ids": list(request.get("selected_media_ids") or []),
        "generation_profile": "fast",
        "generation_variant_instruction": variant,
        "reference_policy": "local_open",
        "image_policy": "clinical_visuals" if request.get("selected_media_ids") else "none",
        "provider": str(request.get("provider") or "auto"),
        "model": str(request.get("model") or "auto"),
        "archive_result": False,
        "return_records": True,
    }


def _archive_job_unlocked(
    job: dict[str, Any],
    *,
    archive_fn: Callable[[str, dict[str, Any], list[dict[str, Any]]], Path],
) -> None:
    records: list[dict[str, Any]] = []
    item_outputs: list[str] = []
    for item in job.get("items") or []:
        item_records = _read_item_records(item)
        if not item_records:
            continue
        records.extend(item_records)
        item_outputs.append(str(item.get("output_path") or ""))
    if not records:
        return
    metadata = dict(job.get("generation_metadata") or {})
    metadata.pop("sample", None)
    metadata.pop("status", None)
    metadata.pop("set_id", None)
    metadata["set_name"] = str((job.get("request") or {}).get("set_name") or "새 Ontology 문항 세트")
    metadata["subject"] = str((job.get("request") or {}).get("subject") or "General")
    metadata["unit"] = str((job.get("request") or {}).get("unit") or "미분류")
    metadata["source_name"] = f"generation_job_{job.get('job_id')}"
    metadata["num_questions"] = len(records)
    metadata["requested_num_questions"] = int(job.get("requested_count") or len(records))
    metadata["generation_profile"] = "queued_fast"
    metadata["generation_job_id"] = job.get("job_id")
    item_intents = (job.get("request") or {}).get("item_intents")
    if isinstance(item_intents, list) and item_intents:
        metadata["faculty_item_intents"] = [
            {
                "intent_id": item.get("intent_id"),
                "intent_title": item.get("intent_title"),
                "disease_concept_id": item.get("disease_concept_id"),
                "target_axis_type": item.get("target_axis_type"),
                "faculty_question_intent": item.get("faculty_question_intent") or {},
            }
            for item in item_intents
            if isinstance(item, dict)
        ]
    faculty_assignment = (job.get("request") or {}).get("faculty_assignment")
    if isinstance(faculty_assignment, dict) and faculty_assignment:
        metadata["faculty_assignment"] = faculty_assignment
    metadata["paths"] = {
        "generation_job": str(_job_path(str(job.get("job_id") or ""))),
        "item_outputs": item_outputs,
    }
    archive_fn(str(job.get("result_set_id") or ""), metadata, records)


def run_generation_job(
    job_id: str,
    *,
    generator: Callable[..., dict[str, Any]] | None = None,
    archive_fn: Callable[[str, dict[str, Any], list[dict[str, Any]]], Path] | None = None,
) -> dict[str, Any]:
    generator = generator or generate_studio_questions
    archive_fn = archive_fn or archive_question_set
    with _LOCK:
        job = _load_job_unlocked(job_id)
        if job.get("status") not in {"queued", "retrying", "running"}:
            return public_generation_job(job)
        job["status"] = "running"
        job["started_at"] = job.get("started_at") or _now()
        job["error"] = None
        _save_job_unlocked(job)

    for item_number in range(1, int(job.get("requested_count") or 1) + 1):
        with _LOCK:
            job = _load_job_unlocked(job_id)
            if job.get("cancel_requested"):
                for item in job.get("items") or []:
                    if item.get("status") == "queued":
                        item["status"] = "cancelled"
                        item["completed_at"] = _now()
                break
            item = next((row for row in job.get("items") or [] if int(row.get("index") or 0) == item_number), None)
            if not item or item.get("status") != "queued":
                continue
            item["status"] = "running"
            item["attempts"] = int(item.get("attempts") or 0) + 1
            item["started_at"] = _now()
            item["error"] = None
            _save_job_unlocked(job)

        try:
            lecture, variant = _build_item_source(job, item_number)
            effective_request = _effective_item_request(job, item_number)
            result = generator(lecture, **_generation_kwargs(effective_request, variant))
            records = result.get("_records") if isinstance(result.get("_records"), list) else []
            if not records:
                raise RuntimeError("생성 결과에 저장할 문항이 없습니다.")
            output_path = str((result.get("paths") or {}).get("output") or "")
            if not output_path or not Path(output_path).exists():
                raise RuntimeError("생성된 문항 파일을 찾을 수 없습니다.")
            intent_id = str(effective_request.get("intent_id") or "").strip()
            faculty_intent = effective_request.get("faculty_question_intent")
            for record in records:
                if intent_id:
                    record["faculty_intent_id"] = intent_id
                if isinstance(faculty_intent, dict) and faculty_intent:
                    record["faculty_question_intent"] = faculty_intent
                record["needs_review"] = True
                record["gen_ready"] = False
            _write_json_atomic(Path(output_path), records)
            metadata = {key: value for key, value in result.items() if key not in {"_records", "sample"}}
            with _LOCK:
                job = _load_job_unlocked(job_id)
                item = next(row for row in job.get("items") or [] if int(row.get("index") or 0) == item_number)
                item["status"] = "done"
                item["output_path"] = output_path
                item["completed_at"] = _now()
                item["error"] = None
                job["generation_metadata"] = metadata
                _refresh_counts(job)
                _save_job_unlocked(job)
        except Exception as exc:
            with _LOCK:
                job = _load_job_unlocked(job_id)
                item = next(row for row in job.get("items") or [] if int(row.get("index") or 0) == item_number)
                item["status"] = "failed"
                item["error"] = _friendly_error(exc)
                item["completed_at"] = _now()
                _refresh_counts(job)
                _save_job_unlocked(job)

    with _LOCK:
        job = _load_job_unlocked(job_id)
        _refresh_counts(job)
        try:
            _archive_job_unlocked(job, archive_fn=archive_fn)
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = f"생성 문항 세트 저장 실패: {_friendly_error(exc)}"
        else:
            if job.get("cancel_requested"):
                job["status"] = "cancelled"
            elif int(job.get("failed_count") or 0) and int(job.get("success_count") or 0):
                job["status"] = "partial"
                job["error"] = "일부 문항 생성에 실패했습니다. 실패 문항만 다시 시도할 수 있습니다."
            elif int(job.get("failed_count") or 0):
                job["status"] = "failed"
                job["error"] = "모든 문항 생성에 실패했습니다. 다시 시도할 수 있습니다."
            else:
                job["status"] = "done"
                job["error"] = None
        job["completed_at"] = _now()
        _save_job_unlocked(job)
        return public_generation_job(job)


def submit_generation_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        current = _FUTURES.get(job_id)
        if current and not current.done():
            return public_generation_job(_load_job_unlocked(job_id))
        future = _EXECUTOR.submit(run_generation_job, job_id)
        _FUTURES[job_id] = future
        return public_generation_job(_load_job_unlocked(job_id))


def retry_failed_generation_job(job_id: str, *, auto_submit: bool = True) -> dict[str, Any]:
    with _LOCK:
        job = _load_job_unlocked(job_id)
        failed = [item for item in job.get("items") or [] if item.get("status") == "failed"]
        if not failed:
            return public_generation_job(job)
        for item in failed:
            item["status"] = "queued"
            item["error"] = None
            item.pop("completed_at", None)
        job["status"] = "retrying"
        job["cancel_requested"] = False
        job["completed_at"] = None
        job["error"] = None
        _refresh_counts(job)
        _save_job_unlocked(job)
    if auto_submit:
        return submit_generation_job(job_id)
    return public_generation_job(job)


def cancel_generation_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _load_job_unlocked(job_id)
        if job.get("status") in {"done", "failed", "partial", "cancelled"}:
            return public_generation_job(job)
        job["cancel_requested"] = True
        _save_job_unlocked(job)
        return public_generation_job(job)


def resume_generation_job(job_id: str, *, auto_submit: bool = True) -> dict[str, Any]:
    with _LOCK:
        job = _load_job_unlocked(job_id)
        future = _FUTURES.get(job_id)
        if future and not future.done():
            return public_generation_job(job)
        if job.get("status") != "running":
            return public_generation_job(job)
        for item in job.get("items") or []:
            if item.get("status") == "running":
                item["status"] = "queued"
                item["error"] = "서버 재시작 후 작업을 재개합니다."
        job["status"] = "queued"
        _refresh_counts(job)
        _save_job_unlocked(job)
    if auto_submit:
        return submit_generation_job(job_id)
    return public_generation_job(job)
