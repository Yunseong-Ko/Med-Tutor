from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_RELATIVE_PATH = Path("data_private/kr_guidelines/verified_latest_registry.json")
OVERLAY_RELATIVE_PATH = Path("data_private/kr_guidelines/ontology_overlay.json")
CONCEPT_REGISTRY_RELATIVE_PATH = Path("data_private/concept_registry.json")

CURRENT_SOURCE_STATUSES = {"verified_latest_on_official_source"}
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+/#.\-]*|[가-힣]{2,}")
SPACE_RE = re.compile(r"\s+")
STOPWORDS = {
    "about",
    "case",
    "guideline",
    "patient",
    "study",
    "the",
    "with",
    "가이드라인",
    "대해서",
    "문헌",
    "어떻게",
    "정리",
    "지침",
    "환자",
}

DIRECT_IDENTIFIER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("resident_registration_number", re.compile(r"(?<!\d)\d{6}\s*-?\s*[1-4]\d{6}(?!\d)")),
    ("phone_number", re.compile(r"(?<!\d)01[016789]\s*-?\s*\d{3,4}\s*-?\s*\d{4}(?!\d)")),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    (
        "patient_or_registration_number",
        re.compile(r"(?:환자\s*번호|등록\s*번호|병록\s*번호|MRN)\s*[:：]?\s*[A-Z0-9-]{4,}", re.IGNORECASE),
    ),
    (
        "explicit_name_field",
        re.compile(r"(?:환자명|성명|이름)\s*[:：]\s*[가-힣A-Za-z]{2,20}"),
    ),
)


def _root(root: Path | None) -> Path:
    return (root or DEFAULT_ROOT).resolve()


@lru_cache(maxsize=32)
def _read_json_cached(path_text: str, mtime_ns: int, size: int) -> Any:
    return json.loads(Path(path_text).read_text(encoding="utf-8"))


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"국내 진료지침 자산을 찾을 수 없습니다: {path}")
    stat = path.stat()
    return _read_json_cached(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def _clean_text(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "").replace("\u00a0", " ")).strip()


def _tokens(value: Any) -> list[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(_clean_text(value))]
    return [token for token in tokens if token not in STOPWORDS and len(token) >= 2]


def _normalized_values(value: Any) -> list[str]:
    if isinstance(value, str):
        values = re.split(r"[,;|\n]", value)
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    return list(dict.fromkeys(_clean_text(item) for item in values if _clean_text(item)))


def guideline_privacy_preflight(case_text: Any) -> dict[str, Any]:
    """Fail before retrieval when likely direct patient identifiers are present.

    Only identifier categories are returned. The input text is never included in the
    result and this service does not write requests to disk.
    """

    text = str(case_text or "")
    flags = [
        identifier_type
        for identifier_type, pattern in DIRECT_IDENTIFIER_PATTERNS
        if pattern.search(text)
    ]
    flags = list(dict.fromkeys(flags))
    if flags:
        return {
            "status": "rejected_direct_identifiers",
            "accepted": False,
            "flags": flags,
            "stateless": True,
            "persisted": False,
            "warning": (
                "환자 직접 식별정보로 보이는 내용이 있습니다. 이름·환자번호·주민등록번호·전화번호·"
                "이메일을 제거한 뒤 다시 입력하세요."
            ),
        }
    return {
        "status": "clear" if text.strip() else "not_provided",
        "accepted": True,
        "flags": [],
        "stateless": True,
        "persisted": False,
        "warning": "직접 식별정보를 입력하지 마세요." if text.strip() else None,
    }


def _source_registry(root: Path | None = None) -> dict[str, Any]:
    payload = _read_json(_root(root) / REGISTRY_RELATIVE_PATH)
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("국내 진료지침 레지스트리 형식이 올바르지 않습니다.")
    return payload


def _ontology_overlay(root: Path | None = None) -> dict[str, Any]:
    path = _root(root) / OVERLAY_RELATIVE_PATH
    if not path.exists():
        return {}
    payload = _read_json(path)
    return payload if isinstance(payload, dict) else {}


def _concept_registry(root: Path | None = None) -> dict[str, Any]:
    path = _root(root) / CONCEPT_REGISTRY_RELATIVE_PATH
    if not path.exists():
        return {}
    payload = _read_json(path)
    concepts = payload.get("concepts") if isinstance(payload, dict) else None
    return concepts if isinstance(concepts, dict) else {}


