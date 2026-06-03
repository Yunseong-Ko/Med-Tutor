from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.generate_lecture_questions import slugify


DATA_ROOT = Path("data_private/medlegal")
CASE_DIR = DATA_ROOT / "cases"
SUBMISSION_DIR = DATA_ROOT / "submissions"
SOURCE_DIR = DATA_ROOT / "sources"

DISCLAIMER = (
    "Educational feedback only. This simulator does not provide legal advice "
    "or replace institutional legal/privacy review."
)

SOURCE_LIBRARY: dict[str, dict[str, str]] = {
    "medical-act-records": {
        "source_id": "medical-act-records",
        "title": "의료법상 진료기록 작성·보존 원칙",
        "url": "https://www.law.go.kr/법령/의료법",
        "note": "진료기록은 사실관계, 판단 근거, 설명/동의 내용을 사후 확인 가능하게 남기는 훈련 근거로 사용합니다.",
    },
    "privacy-health-data": {
        "source_id": "privacy-health-data",
        "title": "보건의료 데이터 가명처리·활용 가이드라인",
        "url": "https://www.pipc.go.kr/",
        "note": "실제 병원 EMR 활용 전 IRB, 가명처리, 최소수집, 접근통제 원칙을 적용합니다.",
    },
    "medical-dispute-communication": {
        "source_id": "medical-dispute-communication",
        "title": "의료분쟁 예방을 위한 설명·동의·경과기록 교육 자료",
        "url": "",
        "note": "MVP 단계에서는 공개 분쟁 사례와 교수 작성 가상사례를 교육용으로 재구성합니다.",
    },
    "cpx-shared-decision": {
        "source_id": "cpx-shared-decision",
        "title": "CPX 의사-환자 의사소통 및 공동의사결정 평가 축",
        "url": "",
        "note": "추후 나쁜 소식 전달, 검사 거부, 퇴원 설명, 라포 형성 시나리오로 확장합니다.",
    },
}

