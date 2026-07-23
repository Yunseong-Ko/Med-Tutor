from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
MAP_RELATIVE_PATH = Path("data_private/guideline_map/source_map.json")
CLAIM_RELATIVE_PATH = Path("data_private/guideline_map/atomic_claim_candidates.json")

ALLOWED_MODES = {
    "korean_clinical_learning",
    "us_exam",
    "research_comparison",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+/#.\-]*|[가-힣]{2,}")
SPACE_RE = re.compile(r"\s+")
STOPWORDS = {
    "about",
    "guideline",
    "patient",
    "the",
    "with",
    "가이드라인",
    "관련",
    "문헌",
    "어떻게",
    "지침",
    "환자",
}


def _root(root: Path | None) -> Path:
    return (root or DEFAULT_ROOT).resolve()


def _clean(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "").replace("\u00a0", " ")).strip()


def _tokens(value: Any) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(_clean(value))
        if len(token) >= 2 and token.lower() not in STOPWORDS
    ]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"가이드라인 지도 자산을 찾을 수 없습니다: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"가이드라인 지도 형식이 올바르지 않습니다: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_ref_path(root: Path, ref: dict[str, Any]) -> Path:
    relative = Path(str(ref.get("path") or ""))
    if not str(relative) or relative.is_absolute():
        raise ValueError("가이드라인 지도 input 경로가 안전하지 않습니다.")
    resolved = (root / relative).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("가이드라인 지도 input 경로가 workspace 밖을 가리킵니다.")
    return resolved


def _verify_ref(root: Path, ref: dict[str, Any], *, label: str) -> None:
    path = _safe_ref_path(root, ref)
    if not path.is_file():
        raise ValueError(f"{label} input 파일이 없습니다.")
    if path.stat().st_size != ref.get("bytes") or _sha256(path) != ref.get("sha256"):
        raise ValueError(f"{label} input hash가 달라 지도를 다시 빌드해야 합니다.")