def _safe_local_path(root: Path, relative_path: Any) -> Path | None:
    relative = Path(str(relative_path or ""))
    if not relative_path or relative.is_absolute():
        return None
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate


def _attachment_record(attachment: dict[str, Any]) -> dict[str, Any]:
    expected_bytes = attachment.get("bytes")
    return {
        "attachment_id": attachment.get("attachment_id"),
        "role": attachment.get("role"),
        "filename": attachment.get("filename"),
        "file_type": attachment.get("file_type"),
        "download_status": attachment.get("download_status"),
        "bytes": expected_bytes,
        "sha256": attachment.get("sha256"),
        "pdf_pages": attachment.get("pdf_pages"),
        "pdf_text_chars": attachment.get("pdf_text_chars"),
    }


def _source_record(source: dict[str, Any], *, score: float = 0.0) -> dict[str, Any]:
    version = source.get("version") if isinstance(source.get("version"), dict) else {}
    latest_status = str(source.get("latest_status") or "unknown")
    return {
        "source_id": source.get("source_id"),
        "title": source.get("title"),
        "issuing_body": source.get("issuing_body"),
        "jurisdiction": source.get("jurisdiction"),
        "document_type": source.get("document_type"),
        "publication_year": source.get("publication_year"),
        "priority": source.get("priority"),
        "specialties": list(source.get("specialties") or []),
        "clinical_axes": list(source.get("clinical_axes") or []),
        "official_landing_url": source.get("official_landing_url"),
        "catalog_provider": source.get("catalog_provider"),
        "catalog_record_id": source.get("catalog_record_id"),
        "version": {
            "display_version": version.get("display_version"),
            "printed_publication_year": version.get("printed_publication_year"),
            "operational_release": version.get("operational_release"),
            "last_corrected_at": version.get("last_corrected_at"),
            "version_conflict": bool(version.get("version_conflict")),
            "currency_review_due": bool(version.get("currency_review_due")),
        },
        "currentness": {
            "status": latest_status,
            "verified_current": latest_status in CURRENT_SOURCE_STATUSES,
            "checked_at": source.get("latest_checked_at"),
        },
        "attachments": [
            _attachment_record(attachment)
            for attachment in source.get("attachments") or []
            if isinstance(attachment, dict)
        ],
        "retrieval_score": round(float(score), 4),
        "release": {
            "catalog_preview": True,
            "medical_approval": bool(source.get("medical_approval")),
            "student_visible_source": bool(source.get("student_visible")),
            "student_claim_release_available": False,
            "use_scope": "bibliographic_discovery_and_review_only",
        },
        "needs_review": bool(source.get("needs_review", True)),
    }


def sanitize_student_guideline_source(source: dict[str, Any]) -> dict[str, Any]:
    """Remove local mirror and internal review metadata from a source record."""

    attachments = [
        {
            "role": attachment.get("role"),
            "file_type": attachment.get("file_type"),
            "page_count": attachment.get("pdf_pages"),
        }
        for attachment in source.get("attachments") or []
        if isinstance(attachment, dict)
    ]
    version = source.get("version") if isinstance(source.get("version"), dict) else {}
    currentness = (
        source.get("currentness") if isinstance(source.get("currentness"), dict) else {}
    )
    release = source.get("release") if isinstance(source.get("release"), dict) else {}
    return {
        "source_id": source.get("source_id"),
        "title": source.get("title"),
        "issuing_body": source.get("issuing_body"),
        "jurisdiction": source.get("jurisdiction"),
        "document_type": source.get("document_type"),
        "publication_year": source.get("publication_year"),
        "priority": source.get("priority"),
        "specialties": list(source.get("specialties") or []),
        "clinical_axes": list(source.get("clinical_axes") or []),
        "official_landing_url": source.get("official_landing_url"),
        "catalog_provider": source.get("catalog_provider"),
        "catalog_record_id": source.get("catalog_record_id"),
        "version": {
            "display_version": version.get("display_version"),
            "printed_publication_year": version.get("printed_publication_year"),
            "operational_release": version.get("operational_release"),
            "last_corrected_at": version.get("last_corrected_at"),
            "version_conflict": bool(version.get("version_conflict")),
            "currency_review_due": bool(version.get("currency_review_due")),
        },
        "currentness": {
            "status": currentness.get("status"),
            "verified_current": bool(currentness.get("verified_current")),
            "checked_at": currentness.get("checked_at"),
        },
        "documents": attachments,
        "retrieval_score": source.get("retrieval_score"),
        "release": {
            "catalog_preview": True,
            "medical_approval": bool(release.get("medical_approval")),
            "student_visible_source": bool(release.get("student_visible_source")),
            "student_claim_release_available": False,
            "use_scope": "bibliographic_discovery_and_review_only",
        },
        "needs_review": bool(source.get("needs_review", True)),
    }


