from __future__ import annotations

import hashlib
import re
from typing import Any


EXAM_PROFILE = "clinical_comprehensive"


DEPARTMENT_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "id": "internal_medicine",
        "label": "내과",
        "aliases": ("내과", "internal medicine"),
        "match_terms": (
            "내과",
            "소화기",
            "순환기",
            "심장",
            "호흡기",
            "신장",
            "내분비",
            "혈액",
            "종양",
            "감염",
            "면역알레르기",
        ),
    },
    {
        "id": "hematology_oncology",
        "label": "혈액종양내과",
        "aliases": ("혈액종양", "혈액내과", "종양내과", "hematology", "oncology"),
        "match_terms": ("혈액종양", "혈액내과", "종양내과", "소아혈액종양"),
    },
    {
        "id": "gastroenterology",
        "label": "소화기내과",
        "aliases": ("소화기", "소화기내과", "gastroenterology"),
        "match_terms": ("소화기", "간담도"),
    },
    {
        "id": "cardiology",
        "label": "순환기내과",
        "aliases": ("순환기", "순환기내과", "심장내과", "cardiology"),
        "match_terms": ("순환기", "심장내과"),
    },
    {
        "id": "pulmonology",
        "label": "호흡기내과",
        "aliases": ("호흡기", "호흡기내과", "pulmonology"),
        "match_terms": ("호흡기",),
    },
    {
        "id": "nephrology",
        "label": "신장내과",
        "aliases": ("신장", "신장내과", "nephrology"),
        "match_terms": ("신장내과", "신장비뇨"),
    },
    {
        "id": "endocrinology",
        "label": "내분비대사내과",
        "aliases": ("내분비", "내분비내과", "내분비대사내과", "endocrinology"),
        "match_terms": ("내분비",),
    },
    {
        "id": "infectious_disease",
        "label": "감염내과",
        "aliases": ("감염", "감염내과", "infectious disease"),
        "match_terms": ("감염",),
    },
    {
        "id": "surgery",
        "label": "외과",
        "aliases": ("외과", "일반외과", "general surgery", "surgery"),
        "match_terms": ("외과",),
    },
    {
        "id": "pediatrics",
        "label": "소아청소년과",
        "aliases": ("소아", "소아청소년과", "pediatrics"),
        "match_terms": ("소아", "신생아"),
    },
    {
        "id": "obstetrics_gynecology",
        "label": "산부인과",
        "aliases": ("산부인과", "obstetrics", "gynecology", "obgyn"),
        "match_terms": ("산부인과", "생식의학"),
    },
    {
        "id": "psychiatry",
        "label": "정신건강의학과",
        "aliases": ("정신", "정신건강의학과", "psychiatry"),
        "match_terms": ("정신",),
    },
    {
        "id": "neurology",
        "label": "신경과",
        "aliases": ("신경", "신경과", "neurology"),
        "match_terms": ("신경",),
    },
    {
        "id": "orthopedics",
        "label": "정형외과",
        "aliases": ("정형외과", "orthopedics"),
        "match_terms": ("정형외과",),
    },
    {
        "id": "dermatology",
        "label": "피부과",
        "aliases": ("피부", "피부과", "dermatology"),
        "match_terms": ("피부",),
    },
    {
        "id": "urology",
        "label": "비뇨의학과",
        "aliases": ("비뇨의학", "비뇨의학과", "urology"),
        "match_terms": ("비뇨",),
    },
    {
        "id": "otolaryngology",
        "label": "이비인후과",
        "aliases": ("이비인후과", "otolaryngology", "ent"),
        "match_terms": ("이비인후과",),
    },
    {
        "id": "emergency_medicine",
        "label": "응급의학과",
        "aliases": ("응급의학과", "응급", "emergency medicine"),
        "match_terms": ("응급의학", "중환자의학"),
        "assessment_terms": ("emergency_management", "immediate_management"),
    },
)