SEED_CASES: list[dict[str, Any]] = [
    {
        "case_id": "case_ed_discharge_headache_001",
        "title": "응급실 두통 환자 퇴원 설명 기록",
        "track": "medlegal_emr",
        "care_setting": "응급실",
        "required_note_type": "ed_discharge",
        "difficulty": "basic",
        "status": "seed",
        "fictional_case": True,
        "learning_goal": "단순 퇴원 기록이 아니라 위험징후, 감별진단, 재내원 기준을 남기는 연습",
        "scenario": (
            "24세 여성이 6시간 전 시작된 두통으로 응급실에 왔다. 활력징후는 안정적이고 "
            "신경학적 국소징후는 없다. 진통제 투여 후 증상은 호전되었다. 환자는 귀가를 원한다."
        ),
        "task": "담당 의사로서 퇴원 전 설명 및 EMR 경과기록/퇴원기록을 작성하라.",
        "risk_tags": ["red_flag", "return_precaution", "diagnostic_uncertainty", "follow_up"],
        "required_elements": [
            {
                "id": "red_flags",
                "label": "위험징후 확인",
                "keywords": ["의식", "마비", "경련", "발열", "목경직", "시야", "악화", "신경학적"],
                "feedback": "두통은 호전되었더라도 위험징후 확인 여부를 기록해야 사후 설명 근거가 남습니다.",
            },
            {
                "id": "diagnostic_uncertainty",
                "label": "진단 불확실성 설명",
                "keywords": ["완전히 배제", "가능성", "감별", "불확실", "추적", "관찰"],
                "feedback": "응급실 퇴원 기록에는 현재 평가의 한계와 추적 필요성을 함께 남기는 편이 안전합니다.",
            },
            {
                "id": "return_precautions",
                "label": "재내원 기준",
                "keywords": ["재내원", "응급실", "악화", "구토", "마비", "의식", "발열", "즉시"],
                "feedback": "재내원 기준이 구체적이어야 환자 안전과 설명의무 측면에서 모두 도움이 됩니다.",
            },
            {
                "id": "patient_understanding",
                "label": "환자 이해 확인",
                "keywords": ["이해", "확인", "질문", "동의", "설명", "보호자"],
                "feedback": "설명했다는 문장만으로는 부족할 수 있어 환자 이해/질문 확인을 남기는 것이 좋습니다.",
            },
        ],
        "risky_patterns": [
            {"pattern": "단순 두통", "reason": "위험징후 평가 없이 단정적으로 보일 수 있습니다."},
            {"pattern": "문제 없음", "reason": "진단 불확실성과 재내원 기준이 빠질 위험이 있습니다."},
        ],
        "source_ids": ["medical-act-records", "medical-dispute-communication", "cpx-shared-decision"],
        "expansion_path": "CPX 퇴원 설명 스테이션으로 확장 가능",
    },
    {
        "case_id": "case_informed_refusal_ct_001",
        "title": "검사 거부 환자 설명의무 및 거부기록",
        "track": "medlegal_emr",
        "care_setting": "외래/응급실",
        "required_note_type": "informed_refusal",
        "difficulty": "intermediate",
        "status": "seed",
        "fictional_case": True,
        "learning_goal": "검사 필요성, 대안, 거부 시 위험, 환자 판단능력, 추적계획을 구조화해 기록",
        "scenario": (
            "62세 남성이 흉통으로 내원했다. 심전도는 비특이적이나 고혈압, 당뇨 병력이 있다. "
            "담당의는 추가 혈액검사와 영상검사를 권유했으나 환자는 비용과 시간을 이유로 거부한다."
        ),
        "task": "검사 거부 상황에서 설명 내용과 환자 의사결정을 EMR에 남겨라.",
        "risk_tags": ["informed_refusal", "capacity", "alternative_plan", "high_risk_symptom"],
        "required_elements": [
            {
                "id": "recommended_plan",
                "label": "권고 검사/치료 명시",
                "keywords": ["권유", "검사", "심전도", "혈액검사", "영상", "입원", "관찰"],
                "feedback": "무엇을 왜 권유했는지가 기록되어야 거부기록의 맥락이 분명해집니다.",
            },
            {
                "id": "risk_of_refusal",
                "label": "거부 시 위험 설명",
                "keywords": ["위험", "악화", "심근경색", "사망", "합병증", "지연"],
                "feedback": "거부 시 발생 가능한 중대한 위험을 구체적으로 설명해야 합니다.",
            },
            {
                "id": "capacity_and_reason",
                "label": "판단능력과 거부 사유",
                "keywords": ["판단", "의사결정", "이해", "사유", "비용", "시간", "거부"],
                "feedback": "환자의 판단능력과 거부 사유를 남기면 강압이 아닌 자율적 결정임을 설명할 수 있습니다.",
            },
            {
                "id": "safety_net",
                "label": "대안 및 안전망",
                "keywords": ["대안", "외래", "추적", "재내원", "응급", "연락", "보호자"],
                "feedback": "검사를 거부해도 추적계획과 재내원 기준은 반드시 남겨야 합니다.",
            },
        ],
        "risky_patterns": [
            {"pattern": "본인 책임", "reason": "비난적으로 보일 수 있어 설명 내용과 대안을 중심으로 바꾸는 편이 좋습니다."},
            {"pattern": "거부함", "reason": "단순 거부만 적으면 설명의무 이행 근거가 부족합니다."},
        ],
        "source_ids": ["medical-act-records", "medical-dispute-communication", "cpx-shared-decision"],
        "expansion_path": "CPX 검사 거부/공동의사결정 스테이션으로 확장 가능",
    },
    {
        "case_id": "case_bad_news_consent_001",
        "title": "침습적 처치 전 설명과 동의 기록",
        "track": "cpx_medlegal",
        "care_setting": "병동",
        "required_note_type": "procedure_consent",
        "difficulty": "intermediate",
        "status": "seed",
        "fictional_case": True,
        "learning_goal": "처치 필요성, 기대효과, 대안, 합병증, 환자 질문을 균형 있게 설명하는 연습",
        "scenario": (
            "70세 환자가 흉수로 호흡곤란을 호소한다. 흉수천자가 필요하다고 판단되며, "
            "환자와 보호자는 시술 위험을 걱정하고 있다."
        ),
        "task": "흉수천자 전 설명 및 동의 과정을 의사-환자 대화와 EMR 기록 관점에서 작성하라.",
        "risk_tags": ["procedure_consent", "complication", "shared_decision", "communication"],
        "required_elements": [
            {
                "id": "purpose_benefit",
                "label": "시술 목적/기대효과",
                "keywords": ["목적", "호흡곤란", "흉수", "진단", "치료", "완화"],
                "feedback": "시술이 왜 필요한지와 기대효과를 환자 언어로 설명해야 합니다.",
            },
            {
                "id": "risks_alternatives",
                "label": "위험과 대안",
                "keywords": ["기흉", "출혈", "감염", "통증", "대안", "관찰", "합병증"],
                "feedback": "흔한/중대한 합병증과 가능한 대안을 함께 남겨야 합니다.",
            },
            {
                "id": "questions_and_consent",
                "label": "질문 확인과 동의",
                "keywords": ["질문", "이해", "동의", "보호자", "설명", "확인"],
                "feedback": "질문 기회와 동의 여부를 기록하면 의사소통 과정이 보강됩니다.",
            },
            {
                "id": "empathy",
                "label": "공감적 표현",
                "keywords": ["걱정", "불안", "천천히", "설명", "함께", "확인"],
                "feedback": "CPX 확장에서는 공감적 표현과 환자 감정 확인도 평가 축이 됩니다.",
            },
        ],
        "risky_patterns": [
            {"pattern": "동의서 받음", "reason": "동의서 존재만으로 설명 내용이 충분히 드러나지 않습니다."},
            {"pattern": "합병증 설명함", "reason": "어떤 합병증을 설명했는지 구체성이 필요합니다."},
        ],
        "source_ids": ["medical-act-records", "medical-dispute-communication", "cpx-shared-decision"],
        "expansion_path": "의사-환자 대화형 CPX 코치로 확장 가능",
    },
]