def _source_search_score(source: dict[str, Any], query: str, terms: list[str]) -> float:
    if not query:
        priority_score = {"P0": 3.0, "P1": 2.0, "P2": 1.0}.get(source.get("priority"), 0.0)
        return priority_score + (1.0 if source.get("latest_status") in CURRENT_SOURCE_STATUSES else 0.0)
    title = _clean_text(source.get("title")).lower()
    issuing_body = _clean_text(source.get("issuing_body")).lower()
    development = source.get("development") if isinstance(source.get("development"), dict) else {}
    secondary = " ".join(
        [
            _clean_text(source.get("latest_evidence")),
            _clean_text(development.get("keywords")),
            " ".join(str(item) for item in source.get("specialties") or []),
            " ".join(str(item) for item in source.get("clinical_axes") or []),
        ]
    ).lower()
    query_lower = query.lower()
    score = 0.0
    if len(query_lower) >= 2 and query_lower in title:
        score += 12.0
    for term in terms:
        if term in title:
            score += 4.0
        if term in issuing_body:
            score += 1.5
        if term in secondary:
            score += 0.75
    return score


def _ontology_route(
    *,
    query: str,
    concept_id: str,
    root: Path,
) -> dict[str, Any]:
    overlay = _ontology_overlay(root)
    concepts = _concept_registry(root)
    explicit_index = overlay.get("concept_index") if isinstance(overlay.get("concept_index"), dict) else {}
    candidate_index = (
        overlay.get("candidate_concept_index")
        if isinstance(overlay.get("candidate_concept_index"), dict)
        else {}
    )
    requested = _clean_text(concept_id)
    matched: list[str] = []
    resolution = "not_requested"
    if requested:
        if requested in concepts:
            matched = [requested]
            resolution = "exact_concept_id"
        else:
            resolution = "unknown_concept_id"
    elif query:
        query_lower = query.lower()
        candidates: list[tuple[int, str]] = []
        for item_id, concept in concepts.items():
            if item_id not in explicit_index and item_id not in candidate_index:
                continue
            evidence = concept.get("evidence") if isinstance(concept, dict) else {}
            harrison = evidence.get("harrison") if isinstance(evidence, dict) else {}
            labels = [
                item_id.replace("_", " "),
                *((concept.get("aliases") or []) if isinstance(concept, dict) else []),
                harrison.get("title") if isinstance(harrison, dict) else "",
            ]
            normalized_labels = [_clean_text(label).lower() for label in labels if _clean_text(label)]
            exact = any(label == query_lower for label in normalized_labels)
            contained = any(len(label) >= 2 and label in query_lower for label in normalized_labels)
            if exact or contained:
                candidates.append((0 if exact else 1, item_id))
        for source_link in overlay.get("source_links") or []:
            if not isinstance(source_link, dict):
                continue
            for title_candidate in source_link.get("title_rule_candidates") or []:
                if not isinstance(title_candidate, dict):
                    continue
                matched_term = _clean_text(title_candidate.get("matched_term")).lower()
                item_id = _clean_text(title_candidate.get("concept_id"))
                if matched_term and item_id and matched_term in query_lower and item_id in concepts:
                    candidates.append((2, item_id))
        candidates.sort()
        matched = list(dict.fromkeys(item_id for _, item_id in candidates))[:5]
        resolution = "query_alias_heuristic_review_only" if matched else "no_routable_concept_match"

    routes: list[dict[str, Any]] = []
    source_ids: list[str] = []
    for item_id in matched:
        explicit = list(explicit_index.get(item_id) or [])
        candidates = list(candidate_index.get(item_id) or [])
        combined = list(dict.fromkeys([*explicit, *candidates]))
        source_ids.extend(combined)
        concept = concepts.get(item_id) if isinstance(concepts.get(item_id), dict) else {}
        evidence = concept.get("evidence") if isinstance(concept.get("evidence"), dict) else {}
        harrison = evidence.get("harrison") if isinstance(evidence.get("harrison"), dict) else {}
        routes.append(
            {
                "concept_id": item_id,
                "label": harrison.get("title") or (concept.get("aliases") or [item_id])[0],
                "source_ids": combined,
                "mapping_status": (
                    "explicit_topic_route_review_only"
                    if explicit
                    else "title_rule_candidate_route_review_only"
                ),
            }
        )
    return {
        "requested_concept_id": requested or None,
        "resolution": resolution,
        "routes": routes,
        "source_ids": list(dict.fromkeys(source_ids)),
        "used_for": "source_routing_only",
        "ontology_claims_included": False,
        "warning": "온톨로지 연결은 검토 후보이며 진단·치료 사실의 승인 근거로 사용하지 않습니다.",
    }


