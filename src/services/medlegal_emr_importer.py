from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.generate_lecture_questions import slugify
from src.services.medlegal_studio import CASE_DIR, DATA_ROOT, ensure_medlegal_dirs, timestamp_slug, write_json


IMPORT_DIR = DATA_ROOT / "imports"

HEADER_RE = re.compile(
    r"(?m)^(?P<title>[^\n\t]{2,90})\t(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})(?P<suffix>[^\n]*)$"
)
DATE_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{4}/\d{2}/\d{2}\b"),
    re.compile(r"\b\d{8}\b"),
    re.compile(r"\b\d{2}\.\d{2}\.\d{2}\b"),
]
PHONE_RE = re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b")
MRN_LINE_RE = re.compile(r"(?m)^\s*\d{7,12}\s*$")
MRN_LABEL_RE = re.compile(r"(등록번호\s*[:：]?\s*)[0-9A-Za-z-]+")
PATIENT_NAME_RE = re.compile(r"(환자성명\s*[:：]?\s*)[^\n\r]+")
STAFF_NAME_LINE_RE = re.compile(r"((?:의사|간호사|영양사)성명\s*[:：]?\s*)[^\n\r]+")
CLINICIAN_LABEL_RE = re.compile(
    r"((?:주치의|의뢰자|회신자|최초작성|최종작성|의사명|간호사명|영양사명|집도의|간호사성명|의사성명)\s*[:：]?\s*)"
    r"([가-힣A-Za-z]{2,}(?:\s+[A-Za-z]{2,})?)"
)
NUMBERED_CLINICIAN_RE = re.compile(r"(?m)^(\s*\d+\s*:\s*)[가-힣]{2,4}\s*$")
ENGLISH_MD_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\s+MD\b")
SIGNOFF_RE = re.compile(r"(?m)^.*[가-힣]{2,4}\s+올림\s*$")
ACCESSION_RE = re.compile(r"\b[A-Z]{1,5}\d{4,}[-_]\d+\b")
MONTH_DAY_RE = re.compile(r"\b\d{1,2}/\d{1,2}\b")
FREE_TEXT_IDENTIFIERS_RE = re.compile(r"(?m)^.*(?:주안|평안|고모).*$")


def ensure_import_dirs() -> None:
    ensure_medlegal_dirs()
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)


def deidentify_emr_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = MRN_LINE_RE.sub("[REDACTED_ID]", cleaned)
    cleaned = MRN_LABEL_RE.sub(r"\1[REDACTED_ID]", cleaned)
    cleaned = PATIENT_NAME_RE.sub(r"\1[REDACTED_NAME]", cleaned)
    cleaned = STAFF_NAME_LINE_RE.sub(r"\1[REDACTED_CLINICIAN]", cleaned)
    cleaned = PHONE_RE.sub("[REDACTED_PHONE]", cleaned)
    cleaned = CLINICIAN_LABEL_RE.sub(r"\1[REDACTED_CLINICIAN]", cleaned)
    cleaned = NUMBERED_CLINICIAN_RE.sub(r"\1[REDACTED_CLINICIAN]", cleaned)
    cleaned = ENGLISH_MD_RE.sub("[REDACTED_CLINICIAN]", cleaned)
    cleaned = SIGNOFF_RE.sub("[REDACTED_CLINICIAN_SIGNOFF]", cleaned)
    cleaned = ACCESSION_RE.sub("[REDACTED_ACCESSION]", cleaned)
    cleaned = MONTH_DAY_RE.sub("[DATE]", cleaned)
    cleaned = FREE_TEXT_IDENTIFIERS_RE.sub("[REDACTED_FREE_TEXT]", cleaned)
    for pattern in DATE_PATTERNS:
        cleaned = pattern.sub("[DATE]", cleaned)
    return cleaned.strip()


