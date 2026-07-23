"""학생 문항은행 보강 오버레이 — 원본 불변 + 승인 release만 학생 제공.

저장 구조(원본과 보강 분리):
  data_private/student/qbank.json                    # 원본, 수정 금지
  data_private/student/qbank_enrichment.draft.json   # 생성·매칭 초안(운영/교수 검수 경로만)
  data_private/student/qbank_enrichment.releases.json# 교수 승인 release만

핵심 규칙:
- 학생 payload에는 **원본 + 승인 release overlay**만 반영한다. draft는 절대 병합하지 않는다.
- release는 built_against_sha256(원본 checksum)을 기록하며, 현재 원본과 불일치하면 fail-closed(적용 안 함).
- overlay 필드는 answer 제출 후에만 노출되는 학습 콘텐츠(해설·선지풀이·출제포인트·개념·Axis·Anki)로 제한한다.
- 모든 초안은 needs_review=true에서 시작하고, 승인 전에는 ontology_analytics_approved=false를 유지한다.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
QBANK_PATH = ROOT / "data_private" / "student" / "qbank.json"
DRAFT_PATH = ROOT / "data_private" / "student" / "qbank_enrichment.draft.json"
RELEASES_PATH = ROOT / "data_private" / "student" / "qbank_enrichment.releases.json"

# 승인 release가 원본에 덮어쓸 수 있는(=제출 후 노출되는) 화이트리스트 필드.
RELEASE_OVERLAY_FIELDS = (
    "explanation",
    "choice_explanations",   # [{n, expl, source, needs_review}]
    "points",
    "concept_id",
    "concept_label",
    "concept_registry_status",
    "target_axis_type",
    "target_axis_label",
    "target_axis_ids",
    "target_axis_resolution",
    "anki_cards",
    "connected_media",       # [{url, checksum, caption}] — 결정론 확정 매칭만
    "media_requirement_satisfied_by_text",
    "evidence",              # 공개 locator/provenance only; 원문 segment 금지
)


def _sha256(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def is_student_release_approved(entry: object) -> bool:
    """학생 노출이 가능한 실제 교수 승인 release인지 결정론적으로 판정한다.

    ``approved=true`` 하나만으로는 충분하지 않다. 시연용 승격이나 재검수 대기
    항목은 어떤 호출 경로에서도 학생 payload에 병합되지 않아야 한다.
    """
    if not isinstance(entry, dict):
        return False
    reviewer_id = str(entry.get("reviewer_id") or "").strip()
    reviewed_at = str(entry.get("reviewed_at") or "").strip()
    return bool(
        entry.get("approved") is True
        and entry.get("medical_approval") is True
        and entry.get("demo_release") is not True
        and entry.get("needs_real_faculty_review") is not True
        and reviewer_id
        and reviewed_at
        and not reviewer_id.startswith("demo:")
    )


def is_curated_demo_release_visible(entry: object) -> bool:
    """Return whether an owner-curated demo row may be shown in full-demo mode.

    This is deliberately distinct from faculty medical approval.  It is used
    for the bounded presentation set only, remains labelled as a demo release,
    and cannot be activated unless the deployment explicitly opts into the
    full-demo profile.
    """
    if not isinstance(entry, dict):
        return False
    enabled = str(os.environ.get("PACCINE_REQUIRE_FULL_DEMO") or "").strip().lower()
    reviewer_id = str(entry.get("reviewer_id") or "").strip()
    reviewed_at = str(entry.get("reviewed_at") or "").strip()
    return bool(
        enabled in {"1", "true", "yes", "on"}
        and entry.get("approved") is True
        and entry.get("medical_approval") is not True
        and entry.get("curated_demo_release") is True
        and entry.get("demo_release") is True
        and entry.get("needs_real_faculty_review") is True
        and reviewer_id.startswith("owner:")
        and reviewed_at
    )


def is_student_release_visible(entry: object) -> bool:
    return is_student_release_approved(entry) or is_curated_demo_release_visible(entry)


def releases_checksum_valid() -> bool:
    payload = _load(RELEASES_PATH)
    built_against = str(payload.get("built_against_sha256") or "")
    current = _sha256(QBANK_PATH)
    return bool(built_against and current and built_against == current)


def load_releases() -> dict[str, Any]:
    """승인 release만 로드. 원본 checksum 불일치 release는 제외(fail-closed).

    반환 스키마:
      {"built_against_sha256": str, "releases": {question_id: {field: value, "approved": true, ...}}}
    현재 원본 sha256과 다르면 빈 overlay를 반환한다(조용한 재해석 방지).
    """
    payload = _load(RELEASES_PATH)
    releases = payload.get("releases") if isinstance(payload.get("releases"), dict) else {}
    built_against = str(payload.get("built_against_sha256") or "")
    current = _sha256(QBANK_PATH)
    if not built_against or not current or built_against != current:
        # checksum 누락·원본 누락·불일치는 모두 fail-closed.
        return {}
    approved = {
        qid: entry
        for qid, entry in releases.items()
        if is_student_release_visible(entry)
    }
    return approved


def apply_release_overlay(post_answer_payload: dict, releases: dict[str, Any] | None = None) -> dict:
    """제출 후 payload에 승인 release overlay를 병합. draft는 절대 병합하지 않는다.

    - releases가 None이면 load_releases()로 로드(원본 checksum 가드 포함).
    - 화이트리스트 필드만 덮어쓴다.
    - Axis analytics는 approved release의 target_axis_type이 있을 때만 노출하고,
      ontology_analytics_approved 플래그를 payload에 명시한다.
    """
    releases = load_releases() if releases is None else releases
    qid = str(post_answer_payload.get("id") or "")
    entry = releases.get(qid)
    out = dict(post_answer_payload)
    if not is_student_release_visible(entry):
        out.setdefault("ontology_analytics_approved", False)
        return out
    for field in RELEASE_OVERLAY_FIELDS:
        if field in entry:
            out[field] = entry[field]
    out["ontology_analytics_approved"] = bool(entry.get("target_axis_type"))
    medical_approval = is_student_release_approved(entry)
    out["enrichment_release"] = {
        "approved": True,
        "medical_approval": medical_approval,
        "release_mode": "faculty_approved" if medical_approval else "owner_curated_demo",
        "needs_real_faculty_review": not medical_approval,
        "reviewer_id": entry.get("reviewer_id"),
        "reviewed_at": entry.get("reviewed_at"),
    }
    return out


def student_release_snapshot(question_id: str) -> dict[str, Any] | None:
    """제출 event에 고정할 최소 승인 snapshot. 해설 원문은 포함하지 않는다."""
    entry = load_releases().get(str(question_id or ""))
    if not is_student_release_visible(entry):
        return None
    medical_approval = is_student_release_approved(entry)
    identity = {
        "question_id": str(question_id),
        "qbank_sha256": _sha256(QBANK_PATH),
        "reviewer_id": entry.get("reviewer_id"),
        "reviewed_at": entry.get("reviewed_at"),
        "concept_id": entry.get("concept_id"),
        "target_axis_type": entry.get("target_axis_type"),
        "target_axis_ids": entry.get("target_axis_ids") or [],
        "release_mode": "faculty_approved" if medical_approval else "owner_curated_demo",
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        **identity,
        "release_version": hashlib.sha256(encoded).hexdigest(),
        "ontology_analytics_approved": bool(entry.get("target_axis_type")),
    }


def load_draft() -> dict[str, Any]:
    """초안 로드 — 운영/교수 검수 경로 전용. 학생 payload에 병합 금지."""
    payload = _load(DRAFT_PATH)
    return payload.get("drafts") if isinstance(payload.get("drafts"), dict) else {}


def build_faculty_review_queue() -> dict[str, Any]:
    """교수 검수 화면용 큐. 학생 API에서는 호출하지 않는다."""
    drafts_payload = _load(DRAFT_PATH)
    drafts = drafts_payload.get("drafts") if isinstance(drafts_payload.get("drafts"), dict) else {}
    releases_payload = _load(RELEASES_PATH)
    releases = releases_payload.get("releases") if isinstance(releases_payload.get("releases"), dict) else {}
    current_sha = _sha256(QBANK_PATH)
    draft_sha = str(drafts_payload.get("built_against_sha256") or "")
    checksum_valid = bool(current_sha and draft_sha and current_sha == draft_sha)
    items: list[dict[str, Any]] = []
    for qid, draft in drafts.items():
        if not isinstance(draft, dict):
            continue
        release = releases.get(qid) if isinstance(releases.get(qid), dict) else {}
        if is_student_release_approved(release):
            status = "faculty_approved"
        elif is_curated_demo_release_visible(release):
            status = "owner_curated_demo_release"
        elif release.get("review_status") == "rejected":
            status = "rejected"
        elif release.get("demo_release") is True:
            status = "needs_real_faculty_review"
        elif draft.get("answer_conflict"):
            status = "answer_conflict"
        else:
            status = "pending_review"
        items.append({
            "question_id": qid,
            "status": status,
            "release_eligible": draft.get("release_eligible") is True,
            "answer_conflict": bool(draft.get("answer_conflict")),
            "answer_conflict_note": draft.get("answer_conflict_note"),
            "explanation": draft.get("explanation"),
            "choice_explanations": draft.get("choice_explanations") or [],
            "points": draft.get("points") or [],
            "concept_id": draft.get("concept_id"),
            "concept_label": draft.get("concept_label"),
            "target_axis_type": draft.get("target_axis_type"),
            "target_axis_label": draft.get("target_axis_label"),
            "target_axis_ids": draft.get("target_axis_ids") or [],
            "anki_cards": draft.get("anki_cards") or [],
            "connected_media": draft.get("connected_media") or [],
            "evidence": draft.get("evidence") or [],
            "source": draft.get("source"),
            "provenance": draft.get("provenance"),
            "reviewer_id": release.get("reviewer_id"),
            "reviewed_at": release.get("reviewed_at"),
        })
    return {
        "built_against_sha256": draft_sha,
        "current_qbank_sha256": current_sha,
        "checksum_valid": checksum_valid,
        "summary": {
            "total": len(items),
            "pending_review": sum(item["status"] in {"pending_review", "needs_real_faculty_review"} for item in items),
            "answer_conflict": sum(item["status"] == "answer_conflict" for item in items),
            "faculty_approved": sum(item["status"] == "faculty_approved" for item in items),
            "rejected": sum(item["status"] == "rejected" for item in items),
        },
        "items": items,
    }


def record_faculty_review(
    question_id: str,
    *,
    decision: str,
    reviewer_id: str,
    reviewed_at: str,
    medical_approval: bool,
    review_note: str = "",
) -> dict[str, Any]:
    """교수 검수 결정을 release overlay에 원자적으로 기록한다.

    승인에는 명시적 medical_approval, 실 reviewer_id, checksum 일치,
    release_eligible=true가 모두 필요하다. 하나라도 빠지면 release하지 않는다.
    """
    decision = str(decision or "").strip().lower()
    reviewer_id = str(reviewer_id or "").strip()
    reviewed_at = str(reviewed_at or "").strip()
    qid = str(question_id or "").strip()
    if decision not in {"approve", "reject"}:
        raise ValueError("decision은 approve 또는 reject여야 합니다.")
    if not qid or not reviewer_id or reviewer_id.startswith("demo:") or not reviewed_at:
        raise ValueError("실제 reviewer_id와 reviewed_at이 필요합니다.")

    drafts_payload = _load(DRAFT_PATH)
    drafts = drafts_payload.get("drafts") if isinstance(drafts_payload.get("drafts"), dict) else {}
    draft = drafts.get(qid)
    if not isinstance(draft, dict):
        raise KeyError(qid)
    current_sha = _sha256(QBANK_PATH)
    draft_sha = str(drafts_payload.get("built_against_sha256") or "")
    if not current_sha or not draft_sha or current_sha != draft_sha:
        raise ValueError("원본 checksum과 draft 기준 checksum이 일치하지 않습니다.")
    if decision == "approve" and (medical_approval is not True or draft.get("release_eligible") is not True):
        raise ValueError("교수 medical_approval과 release_eligible=true가 모두 필요합니다.")

    payload = _load(RELEASES_PATH)
    payload["schema_version"] = "paccine.qbank_enrichment.releases.v1"
    payload["built_against_sha256"] = current_sha
    payload["notice"] = "실제 교수 medical approval을 통과한 release만 학생에게 노출합니다."
    releases = payload.setdefault("releases", {})
    if decision == "approve":
        entry = {
            "approved": True,
            "medical_approval": True,
            "demo_release": False,
            "needs_real_faculty_review": False,
            "review_status": "faculty_approved",
            "reviewer_id": reviewer_id,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
            **{
                field: draft.get(field)
                for field in RELEASE_OVERLAY_FIELDS
                if field in draft
            },
            "source": draft.get("source"),
            "provenance": draft.get("provenance"),
        }
    else:
        entry = {
            "approved": False,
            "medical_approval": False,
            "demo_release": False,
            "needs_real_faculty_review": True,
            "review_status": "rejected",
            "reviewer_id": reviewer_id,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
        }
    releases[qid] = entry

    RELEASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = RELEASES_PATH.with_name(f".{RELEASES_PATH.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, RELEASES_PATH)
    return dict(entry)


def enrichment_status() -> dict[str, int]:
    """오버레이 현황(운영자용)."""
    return {
        "draft_questions": len(load_draft()),
        "approved_releases": len(load_releases()),
        "releases_checksum_valid": releases_checksum_valid() or not RELEASES_PATH.exists(),
    }