def get_guideline_library_status(*, root: Path | None = None) -> dict[str, Any]:
    resolved_root = _root(root)
    registry = _source_registry(resolved_root)
    sources = registry.get("sources") or []
    attachments = [
        attachment
        for source in sources
        for attachment in source.get("attachments") or []
        if isinstance(attachment, dict)
    ]
    downloaded = [item for item in attachments if item.get("download_status") == "downloaded"]
    current = [source for source in sources if source.get("latest_status") in CURRENT_SOURCE_STATUSES]
    approved_claim_ids: set[str] = set()
    try:
        from src.services.kr_guideline_claim_review import ALLOWED_SURFACES, list_valid_released_claims

        for surface in ALLOWED_SURFACES:
            approved_claim_ids.update(
                str(claim.get("claim_id") or "")
                for claim in list_valid_released_claims(surface=surface, root=resolved_root)
                if str(claim.get("claim_id") or "")
            )
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        approved_claim_ids = set()
    return {
        "ready": True,
        "library_role": "student_guideline_catalog_preview_and_evidence_packet_source",
        "registry_version": registry.get("schema_version"),
        "generated_at": registry.get("generated_at"),
        "latest_checked_at": registry.get("latest_checked_at"),
        "counts": {
            "sources": len(sources),
            "verified_current_sources": len(current),
            "currentness_review_sources": len(sources) - len(current),
            "attachments": len(attachments),
            "downloaded_attachments": len(downloaded),
            "student_visible_sources": sum(bool(source.get("student_visible")) for source in sources),
            "medically_approved_sources": sum(bool(source.get("medical_approval")) for source in sources),
            "approved_claims_connected": len(approved_claim_ids),
        },
        "facets": {
            "specialties": sorted(
                {item for source in sources for item in source.get("specialties") or []}
            ),
            "clinical_axes": sorted(
                {item for source in sources for item in source.get("clinical_axes") or []}
            ),
            "latest_statuses": sorted({str(source.get("latest_status")) for source in sources}),
        },
        "text_retrieval": {
            "available": importlib.util.find_spec("fitz") is not None,
            "supported_file_type": "pdf",
            "mode": "bounded_local_excerpt_search",
        },
        "safety": {
            "autonomous_clinical_advice": False,
            "student_claim_release_available": bool(approved_claim_ids),
            "default_assistant_currentness_policy": "verified_latest_only",
            "message": (
                "사람 검토를 통과하고 현재 유효한 claim만 지정된 학생 화면에서 사용합니다."
                if approved_claim_ids
                else "현재 문서는 출처 탐색과 검토용입니다. 승인된 진단·치료 claim이 없어 학생용 정답이나 환자별 임상 권고로 배포하지 않습니다."
            ),
        },
    }