def parse_record_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def classify_record(title: str, body: str) -> str:
    joined = f"{title}\n{body}"
    if "협진" in title:
        return "consult"
    if "입퇴원요약" in title:
        return "discharge_summary"
    if "입원기록" in title:
        return "admission"
    if "수술기록" in title:
        return "operative_note"
    if "수술(시술) 후" in title:
        return "postop_note"
    if "경과기록" in title:
        return "progress_note"
    if "교육상담" in title:
        return "patient_education"
    if "외래초진" in title:
        return "outpatient_initial"
    if "외래재진" in title:
        return "outpatient_followup"
    if "병리" in joined:
        return "pathology"
    return "clinical_note"


def extract_care_setting(text: str) -> str:
    if "[입원]" in text:
        return "입원"
    if "[외래]" in text:
        return "외래"
    if "[응급]" in text:
        return "응급"
    return "미분류"


def extract_specialty(text: str) -> str:
    match = re.search(r"진료과\s*:\s*([^\s\]]+)", text)
    return match.group(1) if match else ""


def parse_emr_records(raw_text: str) -> list[dict[str, Any]]:
    matches = list(HEADER_RE.finditer(raw_text or ""))
    if not matches:
        return []
    first_dt = parse_record_datetime(matches[0].group("timestamp"))
    records: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        title = match.group("title").strip()
        timestamp = match.group("timestamp")
        body = raw_text[match.end() : next_start].strip()
        record_dt = parse_record_datetime(timestamp)
        relative_day = (record_dt.date() - first_dt.date()).days
        deidentified_body = deidentify_emr_text(body)
        record_text = f"{title}\n{deidentified_body}".strip()
        records.append(
            {
                "record_id": f"R{index + 1:03d}",
                "title": title,
                "note_type": classify_record(title, body),
                "care_setting": extract_care_setting(body),
                "specialty": extract_specialty(body),
                "relative_day": f"D+{relative_day}",
                "relative_time": record_dt.strftime("%H:%M"),
                "deidentified_text": record_text,
                "char_count": len(deidentified_body),
            }
        )
    return records


