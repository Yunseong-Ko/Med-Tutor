#!/usr/bin/env python3
"""Create review-only claim candidates from the official 2026 KDCA CAP guideline.

The script is intentionally fail-closed: it creates draft records only. It never
releases a medical claim or makes it visible to students.
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


SOURCE_ID = "kr-cpg:kdca:asp-2026-cap"
ATTACHMENT_ID = "kr-cpg:kdca:asp-2026-cap:a1"
CONCEPT_ID = "community_acquired_pneumonia"
POPULATION = "대한민국 의료기관에서 지역사회획득 폐렴이 의심되거나 진단된 19세 이상 성인"
CREATED_BY = "codex_candidate_extraction_20260721"
REVIEW_NOTE = (
    "2026-07-21 공식 원문 PDF를 페이지 렌더링으로 재확인한 검토 전 후보입니다. "
    "대상군·예외·권고 강도·적용 화면은 의료 검토자가 원문과 대조한 뒤 승인해야 합니다."
)


CANDIDATES = [
    {
        "task_id": "kr-cpg-task:f80f7210a8a5a286450a",
        "page": 16,
        "relation": "suggests",
        "object_text": "입원 필요도를 평가할 때 CURB-65를 계산하고, 2점 이상이면 입원 치료를 고려한다.",
        "locator_note": "PDF 16쪽, 1단계(입원 필요 여부 평가) 첫 번째 항목",
    },
    {
        "task_id": "kr-cpg-task:897c762f1f987d1d4407",
        "page": 17,
        "relation": "recommends",
        "object_text": "초기 치료 후 3일째와 5일째에 발열·기침·가래 등 임상 증상의 호전 여부로 치료 반응을 평가한다.",
        "locator_note": "PDF 17쪽, 3단계(치료 반응 평가) 첫 번째 문단 첫 두 문장",
    },
    {
        "task_id": "kr-cpg-task:d04e14c17202d101fb6b",
        "page": 17,
        "relation": "recommends",
        "object_text": "원인균 확인을 위한 검사를 시행했다면 검사 결과에 따라 확정적 항생제로 변경한다.",
        "locator_note": "PDF 17쪽, 3단계(치료 반응 평가) 첫 번째 문단 원인균 확인 문장",
    },
    {
        "task_id": "kr-cpg-task:d04e14c17202d101fb6b",
        "page": 17,
        "relation": "recommends",
        "object_text": "원인균이 확인되지 않았더라도 경험적 항생제에 임상 반응이 있으면 총 5~7일 사용 후 치료를 종결한다.",
        "locator_note": "PDF 17쪽, 3단계(치료 반응 평가) 첫 번째 문단 치료 기간 문장",
    },
    {
        "task_id": "kr-cpg-task:d04e14c17202d101fb6b",
        "page": 17,
        "relation": "suggests",
        "object_text": "임상 증상이 호전된 비중증 입원 환자가 표 5의 모든 기준을 충족하면 정주 항생제에서 경구 항생제로 전환을 고려한다.",
        "locator_note": "PDF 17쪽, 3단계(치료 반응 평가) 첫 번째 문단 및 표 5",
    },
    {
        "task_id": "kr-cpg-task:f94b8dff30288b662706",
        "page": 17,
        "relation": "does_not_recommend",
        "object_text": "영상검사에서 폐 병변이 완전히 소실되었는지를 항생제 치료 종결 기준으로 사용하지 않는다.",
        "polarity": "negative",
        "locator_note": "PDF 17쪽, 3단계(치료 반응 평가) 첫 번째 문단 영상검사 문장",
    },
]


def _payload(candidate: dict[str, object]) -> dict[str, object]:
    return {
        **candidate,
        "attachment_id": ATTACHMENT_ID,
        "subject_concept_id": CONCEPT_ID,
        "population": POPULATION,
        "recommendation_strength": "not_reported",
        "evidence_grade": "not_reported",
        "effective_version": "2026",
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
        raise RuntimeError("2026 CAP source가 최신판 레지스트리에 없습니다.")
    version = source.get("version") or {}
    if (
        source.get("latest_status") != "verified_latest_on_official_source"
        or source.get("publication_year") != 2026
        or version.get("version_conflict") is not False
    ):
        raise RuntimeError("2026 CAP source의 최신성 또는 판본 충돌 검토가 끝나지 않았습니다.")


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