def search_guideline_library(
    query: str = "",
    *,
    specialty: str = "",
    clinical_axes: Any = None,
    latest_status: str = "",
    concept_id: str = "",
    current_only: bool = False,
    offset: int = 0,
    limit: int = 20,
    root: Path | None = None,
) -> dict[str, Any]:
    resolved_root = _root(root)
    registry = _source_registry(resolved_root)
    query = _clean_text(query)
    specialty = _clean_text(specialty)
    latest_status = _clean_text(latest_status)
    axes = _normalized_values(clinical_axes)
    safe_offset = max(0, int(offset or 0))
    safe_limit = max(1, min(50, int(limit or 20)))
    terms = _tokens(query)
    ontology_route = _ontology_route(
        query=query,
        concept_id=concept_id,
        root=resolved_root,
    )
    routed_source_ids = set(ontology_route.get("source_ids") or [])

    ranked: list[tuple[float, int, str, dict[str, Any]]] = []
    excluded_by_currentness = 0
    for source in registry.get("sources") or []:
        source_status = str(source.get("latest_status") or "")
        if current_only and source_status not in CURRENT_SOURCE_STATUSES:
            excluded_by_currentness += 1
            continue
        if latest_status and source_status != latest_status:
            continue
        if specialty and specialty not in (source.get("specialties") or []):
            continue
        if axes and not set(axes).intersection(source.get("clinical_axes") or []):
            continue
        score = _source_search_score(source, query, terms)
        if source.get("source_id") in routed_source_ids:
            score += 20.0
        if (query or concept_id) and score <= 0:
            continue
        year = int(source.get("publication_year") or 0)
        ranked.append((score, year, str(source.get("title") or ""), source))

    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
    selected = ranked[safe_offset : safe_offset + safe_limit]
    return {
        "query": query,
        "filters": {
            "specialty": specialty or None,
            "clinical_axes": axes,
            "latest_status": latest_status or None,
            "current_only": bool(current_only),
            "concept_id": _clean_text(concept_id) or None,
        },
        "offset": safe_offset,
        "limit": safe_limit,
        "total": len(ranked),
        "excluded_by_currentness": excluded_by_currentness,
        "results": [
            _source_record(source, score=score)
            for score, _, _, source in selected
        ],
        "ontology_routing": ontology_route,
        "release_note": (
            "검색 결과는 문서 목록입니다. 문서 존재나 온톨로지 연결은 개별 임상 claim의 승인과 같지 않습니다."
        ),
    }


@lru_cache(maxsize=6)
def _extract_pdf_pages(path_text: str, mtime_ns: int, size: int) -> tuple[str, ...]:
    del mtime_ns, size
    import fitz  # type: ignore

    document = fitz.open(path_text)
    try:
        return tuple(_clean_text(page.get_text("text")) for page in document)
    finally:
        document.close()