def build_medlegal_case_from_records(
    records: list[dict[str, Any]],
    *,
    case_id: str,
    title: str,
) -> dict[str, Any]:
    note_types = sorted({record["note_type"] for record in records})
    timeline = [
        {
            "record_id": record["record_id"],
            "relative_day": record["relative_day"],
            "relative_time": record["relative_time"],
            "title": record["title"],
            "note_type": record["note_type"],
            "care_setting": record["care_setting"],
            "specialty": record["specialty"],
        }
        for record in records
    ]
    return {
        "case_id": slugify(case_id),
        "title": title,
        "track": "surgical_medlegal",
        "care_setting": "외래-입원-수술-퇴원",
        "required_note_type": "perioperative_continuity",
        "difficulty": "advanced",
        "status": "imported_draft",
        "fictional_case": False,
        "deidentified": True,
        "learning_goal": "수술 전후 진료기록에서 설명, 협진, 계획 변경, 환자교육, 퇴원계획의 연속성을 점검한다.",
        "scenario": (
            "유방암 수술을 앞둔 환자의 외래 초진, 재진, 협진, 입원기록, 환자교육상담, "
            "수술기록, 수술 후 경과기록, 입퇴원요약이 시간순으로 축적되어 있다."
        ),
        "task": (
            "제공된 시간순 기록을 바탕으로 수술 전 설명과 동의, 계획 변경, 협진 회신, "
            "수술 후 주의관찰, 퇴원 후 추적계획이 충분히 기록되었는지 평가하고 보강 기록을 작성하라."
        ),
        "risk_tags": [
            "perioperative_consent",
            "care_continuity",
            "consult_followup",
            "patient_education",
            "discharge_instruction",
            "documentation_quality",
        ],
        "required_elements": [
            {
                "id": "diagnosis_and_stage_context",
                "label": "진단 변화와 수술 적응증 정리",
                "keywords": ["진단", "재판독", "침윤", "수술", "적응증", "검사결과"],
                "feedback": "초진 이후 진단이 바뀌거나 추가 검사 결과가 나온 경우 수술 계획과 연결해 기록해야 합니다.",
            },
            {
                "id": "plan_change_communication",
                "label": "수술 일정/계획 변경 설명",
                "keywords": ["일정", "변경", "설명", "재건", "취소", "수술계획"],
                "feedback": "수술 일정이나 재건 여부가 바뀌면 환자에게 설명한 내용과 최종 결정을 남기는 것이 중요합니다.",
            },
            {
                "id": "consult_continuity",
                "label": "협진 의뢰와 회신 반영",
                "keywords": ["협진", "의뢰", "회신", "성형외과", "갑상선", "추적"],
                "feedback": "협진 회신이 실제 수술/추적 계획에 어떻게 반영되었는지 연결 기록이 필요합니다.",
            },
            {
                "id": "consent_and_education",
                "label": "설명·동의·환자교육 구체성",
                "keywords": ["교육", "동의", "위험", "예상효과", "합병증", "질문", "이해"],
                "feedback": "교육상담 체크리스트뿐 아니라 어떤 위험과 대안을 설명했는지 서술형 근거가 필요할 수 있습니다.",
            },
            {
                "id": "postop_monitoring",
                "label": "수술 후 주의관찰 및 합병증 기록",
                "keywords": ["수술 후", "bleeding", "배액", "통증", "합병증", "주의관찰"],
                "feedback": "수술 후 경과기록에는 배액량, 출혈, 통증, 합병증 여부와 대응 계획이 일관되게 남아야 합니다.",
            },
            {
                "id": "discharge_followup",
                "label": "퇴원 교육과 추적계획",
                "keywords": ["퇴원", "외래", "추후", "처방", "재내원", "주의사항"],
                "feedback": "퇴원요약은 단순 외래 추적이 아니라 병리 결과 확인, 상처/배액, 응급 재내원 기준을 포함하는 편이 좋습니다.",
            },
        ],
        "risky_patterns": [
            {"pattern": "opd f.u", "reason": "추적계획이 지나치게 포괄적으로 보일 수 있습니다."},
            {"pattern": "N-S", "reason": "중요 항목에서 반복 사용되면 실제 설명/평가 내용이 부족해 보일 수 있습니다."},
            {"pattern": "교육함", "reason": "교육 내용, 환자 이해, 질문 확인이 구체적으로 남지 않을 수 있습니다."},
        ],
        "source_ids": ["medical-act-records", "privacy-health-data", "medical-dispute-communication"],
        "source_record_count": len(records),
        "source_note_types": note_types,
        "timeline": timeline,
        "deidentified_records": records,
        "expansion_path": "수술 전 설명 CPX, 입퇴원요약 작성 훈련, 협진 회신 반영 훈련으로 확장 가능",
    }


def import_emr_text_to_case(
    raw_text: str,
    *,
    source_name: str,
    case_id: str | None = None,
    title: str = "수술 전후 설명·협진·입퇴원 기록 연속성 케이스",
) -> dict[str, Any]:
    ensure_import_dirs()
    records = parse_emr_records(raw_text)
    if not records:
        raise ValueError("EMR record header를 찾지 못했습니다.")
    safe_case_id = slugify(case_id or f"imported_{Path(source_name).stem}_{timestamp_slug()}")
    case = build_medlegal_case_from_records(records, case_id=safe_case_id, title=title)
    import_payload = {
        "source_name": Path(source_name).name,
        "imported_at": timestamp_slug(),
        "raw_text_stored": False,
        "privacy_note": "Raw EMR text is not persisted. Only deidentified records and educational case draft are stored.",
        "case": case,
    }
    import_path = IMPORT_DIR / f"{safe_case_id}.medlegal_import.json"
    case_path = CASE_DIR / f"{safe_case_id}.case.json"
    write_json(import_path, import_payload)
    write_json(case_path, case)
    return {
        "case_id": safe_case_id,
        "record_count": len(records),
        "note_types": case["source_note_types"],
        "paths": {
            "import": str(import_path),
            "case": str(case_path),
        },
        "case": case,
    }