def load_guideline_agent_assets(*, root: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved_root = _root(root)
    map_path = resolved_root / MAP_RELATIVE_PATH
    claim_path = resolved_root / CLAIM_RELATIVE_PATH
    source_map = _load_json(map_path)
    claims = _load_json(claim_path)
    if source_map.get("schema_version") != "guideline_agent_map.v1":
        raise ValueError("지원하지 않는 guideline source map schema입니다.")
    if claims.get("schema_version") != "guideline_atomic_claim_candidates.v1":
        raise ValueError("지원하지 않는 guideline claim candidate schema입니다.")
    for label, ref in (source_map.get("inputs") or {}).items():
        if not isinstance(ref, dict):
            raise ValueError(f"{label} input reference가 올바르지 않습니다.")
        _verify_ref(resolved_root, ref, label=label)
    _verify_ref(resolved_root, claims.get("source_map") or {}, label="claim source_map")
    return source_map, claims


def get_guideline_agent_map_status(*, root: Path | None = None) -> dict[str, Any]:
    source_map, claims = load_guideline_agent_assets(root=root)
    return {
        "ready": True,
        "schema_version": "paccine.guideline_agent_map_status.v1",
        "generated_at": source_map.get("generated_at"),
        "map_role": source_map.get("map_role"),
        "counts": {
            **(source_map.get("summary") or {}),
            "atomic_claim_candidates": (claims.get("summary") or {}).get("candidates", 0),
            "claim_extraction_tasks": (claims.get("summary") or {}).get(
                "extraction_tasks", 0
            ),
        },
        "routing_modes": sorted((source_map.get("routing_modes") or {}).keys()),
        "boundary": {
            "source_map_is_medical_evidence": False,
            "candidate_claims_are_medically_approved": False,
            "candidate_claims_runtime_answer_eligible": False,
            "automatic_cross_jurisdiction_merge": False,
            "student_or_generation_release": 0,
        },
    }


def _source_score(
    source: dict[str, Any],
    *,
    query_terms: list[str],
    concept_id: str,
    clinical_axis: str,
) -> float:
    score = {"P0": 4.0, "P1": 2.0, "P2": 1.0}.get(source.get("priority"), 0.0)
    route_ids = {item.get("concept_id") for item in source.get("concept_routes") or []}
    if concept_id:
        if concept_id not in route_ids:
            return -1.0
        score += 30.0
    if clinical_axis:
        if clinical_axis not in (source.get("clinical_axes") or []):
            return -1.0
        score += 8.0
    title = _clean(source.get("title")).lower()
    haystack = " ".join(
        [title, *(_clean(item).lower() for item in source.get("search_terms") or [])]
    )
    for term in set(query_terms):
        if term in title:
            score += 5.0
        elif term in haystack:
            score += 1.5
    if query_terms and score <= 4.0 and not concept_id and not clinical_axis:
        return -1.0
    return score


def _allowed_jurisdictions(mode: str) -> set[str]:
    if mode == "us_exam":
        return {"US"}
    return {"KR", "US"}


def _source_role(mode: str, jurisdiction: str) -> str:
    if mode == "korean_clinical_learning":
        return "primary" if jurisdiction == "KR" else "comparison"
    if mode == "us_exam":
        return "primary"
    return "parallel"


def _public_source(source: dict[str, Any], *, role: str, score: float) -> dict[str, Any]:
    access = source.get("access") if isinstance(source.get("access"), dict) else {}
    applicability = (
        source.get("applicability") if isinstance(source.get("applicability"), dict) else {}
    )
    return {
        "source_id": source.get("source_id"),
        "title": source.get("title"),
        "issuing_body": source.get("issuing_body"),
        "jurisdiction": source.get("jurisdiction"),
        "role": role,
        "priority": source.get("priority"),
        "publication_year": source.get("publication_year"),
        "version": source.get("version"),
        "official_landing_url": source.get("official_landing_url"),
        "latest_status": source.get("latest_status"),
        "latest_checked_at": source.get("latest_checked_at"),
        "specialties": list(source.get("specialties") or []),
        "clinical_axes": list(source.get("clinical_axes") or []),
        "concept_ids": [
            item.get("concept_id") for item in source.get("concept_routes") or []
        ],
        "retrieval_score": round(float(score), 4),
        "access": {
            "metadata_only": bool(access.get("metadata_only")),
            "runtime_text_ingest_allowed": bool(
                access.get("runtime_text_ingest_allowed")
            ),
            "review_excerpt_search_allowed": bool(
                access.get("review_excerpt_search_allowed")
            ),
        },
        "applicability": {
            "korean_role": applicability.get("korean_role"),
            "localization_risks": list(applicability.get("localization_risks") or []),
        },
        "claim_status": "source_navigation_only",
    }


def _candidate_matches(
    candidate: dict[str, Any],
    *,
    source_ids: set[str],
    concept_id: str,
    clinical_axis: str,
    query_terms: list[str],
) -> bool:
    if candidate.get("source_id") not in source_ids:
        return False
    if concept_id and concept_id not in (candidate.get("concept_ids") or []):
        return False
    if clinical_axis and candidate.get("clinical_axis") != clinical_axis:
        return False
    if query_terms:
        haystack = " ".join(
            [
                _clean(candidate.get("population")),
                _clean(candidate.get("trigger")),
                _clean(candidate.get("action")),
                " ".join(candidate.get("topic_tags") or []),
            ]
        ).lower()
        if not any(term in haystack for term in query_terms):
            return False
    return True


def route_guideline_sources(
    query: str = "",
    *,
    concept_id: str = "",
    clinical_axis: str = "",
    mode: str = "korean_clinical_learning",
    include_candidate_claims: bool = False,
    limit: int = 12,
    root: Path | None = None,
) -> dict[str, Any]:
    mode = _clean(mode) or "korean_clinical_learning"
    if mode not in ALLOWED_MODES:
        raise ValueError(f"지원하지 않는 guideline mode입니다: {mode}")
    query = _clean(query)
    concept_id = _clean(concept_id)
    clinical_axis = _clean(clinical_axis)
    safe_limit = max(1, min(50, int(limit or 12)))
    query_terms = _tokens(query)
    source_map, claims = load_guideline_agent_assets(root=root)
    allowed = _allowed_jurisdictions(mode)

    ranked: list[tuple[float, int, str, dict[str, Any]]] = []
    for source in source_map.get("sources") or []:
        if source.get("jurisdiction") not in allowed:
            continue
        score = _source_score(
            source,
            query_terms=query_terms,
            concept_id=concept_id,
            clinical_axis=clinical_axis,
        )
        if score < 0:
            continue
        ranked.append(
            (
                score,
                int(source.get("publication_year") or 0),
                str(source.get("source_id") or ""),
                source,
            )
        )
    ranked.sort(
        key=lambda item: (
            0 if _source_role(mode, item[3].get("jurisdiction")) == "primary" else 1,
            -item[0],
            -item[1],
            item[2],
        )
    )
    selected = ranked[:safe_limit]
    sources = [
        _public_source(
            source,
            role=_source_role(mode, str(source.get("jurisdiction"))),
            score=score,
        )
        for score, _year, _source_id, source in selected
    ]
    selected_ids = {str(source.get("source_id")) for source in sources}

    candidate_rows: list[dict[str, Any]] = []
    if include_candidate_claims:
        candidate_rows = [
            dict(candidate)
            for candidate in claims.get("candidates") or []
            if _candidate_matches(
                candidate,
                source_ids=selected_ids,
                concept_id=concept_id,
                clinical_axis=clinical_axis,
                query_terms=query_terms,
            )
        ]

    return {
        "schema_version": "paccine.guideline_agent_route.v1",
        "mode": mode,
        "query": query,
        "filters": {
            "concept_id": concept_id or None,
            "clinical_axis": clinical_axis or None,
        },
        "sources": sources,
        "source_count": len(sources),
        "candidate_claims": candidate_rows,
        "candidate_claim_count": len(candidate_rows),
        "routing_plan": {
            "primary_source_ids": [
                source["source_id"] for source in sources if source["role"] == "primary"
            ],
            "comparison_source_ids": [
                source["source_id"]
                for source in sources
                if source["role"] == "comparison"
            ],
            "parallel_source_ids": [
                source["source_id"] for source in sources if source["role"] == "parallel"
            ],
        },
        "boundary": {
            "metadata_is_medical_claim": False,
            "candidate_claims_included_for_review": len(candidate_rows),
            "candidate_claims_used_for_answer": 0,
            "released_claims_included": 0,
            "silent_cross_jurisdiction_merge": False,
            "medical_answer_generated": False,
            "student_visible": False,
            "generation_eligible": False,
        },
    }