def _make_excerpt(text: str, terms: list[str], *, max_chars: int = 650) -> str:
    text = _clean_text(text)
    if len(text) <= max_chars:
        return text
    lower = text.lower()
    positions = [lower.find(term) for term in sorted(set(terms), key=len, reverse=True)]
    positions = [position for position in positions if position >= 0]
    start = max(0, (min(positions) if positions else 0) - max_chars // 4)
    end = min(len(text), start + max_chars)
    return f"{'...' if start else ''}{text[start:end].strip()}{'...' if end < len(text) else ''}"


def _page_score(text: str, query: str, terms: list[str]) -> float:
    lower = text.lower()
    score = 0.0
    if query and len(query) >= 3 and query.lower() in lower:
        score += 10.0
    for term in set(terms):
        count = lower.count(term)
        if count:
            score += 1.0 + min(count, 6) * 0.5
    return score


def _search_source_passages(
    source: dict[str, Any],
    *,
    query: str,
    terms: list[str],
    root: Path,
    per_source_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    passages: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    if importlib.util.find_spec("fitz") is None:
        return passages, [{"status": "extractor_unavailable", "file_type": "pdf"}]
    for attachment in source.get("attachments") or []:
        if attachment.get("download_status") != "downloaded":
            continue
        if str(attachment.get("file_type") or "").lower() != "pdf":
            diagnostics.append(
                {
                    "attachment_id": attachment.get("attachment_id"),
                    "status": "unsupported_file_type",
                    "file_type": attachment.get("file_type"),
                }
            )
            continue
        path = _safe_local_path(root, attachment.get("relative_path"))
        if not path or not path.is_file():
            diagnostics.append(
                {"attachment_id": attachment.get("attachment_id"), "status": "local_file_missing"}
            )
            continue
        try:
            stat = path.stat()
            pages = _extract_pdf_pages(str(path), stat.st_mtime_ns, stat.st_size)
        except Exception as exc:  # malformed/encrypted PDFs must not break the whole packet
            diagnostics.append(
                {
                    "attachment_id": attachment.get("attachment_id"),
                    "status": "extraction_failed",
                    "error_type": type(exc).__name__,
                }
            )
            continue
        scored_pages = [
            (_page_score(text, query, terms), page_number, text)
            for page_number, text in enumerate(pages, start=1)
            if text
        ]
        scored_pages = [row for row in scored_pages if row[0] > 0]
        scored_pages.sort(key=lambda row: (-row[0], row[1]))
        for score, page_number, text in scored_pages[:per_source_limit]:
            excerpt = _make_excerpt(text, terms)
            passages.append(
                {
                    "passage_id": hashlib.sha1(
                        f"{source.get('source_id')}::{attachment.get('attachment_id')}::{page_number}".encode(
                            "utf-8"
                        )
                    ).hexdigest()[:16],
                    "source_id": source.get("source_id"),
                    "source_title": source.get("title"),
                    "issuing_body": source.get("issuing_body"),
                    "publication_year": source.get("publication_year"),
                    "version": (source.get("version") or {}).get("display_version"),
                    "latest_status": source.get("latest_status"),
                    "latest_checked_at": source.get("latest_checked_at"),
                    "official_landing_url": source.get("official_landing_url"),
                    "attachment_id": attachment.get("attachment_id"),
                    "filename": attachment.get("filename"),
                    "file_sha256": attachment.get("sha256"),
                    "pdf_page": page_number,
                    "printed_page": None,
                    "page_locator_status": "pdf_page_only_printed_page_not_resolved",
                    "score": round(score, 4),
                    "excerpt": excerpt,
                    "evidence_status": "unreviewed_source_excerpt_not_medical_claim",
                    "medical_approval": False,
                    "student_claim_release": False,
                }
            )
        diagnostics.append(
            {
                "attachment_id": attachment.get("attachment_id"),
                "status": "searched",
                "pages": len(pages),
                "matching_pages": len(scored_pages),
            }
        )
    return passages, diagnostics


def build_guideline_evidence_packet(
    query: str,
    *,
    concept_id: str = "",
    specialty: str = "",
    clinical_axes: Any = None,
    include_uncertain: bool = False,
    include_passages: bool = True,
    source_limit: int = 5,
    passage_limit: int = 8,
    root: Path | None = None,
) -> dict[str, Any]:
    query = _clean_text(query)
    concept_id = _clean_text(concept_id)
    if not query and not concept_id:
        raise ValueError("질문 또는 ontology concept_id가 필요합니다.")
    resolved_root = _root(root)
    safe_source_limit = max(1, min(10, int(source_limit or 5)))
    safe_passage_limit = max(0, min(12, int(passage_limit or 8)))
    library = search_guideline_library(
        query,
        specialty=specialty,
        clinical_axes=clinical_axes,
        concept_id=concept_id,
        current_only=not include_uncertain,
        limit=safe_source_limit,
        root=resolved_root,
    )
    routed_source_ids = set((library.get("ontology_routing") or {}).get("source_ids") or [])
    if routed_source_ids:
        library["results"] = [
            source
            for source in library.get("results") or []
            if source.get("source_id") in routed_source_ids
        ]
        library["total"] = len(library["results"])
    source_ids = [item.get("source_id") for item in library.get("results") or []]
    source_lookup = {
        source.get("source_id"): source
        for source in _source_registry(resolved_root).get("sources") or []
    }
    passages: list[dict[str, Any]] = []
    extraction_diagnostics: list[dict[str, Any]] = []
    if include_passages and safe_passage_limit:
        extraction_terms = _tokens(query or concept_id.replace("_", " "))
        per_source_limit = max(1, min(4, safe_passage_limit))
        for source_id in source_ids[:3]:
            source = source_lookup.get(source_id)
            if not isinstance(source, dict):
                continue
            source_passages, diagnostics = _search_source_passages(
                source,
                query=query,
                terms=extraction_terms,
                root=resolved_root,
                per_source_limit=per_source_limit,
            )
            passages.extend(source_passages)
            extraction_diagnostics.extend(
                {"source_id": source_id, **diagnostic} for diagnostic in diagnostics
            )
        passages.sort(key=lambda item: (-float(item.get("score") or 0), int(item["pdf_page"])))
        passages = passages[:safe_passage_limit]

    return {
        "status": "evidence_packet_ready" if library.get("results") else "no_matching_source",
        "packet_role": "source_discovery_and_review_packet_not_answer",
        "query": query,
        "requested_clinical_axes": _normalized_values(clinical_axes),
        "currentness_policy": (
            "verified_latest_only" if not include_uncertain else "include_uncertain_with_badges"
        ),
        "ontology_routing": library.get("ontology_routing") or {},
        "sources": library.get("results") or [],
        "passages": passages,
        "extraction": {
            "requested": bool(include_passages),
            "passage_count": len(passages),
            "diagnostics": extraction_diagnostics,
        },
        "claim_boundary": {
            "approved_claims_included": 0,
            "ontology_claims_included": False,
            "source_excerpts_are_claims": False,
            "student_claim_release_available": False,
            "autonomous_clinical_advice": False,
        },
        "next_review_steps": [
            "원문 문맥과 인쇄 페이지를 확인합니다.",
            "대상 인구·제외 조건·진료 환경을 구조화합니다.",
            "권고 강도와 근거 수준을 확인합니다.",
            "전문의 검토 후 사용 목적별 release를 별도로 승인합니다.",
        ],
    }


def _case_context_preview(case_context: Any) -> dict[str, Any]:
    if not isinstance(case_context, dict):
        return {}
    allowed = (
        "demographics",
        "setting",
        "chief_concern",
        "timeline",
        "key_findings",
        "existing_problem_list",
    )
    preview: dict[str, Any] = {}
    for key in allowed:
        value = case_context.get(key)
        if isinstance(value, str):
            preview[key] = _clean_text(value)[:1000]
        elif isinstance(value, list):
            preview[key] = [_clean_text(item)[:300] for item in value[:20] if _clean_text(item)]
    return preview


def detect_guideline_intents(query: str, clinical_axes: Any = None) -> list[str]:
    """Return deterministic retrieval intents; this is routing, not medical inference."""

    text = _clean_text(query).lower()
    intents = _normalized_values(clinical_axes)
    keyword_map = {
        "diagnosis": ("진단", "검사", "기준", "diagnos", "test", "criteria"),
        "treatment": ("치료", "처치", "약제", "therapy", "treat", "management"),
        "indication": ("적응증", "언제", "indication", "eligible"),
        "contraindication": ("금기", "피해야", "contraindication", "avoid"),
        "risk_factor": ("위험인자", "위험 요인", "risk factor", "risk"),
        "screening": ("선별", "검진", "screen"),
        "prevention": ("예방", "백신", "prevention", "vaccine"),
        "prognosis": ("예후", "prognos", "outcome"),
        "follow_up": ("추적", "모니터링", "follow-up", "follow up", "monitor"),
    }
    for intent, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            intents.append(intent)
    return list(dict.fromkeys(intents)) or ["general_guideline_lookup"]


def _assistant_template(mode: str, packet: dict[str, Any], case_context: Any) -> dict[str, Any]:
    source_table = [
        {
            "source_id": source.get("source_id"),
            "title": source.get("title"),
            "version": (source.get("version") or {}).get("display_version"),
            "latest_status": (source.get("currentness") or {}).get("status"),
            "checked_at": (source.get("currentness") or {}).get("checked_at"),
            "official_landing_url": source.get("official_landing_url"),
        }
        for source in packet.get("sources") or []
    ]
    if mode == "case_presentation":
        return {
            "template_type": "supervised_case_presentation",
            "prefill": _case_context_preview(case_context),
            "sections": [
                {"id": "problem_representation", "prompt": "한 문장 문제 표상(진단 확정 표현 금지)"},
                {"id": "timeline", "prompt": "증상·검사·처치의 시간순 경과"},
                {"id": "problem_list", "prompt": "능동 문제와 안정된 문제 분리"},
                {"id": "differential", "prompt": "가능성·위험도·배제 필요성으로 정리"},
                {"id": "guideline_questions", "prompt": "지침에서 확인할 질문과 대상 인구"},
                {"id": "evidence_table", "prompt": "원문 페이지·버전·최신성·적용 가능성"},
                {"id": "uncertainties", "prompt": "상충 근거·누락 정보·지도전문의 확인사항"},
            ],
            "guideline_checklist": [
                "이 환자가 지침의 대상 인구에 포함되는가?",
                "명시된 제외 조건이나 금기가 있는가?",
                "진단·중증도·위험도 기준 중 확인되지 않은 항목은 무엇인가?",
                "권고 강도와 근거 수준은 무엇인가?",
                "국내 진료 환경 및 최신판 여부를 확인했는가?",
            ],
            "source_table": source_table,
        }
    if mode == "study_qa":
        sections = [
            {"id": "question_reframe", "prompt": "질문을 대상·중재·비교·결과 또는 임상 축으로 재작성"},
            {"id": "source_check", "prompt": "관련 원문 문서의 버전·최신성·대상 인구 확인"},
            {"id": "conflict_check", "prompt": "출처 간 권고 차이와 적용 조건 기록"},
            {"id": "supervisor_review", "prompt": "지도전문의 검토 후 답변 문장으로 전환"},
        ]
        return {
            "template_type": "evidence_first_qna",
            "direct_answer_status": "not_generated_without_approved_claims",
            "sections": sections,
            "answer_workbench": [item["prompt"] for item in sections],
            "source_table": source_table,
        }
    return {
        "template_type": "guideline_study_plan",
        "sections": [
            {"id": "learning_questions", "prompt": "오늘 답할 핵심 질문 3~5개"},
            {"id": "concept_map", "prompt": "온톨로지 개념과 진단·치료·금기·추적 축 연결"},
            {"id": "source_reading", "prompt": "최신 지침의 관련 페이지 우선 읽기"},
            {"id": "compare", "prompt": "교과서 원리와 국내 지침의 적용 조건 비교"},
            {"id": "retrieval_practice", "prompt": "검토된 내용만 회상 질문/Anki 후보로 변환"},
            {"id": "open_questions", "prompt": "불확실하거나 교수자 확인이 필요한 항목"},
        ],
        "source_table": source_table,
    }


def build_guideline_study_assistant(
    question: str,
    *,
    mode: str = "study_qa",
    concept_id: str = "",
    specialty: str = "",
    clinical_axes: Any = None,
    case_context: Any = None,
    case_text: str = "",
    include_uncertain: bool = False,
    include_passages: bool = True,
    root: Path | None = None,
) -> dict[str, Any]:
    normalized_mode = _clean_text(mode).lower().replace("-", "_")
    aliases = {
        "case": "case_presentation",
        "case_prep": "case_presentation",
        "question_answering": "study_qa",
        "qna": "study_qa",
        "qa": "study_qa",
        "study": "study_qa",
    }
    normalized_mode = aliases.get(normalized_mode, normalized_mode or "study_qa")
    if normalized_mode not in {"study_qa", "case_presentation"}:
        raise ValueError("mode는 study_qa 또는 case_presentation이어야 합니다.")
    privacy_status = guideline_privacy_preflight(case_text)
    if not privacy_status["accepted"]:
        return {
            "status": "privacy_blocked",
            "mode": normalized_mode,
            "assistant_role": "study_and_case_preparation_workbench_not_clinical_decision_support",
            "answer_status": "blocked_direct_identifiers",
            "grounding_state": "retrieval_not_started",
            "message": privacy_status["warning"],
            "detected_intents": detect_guideline_intents(question, clinical_axes),
            "detected_concepts": [],
            "evidence_packet": None,
            "workspace_template": None,
            "privacy_status": privacy_status,
            "safety": {
                "medical_advice_generated": False,
                "diagnosis_generated": False,
                "treatment_recommendation_generated": False,
                "approved_claims_used": 0,
                "requires_supervisor_review": True,
            },
        }
    # De-identified case text may improve routing, but it is not returned or persisted.
    routing_question = _clean_text(f"{question} {str(case_text or '')[:5000]}")
    packet = build_guideline_evidence_packet(
        routing_question,
        concept_id=concept_id,
        specialty=specialty,
        clinical_axes=clinical_axes,
        include_uncertain=include_uncertain,
        include_passages=include_passages,
        root=root,
    )
    packet["query"] = _clean_text(question)
    ontology_matches = (packet.get("ontology_routing") or {}).get("routes") or []
    intents = detect_guideline_intents(routing_question, clinical_axes)
    source_count = len(packet.get("sources") or [])
    passage_count = len(packet.get("passages") or [])
    message = (
        f"관련 국내 지침 {source_count}건과 원문 근거 조각 {passage_count}건을 찾았습니다. "
        "현재 학생에게 공개 가능한 승인 claim이 없어 정답 문장 대신 출처·최신성·문서 정보와 "
        "검토 순서를 제공합니다."
    )
    return {
        "status": packet.get("status"),
        "mode": normalized_mode,
        "assistant_role": "study_and_case_preparation_workbench_not_clinical_decision_support",
        "answer_status": "retrieval_only_approved_claims_unavailable",
        "grounding_state": (
            "guideline_metadata_and_unreviewed_source_excerpts"
            if passage_count
            else "guideline_metadata_only"
        ),
        "message": message,
        "detected_intents": intents,
        "detected_concepts": ontology_matches,
        "evidence_packet": packet,
        "workspace_template": _assistant_template(normalized_mode, packet, case_context),
        "privacy_status": privacy_status,
        "safety": {
            "medical_advice_generated": False,
            "diagnosis_generated": False,
            "treatment_recommendation_generated": False,
            "approved_claims_used": 0,
            "requires_supervisor_review": True,
            "privacy_note": "환자 이름·등록번호·연락처 등 직접 식별정보를 입력하지 마세요.",
        },
    }
