"""교수 문항 확정·편집 서비스(src/services/faculty_adjudication) 단위 테스트.

실데이터(data_private/)는 건드리지 않는다: 임시 디렉터리에 세트당 2문항짜리 합성 사본을 만들어
AdjudicationPaths로 경로를 넘긴다. 합성 문항은 원본 기출 텍스트를 포함하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services import faculty_adjudication as fa


ROOT = Path(__file__).resolve().parents[1]
REAL_PRIVATE = (ROOT / "data_private").resolve()


def _item(no: int, subject: str, answer: str = "2", **extra):
    stem = (
        f"{40 + no}세 남자가 3일 전부터 열이 나서 왔다. 혈압 120/80 mmHg, 맥박 90회/분이다. "
        "가장 가능성 있는 진단은?"
    )
    item = {
        "no": no,
        "mgmt_no": f"M-{no:02d}",
        "subject": subject,
        "concept": f"concept_{no}",
        "axis": "진단",
        "stem": stem,
        "lab_box": "",
        "image": "",
        "choices": {"1": "진단 가", "2": "진단 나", "3": "진단 다", "4": "진단 라", "5": "진단 마"},
        "answer": answer,
        "explanation": "정답 근거 해설.",
        "evidence": "",
        "modality": "",
        "disease_concept_id": f"concept_{no}",
        "harrison_sources": [
            {"source_id": "H10", "chapter": 10, "printed_page": 100, "entailment_status": "partially_supported"}
        ],
        "choice_explanations": {
            "1": {"why_attractive": "a"},
            "2": {"why_correct": "b"},
            "3": {"why_attractive": "c"},
            "4": {"why_attractive": "d"},
            "5": {"why_attractive": "e"},
        },
        "reasoning_hops": 2,
        "cognitive_level": "해석",
        "item_quality": {
            "hard_rule_failures": ["14_homogeneous_choices"],
            "manual_review_rules": list(fa.MANUAL_REVIEW_RULES_DEFAULT),
        },
        "needs_review": True,
        "gen_ready": False,
        "entailment_verdict": "partially",
        "self_check": {"common_high_stakes_problem": True},
    }
    item.update(extra)
    return item


def _review(no: int, who: str, scores, verdict: str, note: str = ""):
    return {"no": no, "who": who, "scores": list(scores), "verdict": verdict, "note": note}


@pytest.fixture
def paths(tmp_path: Path) -> fa.AdjudicationPaths:
    generated = tmp_path / "generated"
    review = tmp_path / "review"
    curriculum = tmp_path / "curriculum"
    for d in (generated, review, curriculum):
        d.mkdir()

    # set_1: g1(그대로), g2(폐기 + 교수판단 필요) / set_2: g81(정답변경 + 수정필요), g82(검토자 불일치 → 경미)
    set_1 = [
        _item(1, "내과"),
        _item(2, "내과", professor_review_required=True, professor_note="이미지 교체 필요"),
    ]
    set_2 = [
        _item(
            1,
            "소아과",
            v2_revision={"date": "2026-09-05", "fields": ["문두", "정답"], "log": ["정답 1→2"], "evidence": "Ch.10"},
        ),
        _item(2, "소아과"),
    ]
    (generated / "set_1.json").write_text(json.dumps(set_1, ensure_ascii=False, indent=1), encoding="utf-8")
    (generated / "set_2.json").write_text(json.dumps(set_2, ensure_ascii=False, indent=1), encoding="utf-8")

    reviews = [
        _review(1, "01", (5, 5, 5), "수정없이 사용"),
        _review(1, "02", (5, 4, 5), "수정없이 사용"),
        _review(1, "03", (5, 5, 4), "수정없이 사용"),
        _review(2, "01", (5, 5, 5), "수정없이 사용"),
        _review(2, "02", (1, 2, 1), "사용 불가", "정답이 없는 문제"),
        _review(2, "03", (4, 4, 4), "소폭 수정하여 사용", "원자료에만 있는 의견"),
        _review(81, "04", (3, 1, 2), "대폭 수정 필요", "정답 이의"),
        _review(81, "05", (4, 4, 4), "소폭 수정하여 사용"),
        _review(81, "06", (5, 5, 5), "수정없이 사용"),
        _review(82, "04", (5, 5, 5), "수정없이 사용"),
        _review(82, "05", (3, 3, 3), "수정없이 사용"),
        _review(82, "06", (5, 5, 5), "수정없이 사용"),
    ]
    (review / fa.REVIEWS_FILENAME).write_text(json.dumps(reviews, ensure_ascii=False), encoding="utf-8")
    # 원본 CSV처럼 BOM으로 시작
    (review / fa.COMMENTS_FILENAME).write_text(
        "﻿global_no,who,subject,image,note,primary_theme,all_themes\n"
        "2,02,내과,0,정답이 없는 문제,T9,T9;T6\n"
        "81,04,소아과,0,정답 이의,T2,T2\n",
        encoding="utf-8",
    )
    (curriculum / "evidence_routing.json").write_text(
        json.dumps(
            {
                "schema": "paccine.evidence_routing.v1",
                "books": {
                    "harrison_22e": {"title": "Harrison 22e", "index": "x"},
                    "nelson_21e": {"title": "Nelson 21e", "index": "y"},
                },
                "routes": {"내과": ["harrison_22e"], "소아과": ["nelson_21e", "harrison_22e"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fa.clear_caches()
    resolved = fa.AdjudicationPaths.resolve(generated, review, curriculum / "evidence_routing.json")
    assert REAL_PRIVATE not in resolved.generated_dir.resolve().parents
    return resolved


def _read_set(paths: fa.AdjudicationPaths, set_no: int):
    return json.loads(paths.set_path(set_no).read_text(encoding="utf-8"))


def _read_edits(paths: fa.AdjudicationPaths):
    if not paths.edits_path.exists():
        return []
    return [json.loads(line) for line in paths.edits_path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# qid · 집계 규칙
# ---------------------------------------------------------------------------
def test_parse_qid_and_global_no():
    assert fa.parse_qid("AIGEN_3_007") == (3, 7)
    assert fa.make_qid(3, 7) == "AIGEN_3_007"
    assert fa.global_no_of(3, 7) == 167
    for bad in ("AIGEN_3_7", "AIGEN_0_001", "X_1_001", "", None):
        with pytest.raises(fa.ItemNotFoundError):
            fa.parse_qid(bad)


def test_aggregate_reviews_matches_reference_rules():
    rows = [
        # 한 명이라도 '사용 불가' → 폐기 (다른 두 명이 만점이어도)
        _review(1, "a", (5, 5, 5), "수정없이 사용"),
        _review(1, "b", (5, 5, 5), "수정없이 사용"),
        _review(1, "c", (5, 5, 5), "사용 불가"),
        # '대폭 수정 필요' → 수정필요
        _review(2, "a", (5, 5, 5), "대폭 수정 필요"),
        _review(2, "b", (5, 5, 5), "수정없이 사용"),
        # 판정은 좋아도 최저점 ≤2 → 수정필요
        _review(3, "a", (5, 2, 5), "수정없이 사용"),
        _review(3, "b", (5, 5, 5), "수정없이 사용"),
        # '소폭 수정' → 경미
        _review(4, "a", (5, 5, 5), "소폭 수정하여 사용"),
        _review(4, "b", (5, 5, 5), "수정없이 사용"),
        # 판정은 모두 '수정없이'지만 점수범위 ≥2 → 경미 + 불일치
        _review(5, "a", (5, 5, 5), "수정없이 사용"),
        _review(5, "b", (3, 5, 5), "수정없이 사용"),
        # 전원 만족 → 그대로
        _review(6, "a", (5, 5, 5), "수정없이 사용"),
        _review(6, "b", (4, 5, 5), "수정없이 사용"),
    ]
    index = fa.aggregate_reviews(rows)
    assert [index[n]["action"] for n in range(1, 7)] == ["폐기", "수정필요", "수정필요", "경미", "경미", "그대로"]
    assert index[5]["disagreement"] is True and index[6]["disagreement"] is False
    assert index[1]["verdict_worst"] == "사용 불가"
    assert index[3]["score_worst"] == 2
    assert index[6]["ratings"] == [[5, 5, 5], [4, 5, 5]]
    assert index[6]["score_mean"] == 4.83


# ---------------------------------------------------------------------------
# 큐
# ---------------------------------------------------------------------------
def test_queue_priority_order_and_counts(paths):
    queue = fa.build_queue("all", paths=paths)
    assert [e["qid"] for e in queue["items"]] == ["AIGEN_2_001", "AIGEN_1_002", "AIGEN_2_002", "AIGEN_1_001"]
    assert [e["priority_label"] for e in queue["items"]] == ["정답변경", "폐기", "검토자불일치", "기타"]
    assert [e["global_no"] for e in queue["items"]] == [81, 2, 82, 1]
    counts = queue["counts"]
    assert counts["all"] == 4
    assert counts["needs_review"] == 1
    assert counts["revise"] == 1
    assert counts["discard"] == 1
    assert counts["answer_changed"] == 1
    assert counts["disagreement"] == 3  # g2·g81·g82 모두 점수범위 ≥2
    assert counts["decided"] == 0 and counts["pending"] == 4
    assert counts["hard_rule_failures"] == 0  # 14번은 manual_review_rules라 제외

    discard = next(e for e in queue["items"] if e["qid"] == "AIGEN_1_002")
    assert discard["professor_review_required"] is True
    assert discard["professor_note"] == "이미지 교체 필요"
    assert discard["review"]["action"] == "폐기"
    assert discard["review"]["ratings"] == [[5, 5, 5], [1, 2, 1], [4, 4, 4]]
    assert discard["review"]["verdicts"] == ["수정없이 사용", "사용 불가", "소폭 수정하여 사용"]
    # 코딩 CSV(주제 태그) 우선 + CSV에 없는 검토자 note는 원자료에서 보충
    comments = {c["who"]: c for c in discard["review"]["comments"]}
    assert comments["02"]["themes"] == ["T9", "T6"] and comments["02"]["primary_theme"] == "T9"
    assert comments["03"]["note"] == "원자료에만 있는 의견" and comments["03"]["themes"] == []
    assert discard["badge"] == {
        "entailment_verdict": "partially",
        "sources": [
            {
                "book_id": "harrison_22e",
                "locator": "Harrison 22e Ch.10 p.100",
                "chapter": 10,
                "page": 100,
                "entailment_status": "partially_supported",
            }
        ],
    }
    assert discard["stem_preview"].startswith("42세 남자가")
    assert "faculty_decision" not in discard and "faculty_edited" not in discard

    changed = queue["items"][0]
    assert changed["answer_changed"] is True
    assert changed["v2_revision"] == {"date": "2026-09-05", "fields": ["문두", "정답"], "log": ["정답 1→2"]}


def test_queue_filters(paths):
    assert [e["qid"] for e in fa.build_queue("needs_review", paths=paths)["items"]] == ["AIGEN_1_002"]
    assert [e["qid"] for e in fa.build_queue("revise", paths=paths)["items"]] == ["AIGEN_2_001"]
    assert [e["qid"] for e in fa.build_queue("discard", paths=paths)["items"]] == ["AIGEN_1_002"]
    assert [e["qid"] for e in fa.build_queue("answer_changed", paths=paths)["items"]] == ["AIGEN_2_001"]
    # 필터를 걸어도 counts는 전체 기준
    assert fa.build_queue("discard", paths=paths)["counts"]["all"] == 4
    with pytest.raises(fa.AdjudicationError):
        fa.build_queue("bogus", paths=paths)


def test_queue_without_review_files_is_fail_soft(paths):
    paths.reviews_path.unlink()
    paths.comments_path.unlink()
    queue = fa.build_queue("all", paths=paths)
    assert all(e["review"] is None for e in queue["items"])
    assert queue["counts"]["unreviewed"] == 4
    # 검토가 없으면 정답변경만 앞서고 나머지는 global_no 순
    assert [e["global_no"] for e in queue["items"]] == [81, 1, 2, 82]


# ---------------------------------------------------------------------------
# 단건 조회
# ---------------------------------------------------------------------------
def test_get_item_payload(paths):
    item = fa.get_item("AIGEN_2_001", paths=paths)
    assert item["qid"] == "AIGEN_2_001" and item["set"] == 2 and item["no"] == 1 and item["global_no"] == 81
    assert item["choices"]["5"] == "진단 마" and item["answer"] == "2"
    assert item["textbook_sources"] == []
    assert item["edit_history"] == []
    assert item["available_books"] == [
        {"book_id": "harrison_22e", "title": "Harrison 22e"},
        {"book_id": "nelson_21e", "title": "Nelson 21e"},
    ]
    assert item["recommended_book_ids"] == ["nelson_21e", "harrison_22e"]
    assert item["review"]["action"] == "수정필요" and item["review"]["comments"][0]["themes"] == ["T2"]
    assert item["answer_changed"] is True
    assert item["hard_rule_failures"] == []
    assert item["badge"]["sources"][0]["locator"] == "Harrison 22e Ch.10 p.100"
    # 반환값을 고쳐도 캐시가 오염되지 않는다
    item["choices"]["1"] = "오염"
    assert fa.get_item("AIGEN_2_001", paths=paths)["choices"]["1"] == "진단 가"


def test_get_item_not_found(paths):
    with pytest.raises(fa.ItemNotFoundError):
        fa.get_item("AIGEN_1_003", paths=paths)
    with pytest.raises(fa.ItemNotFoundError):
        fa.get_item("AIGEN_4_001", paths=paths)  # 세트 파일 자체가 없음


# ---------------------------------------------------------------------------
# 편집
# ---------------------------------------------------------------------------
def test_update_item_writes_diff_and_stamps(paths):
    before = fa.get_item("AIGEN_1_001", paths=paths)
    result = fa.update_item(
        "AIGEN_1_001",
        {
            "stem": before["stem"] + " 추가 단서.",
            "choices": {**before["choices"], "3": "진단 다(수정)"},
            "textbook_sources": [{"book_id": "nelson_21e", "chapter": "12"}],
            "explanation": before["explanation"],  # 무변경 필드는 이력에 남지 않는다
        },
        editor="prof@example.org",
        paths=paths,
    )
    assert result["saved"] is True
    assert result["changed_fields"] == ["stem", "choices", "textbook_sources"]
    assert isinstance(result["gate"]["failed_rules"], list)
    assert not (set(result["gate"]["failed_rules"]) & set(fa.MANUAL_REVIEW_RULES_DEFAULT))
    assert "14_homogeneous_choices" in result["gate"]["manual_review_rules"]
    assert result["item"]["faculty_edited"] is True

    # 디스크 반영 + 원자적 쓰기 잔여물 없음 + 다른 문항 무손상
    on_disk = _read_set(paths, 1)
    assert len(on_disk) == 2 and on_disk[1]["stem"] == before["stem"].replace(f"{41}세", f"{42}세")
    saved = on_disk[0]
    assert saved["stem"].endswith(" 추가 단서.")
    assert saved["choices"]["3"] == "진단 다(수정)"
    assert saved["textbook_sources"] == [{"book_id": "nelson_21e", "chapter": "12"}]
    assert saved["faculty_edited"] is True and saved["faculty_edited_at"] == result["faculty_edited_at"]
    assert saved["item_quality"]["hard_rule_total"] == 20
    assert not list(paths.generated_dir.glob("*.tmp"))

    # append-only 이력: 계약 필드(qid, editor, at, field, before, after)
    edits = _read_edits(paths)
    assert [e["field"] for e in edits] == ["stem", "choices", "textbook_sources"]
    assert all(set(e) == {"qid", "editor", "at", "field", "before", "after"} for e in edits)
    assert edits[1]["before"]["3"] == "진단 다" and edits[1]["after"]["3"] == "진단 다(수정)"
    assert edits[2]["before"] is None
    assert all(e["editor"] == "prof@example.org" and e["qid"] == "AIGEN_1_001" for e in edits)

    after = fa.get_item("AIGEN_1_001", paths=paths)
    assert [e["field"] for e in after["edit_history"]] == ["stem", "choices", "textbook_sources"]
    assert after["badge"]["sources"][1] == {
        "book_id": "nelson_21e",
        "locator": "Nelson 21e Ch.12",
        "chapter": "12",
        "page": None,
        "entailment_status": None,
    }
    queue_entry = next(e for e in fa.build_queue(paths=paths)["items"] if e["qid"] == "AIGEN_1_001")
    assert queue_entry["faculty_edited"] is True and queue_entry["edit_count"] == 3
    assert fa.summary(paths=paths)["faculty_edited"] == 1


def test_update_item_choice_explanations_merge(paths):
    fa.update_item(
        "AIGEN_1_001",
        {"choice_explanations": {"3": {"why_attractive": "새 오답 근거"}, "2": {"why_correct": "새 정답 근거"}}},
        editor="prof",
        paths=paths,
    )
    saved = _read_set(paths, 1)[0]["choice_explanations"]
    assert saved["3"] == {"why_attractive": "새 오답 근거"}
    assert saved["2"] == {"why_correct": "새 정답 근거"}
    assert saved["1"] == {"why_attractive": "a"}  # 건드리지 않은 선지는 보존
    edits = _read_edits(paths)
    assert len(edits) == 1 and edits[0]["field"] == "choice_explanations"


def test_update_item_harrison_sources_normalized(paths):
    fa.update_item(
        "AIGEN_1_001",
        {"harrison_sources": [{"chapter": "12", "printed_page": "120"}]},
        editor="prof",
        paths=paths,
    )
    saved = _read_set(paths, 1)[0]["harrison_sources"]
    assert saved == [{"chapter": 12, "printed_page": 120, "source_id": "H12"}]


@pytest.mark.parametrize(
    "changes",
    [
        {"answer": "6"},
        {"answer": ""},
        {"choices": {"1": "가", "2": "나", "3": "다", "4": "라"}},
        {"choices": {"1": "가", "2": "나", "3": "다", "4": "라", "5": ""}},
        {"choices": ["가", "나", "다", "라", "마"]},
        {"stem": ""},
        {"stem": 123},
        {"explanation": "   "},
        {"textbook_sources": [{"book_id": "unknown_book", "chapter": 1}]},
        {"textbook_sources": [{"book_id": "nelson_21e"}]},
        {"harrison_sources": [{"printed_page": 10}]},
        {"choice_explanations": {"9": {"why_correct": "x"}}},
        {"choice_explanations": {"1": {"misconception": "x"}}},
        {"image": "new.png"},  # 허용 필드 밖(계약: image는 편집 범위 아님)
        {"medical_approval": True},
        {},
    ],
)
def test_update_item_rejects_invalid_changes(paths, changes):
    with pytest.raises(fa.InvalidChangeError):
        fa.update_item("AIGEN_1_001", changes, editor="prof", paths=paths)
    assert not paths.edits_path.exists()
    assert "faculty_edited" not in _read_set(paths, 1)[0]


def test_update_item_requires_editor_and_existing_item(paths):
    with pytest.raises(fa.InvalidChangeError):
        fa.update_item("AIGEN_1_001", {"stem": "x"}, editor="  ", paths=paths)
    with pytest.raises(fa.ItemNotFoundError):
        fa.update_item("AIGEN_1_009", {"stem": "새 문두"}, editor="prof", paths=paths)


def test_update_item_noop_does_not_write(paths):
    current = fa.get_item("AIGEN_1_001", paths=paths)
    signature_before = paths.set_path(1).stat().st_mtime_ns
    result = fa.update_item("AIGEN_1_001", {"stem": current["stem"], "answer": "2"}, editor="prof", paths=paths)
    assert result["saved"] is False and result["changed_fields"] == []
    assert "failed_rules" in result["gate"]
    assert not paths.edits_path.exists()
    assert paths.set_path(1).stat().st_mtime_ns == signature_before
    assert "faculty_edited" not in _read_set(paths, 1)[0]


def test_update_answer_marks_answer_changed(paths):
    fa.update_item("AIGEN_1_001", {"answer": "4"}, editor="prof", paths=paths)
    queue = fa.build_queue("answer_changed", paths=paths)
    assert [e["qid"] for e in queue["items"]] == ["AIGEN_1_001", "AIGEN_2_001"]
    assert fa.build_queue(paths=paths)["items"][0]["qid"] == "AIGEN_1_001"
    assert fa.summary(paths=paths)["answer_changed"] == 2


# ---------------------------------------------------------------------------
# 결정
# ---------------------------------------------------------------------------
def test_record_decision_approve_then_revoke(paths):
    approved = fa.record_decision("AIGEN_1_002", "approve", by="prof@example.org", note="확인", paths=paths)
    assert approved["faculty_decision"]["decision"] == "approve"
    assert approved["faculty_decision"]["by"] == "prof@example.org"
    assert approved["faculty_decision"]["note"] == "확인"
    assert approved["medical_approval"] is True and approved["professor_review_required"] is False

    saved = _read_set(paths, 1)[1]
    assert saved["medical_approval"] is True
    assert "professor_review_required" not in saved
    assert saved["professor_note"] == "이미지 교체 필요"  # 이력 보존
    assert saved["faculty_decision"] == approved["faculty_decision"]

    queue = fa.build_queue(paths=paths)
    entry = next(e for e in queue["items"] if e["qid"] == "AIGEN_1_002")
    assert entry["faculty_decision"]["decision"] == "approve" and entry["medical_approval"] is True
    assert "professor_review_required" not in entry
    assert queue["counts"]["needs_review"] == 0 and queue["counts"]["decided"] == 1

    summary = fa.summary(paths=paths)
    assert summary["decided"] == {"approve": 1, "revise": 0, "discard": 0}
    assert summary["pending"] == 3 and summary["medical_approved"] == 1

    revised = fa.record_decision("AIGEN_1_002", "revise", by="prof", paths=paths)
    assert revised["medical_approval"] is False
    saved = _read_set(paths, 1)[1]
    assert saved["medical_approval"] is False and saved["faculty_decision"]["decision"] == "revise"
    assert fa.summary(paths=paths)["decided"] == {"approve": 0, "revise": 1, "discard": 0}

    edits = _read_edits(paths)
    assert [e["field"] for e in edits] == ["faculty_decision", "faculty_decision"]
    assert edits[0]["before"] is None and edits[0]["after"]["decision"] == "approve"
    assert edits[1]["before"]["decision"] == "approve" and edits[1]["after"]["decision"] == "revise"
    # 결정 로그는 편집 횟수에 세지 않는다
    entry = next(e for e in fa.build_queue(paths=paths)["items"] if e["qid"] == "AIGEN_1_002")
    assert entry["edit_count"] == 0


def test_record_decision_validation(paths):
    with pytest.raises(fa.AdjudicationError):
        fa.record_decision("AIGEN_1_001", "maybe", by="prof", paths=paths)
    with pytest.raises(fa.AdjudicationError):
        fa.record_decision("AIGEN_1_001", "approve", by="", paths=paths)
    with pytest.raises(fa.ItemNotFoundError):
        fa.record_decision("AIGEN_3_001", "approve", by="prof", paths=paths)
    assert not paths.edits_path.exists()


# ---------------------------------------------------------------------------
# 캐시 · 경로 오버라이드
# ---------------------------------------------------------------------------
def test_set_cache_reloads_when_file_changes_externally(paths):
    assert fa.get_item("AIGEN_1_001", paths=paths)["explanation"] == "정답 근거 해설."
    items = _read_set(paths, 1)
    items[0]["explanation"] = "외부 스크립트가 바꾼 해설 — 길이가 확실히 달라진다."
    paths.set_path(1).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    assert fa.get_item("AIGEN_1_001", paths=paths)["explanation"].startswith("외부 스크립트가 바꾼 해설")


def test_module_constants_can_be_monkeypatched(paths, monkeypatch):
    monkeypatch.setattr(fa, "GENERATED_DIR", paths.generated_dir)
    monkeypatch.setattr(fa, "REVIEW_DIR", paths.review_dir)
    monkeypatch.setattr(fa, "EVIDENCE_ROUTING_PATH", paths.evidence_routing_path)
    queue = fa.build_queue("discard")
    assert [e["qid"] for e in queue["items"]] == ["AIGEN_1_002"]
    assert fa.summary()["total"] == 4
    fa.record_decision("AIGEN_1_001", "discard", by="prof")
    assert _read_set(paths, 1)[0]["faculty_decision"]["decision"] == "discard"
