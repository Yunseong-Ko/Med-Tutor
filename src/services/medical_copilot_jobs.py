from __future__ import annotations

import re
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from src.services.kr_guideline_library import guideline_privacy_preflight
from src.services.medical_copilot import build_medical_copilot_response


_JOB_ID_PATTERN = re.compile(r"^mcj_[0-9TZ]+_[0-9a-f]{16}$")
_LOCK = threading.RLock()
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="paccine-medical-copilot")
_JOBS: dict[str, dict[str, Any]] = {}
_FUTURES: dict[str, Future] = {}
_JOB_TTL_SECONDS = 30 * 60
_TERMINAL = {"done", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _elapsed_seconds(job: dict[str, Any]) -> int:
    started = float(job.get("started_monotonic") or job.get("created_monotonic") or time.monotonic())
    completed = float(job.get("completed_monotonic") or time.monotonic())
    return max(0, int(completed - started))


def _privacy_text(request: dict[str, Any]) -> str:
    history = request.get("history") if isinstance(request.get("history"), list) else []
    history_text = [
        str(item.get("content") or "")
        for item in history
        if isinstance(item, dict) and str(item.get("role") or "") == "user"
    ]
    return "\n".join(
        [
            str(request.get("query") or ""),
            str(request.get("case_text") or ""),
            *history_text,
        ]
    )


def _privacy_block_result(request: dict[str, Any], privacy: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "privacy_blocked",
        "mode": str(request.get("mode") or "concept"),
        "answer_status": "blocked_direct_identifiers",
        "message": privacy.get("warning"),
        "privacy_status": privacy,
        "blocked": True,
        "reasons": ["direct_identifiers_detected"],
        "ontology": {"matches": []},
        "ontology_matches": [],
        "harrison_sources": [],
        "guidelines": [],
        "approved_guideline_claims": [],
        "answer": None,
        "safety": {"retrieval_started": False, "input_persisted": False},
    }


def _cleanup_expired_unlocked() -> None:
    now = time.monotonic()
    expired: list[str] = []
    for job_id, job in _JOBS.items():
        touched = float(job.get("updated_monotonic") or job.get("created_monotonic") or now)
        future = _FUTURES.get(job_id)
        if job.get("status") in _TERMINAL and now - touched > _JOB_TTL_SECONDS:
            expired.append(job_id)
        elif job.get("status") == "running" and future is not None and future.done():
            # The worker normally finalizes status. This only protects against a
            # future that ended before it could update the in-memory record.
            job["status"] = "failed"
            job["stage"] = "failed"
            job["error"] = "답변 작업이 비정상 종료되었습니다. 다시 시도해 주세요."
            job["completed_at"] = _now()
            job["completed_monotonic"] = now
            job["updated_monotonic"] = now
    for job_id in expired:
        _JOBS.pop(job_id, None)
        _FUTURES.pop(job_id, None)


def public_medical_copilot_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "stage": job.get("stage"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "elapsed_seconds": _elapsed_seconds(job),
        "cancel_requested": bool(job.get("cancel_requested")),
        "recoverable_after_reload": job.get("status") not in {"cancelled"},
        "server_persistence": "memory_only",
        "error": job.get("error"),
    }
    if job.get("status") == "done":
        payload["result"] = job.get("result")
    return payload


def _validated_request(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("요청 객체가 필요합니다.")
    query = str(request.get("query") or request.get("q") or "").strip()
    if not query:
        raise ValueError("query가 필요합니다.")
    history = request.get("history")
    if history is not None and not isinstance(history, list):
        raise ValueError("history는 배열이어야 합니다.")
    return {
        "query": query,
        "mode": str(request.get("mode") or "concept").strip() or "concept",
        "concept_id": str(request.get("concept_id") or "").strip(),
        "specialty": str(request.get("specialty") or "").strip(),
        "case_text": str(request.get("case_text") or ""),
        "history": history or [],
        "generate_answer": bool(request.get("generate_answer", True)),
    }


def _run_job(
    job_id: str,
    *,
    builder: Callable[..., dict[str, Any]] = build_medical_copilot_response,
) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        if job.get("cancel_requested"):
            job.update(
                status="cancelled",
                stage="cancelled",
                completed_at=_now(),
                completed_monotonic=time.monotonic(),
                updated_monotonic=time.monotonic(),
            )
            return
        request = dict(job.get("request") or {})
        job.update(
            status="running",
            stage="grounding_and_answer",
            started_at=_now(),
            started_monotonic=time.monotonic(),
            updated_monotonic=time.monotonic(),
            error=None,
        )
    try:
        result = builder(
            request["query"],
            mode=request["mode"],
            concept_id=request["concept_id"],
            specialty=request["specialty"],
            case_text=request["case_text"],
            history=request["history"],
            generate_answer=request["generate_answer"],
        )
    except Exception as exc:  # The public endpoint returns a safe failure state.
        with _LOCK:
            job = _JOBS.get(job_id)
            if not job:
                return
            job.update(
                status="cancelled" if job.get("cancel_requested") else "failed",
                stage="cancelled" if job.get("cancel_requested") else "failed",
                error=None if job.get("cancel_requested") else (str(exc).strip()[:500] or "답변 생성에 실패했습니다."),
                completed_at=_now(),
                completed_monotonic=time.monotonic(),
                updated_monotonic=time.monotonic(),
            )
        return
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        cancelled = bool(job.get("cancel_requested"))
        job.update(
            status="cancelled" if cancelled else "done",
            stage="cancelled" if cancelled else "complete",
            result=None if cancelled else result,
            request=job.get("request") if cancelled else None,
            error=None,
            completed_at=_now(),
            completed_monotonic=time.monotonic(),
            updated_monotonic=time.monotonic(),
        )


def create_medical_copilot_job(
    request: dict[str, Any],
    *,
    owner_id: str,
    auto_submit: bool = True,
    builder: Callable[..., dict[str, Any]] = build_medical_copilot_response,
) -> dict[str, Any]:
    normalized = _validated_request(request)
    privacy = guideline_privacy_preflight(_privacy_text(normalized))
    if not privacy.get("accepted"):
        return {
            "job_id": None,
            "status": "done",
            "stage": "privacy_blocked",
            "elapsed_seconds": 0,
            "cancel_requested": False,
            "recoverable_after_reload": False,
            "server_persistence": "none",
            "error": None,
            "result": _privacy_block_result(normalized, privacy),
        }
    now = time.monotonic()
    job_id = f"mcj_{_timestamp_id()}_{uuid.uuid4().hex[:16]}"
    job = {
        "schema_version": "paccine.medical_copilot_job.v1",
        "job_id": job_id,
        "owner_id": str(owner_id or "anonymous"),
        "status": "queued",
        "stage": "queued",
        "request": normalized,
        "result": None,
        "error": None,
        "cancel_requested": False,
        "created_at": _now(),
        "created_monotonic": now,
        "updated_monotonic": now,
    }
    with _LOCK:
        _cleanup_expired_unlocked()
        _JOBS[job_id] = job
        if auto_submit:
            _FUTURES[job_id] = _EXECUTOR.submit(_run_job, job_id, builder=builder)
    return public_medical_copilot_job(job)


def _owned_job_unlocked(job_id: str, owner_id: str) -> dict[str, Any]:
    if not _JOB_ID_PATTERN.fullmatch(str(job_id or "")):
        raise FileNotFoundError(job_id)
    job = _JOBS.get(job_id)
    if not job or str(job.get("owner_id") or "") != str(owner_id or ""):
        raise FileNotFoundError(job_id)
    return job


def get_medical_copilot_job(job_id: str, *, owner_id: str) -> dict[str, Any]:
    with _LOCK:
        _cleanup_expired_unlocked()
        return public_medical_copilot_job(_owned_job_unlocked(job_id, owner_id))


def cancel_medical_copilot_job(job_id: str, *, owner_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _owned_job_unlocked(job_id, owner_id)
        if job.get("status") in _TERMINAL:
            return public_medical_copilot_job(job)
        job["cancel_requested"] = True
        job["status"] = "cancel_requested"
        job["stage"] = "cancel_requested"
        job["updated_monotonic"] = time.monotonic()
        future = _FUTURES.get(job_id)
        if future is not None and future.cancel():
            job.update(
                status="cancelled",
                stage="cancelled",
                completed_at=_now(),
                completed_monotonic=time.monotonic(),
            )
        return public_medical_copilot_job(job)

def retry_medical_copilot_job(
    job_id: str,
    *,
    owner_id: str,
    builder: Callable[..., dict[str, Any]] = build_medical_copilot_response,
) -> dict[str, Any]:
    with _LOCK:
        job = _owned_job_unlocked(job_id, owner_id)
        if job.get("status") not in {"failed", "cancelled"} or not isinstance(job.get("request"), dict):
            raise ValueError("다시 시도할 수 있는 작업이 아닙니다.")
        job.update(
            status="queued",
            stage="queued",
            result=None,
            error=None,
            cancel_requested=False,
            completed_at=None,
            completed_monotonic=None,
            updated_monotonic=time.monotonic(),
        )
        _FUTURES[job_id] = _EXECUTOR.submit(_run_job, job_id, builder=builder)
        return public_medical_copilot_job(job)