TASK_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "most_likely_diagnosis",
        "label": "가장 가능성 높은 진단 판단",
        "family": "diagnosis",
        "axis": "diagnosis",
        "domains": ("diagnosis",),
        "relations": ("presents_with", "diagnosed_by"),
        "axes": ("diagnosis",),
    },
    {
        "id": "test_selection",
        "label": "다음 진단검사 선택",
        "family": "diagnosis",
        "axis": "diagnosis",
        "domains": ("test_selection",),
        "relations": ("diagnosed_by",),
        "axes": ("diagnosis",),
    },
    {
        "id": "test_interpretation",
        "label": "검사 결과 해석",
        "family": "diagnosis",
        "axis": "diagnosis",
        "domains": ("test_interpretation",),
        "relations": ("diagnosed_by",),
        "axes": ("diagnosis",),
    },
    {
        "id": "differential_diagnosis",
        "label": "핵심 감별진단 판단",
        "family": "diagnosis",
        "axis": "diagnosis",
        "domains": ("differential_diagnosis", "diagnosis"),
        "relations": ("differential_of",),
        "axes": ("diagnosis",),
    },
    {
        "id": "severity_staging",
        "label": "중증도·병기 판단",
        "family": "diagnosis",
        "axis": "diagnosis",
        "domains": ("staging_severity", "severity_staging"),
        "relations": ("diagnosed_by",),
        "axes": ("diagnosis", "prognosis"),
    },
    {
        "id": "immediate_management",
        "label": "초기 처치 선택",
        "family": "management",
        "axis": "treatment",
        "domains": ("emergency_management", "immediate_management"),
        "relations": ("treated_with", "indicated_for"),
        "axes": ("treatment",),
    },
    {
        "id": "first_line_treatment",
        "label": "1차 또는 최선의 치료 선택",
        "family": "management",
        "axis": "treatment",
        "domains": ("treatment", "treatment_principle"),
        "relations": ("treated_with", "indicated_for"),
        "axes": ("treatment",),
    },
    {
        "id": "pharmacotherapy",
        "label": "적절한 약물치료 선택",
        "family": "management",
        "axis": "treatment",
        "domains": ("pharmacotherapy",),
        "relations": ("treated_with", "indicated_for", "contraindicated_for"),
        "axes": ("treatment",),
    },
    {
        "id": "mechanism",
        "label": "병태생리 기전 추론",
        "family": "mechanism",
        "axis": "pathophysiology",
        "domains": ("pathophysiology", "concept_check"),
        "relations": ("due_to", "causative_agent"),
        "axes": ("pathophysiology",),
    },
    {
        "id": "risk_harm",
        "label": "위험인자 판단",
        "family": "mechanism",
        "axis": "risk_factor",
        "domains": ("risk_factor", "risk_harm"),
        "relations": ("predisposes",),
        "axes": ("risk_factors",),
    },
    {
        "id": "prognostic_factor",
        "label": "예후인자 판단",
        "family": "prognosis",
        "axis": "prognosis",
        "domains": ("prognosis",),
        "relations": (),
        "axes": ("prognosis",),
    },
    {
        "id": "complication",
        "label": "주요 합병증 예측",
        "family": "prognosis",
        "axis": "prognosis",
        "domains": ("complication",),
        "relations": (),
        "axes": ("prognosis",),
    },
)


def target_axis_for_task(task_id: Any) -> str:
    normalized = str(task_id or "").strip()
    return next((str(task["axis"]) for task in TASK_SPECS if task["id"] == normalized), "")


def _normalized_text(value: Any) -> str:
    return "".join(char.lower() for char in str(value or "") if char.isalnum())


def _profile_aliases(profile: dict[str, Any]) -> set[str]:
    return {
        _normalized_text(value)
        for value in (profile.get("id"), profile.get("label"), *(profile.get("aliases") or ()))
        if value
    }


def resolve_department(value: Any) -> dict[str, Any] | None:
    normalized = _normalized_text(value)
    if not normalized:
        return None
    for profile in DEPARTMENT_PROFILES:
        if normalized in _profile_aliases(profile):
            return profile
    return None


def _assessment_domains(concept: dict[str, Any]) -> set[str]:
    values = concept.get("assessment_domains")
    if isinstance(values, str):
        values = re.split(r"[,;\n]+", values)
    if not isinstance(values, list):
        values = []
    return {_normalized_text(value) for value in values if value}


