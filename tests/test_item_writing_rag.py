from __future__ import annotations

import json
from pathlib import Path

from src.services.item_writing_rag import (
    build_generation_item_writing_context,
    load_item_writing_index,
    search_item_writing_rules,
)


def _write_index(path: Path) -> None:
    payload = {
        "profiles": {
            "kmle_summative": {
                "target_seconds_per_item": 75,
                "terminology_policy": "의학용어집 제6판 우선",
            }
        },
        "retrieval_routing": {
            "generation_stages": ["blueprint", "disclosure", "lead_in"],
            "always_include_rule_ids": ["IW-DISC-003"],
        },
        "rules": [
            {
                "rule_id": "IW-DISC-003",
                "title": "confounder 의무화 금지",
                "statement_ko": "경합 단서는 필요한 경우 0~1개만 사용한다.",
                "stage": "disclosure",
                "severity": "hard",
                "exam_profiles": ["all"],
                "assessment_tasks": ["all"],
                "tags": ["confounder", "red_herring"],
                "source_refs": [{"source_id": "guide", "locator": "page 1"}],
                "prompt": True,
            },
            {
                "rule_id": "IW-POST-001",
                "title": "시험 후 정답률",
                "statement_ko": "정답률은 시행 후 해석한다.",
                "stage": "post_exam_analysis",
                "severity": "post_exam",
                "exam_profiles": ["all"],
                "assessment_tasks": ["all"],
                "tags": ["difficulty"],
                "source_refs": [{"source_id": "analytics", "locator": "page 2"}],
                "prompt": False,
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_generation_context_is_curated_and_excludes_local_paths(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    _write_index(index_path)
    load_item_writing_index.cache_clear()
    context = build_generation_item_writing_context(
        exam_profile="kmle_summative",
        assessment_task="treatment",
        question_type="clinical_case",
        query="치료 증례",
        index_path=index_path,
    )
    assert "IW-DISC-003" in context
    assert "0~1개" in context
    assert "post_exam" not in context
    assert "/Users/" not in context


def test_search_keeps_always_include_rule_without_mandatory_confounder(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    _write_index(index_path)
    load_item_writing_index.cache_clear()
    rules = search_item_writing_rules(
        exam_profile="kmle_summative",
        assessment_task="mechanism",
        index_path=index_path,
    )
    assert [rule["rule_id"] for rule in rules] == ["IW-DISC-003"]
