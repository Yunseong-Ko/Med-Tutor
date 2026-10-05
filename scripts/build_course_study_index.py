#!/usr/bin/env python3
"""Build an Obsidian-friendly index for generated course study notes."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def display_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def build_index(inventory_path: Path, output_path: Path) -> None:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    by_date: dict[str, list[dict]] = defaultdict(list)
    for group in inventory["groups"]:
        by_date[group["date"]].append(group)

    completed = sum(Path(group["note_path"]).exists() for group in inventory["groups"])
    expected_questions = sum(group["expected_question_count"] for group in inventory["groups"])
    lines = [
        "# 혈액종양 시험노트 — 전체 인덱스",
        "",
        "> 원본 95개(PDF/PPT/PPTX)를 동일 강의 기준 56개로 병합한 교시별 노트입니다. 강의자료가 교내 시험 대비의 1차 근거이고, Ontology는 consistency check로만 사용했습니다.",
        "",
        "## 현황",
        "",
        f"- 원본 파일: **{inventory['source_file_count']}개**",
        f"- 강의 노트: **{completed}/{inventory['lecture_group_count']}개**",
        f"- 예정 연관 문항: **{expected_questions}개** (교시 수 기준)",
        "- 이미지: 각 노트의 `사진자료`에 원본 슬라이드·페이지와 출처를 표시",
        "- 빠른 종합 복습: [[01_시험직전_통합복습]]",
        "- 제작·검증 기록: [[02_제작_검증_기록]]",
        "",
        "## 사용 순서",
        "",
        "1. 아래 날짜·교시 순서로 강의노트를 읽습니다.",
        "2. 각 노트의 `시험에 잘 나오는 부분`과 `감별·암기표`를 먼저 복습합니다.",
        "3. `연관 문항`을 답한 뒤 접힌 해설을 확인합니다.",
        "4. `Ontology 검증 기록`은 자동 지식층의 일관성 확인이며 의학 승인 표시가 아닙니다.",
        "",
    ]

    for date in sorted(by_date):
        lines.extend([f"## {display_date(date)}", ""])
        for group in sorted(by_date[date], key=lambda row: (row["periods"] or [99], row["group_id"])):
            note_path = Path(group["note_path"])
            relative = note_path.relative_to(output_path.parent).with_suffix("")
            periods = ", ".join(str(period) for period in group["periods"]) or "교시 미상"
            source_formats = "/".join(
                sorted({source["source_suffix"].lstrip(".").upper() for source in group["sources"]})
            )
            lines.append(
                f"- [[{relative.as_posix()}|{periods}교시 · {group['title']}]] "
                f"— {source_formats}, 문항 {group['expected_question_count']}개"
            )
        lines.append("")

    lines.extend(
        [
            "## 검증 경계",
            "",
            "- 과거 시험 match는 반복 개념을 찾기 위한 보조자료이며 다음 시험 출제를 보장하지 않습니다.",
            "- 기존 Ontology의 관련 claim은 대부분 `needs_review`이고 `medical_approval=false`입니다.",
            "- 약제·용량·치료 순서는 시점 의존성이 있으므로 실제 진료에는 최신 지침 확인이 필요합니다.",
            "- `source_manifest.json`에 원본 경로·SHA-256·병합 관계가 기록되어 있습니다.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"course_study_index_built notes={completed}/{inventory['lecture_group_count']} path={output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_index(args.inventory.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