RUBRIC_DIMENSIONS = [
    "clinical_completeness",
    "reasoning_trace",
    "patient_safety",
    "communication",
    "continuity",
    "record_integrity",
    "medico_legal_awareness",
]


def ensure_medlegal_dirs() -> None:
    for directory in (CASE_DIR, SUBMISSION_DIR, SOURCE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as temp_file:
        temp_file.write(content)
        temp_name = temp_file.name
    os.replace(temp_name, path)


def write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def seed_cases_if_needed() -> None:
    ensure_medlegal_dirs()
    for case in SEED_CASES:
        path = CASE_DIR / f"{case['case_id']}.case.json"
        if not path.exists():
            write_json(path, case)
    source_path = SOURCE_DIR / "source_library.json"
    if not source_path.exists():
        write_json(source_path, list(SOURCE_LIBRARY.values()))


def read_case_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"케이스 파일을 읽을 수 없습니다: {path.name}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"케이스 파일 형식이 올바르지 않습니다: {path.name}")
    return data


def list_medlegal_cases(*, track: str | None = None) -> list[dict[str, Any]]:
    seed_cases_if_needed()
    cases = [read_case_file(path) for path in sorted(CASE_DIR.glob("*.case.json"))]
    if track:
        cases = [case for case in cases if str(case.get("track") or "") == track]
    return [
        {
            "case_id": case["case_id"],
            "title": case.get("title", ""),
            "track": case.get("track", ""),
            "care_setting": case.get("care_setting", ""),
            "required_note_type": case.get("required_note_type", ""),
            "difficulty": case.get("difficulty", ""),
            "risk_tags": case.get("risk_tags", []),
            "learning_goal": case.get("learning_goal", ""),
            "fictional_case": bool(case.get("fictional_case", True)),
        }
        for case in cases
    ]


def load_medlegal_case(case_id: str) -> dict[str, Any]:
    seed_cases_if_needed()
    safe_case_id = slugify(case_id)
    path = CASE_DIR / f"{safe_case_id}.case.json"
    if not path.exists():
        raise FileNotFoundError(case_id)
    case = read_case_file(path)
    case["sources"] = resolve_sources(case.get("source_ids", []))
    return case


def resolve_sources(source_ids: list[str]) -> list[dict[str, str]]:
    return [deepcopy(SOURCE_LIBRARY[source_id]) for source_id in source_ids if source_id in SOURCE_LIBRARY]


def contains_any(note_text: str, keywords: list[str]) -> bool:
    normalized = note_text.casefold()
    return any(keyword.casefold() in normalized for keyword in keywords)


def score_case_submission(case: dict[str, Any], note_text: str) -> dict[str, Any]:
    stripped_note = note_text.strip()
    required_elements = case.get("required_elements", [])
    covered = []
    missing = []
    for element in required_elements:
        if contains_any(stripped_note, element.get("keywords", [])):
            covered.append(
                {
                    "id": element.get("id"),
                    "label": element.get("label"),
                }
            )
        else:
            missing.append(
                {
                    "id": element.get("id"),
                    "label": element.get("label"),
                    "feedback": element.get("feedback"),
                }
            )

    risky_phrases = [
        risky
        for risky in case.get("risky_patterns", [])
        if str(risky.get("pattern") or "").casefold() in stripped_note.casefold()
    ]
    coverage_score = round((len(covered) / max(1, len(required_elements))) * 100)
    length_bonus = 10 if len(stripped_note) >= 350 else 5 if len(stripped_note) >= 150 else 0
    risk_penalty = min(20, len(risky_phrases) * 8)
    overall_score = max(0, min(100, coverage_score + length_bonus - risk_penalty))

    dimension_scores = build_dimension_scores(case, covered, missing, overall_score)
    recommended_revision = build_recommended_revision(case, missing, risky_phrases)
    return {
        "overall_score": overall_score,
        "dimension_scores": dimension_scores,
        "covered_items": covered,
        "missing_items": missing,
        "risky_phrases": risky_phrases,
        "recommended_revision": recommended_revision,
        "source_refs": resolve_sources(case.get("source_ids", [])),
        "next_training": case.get("expansion_path", ""),
        "disclaimer": DISCLAIMER,
    }


def build_dimension_scores(
    case: dict[str, Any],
    covered: list[dict[str, str]],
    missing: list[dict[str, str]],
    overall_score: int,
) -> dict[str, int]:
    covered_ids = {item.get("id") for item in covered}
    missing_count = len(missing)
    scores = {dimension: max(20, overall_score - 5) for dimension in RUBRIC_DIMENSIONS}

    if "return_precautions" in covered_ids or "safety_net" in covered_ids:
        scores["patient_safety"] = min(100, overall_score + 10)
        scores["continuity"] = min(100, overall_score + 8)
    if "patient_understanding" in covered_ids or "questions_and_consent" in covered_ids or "empathy" in covered_ids:
        scores["communication"] = min(100, overall_score + 10)
    if "diagnostic_uncertainty" in covered_ids or "risk_of_refusal" in covered_ids:
        scores["reasoning_trace"] = min(100, overall_score + 8)
        scores["medico_legal_awareness"] = min(100, overall_score + 8)
    if missing_count >= 2:
        scores["record_integrity"] = max(10, overall_score - 15)
    if case.get("track") == "cpx_medlegal":
        scores["communication"] = min(100, scores["communication"] + 5)
    return scores


def build_recommended_revision(
    case: dict[str, Any],
    missing: list[dict[str, str]],
    risky_phrases: list[dict[str, str]],
) -> str:
    if not missing and not risky_phrases:
        return (
            "핵심 항목이 대부분 포함되어 있습니다. 실제 교육용 제출 전에는 담당 교수/법무 검토자가 "
            "표현의 정확성과 기관 양식 적합성을 확인하는 단계로 넘기면 됩니다."
        )
    missing_labels = ", ".join(item.get("label", "") for item in missing if item.get("label"))
    risky_labels = ", ".join(item.get("pattern", "") for item in risky_phrases if item.get("pattern"))
    parts = []
    if missing_labels:
        parts.append(f"보강할 항목: {missing_labels}.")
    if risky_labels:
        parts.append(f"주의 표현: {risky_labels}.")
    parts.append("문장은 환자에게 설명한 내용, 환자 반응, 추적계획이 사후에도 재구성되도록 구체화하세요.")
    return " ".join(parts)


def submit_medlegal_note(
    case_id: str,
    note_text: str,
    *,
    learner_role: str = "student",
    note_type: str = "",
) -> dict[str, Any]:
    if not note_text.strip():
        raise ValueError("작성한 기록이 비어 있습니다.")
    case = load_medlegal_case(case_id)
    feedback = score_case_submission(case, note_text)
    submitted_at = datetime.now(timezone.utc).isoformat()
    submission_id = f"medlegal_{timestamp_slug()}_{slugify(case_id)}"
    payload = {
        "submission_id": submission_id,
        "case_id": case["case_id"],
        "learner_role": learner_role or "student",
        "note_type": note_type or case.get("required_note_type", ""),
        "submitted_at": submitted_at,
        "note_text": note_text,
        "feedback": feedback,
        "privacy": {
            "uses_real_patient_data": False,
            "fictional_case": bool(case.get("fictional_case", True)),
            "storage_scope": "local data_private/medlegal only",
        },
    }
    write_json(SUBMISSION_DIR / f"{submission_id}.submission.json", payload)
    return payload


def load_medlegal_submission(submission_id: str) -> dict[str, Any]:
    ensure_medlegal_dirs()
    safe_submission_id = slugify(submission_id)
    path = SUBMISSION_DIR / f"{safe_submission_id}.submission.json"
    if not path.exists():
        raise FileNotFoundError(submission_id)
    return json.loads(path.read_text(encoding="utf-8"))
