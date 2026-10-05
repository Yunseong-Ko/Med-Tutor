#!/usr/bin/env python3
"""Create review-only claims from the official KDA 2025 diabetes guideline.

The script is intentionally fail-closed. It creates draft candidates only and
cannot release them to the student chatbot, FSRS, or item generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.kr_guideline_claim_review import create_claim_draft


SOURCE_ID = "kr-cpg:kda:diabetes-2025-9e"
ATTACHMENT_ID = "kr-cpg:kda:diabetes-2025-9e:a1"
CREATED_BY = "codex_candidate_extraction_20260721"
REVIEW_NOTE = (
    "2026-07-21 대한당뇨병학회 공식 2025 제9판 전문과 로컬 PDF를 대조하고, "
    "해당 PDF 페이지를 렌더링해 재확인한 검토 전 후보입니다. 의료 검토자가 원문, "
    "대상군, 예외, 근거수준과 적용 화면을 확인한 뒤 승인해야 합니다."
)


CANDIDATES = [
    {
        "task_id": "kr-cpg-task:a4d1636ebf62a39ac0c3",
        "page": 8,
        "subject_concept_id": "diabetes_mellitus",
        "relation": "defines",
        "object_text": (
            "당뇨병 진단기준은 당화혈색소 6.5% 이상, 8시간 이상 금식 후 혈장포도당 126 mg/dL 이상, "
            "75 g 경구포도당부하 2시간 후 혈장포도당 200 mg/dL 이상, 또는 전형적 고혈당 증상과 "
            "무작위 혈장포도당 200 mg/dL 이상 중 하나이다."
        ),
        "population": "당뇨병이 의심되는 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "비무작위대조군연구",
        "locator_note": "PDF 8쪽, 1-1 당뇨병 진단 및 분류, 표 1-1.1의 당뇨병 진단기준",
    },
    {
        "task_id": "kr-cpg-task:ef23a8a7725e9c554ad5",
        "page": 11,
        "subject_concept_id": "type_2_diabetes",
        "relation": "recommends",
        "object_text": "표 1-2.1의 2형당뇨병 위험인자가 있는 19세 이상 성인은 당뇨병 선별검사를 시행한다.",
        "population": "2형당뇨병 위험인자가 있는 19세 이상 무증상 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "기타연구",
        "locator_note": "PDF 11쪽, 1-2 당뇨병 선별검사, 권고 1의 첫 번째 대상군",
    },
    {
        "task_id": "kr-cpg-task:ef23a8a7725e9c554ad5",
        "page": 11,
        "subject_concept_id": "type_2_diabetes",
        "relation": "recommends",
        "object_text": "위험인자 유무와 관계없이 35세 이상 모든 성인은 당뇨병 선별검사를 시행한다.",
        "population": "35세 이상 무증상 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "기타연구",
        "locator_note": "PDF 11쪽, 1-2 당뇨병 선별검사, 권고 1의 두 번째 대상군",
    },
    {
        "task_id": "kr-cpg-task:19c6fee55f0440f566ed",
        "page": 11,
        "subject_concept_id": "type_2_diabetes",
        "relation": "recommends",
        "object_text": "당뇨병 선별검사 결과가 정상인 성인은 매년 선별검사를 다시 시행한다.",
        "population": "당뇨병 선별검사 결과가 정상인 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "전문가의견",
        "locator_note": "PDF 11쪽, 1-2 당뇨병 선별검사, 선별검사 후 추가검사 및 추적관찰 2항",
    },
    {
        "task_id": "kr-cpg-task:19c6fee55f0440f566ed",
        "page": 32,
        "subject_concept_id": "diabetes_mellitus",
        "relation": "recommends",
        "object_text": "일반적인 당뇨병 성인은 혈당조절 모니터링을 위해 당화혈색소를 2~3개월마다 측정한다.",
        "population": "혈당조절 상태를 모니터링하는 당뇨병 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "전문가의견",
        "locator_note": "PDF 32쪽, 4-1 혈당조절의 모니터링 및 평가, 권고 1의 1항",
    },
    {
        "task_id": "kr-cpg-task:19c6fee55f0440f566ed",
        "page": 32,
        "subject_concept_id": "diabetes_mellitus",
        "relation": "permits",
        "object_text": "혈당조절이 안정적인 당뇨병 성인은 당화혈색소 측정 빈도를 연 2회까지 줄일 수 있다.",
        "population": "혈당조절이 안정적인 당뇨병 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "전문가의견",
        "locator_note": "PDF 32쪽, 4-1 혈당조절의 모니터링 및 평가, 권고 1의 2항",
    },
    {
        "task_id": "kr-cpg-task:3c5096cefa3b90991225",
        "page": 78,
        "subject_concept_id": "type_2_diabetes",
        "relation": "recommends",
        "object_text": (
            "심부전을 동반한 2형당뇨병에서는 당화혈색소 수치와 무관하게 심부전 이익이 입증된 "
            "SGLT2억제제를 우선 사용하고, 금기나 부작용이 없으면 유지한다."
        ),
        "population": "심부전을 동반한 2형당뇨병 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "무작위대조군연구",
        "locator_note": "PDF 78쪽, 6-2 약물치료, 권고 8",
    },
    {
        "task_id": "kr-cpg-task:3c5096cefa3b90991225",
        "page": 79,
        "subject_concept_id": "type_2_diabetes",
        "relation": "recommends",
        "object_text": (
            "알부민뇨가 있거나 추정사구체여과율이 감소한 2형당뇨병에서는 당화혈색소 수치와 무관하게 "
            "신장 이익이 입증된 SGLT2억제제를 우선 사용하고, 금기나 부작용이 없으면 유지한다."
        ),
        "population": "알부민뇨 또는 추정사구체여과율 감소가 있는 2형당뇨병 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "무작위대조군연구",
        "locator_note": "PDF 79쪽, 6-2 약물치료, 권고 9",
    },
    {
        "task_id": "kr-cpg-task:3c5096cefa3b90991225",
        "page": 80,
        "subject_concept_id": "type_2_diabetes",
        "relation": "recommends",
        "object_text": (
            "죽상경화심혈관질환을 동반한 2형당뇨병에서는 심혈관 이익이 입증된 GLP-1수용체작용제 "
            "또는 SGLT2억제제를 포함한 치료를 우선한다."
        ),
        "population": "죽상경화심혈관질환을 동반한 2형당뇨병 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "무작위대조군연구",
        "locator_note": "PDF 80쪽, 6-2 약물치료, 권고 10",
    },
    {
        "task_id": "kr-cpg-task:3c5096cefa3b90991225",
        "page": 95,
        "subject_concept_id": "diabetes_mellitus",
        "relation": "recommends",
        "object_text": "당뇨병 성인의 일반적인 혈압조절 목표는 130/80 mmHg 미만이다.",
        "population": "혈압을 관리하는 당뇨병 성인",
        "recommendation_strength": "일반적권고",
        "evidence_grade": "무작위대조군연구",
        "locator_note": "PDF 95쪽, 7-1 고혈압관리, 권고 3",
    },
]


def _payload(candidate: dict[str, object]) -> dict[str, object]:
    return {
        **candidate,
        "attachment_id": ATTACHMENT_ID,
        "effective_version": "2025 제9판",
        "review_notes": REVIEW_NOTE,
        "created_by": CREATED_BY,
    }


def _assert_current_source(root: Path) -> None:
    registry_path = root / "data_private/kr_guidelines/verified_latest_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source = next(
        (item for item in registry.get("sources", []) if item.get("source_id") == SOURCE_ID),
        None,
    )
    if not source:
        raise RuntimeError("2025 당뇨병 진료지침 source가 최신판 레지스트리에 없습니다.")
    version = source.get("version") or {}
    if (
        source.get("latest_status") != "verified_latest_on_official_source"
        or source.get("publication_year") != 2025
        or version.get("display_version") != "제9판"
        or version.get("version_conflict") is not False
    ):
        raise RuntimeError("2025 당뇨병 진료지침의 최신성 또는 판본 검토가 끝나지 않았습니다.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="검토 전 claim 초안을 저장합니다. 생략하면 후보만 출력합니다.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    _assert_current_source(root)
    payloads = [_payload(candidate) for candidate in CANDIDATES]
    if not args.apply:
        print(json.dumps({"mode": "dry_run", "candidates": payloads}, ensure_ascii=False, indent=2))
        return 0

    claims = [create_claim_draft(payload, root=root) for payload in payloads]
    print(
        json.dumps(
            {
                "mode": "draft_only",
                "source_id": SOURCE_ID,
                "claim_ids": [claim["claim_id"] for claim in claims],
                "medical_approval": False,
                "student_visible": False,
                "human_review_required": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
