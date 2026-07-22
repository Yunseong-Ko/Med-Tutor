from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.services.kr_guideline_library as guideline_library
import src.services.medical_copilot as medical_copilot
from api_server import app
from src.services.medical_copilot import (
    build_medical_copilot_response,
    get_medical_copilot_status,
    match_ontology_concepts,
)


@pytest.fixture()
def copilot_root(tmp_path: Path) -> Path:
    concept_path = tmp_path / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    concept_path.parent.mkdir(parents=True, exist_ok=True)
    concept_path.write_text(
        json.dumps(
            {
                "concepts": {
                    "asthma": {
                        "disease_concept_id": "asthma",
                        "node_type": "disease",
                        "aliases": ["천식", "Asthma"],
                        "specialty": "pulmonology",
                        "edges": {"diagnosed_by": [{"id": "spirometry", "in_registry": False}]},
                        "evidence": {
                            "harrison": {
                                "edition": "22e",
                                "chapter": 1,
                                "title": "Asthma",
                                "page": 10,
                                "confidence": "curated",
                                "status": "harrison_22e_snapshot_validated",
                                "needs_review": True,
                            }
                        },
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    pages_path = tmp_path / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    pages_path.parent.mkdir(parents=True, exist_ok=True)
    pages = [
        {
            "chapter": 1,
            "pdf_page": 1,
            "printed_page": 10,
            "segment_text": "Asthma is characterized by variable symptoms and variable expiratory airflow limitation.",
        },
        {
            "chapter": 1,
            "pdf_page": 2,
            "printed_page": 11,
            "segment_text": "Diagnosis includes a compatible clinical history and objective demonstration of variable airflow limitation.",
        },
    ]
    pages_path.write_text("\n".join(json.dumps(row) for row in pages), encoding="utf-8")

    registry_path = tmp_path / guideline_library.REGISTRY_RELATIVE_PATH
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": "kr_guideline_source_registry.v1",
                "generated_at": "2026-07-18T00:00:00+00:00",
                "latest_checked_at": "2026-07-18",
                "sources": [
                    {
                        "source_id": "kr-cpg:test:asthma",
                        "title": "대한천식학회 천식 진료지침",
                        "issuing_body": "대한천식학회",
                        "jurisdiction": "KR",
                        "document_type": "clinical_practice_guideline",
                        "publication_year": 2026,
                        "priority": "P0",
                        "specialties": ["pulmonology"],
                        "clinical_axes": ["diagnosis", "treatment"],
                        "official_landing_url": "https://example.org/asthma",
                        "latest_status": "verified_latest_on_official_source",
                        "latest_checked_at": "2026-07-18",
                        "version": {"display_version": "2026"},
                        "development": {"keywords": "asthma 천식 diagnosis treatment"},
                        "attachments": [],
                        "needs_review": True,
                        "medical_approval": False,
                        "student_visible": False,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    overlay_path = tmp_path / medical_copilot.GUIDELINE_OVERLAY_RELATIVE_PATH
    overlay_path.write_text(
        json.dumps(
            {
                "concept_index": {},
                "candidate_concept_index": {"asthma": ["kr-cpg:test:asthma"]},
                "source_links": [
                    {
                        "source_id": "kr-cpg:test:asthma",
                        "title_rule_candidates": [
                            {"concept_id": "asthma", "matched_term": "천식", "resolved_in_registry": True}
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_status_and_korean_ontology_route(copilot_root: Path) -> None:
    status = get_medical_copilot_status(root=copilot_root)
    assert status["ready"] is True
    assert status["counts"] == {
        "ontology_concepts": 1,
        "harrison_mapped_concepts": 1,
        "harrison_page_segments": 2,
    }
    assert status["assets"]["harrison_raw_text_exposed_to_client"] is False

    matches = match_ontology_concepts("천식 진단을 공부하고 싶어", root=copilot_root)
    assert matches[0]["concept_id"] == "asthma"
    assert matches[0]["harrison"]["chapter"] == 1
    assert matches[0]["ontology_links"][0]["target"] == "spirometry"


@pytest.mark.parametrize(
    "wrapped",
    [
        '```json\n{"answer_summary":"ok","sections":[],"uncertainties":[],"suggested_followups":[]}\n```',
        '응답 JSON입니다.\n{"answer_summary":"ok","sections":[],"uncertainties":[],"suggested_followups":[]}',
        '\ufeff```JSON\n{"answer_summary":"ok","sections":[],"uncertainties":[],"suggested_followups":[]}\n```',
    ],
)
def test_model_json_parser_accepts_safe_wrappers(wrapped: str) -> None:
    payload = medical_copilot._parse_model_json(wrapped)
    assert payload["answer_summary"] == "ok"


def test_anthropic_provider_uses_schema_constrained_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, dict] = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "answer_summary": "요약",
                                "direct_answer_supported": True,
                                "key_points": [],
                                "sections": [],
                                "tables": [],
                                "uncertainties": [],
                                "suggested_followups": [],
                            },
                            ensure_ascii=False,
                        ),
                    }
                ]
            }

    def fake_post(_url: str, **kwargs) -> FakeResponse:
        captured["json"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setenv("PACCINE_COPILOT_PROVIDER", "anthropic")
    monkeypatch.setenv("PACCINE_COPILOT_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(medical_copilot.requests, "post", fake_post)

    raw = medical_copilot._compose_with_model(
        "prompt",
        {"provider": {"provider": "anthropic", "model": "claude-sonnet-4-6"}},
    )

    output_format = captured["json"]["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["schema"]["required"] == [
        "answer_summary",
        "direct_answer_supported",
        "key_points",
        "sections",
        "tables",
        "uncertainties",
        "suggested_followups",
    ]
    assert raw["direct_answer_supported"] is True
    assert output_format["schema"]["properties"]["key_points"]["minItems"] == 1
    assert "maxItems" not in output_format["schema"]["properties"]["key_points"]
    assert "maxItems" not in output_format["schema"]["properties"]["tables"]
    citations_schema = output_format["schema"]["properties"]["sections"]["items"]["properties"]["citations"]
    assert citations_schema["minItems"] == 1


def test_answer_schema_constrains_citations_to_retrieved_sources() -> None:
    schema = medical_copilot._answer_schema(["H2", "H1", "H1", "G1"])

    for collection in ("key_points", "sections", "tables"):
        citations = schema["properties"][collection]["items"]["properties"]["citations"]
        assert citations["minItems"] == 1
        assert citations["items"]["enum"] == ["G1", "H1", "H2"]


def test_grounded_answer_requires_harrison_citations_and_redacts_dose(
    copilot_root: Path,
) -> None:
    def composer(prompt: str, context: dict) -> dict:
        assert "Asthma is characterized" in prompt
        assert context["guidelines"][0]["title"] == "대한천식학회 천식 진료지침"
        return {
            "answer_summary": "천식 진단의 학습 핵심입니다.",
            "direct_answer_supported": True,
            "sections": [
                {
                    "id": "concept",
                    "title": "개념",
                    "body": "증상 변동성과 가변적 기류 제한을 함께 이해합니다. [H1]",
                    "citations": ["H1"],
                },
                {
                    "id": "guideline_guess",
                    "title": "국내 권고 추측",
                    "body": "국내 지침은 특정 치료를 권고합니다. [G1]",
                    "citations": ["G1"],
                },
                {
                    "id": "dose",
                    "title": "용량",
                    "body": "약제를 20 mg/day 투여합니다. [H1]",
                    "citations": ["H1"],
                },
            ],
            "uncertainties": ["국내 권고 세부 내용은 승인 전입니다."],
            "suggested_followups": ["진단 객관화 방법은?"],
        }

    response = build_medical_copilot_response(
        "천식 진단을 공부하고 싶어",
        mode="concept",
        composer=composer,
        root=copilot_root,
    )
    assert response["answer_status"] == "grounded_learning_draft"
    assert response["blocked"] is False
    assert [section["id"] for section in response["answer"]["sections"]] == ["concept", "dose"]
    assert response["harrison_sources"][0]["quote_exposed"] is False
    assert response["guideline_boundary"]["approved_claims_used"] == 0
    assert response["guideline_boundary"]["recommendations_generated_from_metadata"] is False
    serialized = json.dumps(response, ensure_ascii=False)
    assert "20 mg/day" not in serialized
    assert "구체 용량은 별도 프로토콜 확인" in serialized
    assert "Asthma is characterized" not in serialized
    assert "private_excerpt" not in serialized


def test_dose_redaction_preserves_laboratory_concentration() -> None:
    text = medical_copilot._redact_numeric_doses(
        "인슐린 10 units와 포도당을 사용하고 혈당 200 mg/dL, 소변량 0.5 mL/kg/h이면 재평가한다."
    )

    assert "10 units" not in text
    assert "200 mg/dL" in text
    assert "0.5 mL/kg/h" in text


def test_bm25_ranking_penalizes_long_generic_passages() -> None:
    scores = medical_copilot._bm25_scores(
        [
            "diagnosis asthma variable airflow limitation",
            "diagnosis asthma " + "generic clinical material " * 120,
        ],
        ["diagnosis", "asthma"],
    )

    assert scores[0] > scores[1]


def test_learning_question_not_withheld_for_guideline_mention(copilot_root: Path) -> None:
    """A Harrison-groundable study question must not be withheld merely because it
    mentions domestic guidelines. Guards the fix for the flaky over-withholding of
    legitimate concept/study questions (e.g. '...국내 가이드라인 관점에서 어떻게 공부...')."""
    seen: dict[str, str] = {}

    def composer(prompt: str, _context: dict) -> dict:
        seen["prompt"] = prompt
        return {
            "answer_summary": "천식 학습은 개념·기전·진단 원리부터 쌓습니다.",
            "direct_answer_supported": True,
            "key_points": [{"text": "증상 변동성을 먼저 이해합니다.", "citations": ["H1"]}],
            "sections": [
                {
                    "id": "roadmap",
                    "title": "학습 로드맵",
                    "body": "개념과 진단 원리를 먼저 이해합니다. [H1]",
                    "citations": ["H1"],
                }
            ],
            "tables": [],
            "uncertainties": [],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "천식을 Harrison과 국내 가이드라인 관점에서 어떻게 공부하면 좋을까?",
        composer=composer,
        root=copilot_root,
    )

    # The model prompt must instruct not to withhold learning questions on guideline mention.
    assert "학습형 질문" in seen["prompt"]
    assert "언급했다는 사실만으로 false로 두지 않는다" in seen["prompt"]
    # A grounded learning answer is surfaced, not withheld.
    assert response["answer_status"] == "grounded_learning_draft"
    assert response["blocked"] is False


def test_direct_answer_gap_is_concise_and_blocks_tangential_fill(copilot_root: Path) -> None:
    def composer(_prompt: str, _context: dict) -> dict:
        return {
            "answer_summary": "질문한 약제 선택은 현재 근거에서 직접 확인되지 않습니다.",
            "direct_answer_supported": False,
            "key_points": [
                {"text": "인접 질환의 치료 원칙입니다.", "citations": ["H1"]},
            ],
            "sections": [
                {
                    "id": "gap",
                    "title": "근거 한계",
                    "body": "질문의 핵심 약제 선택을 직접 확인할 수 없습니다. [H1]",
                    "citations": ["H1"],
                },
                {
                    "id": "tangential",
                    "title": "주변 치료",
                    "body": "질문과 다른 치료 내용을 길게 설명합니다. [H1]",
                    "citations": ["H1"],
                },
            ],
            "tables": [
                {
                    "title": "주변 비교",
                    "columns": ["구분", "내용"],
                    "rows": [["다른 치료", "질문과 무관"]],
                    "citations": ["H1"],
                }
            ],
            "uncertainties": ["승인된 직접 근거가 필요합니다."],
            "suggested_followups": ["직접 근거가 연결된 뒤 다시 질문하기"],
        }

    response = build_medical_copilot_response(
        "천식에 특정 신약이 효과적인가?",
        composer=composer,
        root=copilot_root,
    )

    assert response["answer_status"] == "answer_withheld_direct_support_missing"
    assert response["blocked"] is True
    assert response["reasons"] == ["direct_answer_evidence_missing"]
    assert response["answer"]["direct_answer_supported"] is False
    assert response["answer"]["key_points"] == []
    assert len(response["answer"]["sections"]) == 1
    assert response["answer"]["sections"][0]["title"] == "현재 확인 가능한 범위"
    assert response["answer"]["tables"] == []


def test_missing_direct_answer_supported_flag_fails_closed(copilot_root: Path) -> None:
    def composer(_prompt: str, _context: dict) -> dict:
        return {
            "answer_summary": "모델이 필수 판정 필드를 생략했습니다.",
            "key_points": [{"text": "표면상 근거가 있습니다.", "citations": ["H1"]}],
            "sections": [
                {
                    "id": "unsafe_default",
                    "title": "필수 필드 누락",
                    "body": "필수 판정 없이 본문을 통과시키면 안 됩니다. [H1]",
                    "citations": ["H1"],
                }
            ],
            "tables": [],
            "uncertainties": [],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "천식 진단을 설명해줘",
        composer=composer,
        root=copilot_root,
    )

    assert response["answer_status"] == "answer_withheld_direct_support_missing"
    assert response["blocked"] is True
    assert response["answer"]["direct_answer_supported"] is False


def test_cross_lingual_entailment_shadow_reports_without_blocking_or_raw_text(
    copilot_root: Path,
) -> None:
    def composer(_prompt: str, _context: dict) -> dict:
        return {
            "answer_summary": "천식 진단은 증상 변동성과 객관적 검사를 함께 봅니다.",
            "direct_answer_supported": True,
            "key_points": [{"text": "가변성을 확인합니다.", "citations": ["H1"]}],
            "sections": [
                {
                    "id": "diagnosis",
                    "title": "진단",
                    "body": "증상과 객관적 검사를 함께 확인합니다. [H1]",
                    "citations": ["H1"],
                }
            ],
            "tables": [],
            "uncertainties": [],
            "suggested_followups": [],
        }

    def judge(prompt: str, context: dict) -> dict:
        assert "Asthma is characterized" in prompt
        assert context["evidence"][0]["source_id"] == "H1"
        return {
            "claims": [
                {
                    "claim_id": item["claim_id"],
                    "supported": not item["claim_id"].startswith("summary"),
                    "source_ids": item["source_ids"],
                }
                for item in context["claims"]
            ]
        }

    response = build_medical_copilot_response(
        "천식 진단 원리를 설명해줘",
        composer=composer,
        entailment_judge=judge,
        root=copilot_root,
    )

    shadow = response["quality_validation"]["entailment_shadow"]
    assert response["blocked"] is False
    assert shadow["status"] == "issues_detected"
    assert shadow["unsupported_claim_ids"] == ["summary_1"]
    assert shadow["blocks_answer"] is False
    serialized = json.dumps(response, ensure_ascii=False)
    assert "Asthma is characterized" not in serialized
    assert "private_excerpt" not in serialized


def test_current_korean_guideline_specifics_wait_for_released_claim(
    copilot_root: Path,
) -> None:
    def composer(_prompt: str, _context: dict) -> dict:
        raise AssertionError("국내 세부 권고 보류는 모델 호출 전에 결정되어야 합니다.")

    response = build_medical_copilot_response(
        "국내 천식 진료지침에서 어떤 약제를 우선 사용해?",
        composer=composer,
        root=copilot_root,
    )

    assert response["guidelines"][0]["source_id"] == "kr-cpg:test:asthma"
    assert response["answer_status"] == "answer_withheld_current_guideline_claim_pending"
    assert response["blocked"] is True
    assert response["reasons"] == ["current_korean_guideline_claim_pending"]
    assert response["answer"]["key_points"] == []
    assert "특정 약제를 우선" not in response["answer"]["answer_summary"]
    assert response["guideline_boundary"]["current_guideline_claim_pending"] is True
    assert response["guideline_boundary"]["query_class"] == "korean_current_recommendation"


def test_general_harrison_treatment_question_is_not_reclassified_as_korean_claim(
    copilot_root: Path,
) -> None:
    def composer(_prompt: str, context: dict) -> dict:
        assert context["current_guideline_claim_pending"] is False
        assert context["guideline_query_policy"]["query_class"] == "general_harrison_learning"
        return {
            "answer_summary": "천식의 일반 치료 원칙입니다.",
            "direct_answer_supported": True,
            "key_points": [{"text": "항염증 치료를 중심으로 봅니다.", "citations": ["H1"]}],
            "sections": [
                {
                    "id": "treatment",
                    "title": "일반 치료 원칙",
                    "body": "Harrison 근거 범위의 일반 치료 원칙을 설명합니다. [H1]",
                    "citations": ["H1"],
                }
            ],
            "tables": [],
            "uncertainties": [],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "천식 치료 원칙을 설명해줘",
        composer=composer,
        root=copilot_root,
    )

    assert response["answer_status"] == "grounded_learning_draft"
    assert response["blocked"] is False


@pytest.mark.parametrize(
    ("query", "expected_class", "requires_release"),
    [
        (
            "당뇨병을 Harrison과 국내 가이드라인 관점에서 어떻게 공부하면 좋을까?",
            "general_learning_with_guideline_context",
            False,
        ),
        ("국내 가이드라인의 목표 HbA1c는?", "korean_current_recommendation", True),
        ("국내에서 당뇨병은 어떻게 진단해?", "korean_current_recommendation", True),
        ("국내 가이드라인 원문은 어디서 확인해?", "guideline_source_navigation", False),
        ("한국인 당뇨병의 병태생리는?", "general_learning_with_guideline_context", False),
        ("고혈압 1차 약제는?", "general_harrison_learning", False),
    ],
)
def test_guideline_question_policy_is_jurisdiction_aware(
    query: str,
    expected_class: str,
    requires_release: bool,
) -> None:
    policy = medical_copilot.classify_guideline_question(query)

    assert policy["query_class"] == expected_class
    assert policy["requires_released_claim"] is requires_release


def test_safe_bold_markers_survive_for_student_typography(copilot_root: Path) -> None:
    def composer(_prompt: str, _context: dict) -> dict:
        return {
            "answer_summary": "**증상 변동성**과 객관적 검사를 함께 봅니다.",
            "direct_answer_supported": True,
            "key_points": [
                {"text": "**핵심:** 가변성을 확인합니다.", "citations": ["H1"]}
            ],
            "sections": [
                {
                    "id": "diagnosis",
                    "title": "진단 접근",
                    "body": "**가변적 기류 제한**을 객관적으로 확인합니다. [H1]",
                    "citations": ["H1"],
                }
            ],
            "tables": [],
            "uncertainties": [],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "천식 진단 개념 설명",
        composer=composer,
        root=copilot_root,
    )

    assert "**증상 변동성**" in response["answer"]["answer_summary"]
    assert "**핵심:**" in response["answer"]["key_points"][0]["text"]
    assert "**가변적 기류 제한**" in response["answer"]["sections"][0]["body"]


def test_ontology_followups_hide_axes_without_direct_harrison_anchor(copilot_root: Path) -> None:
    def composer(_prompt: str, context: dict) -> dict:
        assert context["ontology_followup_candidates"] == []
        return {
            "answer_summary": "천식 진단 개요입니다.",
            "direct_answer_supported": True,
            "key_points": [{"text": "가변성을 확인합니다.", "citations": ["H1"]}],
            "sections": [
                {
                    "id": "diagnosis",
                    "title": "진단 접근",
                    "body": "가변적 기류 제한을 확인합니다. [H1]",
                    "citations": ["H1"],
                }
            ],
            "tables": [],
            "uncertainties": [],
            "suggested_followups": ["모델이 임의로 추가한 네 번째 질문"],
        }

    response = build_medical_copilot_response(
        "천식 진단 기준을 설명해줘",
        composer=composer,
        root=copilot_root,
    )

    followups = response["answer"]["suggested_followups"]
    assert followups == []


def test_ontology_followups_are_single_axis_and_harrison_preflighted(
    copilot_root: Path,
) -> None:
    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.extend(
        [
            {
                "chapter": 1,
                "pdf_page": 3,
                "printed_page": 12,
                "segment_text": "Asthma pathophysiology involves chronic airway inflammation and variable airflow obstruction.",
            },
            {
                "chapter": 1,
                "pdf_page": 4,
                "printed_page": 13,
                "segment_text": "Asthma treatment and management use controller therapy with monitoring of response.",
            },
        ]
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    concepts = match_ontology_concepts("천식", root=copilot_root)

    followups = medical_copilot._ontology_followup_candidates(
        concepts,
        [],
        root=copilot_root,
    )

    assert followups == [
        "천식의 진단 원리와 핵심 검사 소견을 Harrison 기준으로 설명해줘",
        "천식의 핵심 병태생리와 기전을 Harrison 기준으로 설명해줘",
        "천식의 일반적인 치료 원칙을 Harrison 기준으로 설명해줘",
    ]


def test_ontology_answer_scaffold_is_structure_only(copilot_root: Path) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["asthma"]["clinical_axes"] = {
        "pathophysiology": {"summary": "UNAPPROVED AXIS FREE TEXT"},
        "treatment": {"principles": "UNAPPROVED TREATMENT FREE TEXT"},
    }
    payload["concepts"]["asthma"]["edges"] = {
        "diagnosed_by": [
            {"id": "spirometry", "in_registry": True},
            {"id": "UNAPPROVED EDGE FREE TEXT", "in_registry": False},
        ]
    }
    payload["concepts"]["spirometry"] = {
        "node_type": "test_procedure",
        "aliases": [],
        "specialty": "pulmonology",
        "edges": {},
        "evidence": {},
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    captured: dict[str, str] = {}

    def composer(prompt: str, context: dict) -> dict:
        captured["prompt"] = prompt
        scaffold = context["ontology_answer_scaffold"]
        assert scaffold[0]["requested_slots"] == ["diagnosis"]
        assert scaffold[0]["available_slots"] == ["mechanism", "diagnosis", "treatment", "safety"]
        assert scaffold[0]["relations"] == [
            {
                "relation": "diagnosed_by",
                "target_concept_id": "spirometry",
                "section_slot": "diagnosis",
            }
        ]
        return {
            "answer_summary": "천식 진단 원리입니다.",
            "direct_answer_supported": True,
            "key_points": [{"text": "가변성을 확인합니다.", "citations": ["H1"]}],
            "sections": [
                {
                    "id": "diagnosis",
                    "title": "진단 원리",
                    "body": "증상과 객관적 기류 제한을 함께 확인합니다. [H1]",
                    "citations": ["H1"],
                }
            ],
            "tables": [],
            "uncertainties": [],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "천식 진단 원리를 설명해줘",
        composer=composer,
        root=copilot_root,
    )

    assert response["blocked"] is False
    assert response["ontology"]["answer_scaffold"][0]["content_policy"].startswith("structure_only")
    assert "UNAPPROVED AXIS FREE TEXT" not in captured["prompt"]
    assert "UNAPPROVED TREATMENT FREE TEXT" not in captured["prompt"]
    assert "UNAPPROVED EDGE FREE TEXT" not in captured["prompt"]


def test_ontology_differential_scaffold_drops_cross_specialty_edges(copilot_root: Path) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["asthma"]["edges"] = {
        "differential_of": [
            {"id": "copd", "in_registry": True},
            {"id": "broca_aphasia", "in_registry": True},
        ]
    }
    payload["concepts"]["copd"] = {
        "node_type": "disease",
        "aliases": [],
        "specialty": "pulmonology",
        "edges": {},
        "evidence": {},
    }
    payload["concepts"]["broca_aphasia"] = {
        "node_type": "disease",
        "aliases": [],
        "specialty": "neurology",
        "edges": {},
        "evidence": {},
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    concepts = match_ontology_concepts("천식 감별", root=copilot_root)
    scaffold = medical_copilot.build_ontology_answer_scaffold(
        concepts,
        ["diagnosis"],
        root=copilot_root,
    )

    assert scaffold[0]["relations"] == [
        {
            "relation": "differential_of",
            "target_concept_id": "copd",
            "section_slot": "differential",
        }
    ]


def test_citation_validation_accepts_common_model_shapes(copilot_root: Path) -> None:
    def composer(_prompt: str, _context: dict) -> dict:
        return {
            "answer_summary": "천식 진단의 학습 핵심입니다.",
            "direct_answer_supported": True,
            "sections": [
                {
                    "id": "normalized_citation",
                    "title": "개념",
                    "body": "증상 변동성과 가변적 기류 제한을 함께 확인합니다.",
                    "citations": [{"source_id": "[h01]"}],
                }
            ],
            "uncertainties": [],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "천식 진단을 공부하고 싶어",
        composer=composer,
        root=copilot_root,
    )

    assert response["answer_status"] == "grounded_learning_draft"
    section = response["answer"]["sections"][0]
    assert section["citations"] == ["H1"]
    assert section["body"].endswith("[H1]")


def test_unique_harrison_locator_is_accepted_as_citation(copilot_root: Path) -> None:
    def composer(_prompt: str, _context: dict) -> dict:
        return {
            "answer_summary": "천식 진단의 학습 핵심입니다.",
            "direct_answer_supported": True,
            "sections": [
                {
                    "id": "locator_citation",
                    "title": "개념",
                    "body": "임상력과 객관적인 기류 제한 확인을 함께 봅니다.",
                    "citations": ["Harrison 22e · Ch.1 · p.10"],
                }
            ],
            "uncertainties": [],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "천식 진단을 공부하고 싶어",
        composer=composer,
        root=copilot_root,
    )

    assert response["answer_status"] == "grounded_learning_draft"
    citation = response["answer"]["sections"][0]["citations"][0]
    cited_source = next(
        source for source in response["harrison_sources"] if source["source_id"] == citation
    )
    assert cited_source["printed_page"] == 10


def test_harmless_top_level_model_wrapper_is_unwrapped(copilot_root: Path) -> None:
    def composer(_prompt: str, _context: dict) -> dict:
        return {
            "response": {
                "answer_summary": "천식 진단의 학습 핵심입니다.",
                "direct_answer_supported": True,
                "sections": [
                    {
                        "id": "wrapped",
                        "title": "개념",
                        "body": "임상력과 객관적인 기류 제한을 함께 봅니다. [H1]",
                        "citations": ["H1"],
                    }
                ],
                "uncertainties": [],
                "suggested_followups": [],
            }
        }

    response = build_medical_copilot_response(
        "천식 진단을 공부하고 싶어",
        composer=composer,
        root=copilot_root,
    )

    assert response["answer_status"] == "grounded_learning_draft"
    assert response["answer"]["sections"][0]["id"] == "wrapped"


def test_clinical_answer_key_points_and_table_keep_valid_citations(
    copilot_root: Path,
) -> None:
    def composer(_prompt: str, _context: dict) -> dict:
        return {
            "response": {
                "answer_summary": "천식 진단은 증상 변동성과 객관적 기류 제한을 함께 확인합니다.",
                "direct_answer_supported": True,
                "key_points": [
                    {"text": "증상은 시간에 따라 변할 수 있습니다.", "citations": ["H1"]},
                    {"text": "객관적 기류 제한을 확인합니다.", "citations": ["H2"]},
                    {"text": "임상력과 검사 결과를 함께 해석합니다.", "citations": ["H1", "H2"]},
                ],
                "sections": [
                    {
                        "id": "diagnostic_frame",
                        "title": "진단 프레임",
                        "body": "- 증상 변동성 확인\n- 객관적 기류 제한 확인 [H1] [H2]",
                        "citations": ["H1", "H2"],
                    }
                ],
                "tables": [
                    {
                        "title": "진단 확인 축",
                        "columns": ["축", "확인 내용"],
                        "rows": [["증상", "시간에 따른 변동"], ["검사", "가변적 기류 제한"]],
                        "citations": ["H1", "H2"],
                    }
                ],
                "uncertainties": [],
                "suggested_followups": [],
            }
        }

    response = build_medical_copilot_response(
        "천식 진단을 표로 정리해줘",
        composer=composer,
        root=copilot_root,
    )

    answer = response["answer"]
    assert answer["answer_summary"].startswith("천식 진단은")
    assert len(answer["key_points"]) == 3
    assert answer["key_points"][1]["citations"] == ["H2"]
    assert answer["sections"][0]["title"] == "진단 프레임"
    assert "\n" in answer["sections"][0]["body"]
    assert answer["tables"][0]["columns"] == ["축", "확인 내용"]
    assert answer["tables"][0]["citations"] == ["H1", "H2"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("RPI랑 corrected reticulocyte count 차이를 비교해줘", "comparison"),
        ("Hodgkin lymphoma staging 정리", "classification_or_staging"),
        ("AML 3+7 regimen 설명", "treatment_or_regimen"),
        ("alemtuzumab 기전", "mechanism"),
        ("torticollis", "brief_topic"),
        ("다음 환자 처치는? ① 관찰 ② 면역글로불린", "mcq_vignette"),
    ],
)
def test_answer_template_matches_question_shape(query: str, expected: str) -> None:
    assert medical_copilot.detect_answer_template(query) == expected


def test_cml_mechanism_query_prioritizes_pathogenesis_pages(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["chronic_myeloid_leukemia"] = {
        "disease_concept_id": "chronic_myeloid_leukemia",
        "node_type": "disease",
        "aliases": ["만성골수성백혈병", "CML", "chronic myeloid leukemia"],
        "specialty": "hematology_oncology",
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 110,
                "title": "Chronic Myeloid Leukemia",
                "page": 834,
                "confidence": "curated",
                "status": "harrison_22e_snapshot_validated",
                "needs_review": True,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.extend(
        [
            {
                "chapter": 110,
                "pdf_page": 1,
                "printed_page": 834,
                "segment_text": (
                    "Chronic myeloid leukemia is driven by the BCR::ABL1 chimeric gene "
                    "encoding a constitutively active tyrosine kinase after t(9;22), "
                    "the Philadelphia chromosome. This molecular pathogenesis drives proliferation."
                ),
            },
            {
                "chapter": 110,
                "pdf_page": 2,
                "printed_page": 835,
                "segment_text": (
                    "The BCR::ABL1 oncoprotein activates signal transduction and signaling pathways "
                    "that promote myeloid proliferation and reduce apoptosis."
                ),
            },
            {
                "chapter": 110,
                "pdf_page": 10,
                "printed_page": 843,
                "segment_text": ("Chronic Myeloid Leukemia survival outcome " * 12).strip(),
            },
        ]
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    def composer(_prompt: str, context: dict) -> dict:
        assert context["answer_template"] == "mechanism"
        assert "mechanism" in context["intents"]
        assert {row["printed_page"] for row in context["harrison_internal"][:2]} == {834, 835}
        return {
            "answer_summary": "CML은 BCR::ABL1 융합 단백질의 지속적 kinase 활성으로 발생합니다.",
            "direct_answer_supported": True,
            "key_points": [{"text": "BCR::ABL1이 핵심 분자 기전입니다.", "citations": ["H1", "H2"]}],
            "sections": [
                {
                    "id": "mechanism",
                    "title": "분자 기전",
                    "body": "t(9;22)로 형성된 BCR::ABL1이 증식 신호를 활성화합니다. [H1] [H2]",
                    "citations": ["H1", "H2"],
                }
            ],
            "tables": [],
            "uncertainties": [],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "만성골수성백혈병의 핵심 병태생리와 기전은?",
        composer=composer,
        root=copilot_root,
    )

    assert response["answer_status"] == "grounded_learning_draft"
    assert response["blocked"] is False
    assert {row["printed_page"] for row in response["harrison_sources"][:2]} == {834, 835}
    # This fixture contains mechanism passages only. Do not advertise a
    # diagnosis/treatment/follow-up question that the next retrieval cannot
    # directly ground.
    assert response["answer"]["suggested_followups"] == []


def test_harrison_fulltext_fallback_is_not_blocked_by_missing_ontology(
    copilot_root: Path,
) -> None:
    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.append(
        {
            "chapter": 66,
            "pdf_page": 5,
            "printed_page": 447,
            "source_file": "066_Anemia and Polycythemia.pdf",
            "segment_text": (
                "The reticulocyte count measures red cell production. "
                "Corrected reticulocyte count equals measured reticulocyte count "
                "times patient hematocrit divided by normal hematocrit."
            ),
        }
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    def composer(prompt: str, context: dict) -> dict:
        assert context["concepts"] == []
        assert context["answer_template"] == "comparison"
        assert "Corrected reticulocyte count" in prompt
        return {
            "answer_summary": "CRC는 헤마토크릿을 보정한 망상적혈구 비율입니다.",
            "direct_answer_supported": True,
            "key_points": [
                {"text": "망상적혈구는 골수 적혈구 생산을 반영합니다.", "citations": ["H1"]},
                {"text": "CRC는 환자 헤마토크릿으로 보정합니다.", "citations": ["H1"]},
                {"text": "질문한 두 지표의 범위를 구분해 해석합니다.", "citations": ["H1"]},
            ],
            "sections": [
                {
                    "id": "comparison",
                    "title": "공식과 의미",
                    "body": "CRC = retic% × 환자 Hct / 정상 Hct [H1]",
                    "citations": ["H1"],
                }
            ],
            "tables": [],
            "uncertainties": ["RPI 성숙계수는 이번 발췌 범위에서 확인되지 않습니다."],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "RPI랑 corrected reticulocyte count 차이를 비교해줘",
        composer=composer,
        root=copilot_root,
    )

    assert response["answer_status"] == "grounded_learning_draft"
    assert response["ontology_matches"] == []
    assert response["harrison_sources"][0]["chapter"] == 66
    assert response["harrison_sources"][0]["retrieval_route"] == "full_text_fallback"
    assert response["answer_template"] == "comparison"
    assert response["answer"]["tables"][0]["title"] == "핵심 비교"
    assert response["answer"]["tables"][0]["columns"] == ["구분", "핵심 내용"]


def test_korean_symptom_routes_to_harrison_symptom_concept(copilot_root: Path) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["dyspnea"] = {
        "node_type": "symptom",
        "aliases": [],
        "specialty": "pulmonology",
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 2,
                "title": "Dyspnea",
                "page": 20,
                "needs_review": True,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    matches = match_ontology_concepts(
        "60세 환자가 호흡 곤란과 피로를 호소한다",
        root=copilot_root,
    )

    assert matches[0]["concept_id"] == "dyspnea"
    assert any(str(item).startswith("symptom:") for item in matches[0]["match_basis"])


def test_unrouted_symptom_query_does_not_show_unrelated_guideline(
    copilot_root: Path,
) -> None:
    response = build_medical_copilot_response(
        "피로와 변비가 같이 있으면 무엇을 확인해야 하나요?",
        generate_answer=False,
        root=copilot_root,
    )

    assert response["answer_status"] == "evidence_insufficient"
    assert response["guidelines"] == []


def test_biomarker_expansion_centers_long_passage_on_treatment_evidence() -> None:
    text = (
        "Colorectal cancer overview. "
        + ("general staging context " * 300)
        + "Patients without RAS or RAF mutations may respond to epidermal growth factor antibodies "
        + "such as cetuximab and panitumumab."
    )
    terms = medical_copilot._expanded_query_tokens(
        "Colorectal cancer에서 EGFR amplification 치료 옵션"
    )

    bounded = medical_copilot._bounded_passage(text, terms, max_chars=1200)

    assert "cetuximab" in bounded
    assert "panitumumab" in bounded


def test_biomarker_passage_expansion_does_not_pollute_ontology_route(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["growth_hormone_deficiency"] = {
        "node_type": "disease",
        "aliases": ["Growth hormone deficiency"],
        "specialty": "endocrinology_metabolism",
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 2,
                "title": "Growth Hormone Deficiency",
                "page": 20,
                "needs_review": True,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    matches = match_ontology_concepts(
        "천식에서 EGFR amplification을 확인할까?",
        root=copilot_root,
    )

    assert matches[0]["concept_id"] == "asthma"
    assert all(item["concept_id"] != "growth_hormone_deficiency" for item in matches)


def test_colon_cancer_synonym_routes_to_colorectal_cancer(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["colorectal_cancer"] = {
        "node_type": "neoplasm",
        "aliases": ["대장암", "Colorectal cancer", "CRC"],
        "specialty": "gastroenterology_hepatology",
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 86,
                "title": "Colorectal Cancer",
                "page": 653,
                "needs_review": True,
            }
        },
    }
    payload["concepts"]["breast_cancer"] = {
        "node_type": "neoplasm",
        "aliases": ["Breast cancer"],
        "specialty": "hematology_oncology",
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 84,
                "title": "Breast Cancer",
                "page": 632,
                "needs_review": True,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    matches = match_ontology_concepts(
        "Colon cancer에서 EGFR amplification mutation 치료약제는?",
        root=copilot_root,
    )

    assert [item["concept_id"] for item in matches] == ["colorectal_cancer"]


@pytest.mark.parametrize(
    ("query", "concept_id"),
    [
        ("조현병 치료를 설명해줘", "schizophrenia"),
        ("세균성 수막염의 진단은?", "bacterial_meningitis"),
        ("전신홍반루푸스의 진단 기준은?", "systemic_lupus_erythematosus"),
        ("류마티스관절염의 치료 원칙은?", "rheumatoid_arthritis"),
        ("당뇨병성 케톤산증의 기전은?", "diabetic_ketoacidosis"),
        ("제2형 당뇨병의 치료 원칙은?", "type_2_diabetes"),
        ("신증후군의 병태생리는?", "nephrotic_syndrome"),
        ("임신부가 수두에 노출되면?", "varicella"),
    ],
)
def test_common_korean_learner_terms_route_to_canonical_concept(
    query: str,
    concept_id: str,
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"][concept_id] = {
        "node_type": "disease",
        "aliases": [],
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 99,
                "title": concept_id.replace("_", " ").title(),
                "page": 999,
                "needs_review": True,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    matches = match_ontology_concepts(query, root=copilot_root)

    assert matches
    assert matches[0]["concept_id"] == concept_id


def test_strong_bacterial_meningitis_alias_drops_weak_bacterial_prefixes(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"].update(
        {
            "bacterial_meningitis": {
                "node_type": "disease",
                "aliases": [],
                "edges": {},
                "evidence": {"harrison": {"chapter": 143, "title": "Meningitis", "page": 1100}},
            },
            "bacterial_vaginosis": {
                "node_type": "disease",
                "aliases": ["세균성 질염"],
                "edges": {},
                "evidence": {"harrison": {"chapter": 151, "title": "Vaginitis", "page": 1200}},
            },
        }
    )
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    matches = match_ontology_concepts("세균성 수막염의 진단과 감별은?", root=copilot_root)

    assert [item["concept_id"] for item in matches] == ["bacterial_meningitis"]


def test_short_korean_alias_does_not_match_inside_more_specific_disease(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["gastroenteritis"] = {
        "node_type": "disease",
        "aliases": ["위장염", "장염"],
        "edges": {},
        "evidence": {"harrison": {"chapter": 209, "title": "Gastroenteritis", "page": 1600}},
    }
    payload["concepts"]["acute_pancreatitis"] = {
        "node_type": "disease",
        "aliases": [],
        "edges": {},
        "evidence": {"harrison": {"chapter": 359, "title": "Pancreatitis", "page": 2745}},
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    matches = match_ontology_concepts("급성췌장염의 초기 치료는?", root=copilot_root)

    assert [item["concept_id"] for item in matches] == ["acute_pancreatitis"]


def test_diabetes_treatment_routes_to_management_chapter(copilot_root: Path) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["type_2_diabetes"] = {
        "node_type": "disease",
        "aliases": [],
        "edges": {},
        "evidence": {
            "harrison": {
                "chapter": 417,
                "title": "Diabetes Mellitus: Complications",
                "page": 3221,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.append(
        {
            "chapter": 416,
            "pdf_page": 1,
            "printed_page": 3205,
            "source_file": "416_Diabetes Mellitus Management and Therapies.pdf",
            "segment_text": "Diabetes mellitus management and therapies include individualized comprehensive care.",
        }
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    response = build_medical_copilot_response(
        "제2형 당뇨병의 치료 원칙은?",
        generate_answer=False,
        root=copilot_root,
    )

    assert response["harrison_sources"][0]["chapter"] == 416


def test_hiv_diagnosis_prioritizes_diagnostic_section_over_general_evaluation(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["hiv_anonymous_testing"] = {
        "node_type": "disease",
        "aliases": [],
        "edges": {},
        "evidence": {"harrison": {"chapter": 394, "title": "Incorrect Legacy Chapter", "page": 3020}},
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.extend(
        [
            {
                "chapter": 208,
                "pdf_page": 34,
                "printed_page": 1589,
                "source_file": "208_Human Immunodeficiency Virus Disease AIDS and Related Disorders.pdf",
                "segment_text": "DIAGNOSIS OF HIV INFECTION. Fourth-generation antigen-antibody testing is used in the diagnostic algorithm.",
            },
            {
                "chapter": 208,
                "pdf_page": 42,
                "printed_page": 1597,
                "source_file": "208_Human Immunodeficiency Virus Disease AIDS and Related Disorders.pdf",
                "segment_text": ("HIV disease evaluation test monitoring " * 18).strip(),
            },
        ]
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    response = build_medical_copilot_response(
        "HIV 감염의 진단 검사는?",
        generate_answer=False,
        root=copilot_root,
    )

    assert response["harrison_sources"][0]["chapter"] == 208
    assert response["harrison_sources"][0]["printed_page"] == 1589


def test_generic_cancer_token_does_not_route_to_arbitrary_organ_cancer(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["breast_cancer"] = {
        "node_type": "neoplasm",
        "aliases": ["Breast cancer"],
        "specialty": "hematology_oncology",
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 84,
                "title": "Breast Cancer",
                "page": 632,
                "needs_review": True,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    matches = match_ontology_concepts("cancer treatment", root=copilot_root)

    assert matches == []


def test_query_subject_routes_before_named_complication(copilot_root: Path) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"].update(
        {
            "atrial_fibrillation": {
                "node_type": "disease",
                "aliases": ["심방세동"],
                "edges": {},
                "evidence": {"harrison": {"chapter": 258, "title": "Atrial Fibrillation", "page": 1947}},
            },
            "acute_ischemic_stroke": {
                "node_type": "disease",
                "aliases": ["뇌졸중"],
                "edges": {},
                "evidence": {"harrison": {"chapter": 438, "title": "Ischemic Stroke", "page": 3440}},
            },
        }
    )
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    matches = match_ontology_concepts(
        "심방세동의 ECG 진단 소견과 뇌졸중 위험의 핵심은?",
        root=copilot_root,
    )

    assert matches[0]["concept_id"] == "atrial_fibrillation"


def test_privacy_block_happens_before_retrieval(copilot_root: Path) -> None:
    response = build_medical_copilot_response(
        "천식 환자번호: AB-12345, 전화번호 010-1234-5678",
        root=copilot_root,
    )
    assert response["status"] == "privacy_blocked"
    assert response["safety"]["retrieval_started"] is False
    serialized = json.dumps(response, ensure_ascii=False)
    assert "AB-12345" not in serialized
    assert "010-1234-5678" not in serialized


def test_only_released_guideline_claims_can_ground_g_citations(
    monkeypatch: pytest.MonkeyPatch, copilot_root: Path
) -> None:
    monkeypatch.setattr(
        medical_copilot,
        "list_valid_released_claims",
        lambda **_kwargs: [
            {
                "claim_id": "kr-claim:test",
                "source_id": "kr-cpg:test:asthma",
                "source_title": "대한천식학회 천식 진료지침",
                "clinical_axis": "treatment",
                "subject_concept_id": "asthma",
                "relation": "recommends",
                "object_text": "증상과 위험도 평가에 따라 치료 단계를 조정한다.",
                "population": "천식 성인",
                "recommendation_strength": "strong",
                "evidence_grade": "A",
                "effective_version": "2026",
                "page": 7,
                "release": {"review_due_at": "2027-01-01T00:00:00+00:00"},
            }
        ],
    )

    def composer(prompt: str, context: dict) -> dict:
        assert "human_released_atomic_claim_only" in prompt
        assert len(context["approved_guideline_claims"]) == 1
        return {
            "answer_summary": "승인된 국내 지침의 학습 포인트입니다.",
            "direct_answer_supported": True,
            "sections": [
                {
                    "id": "kr_guideline",
                    "title": "국내 권고",
                    "body": "증상과 위험도 평가에 따라 치료 단계를 조정합니다. [G1]",
                    "citations": ["G1"],
                }
            ],
            "uncertainties": [],
            "suggested_followups": [],
        }

    response = build_medical_copilot_response(
        "천식 치료 원칙",
        composer=composer,
        root=copilot_root,
    )
    assert response["answer"]["sections"][0]["citations"] == ["G1"]
    assert response["guideline_boundary"]["approved_claims_used"] == 1
    assert response["approved_guideline_claims"][0]["source_id"] == "G1"


def test_api_returns_locator_only_when_generation_is_disabled(
    monkeypatch: pytest.MonkeyPatch, copilot_root: Path
) -> None:
    monkeypatch.setattr(medical_copilot, "DEFAULT_ROOT", copilot_root)
    monkeypatch.setattr(guideline_library, "DEFAULT_ROOT", copilot_root)
    response = TestClient(app).post(
        "/api/student/medical-copilot",
        json={"query": "천식 진단", "mode": "concept", "generate_answer": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_status"] == "retrieval_ready_answer_not_requested"
    assert payload["ontology_matches"][0]["concept_id"] == "asthma"
    assert payload["harrison_sources"][0]["source_id"] == "H1"
    assert payload["guidelines"][0]["source_id"] == "kr-cpg:test:asthma"
    assert "segment_text" not in response.text
    assert "private_excerpt" not in response.text


def test_concept_retrieval_covers_diagnosis_and_treatment_axes(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["acute_pancreatitis"] = {
        "node_type": "disease",
        "aliases": ["급성췌장염", "acute pancreatitis"],
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 359,
                "title": "Acute and Chronic Pancreatitis",
                "page": 2745,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.extend(
        [
            {
                "chapter": 359,
                "pdf_page": 2,
                "printed_page": 2745,
                "source_file": "359_Acute and Chronic Pancreatitis.pdf",
                "segment_text": "DIAGNOSIS Acute pancreatitis is diagnosed when two of three diagnostic criteria are present.",
            },
            {
                "chapter": 359,
                "pdf_page": 4,
                "printed_page": 2747,
                "source_file": "359_Acute and Chronic Pancreatitis.pdf",
                "segment_text": "TREATMENT Initial management of acute pancreatitis includes intravenous fluid therapy, analgesia, and monitoring.",
            },
            {
                "chapter": 359,
                "pdf_page": 9,
                "printed_page": 2752,
                "source_file": "359_Acute and Chronic Pancreatitis.pdf",
                "segment_text": ("Acute pancreatitis complications and pseudocyst. " * 30).strip(),
            },
        ]
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    concepts = match_ontology_concepts("급성췌장염의 진단과 초기 치료는?", root=copilot_root)
    public, _internal = medical_copilot.retrieve_harrison_evidence(
        "급성췌장염의 진단과 초기 치료는?",
        concepts,
        ["diagnosis", "treatment"],
        root=copilot_root,
    )

    assert {row["printed_page"] for row in public} >= {2745, 2747}


def test_fulltext_hint_covers_infective_endocarditis_diagnosis_and_treatment(
    copilot_root: Path,
) -> None:
    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.extend(
        [
            {
                "chapter": 133,
                "pdf_page": 3,
                "printed_page": 1032,
                "source_file": "133_Infective Endocarditis.pdf",
                "segment_text": "DIAGNOSIS Infective endocarditis diagnostic criteria combine blood cultures and echocardiographic findings.",
            },
            {
                "chapter": 133,
                "pdf_page": 6,
                "printed_page": 1035,
                "source_file": "133_Infective Endocarditis.pdf",
                "segment_text": "TREATMENT Infective endocarditis antimicrobial therapy is guided by the organism, susceptibility, and valve setting.",
            },
            {
                "chapter": 133,
                "pdf_page": 8,
                "printed_page": 1037,
                "source_file": "133_Infective Endocarditis.pdf",
                "segment_text": ("Infective endocarditis embolic complications. " * 25).strip(),
            },
        ]
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    public, _internal = medical_copilot.retrieve_harrison_fulltext_fallback(
        "감염성 심내막염의 진단 기준과 치료 원칙은?",
        ["diagnosis", "treatment"],
        root=copilot_root,
    )

    assert {row["printed_page"] for row in public} >= {1032, 1035}
    assert all(row["chapter"] == 133 for row in public)


def test_fulltext_hint_prioritizes_aki_definition_before_differential_workup(
    copilot_root: Path,
) -> None:
    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.extend(
        [
            {
                "chapter": 321,
                "pdf_page": 1,
                "printed_page": 2372,
                "source_file": "321_Acute Kidney Injury.pdf",
                "segment_text": "Acute kidney injury diagnostic definition includes serum creatinine change and urine output criteria.",
            },
            {
                "chapter": 321,
                "pdf_page": 10,
                "printed_page": 2381,
                "source_file": "321_Acute Kidney Injury.pdf",
                "segment_text": "Acute kidney injury evaluation uses urinary sediment and blood laboratory findings to identify the cause.",
            },
        ]
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    public, _internal = medical_copilot.retrieve_harrison_fulltext_fallback(
        "급성신손상의 진단 기준과 초기 평가는?",
        ["diagnosis"],
        root=copilot_root,
    )

    assert public[0]["chapter"] == 321
    assert public[0]["printed_page"] == 2372
    assert {row["printed_page"] for row in public} >= {2372, 2381}


def test_pulmonary_embolism_unstable_treatment_uses_reperfusion_page(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["pulmonary_embolism"] = {
        "node_type": "disease",
        "aliases": ["폐색전증", "pulmonary embolism"],
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 290,
                "title": "Deep-Venous Thrombosis and Pulmonary Thromboembolism",
                "page": 2158,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.extend(
        [
            {
                "chapter": 290,
                "pdf_page": 10,
                "printed_page": 2163,
                "source_file": "290_Deep-Venous Thrombosis and Pulmonary Thromboembolism.pdf",
                "segment_text": "MANAGEMENT OF MASSIVE PE includes hemodynamic support for shock.",
            },
            {
                "chapter": 290,
                "pdf_page": 11,
                "printed_page": 2164,
                "source_file": "290_Deep-Venous Thrombosis and Pulmonary Thromboembolism.pdf",
                "segment_text": "FIBRINOLYSIS for massive pulmonary embolism rapidly reverses right heart failure. Catheter and surgical embolectomy are reperfusion alternatives.",
            },
        ]
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    concepts = match_ontology_concepts("혈역학적으로 불안정한 폐색전증 치료", root=copilot_root)
    public, _internal = medical_copilot.retrieve_harrison_evidence(
        "혈역학적으로 불안정한 폐색전증 치료",
        concepts,
        ["treatment"],
        root=copilot_root,
    )

    assert public[0]["printed_page"] == 2164
    assert "fibrinolysis" in _internal[0]["text"].lower()


def test_bipolar_query_expansion_prioritizes_acute_mania_treatment(
    copilot_root: Path,
) -> None:
    concept_path = copilot_root / medical_copilot.CONCEPT_REGISTRY_RELATIVE_PATH
    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    payload["concepts"]["bipolar_disorder"] = {
        "node_type": "disease",
        "aliases": ["양극성장애", "bipolar disorder"],
        "edges": {},
        "evidence": {
            "harrison": {
                "edition": "22e",
                "chapter": 463,
                "title": "Bipolar Disorder",
                "page": 3668,
            }
        },
    }
    concept_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pages_path = copilot_root / medical_copilot.HARRISON_PAGES_RELATIVE_PATH
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    rows.extend(
        [
            {
                "chapter": 463,
                "pdf_page": 11,
                "printed_page": 3667,
                "source_file": "463_Mental Disorders.pdf",
                "segment_text": ("TREATMENT psychiatric medication and antidepressant therapy. " * 20).strip(),
            },
            {
                "chapter": 463,
                "pdf_page": 12,
                "printed_page": 3668,
                "source_file": "463_Mental Disorders.pdf",
                "segment_text": "BIPOLAR DISORDER TREATMENT Acute mania may require a mood stabilizer such as lithium and an antipsychotic.",
            },
        ]
    )
    pages_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    concepts = match_ontology_concepts("양극성장애의 급성 조증 치료 원칙은?", root=copilot_root)
    public, _internal = medical_copilot.retrieve_harrison_evidence(
        "양극성장애의 급성 조증 치료 원칙은?",
        concepts,
        ["treatment"],
        root=copilot_root,
    )

    assert public[0]["printed_page"] == 3668