def _matches_department(profile: dict[str, Any], concept: dict[str, Any]) -> bool:
    specialty = _normalized_text(concept.get("specialty"))
    if specialty and any(_normalized_text(term) in specialty for term in profile.get("match_terms") or ()):
        return True
    assessment_terms = {_normalized_text(value) for value in profile.get("assessment_terms") or ()}
    return bool(assessment_terms & _assessment_domains(concept))


def _korean_label(concept_id: str, concept: dict[str, Any], search_record: dict[str, Any]) -> str:
    record_label = str(search_record.get("label") or "").strip()
    if record_label and re.search(r"[가-힣]", record_label):
        return record_label
    aliases = [str(value).strip() for value in concept.get("aliases") or [] if str(value).strip()]
    korean = next((value for value in aliases if re.search(r"[가-힣]", value)), "")
    return korean or record_label or str(search_record.get("title") or concept_id.replace("_", " ")).strip()


def _relation_count(concept: dict[str, Any], relation_names: tuple[str, ...]) -> int:
    edges = concept.get("edges") if isinstance(concept.get("edges"), dict) else {}
    return sum(len(edges.get(name) or []) for name in relation_names if isinstance(edges.get(name), list))


def _axis_supported(concept: dict[str, Any], axis_names: tuple[str, ...]) -> bool:
    axes = concept.get("clinical_axes") if isinstance(concept.get("clinical_axes"), dict) else {}
    return any(axes.get(name) for name in axis_names)


