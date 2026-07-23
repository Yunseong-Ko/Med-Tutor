"""Curated item-writing policy retrieval for generation and review.

The index contains atomic rules and citations only. Raw sample questions and
source-document text are deliberately excluded from the generation context.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_INDEX_PATH = Path("data_private/rag/item_writing/rag_index.json")
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[가-힣]{2,}")


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(str(value or ""))}


@lru_cache(maxsize=4)
def load_item_writing_index(path: str | Path = DEFAULT_INDEX_PATH) -> dict[str, Any]:
    index_path = Path(path)
    if not index_path.exists():
        return {}
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def _matches(value: str, allowed: list[str]) -> bool:
    return "all" in allowed or value in allowed


def search_item_writing_rules(
    *,
    exam_profile: str = "kmle_summative",
    assessment_task: str = "diagnosis",
    question_type: str = "clinical_case",
    stages: list[str] | None = None,
    query: str = "",
    limit: int = 14,
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> list[dict[str, Any]]:
    """Return compact, profile-aware policy rules for an item-generation task."""
    index = load_item_writing_index(index_path)
    rules = index.get("rules") if isinstance(index.get("rules"), list) else []
    routing = index.get("retrieval_routing") if isinstance(index.get("retrieval_routing"), dict) else {}
    allowed_stages = set(stages or routing.get("generation_stages") or [])
    always = set(routing.get("always_include_rule_ids") or [])
    query_tokens = _tokens(" ".join([query, exam_profile, assessment_task, question_type]))
    ranked: list[tuple[int, str, dict[str, Any]]] = []

    for rule in rules:
        if not isinstance(rule, dict) or not bool(rule.get("prompt", False)):
            continue
        rule_id = str(rule.get("rule_id") or "")
        stage = str(rule.get("stage") or "")
        if allowed_stages and stage not in allowed_stages and rule_id not in always:
            continue
        profiles = [str(value) for value in rule.get("exam_profiles") or []]
        tasks = [str(value) for value in rule.get("assessment_tasks") or []]
        if not _matches(exam_profile, profiles) or not _matches(assessment_task, tasks):
            if rule_id not in always:
                continue
        haystack = " ".join(
            [
                str(rule.get("title") or ""),
                str(rule.get("statement_ko") or ""),
                " ".join(str(value) for value in rule.get("tags") or []),
                stage,
            ]
        )
        overlap = len(query_tokens & _tokens(haystack))
        severity = str(rule.get("severity") or "")
        score = overlap * 3 + (12 if rule_id in always else 0) + (3 if severity == "hard" else 1)
        ranked.append((score, rule_id, rule))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = [rule for _, _, rule in ranked[: max(1, int(limit))]]
    selected.sort(
        key=lambda rule: (
            0 if str(rule.get("rule_id")) in always else 1,
            str(rule.get("stage") or ""),
            str(rule.get("rule_id") or ""),
        )
    )
    return selected


def build_generation_item_writing_context(
    *,
    exam_profile: str = "kmle_summative",
    assessment_task: str = "diagnosis",
    question_type: str = "clinical_case",
    query: str = "",
    limit: int = 14,
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> str:
    """Build safe prompt context from curated rules, never from source text."""
    index = load_item_writing_index(index_path)
    if not index:
        return ""
    profiles = index.get("profiles") if isinstance(index.get("profiles"), dict) else {}
    profile = profiles.get(exam_profile) if isinstance(profiles.get(exam_profile), dict) else {}
    rules = search_item_writing_rules(
        exam_profile=exam_profile,
        assessment_task=assessment_task,
        question_type=question_type,
        query=query,
        limit=limit,
        index_path=index_path,
    )
    if not rules:
        return ""

    lines = [
        "[문항작성 원칙 RAG — 원문 문항이 아닌 검증된 원칙만 제공]",
        f"- exam_profile: {exam_profile}",
        f"- assessment_task: {assessment_task}",
    ]
    if profile.get("target_seconds_per_item"):
        lines.append(f"- 목표 풀이시간: 약 {profile['target_seconds_per_item']}초/문항(프로필 기준)")
    if profile.get("terminology_policy"):
        lines.append(f"- 용어: {profile['terminology_policy']}")
    for rule in rules:
        citations = ", ".join(
            f"{ref.get('source_id')} {ref.get('locator')}" for ref in rule.get("source_refs") or []
        )
        lines.append(
            f"- [{rule.get('rule_id')}/{rule.get('severity')}] {rule.get('statement_ko')} (근거: {citations})"
        )
    lines.extend(
        [
            "- 위 인용 표시는 출처 추적용이다. 표본 문항 문구를 재현·번역·근접복제하지 않는다.",
            "- 규칙 간 충돌 시 단서 필요성, 과업 정렬, 승인된 의학 근거, 저작권 안전을 우선한다.",
        ]
    )
    return "\n".join(lines)


def append_item_writing_context(prompt: str, **kwargs: Any) -> str:
    context = build_generation_item_writing_context(**kwargs)
    if not context:
        return prompt
    return f"{prompt.rstrip()}\n\n{context}"