def _task_support(concept: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    domains = _assessment_domains(concept)
    domain_match = bool(domains & {_normalized_text(value) for value in task.get("domains") or ()})
    relation_count = _relation_count(concept, tuple(task.get("relations") or ()))
    axis_match = _axis_supported(concept, tuple(task.get("axes") or ()))
    supported = domain_match or relation_count > 0 or axis_match
    score = (18 if domain_match else 0) + min(15, relation_count * 3) + (8 if axis_match else 0)
    return {
        "supported": supported,
        "domain_match": domain_match,
        "relation_count": relation_count,
        "axis_match": axis_match,
        "score": score,
    }


def _concept_quality(concept: dict[str, Any], question_count: int) -> dict[str, Any]:
    edges = concept.get("edges") if isinstance(concept.get("edges"), dict) else {}
    total_relations = sum(len(value) for value in edges.values() if isinstance(value, list))
    distractor_count = len(edges.get("differential_of") or [])
    presentation_count = len(edges.get("presents_with") or [])
    evidence = concept.get("evidence") if isinstance(concept.get("evidence"), dict) else {}
    has_chapter_pointer = bool(evidence.get("harrison") or evidence.get("ncbi"))
    score = (
        min(18, total_relations)
        + min(12, distractor_count * 2)
        + min(6, presentation_count * 2)
        + (14 if has_chapter_pointer else 0)
        + min(5, max(0, int(question_count or 0)))
    )
    return {
        "score": score,
        "total_relations": total_relations,
        "distractor_count": distractor_count,
        "presentation_count": presentation_count,
        "has_chapter_pointer": has_chapter_pointer,
    }


def _task_options(concept: dict[str, Any], priority_tasks: list[str]) -> list[dict[str, Any]]:
    priority_index = {task_id: index for index, task_id in enumerate(priority_tasks)}
    rows = []
    for task in TASK_SPECS:
        support = _task_support(concept, task)
        if not support["supported"]:
            continue
        priority_bonus = max(0, 14 - priority_index[task["id"]] * 2) if task["id"] in priority_index else 0
        rows.append({**task, "support": support, "priority_bonus": priority_bonus})
    rows.sort(
        key=lambda row: (
            -(row["support"]["score"] + row["priority_bonus"]),
            row["id"],
        )
    )
    return rows


def _intent_id(department_id: str, concept_id: str, task_id: str) -> str:
    raw = f"{EXAM_PROFILE}|{department_id}|{concept_id}|{task_id}".encode("utf-8")
    return "intent:" + hashlib.sha256(raw).hexdigest()[:20]


def _candidate(
    profile: dict[str, Any],
    concept_id: str,
    concept: dict[str, Any],
    search_record: dict[str, Any],
    task: dict[str, Any],
    task_options: list[dict[str, Any]],
    question_count: int,
) -> dict[str, Any]:
    label = _korean_label(concept_id, concept, search_record)
    quality = _concept_quality(concept, question_count)
    support = task["support"]
    coverage_status = "partial" if quality["has_chapter_pointer"] and support["supported"] else "unsupported"
    reasons = [f"{profile['label']} Ontology 분과 메타데이터와 일치"]
    if support["domain_match"]:
        reasons.append("기존 평가영역 메타데이터가 이 과업을 직접 추천")
    elif support["axis_match"]:
        reasons.append("해당 임상축이 Ontology에 구조화됨")
    if quality["distractor_count"] >= 3:
        reasons.append(f"감별·오답 후보 {quality['distractor_count']}개 확보 가능")
    if quality["has_chapter_pointer"]:
        reasons.append("교재 장 위치 포인터 있음 · 주장 직접 근거는 별도 확인 필요")
    warnings = ["Ontology 의학검토 전 · 교수 검수 필요"]
    if quality["presentation_count"] == 0:
        warnings.append("구조화된 환자표현이 부족하여 증례 단서는 근거 RAG에서 보강 필요")
    if not quality["has_chapter_pointer"]:
        warnings.append("직접 연결 근거 슬롯이 없어 자동 생성 전 근거 보강 필요")

    assessment_claim = f"학생이 {label} 관련 임상상황에서 {task['label']}을 수행할 수 있는지 평가한다."
    evidence_contract = {
        "coverage_status": coverage_status,
        "ontology_review_policy": "faculty_draft",
        "task_relation_count": support["relation_count"],
        "distractor_source_count": quality["distractor_count"],
        "presentation_seed_count": quality["presentation_count"],
        "chapter_pointer_available": quality["has_chapter_pointer"],
        "claim_evidence_ready": False,
        "needs_review": True,
        "gen_ready": False,
    }
    selection_contract = {
        "department": {"id": profile["id"], "label": profile["label"]},
        "target": {"type": "condition", "id": concept_id, "label": label},
        "assessment_claim": {
            "task_family": task["family"],
            "task": task["id"],
            "faculty_claim": assessment_claim,
        },
        "task_model": {
            "format": "clinical_case",
            "reasoning_hops": 2,
            "phase_of_care": "initial",
        },
        "evidence_contract": evidence_contract,
    }
    return {
        "intent_id": _intent_id(profile["id"], concept_id, task["id"]),
        "title": f"{label} · {task['label']}",
        "target": {"type": "condition", "concept_id": concept_id, "label": label},
        "department": {"id": profile["id"], "label": profile["label"], "source_specialty": concept.get("specialty")},
        "assessment_claim": {
            "task_family": task["family"],
            "task": task["id"],
            "task_label": task["label"],
            "faculty_claim": assessment_claim,
        },
        "alternative_tasks": [
            {
                "task": item["id"],
                "task_label": item["label"],
                "task_family": item["family"],
                "target_axis_type": item["axis"],
            }
            for item in task_options
            if item["id"] != task["id"]
        ][:3],
        "task_model": {"format": "clinical_case", "reasoning_hops": 2, "phase_of_care": "initial"},
        "target_axis_type": task["axis"],
        "evidence_contract": evidence_contract,
        "recommendation": {
            "score": quality["score"] + support["score"] + task.get("priority_bonus", 0),
            "reasons": reasons[:4],
            "warnings": warnings,
        },
        "selection_contract": selection_contract,
    }


def build_department_catalog(concepts: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for profile in DEPARTMENT_PROFILES:
        matched = [
            concept
            for concept in concepts.values()
            if isinstance(concept, dict) and _matches_department(profile, concept)
        ]
        task_ready = sum(1 for concept in matched if _task_options(concept, []))
        rows.append(
            {
                "id": profile["id"],
                "label": profile["label"],
                "concept_count": len(matched),
                "candidate_ready_count": task_ready,
                "availability": "available" if task_ready >= 3 else "limited" if task_ready else "unavailable",
            }
        )
    return {
        "schema_version": "faculty_department_catalog.v1",
        "exam_profile": EXAM_PROFILE,
        "departments": rows,
        "defaults": {
            "requested_item_count": 3,
            "candidate_count": 6,
            "allowed_item_count": [2, 3],
            "lecture_required": False,
            "direct_topic_entry_allowed": True,
        },
        "needs_review": True,
    }


def recommend_item_intents(
    concepts: dict[str, Any],
    search_records: dict[str, dict[str, Any]],
    *,
    department: str,
    requested_item_count: int = 3,
    candidate_count: int = 6,
    priority_tasks: list[str] | None = None,
    exclude_concept_ids: list[str] | None = None,
    question_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    profile = resolve_department(department)
    if profile is None:
        raise ValueError("지원하는 과를 선택하세요.")
    if requested_item_count not in {2, 3}:
        raise ValueError("교수별 출제 문항 수는 2개 또는 3개여야 합니다.")
    safe_candidate_count = max(requested_item_count, min(12, int(candidate_count or 6)))
    priorities = [str(value).strip() for value in priority_tasks or [] if str(value).strip()]
    excluded = {str(value).strip() for value in exclude_concept_ids or [] if str(value).strip()}
    counts = question_counts or {}

    ranked: list[dict[str, Any]] = []
    for concept_id, concept in concepts.items():
        if not isinstance(concept, dict) or concept_id in excluded or not _matches_department(profile, concept):
            continue
        task_options = _task_options(concept, priorities)
        if not task_options:
            continue
        primary_task = task_options[0]
        candidate = _candidate(
            profile,
            concept_id,
            concept,
            search_records.get(concept_id) or {},
            primary_task,
            task_options,
            int(counts.get(concept_id) or 0),
        )
        ranked.append(candidate)

    ranked.sort(
        key=lambda item: (
            -int((item.get("recommendation") or {}).get("score") or 0),
            str((item.get("target") or {}).get("label") or ""),
        )
    )

    # Keep the first recommendation set balanced across physician tasks instead of
    # returning six near-identical diagnosis cards from the same department. Fill
    # from partially grounded candidates first; unsupported candidates are a last
    # resort when a department does not have enough structured Ontology coverage.
    selected: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    pools = [
        [item for item in ranked if (item.get("evidence_contract") or {}).get("coverage_status") == "partial"],
        [item for item in ranked if (item.get("evidence_contract") or {}).get("coverage_status") != "partial"],
    ]
    for pool in pools:
        for family_cap in (1, 2, safe_candidate_count):
            for item in pool:
                if item in selected:
                    continue
                family = str((item.get("assessment_claim") or {}).get("task_family") or "other")
                if family_counts.get(family, 0) >= family_cap:
                    continue
                selected.append(item)
                family_counts[family] = family_counts.get(family, 0) + 1
                if len(selected) >= safe_candidate_count:
                    break
            if len(selected) >= safe_candidate_count:
                break
        if len(selected) >= safe_candidate_count:
            break

    return {
        "schema_version": "faculty_item_intent_recommendations.v1",
        "exam_profile": EXAM_PROFILE,
        "department": {"id": profile["id"], "label": profile["label"]},
        "requested_item_count": requested_item_count,
        "recommended_selection_count": requested_item_count,
        "candidate_count": len(selected),
        "candidates": selected,
        "selection_rules": {
            "minimum": 2,
            "maximum": 3,
            "lecture_required": False,
            "direct_topic_entry_allowed": True,
            "faculty_confirmation_required": True,
        },
        "review_contract": {
            "generated_items_start_as": "draft",
            "needs_review": True,
            "gen_ready": False,
            "available_actions": ["edit", "needs_revision", "approve", "reject"],
            "student_auto_release": False,
        },
        "warnings": [
            "추천 순위는 현재 Ontology 구조화 가용성을 반영하며 임상 중요도 순위나 의학 승인을 의미하지 않습니다.",
            "교재 장 위치 포인터는 개별 정답 주장을 직접 지지하는 근거가 아닙니다.",
        ],
    }
