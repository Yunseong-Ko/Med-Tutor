"""학생 신뢰 배지 서비스(src/services/trust_badges) 단위 테스트.

합성 데이터로 규칙·경로 오버라이드·캐시를 검증하고, private 데이터가 있을 때만
scripts/aggregate_review_feedback.aggregate 와의 문항별 조치 일치를 교차검증한다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.services import trust_badges as tb


ROOT = Path(__file__).resolve().parents[1]
REVIEWS = tb.REVIEWS_PATH
GENERATED = tb.GENERATED_DIR

# 2026-09-02 1차 검토 정규화 파일(320문항×3인) 스냅샷. 드리프트 시 분포 고정 테스트는 skip.
_PINNED_REVIEWS_SHA256 = "e4b5e75a8beacda4121f81e5f959fe22c283df002e57e351a0369d11424d6c52"


def _reviews_snapshot_matches() -> bool:
    return REVIEWS.exists() and hashlib.sha256(REVIEWS.read_bytes()).hexdigest() == _PINNED_REVIEWS_SHA256


def _row(no, scores, verdict="", note="", who="01"):
    return {"no": no, "who": who, "scores": list(scores), "verdict": verdict, "note": note}


@pytest.fixture(autouse=True)
def _clear_caches():
    tb.clear_caches()
    yield
    tb.clear_caches()


# ── qid ↔ global_no ───────────────────────────────────────────────────────────
def test_qid_global_no_roundtrip():
    assert tb.parse_qid("AIGEN_1_001") == (1, 1)
    assert tb.qid_to_global_no("AIGEN_1_001") == 1
    assert tb.qid_to_global_no("AIGEN_2_001") == 81
    assert tb.qid_to_global_no("AIGEN_4_080") == 320
    assert tb.global_no_to_qid(1) == "AIGEN_1_001"
    assert tb.global_no_to_qid(81) == "AIGEN_2_001"
    assert tb.global_no_to_qid("320") == "AIGEN_4_080"
    for n in range(1, 321):
        assert tb.qid_to_global_no(tb.global_no_to_qid(n)) == n


def test_qid_mapping_rejects_non_aigen():
    assert tb.parse_qid("HEME-001") is None
    assert tb.parse_qid("") is None
    assert tb.parse_qid(None) is None
    assert tb.qid_to_global_no("AIGEN_1_081") is None      # 세트 크기 초과
    assert tb.qid_to_global_no("AIGEN_0_001") is None
    assert tb.global_no_to_qid(0) is None
    assert tb.global_no_to_qid("abc") is None


# ── 조치 규칙 ─────────────────────────────────────────────────────────────────
def test_classify_action_branches():
    ok = "수정없이 사용"
    assert tb.classify_action([_row(1, [5, 5, 5], ok)] * 3) == "그대로"
    assert tb.classify_action([_row(1, [4, 3, 3], "소폭 수정하여 사용"), _row(1, [5, 5, 5], ok)]) == "경미"
    # 판정은 모두 '수정없이'지만 점수범위 ≥2 → 경미
    assert tb.classify_action([_row(1, [5, 5, 5], ok), _row(1, [3, 5, 5], ok)]) == "경미"
    # 최저점 ≤2 → 수정필요 (판정이 '소폭'이어도)
    assert tb.classify_action([_row(1, [2, 5, 5], "소폭 수정하여 사용"), _row(1, [5, 5, 5], ok)]) == "수정필요"
    assert tb.classify_action([_row(1, [4, 4, 4], "대폭 수정 필요"), _row(1, [5, 5, 5], ok)]) == "수정필요"
    # 한 명이라도 '사용 불가' → 폐기 (다른 두 명이 만점이어도)
    assert tb.classify_action([_row(1, [5, 5, 5], ok), _row(1, [5, 5, 5], ok), _row(1, [3, 3, 3], "사용 불가")]) == "폐기"


def test_classify_action_ignores_blank_verdict_and_bad_scores():
    rows = [_row(1, [5, 5, 5], ""), _row(1, [5, "x", None], "수정없이 사용")]
    assert tb.classify_action(rows) == "그대로"
    assert tb.classify_action([]) == "그대로"


def test_normalize_action_accepts_long_and_short_labels():
    assert tb.normalize_action("그대로 사용") == "그대로"
    assert tb.normalize_action("경미 수정") == "경미"
    assert tb.normalize_action("수정 필요") == "수정필요"
    assert tb.normalize_action("폐기 검토") == "폐기"
    assert tb.normalize_action("수정필요") == "수정필요"
    assert tb.normalize_action("") is None
    assert tb.normalize_action("모름") is None


def test_student_review_status():
    assert tb.student_review_status("그대로") == "passed"
    assert tb.student_review_status("경미 수정") == "passed"
    assert tb.student_review_status("수정필요") == "review_pending"
    assert tb.student_review_status("폐기") == "review_pending"
    assert tb.student_review_status(None) == "unreviewed"


# ── 캐시 빌드·로드(임시 경로 오버라이드) ─────────────────────────────────────
def test_build_and_load_item_actions_with_explicit_paths(tmp_path):
    reviews = tmp_path / "reviews.json"
    out = tmp_path / "nested" / "item_actions.json"
    ok = "수정없이 사용"
    reviews.write_text(json.dumps([
        _row(1, [5, 5, 5], ok), _row(1, [5, 5, 5], ok, who="02"), _row(1, [5, 5, 5], ok, who="03"),
        _row(2, [4, 3, 3], "소폭 수정하여 사용"), _row(2, [5, 5, 5], ok, who="02"),
        _row(3, [2, 4, 4], ok),
        _row(4, [5, 5, 5], "사용 불가"),
        {"no": "bad", "scores": [5], "verdict": ok},      # 번호 없는 행은 무시
        "garbage",
    ], ensure_ascii=False), encoding="utf-8")

    result = tb.build_item_actions(reviews, out)
    assert result["path"] == str(out)
    assert result["items"] == 4
    assert result["counts"] == {"그대로": 1, "경미": 1, "수정필요": 1, "폐기": 1}
    assert result["actions"] == {1: "그대로", 2: "경미", 3: "수정필요", 4: "폐기"}

    stored = json.loads(out.read_text(encoding="utf-8"))
    assert stored == {"1": "그대로", "2": "경미", "3": "수정필요", "4": "폐기"}
    assert not list(out.parent.glob(".*.tmp-*"))            # 원자적 쓰기 임시파일 정리

    loaded = tb.load_item_actions(out)
    assert loaded == {1: "그대로", 2: "경미", 3: "수정필요", 4: "폐기"}
    assert tb.action_for_qid("AIGEN_1_002", loaded) == "경미"
    assert tb.action_for_qid("AIGEN_1_009", loaded) is None
    assert tb.action_for_qid("HEME-001", loaded) is None


def test_env_override_and_cache_invalidation(tmp_path, monkeypatch):
    reviews = tmp_path / "r.json"
    out = tmp_path / "a.json"
    monkeypatch.setenv(tb.ENV_REVIEWS_PATH, str(reviews))
    monkeypatch.setenv(tb.ENV_ITEM_ACTIONS_PATH, str(out))

    reviews.write_text(json.dumps([_row(7, [5, 5, 5], "수정없이 사용")]), encoding="utf-8")
    tb.build_item_actions()
    assert tb.load_item_actions() == {7: "그대로"}

    # 재빌드 → 파일 서명이 바뀌므로 캐시가 갱신되어야 한다
    reviews.write_text(json.dumps([_row(7, [5, 5, 5], "사용 불가"), _row(8, [4, 4, 4], "소폭 수정하여 사용")]),
                       encoding="utf-8")
    tb.build_item_actions()
    assert tb.load_item_actions() == {7: "폐기", 8: "경미"}
    assert tb.action_for_qid("AIGEN_1_008") == "경미"


def test_load_item_actions_fail_soft(tmp_path):
    assert tb.load_item_actions(tmp_path / "missing.json") == {}
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert tb.load_item_actions(broken) == {}
    odd = tmp_path / "odd.json"
    odd.write_text(json.dumps({"1": "그대로 사용", "x": "경미", "2": "???"}), encoding="utf-8")
    assert tb.load_item_actions(odd) == {1: "그대로"}


def test_build_rejects_non_array(tmp_path):
    reviews = tmp_path / "r.json"
    reviews.write_text(json.dumps({"no": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        tb.build_item_actions(reviews, tmp_path / "a.json")


# ── 근거 포인터 ───────────────────────────────────────────────────────────────
def test_evidence_locators_formats():
    q = {
        "harrison_sources": [
            {"source_id": "H350", "chapter": 350, "printed_page": 2649},
            {"source_id": "H350", "chapter": 350, "printed_page": 2649},   # 중복
            {"source_id": "H12", "chapter": "12"},                          # 페이지 없음
            {"chapter": None},                                              # 장 없음 → 건너뜀
            "junk",
        ],
        "textbook_sources": [
            {"book_id": "berek_novak_16e", "chapter": 39},
            {"book_id": "unknown_book", "chapter": 3},
        ],
    }
    assert tb.evidence_locators(q) == [
        "Harrison 22e Ch.350 p.2649",
        "Harrison 22e Ch.12",
        "Berek & Novak 16e Ch.39",
        "unknown_book Ch.3",
    ]
    assert tb.evidence_locators({}) == []
    assert tb.evidence_locators({"harrison_sources": None, "textbook_sources": []}) == []


def test_book_titles_match_review_books_script():
    pytest.importorskip("docx")
    pytest.importorskip("openpyxl")
    from scripts import build_student_review_books as books
    assert tb.BOOK_TITLES == books.BOOK_TITLES


# ── 배지 ──────────────────────────────────────────────────────────────────────
def _q(verdict="partially", pointer=True, approval=None):
    q = {"entailment_verdict": verdict}
    if pointer:
        q["harrison_sources"] = [{"chapter": 350, "printed_page": 2649}]
    if approval is not None:
        q["medical_approval"] = approval
    return q


def test_compute_trust_badges_evidence_levels():
    fully = tb.compute_trust_badges(_q("fully"), "그대로")
    assert fully["evidence_verified"] == {"level": "fully", "label": "교과서 근거 검증", "mark": "✓"}
    partially = tb.compute_trust_badges(_q("partially"), "그대로")
    assert partially["evidence_verified"] == {"level": "partially", "label": "교과서 근거 검증", "mark": "△"}
    for q in (_q("not"), _q(None), _q("fully", pointer=False), _q("partially", pointer=False)):
        assert tb.compute_trust_badges(q, "그대로")["evidence_verified"] == {"level": "none", "label": None, "mark": None}


def test_compute_trust_badges_student_reviewed():
    passed = {"label": "졸업반 3인 검토 통과"}
    assert tb.compute_trust_badges(_q(), "그대로")["student_reviewed"] == passed
    assert tb.compute_trust_badges(_q(), "경미")["student_reviewed"] == passed
    assert tb.compute_trust_badges(_q(), "그대로 사용")["student_reviewed"] == passed   # 긴 라벨 허용
    assert tb.compute_trust_badges(_q(), "수정필요")["student_reviewed"] is None
    assert tb.compute_trust_badges(_q(), "폐기 검토")["student_reviewed"] is None
    assert tb.compute_trust_badges(_q(), None)["student_reviewed"] is None


def test_compute_trust_badges_faculty_approved_strict_bool():
    assert tb.compute_trust_badges(_q(approval=True), None)["faculty_approved"] is True
    assert tb.compute_trust_badges(_q(approval=False), None)["faculty_approved"] is False
    assert tb.compute_trust_badges(_q(approval="true"), None)["faculty_approved"] is False
    assert tb.compute_trust_badges(_q(approval=1), None)["faculty_approved"] is False
    assert tb.compute_trust_badges(_q(), None)["faculty_approved"] is False


def test_compute_trust_badges_shape_is_contract():
    badges = tb.compute_trust_badges(_q(), "경미")
    assert set(badges) == {"evidence_verified", "student_reviewed", "faculty_approved"}
    assert set(badges["evidence_verified"]) == {"level", "label", "mark"}


def test_evidence_summary_block():
    summary = tb.evidence_summary(_q("fully"))
    assert summary == {
        "locators": ["Harrison 22e Ch.350 p.2649"],
        "badge": {"level": "fully", "label": "교과서 근거 검증", "mark": "✓"},
    }


# ── v2 수정 이력 요약 ─────────────────────────────────────────────────────────
def test_revision_note_none_without_history():
    assert tb.revision_note({}) is None
    assert tb.revision_note({"v2_revision": None}) is None
    assert tb.revision_note({"v2_revision": {"date": "2026-09-05", "fields": [], "log": []}}) is None


def test_revision_note_summarizes_two_lines_and_flags_answer_change():
    long_line = "학생 정답 이의 수용(2인 일치, 원문 검증 통과): " + "매우 긴 설명 문장입니다. " * 20
    q = {"v2_revision": {
        "date": "2026-09-05",
        "fields": ["해설", "문두", "정답", "선지해설"],
        "log": [long_line, "정답을 1→2로 변경.", "세 번째 줄은 요약에서 제외된다."],
        "evidence": "원문 인용은 학생에게 전달하지 않는다",
    }}
    note = tb.revision_note(q)
    assert note["date"] == "2026-09-05"
    assert note["fields"] == ["해설", "문두", "정답", "선지해설"]
    assert note["answer_changed"] is True
    assert "세 번째 줄" not in note["summary"]
    assert "정답을 1→2로 변경." in note["summary"]
    assert "원문 인용" not in json.dumps(note, ensure_ascii=False)
    first = note["summary"].split(" 정답을 1→2로")[0]
    assert first.endswith("…") and len(first) <= tb.REVISION_LINE_LIMIT + 1


def test_revision_note_short_log_untouched():
    q = {"v2_revision": {"date": "2026-09-05", "fields": ["해설"], "log": ["해설 보강."]}}
    note = tb.revision_note(q)
    assert note == {"date": "2026-09-05", "summary": "해설 보강.", "fields": ["해설"], "answer_changed": False}


# ── 생성 문항 로더 + payload 조립(합성 디렉터리) ──────────────────────────────
def _write_sets(tmp_path):
    gen = tmp_path / "generated"
    gen.mkdir()
    set1 = [
        {"no": 1, "stem": "s1", "entailment_verdict": "fully",
         "harrison_sources": [{"chapter": 350, "printed_page": 2649}],
         "v2_revision": {"date": "2026-09-05", "fields": ["해설"], "log": ["해설 보강."]}},
        {"no": 2, "stem": "s2", "entailment_verdict": "not",
         "harrison_sources": [{"chapter": 1, "printed_page": 10}], "medical_approval": True},
    ]
    set2 = [{"no": 1, "stem": "s3", "entailment_verdict": "partially",
             "textbook_sources": [{"book_id": "nelson_21e", "chapter": 5}]}]
    (gen / "set_1.json").write_text(json.dumps(set1, ensure_ascii=False), encoding="utf-8")
    (gen / "set_2.json").write_text(json.dumps(set2, ensure_ascii=False), encoding="utf-8")
    (gen / "set_1.security_report.json").write_text("{}", encoding="utf-8")   # set_*.json 패턴 외 파일은 무시
    return gen


def test_load_generated_items_keys_by_qid(tmp_path):
    gen = _write_sets(tmp_path)
    items = tb.load_generated_items(gen)
    assert list(items) == ["AIGEN_1_001", "AIGEN_1_002", "AIGEN_2_001"]
    assert items["AIGEN_1_002"]["global_no"] == 2 and items["AIGEN_1_002"]["set"] == 1
    assert items["AIGEN_2_001"]["global_no"] == 3      # 교시 순서로 이어붙인 전역번호
    assert tb.load_generated_items(tmp_path / "nowhere") == {}


def test_student_trust_payload_assembles_contract_block(tmp_path, monkeypatch):
    gen = _write_sets(tmp_path)
    monkeypatch.setenv(tb.ENV_GENERATED_DIR, str(gen))
    actions = {1: "경미", 2: "폐기"}

    p1 = tb.student_trust_payload("AIGEN_1_001", actions=actions)
    assert p1["trust_badges"] == {
        "evidence_verified": {"level": "fully", "label": "교과서 근거 검증", "mark": "✓"},
        "student_reviewed": {"label": "졸업반 3인 검토 통과"},
        "faculty_approved": False,
    }
    assert p1["evidence"]["locators"] == ["Harrison 22e Ch.350 p.2649"]
    assert p1["revision_note"]["summary"] == "해설 보강."

    p2 = tb.student_trust_payload("AIGEN_1_002", actions=actions)
    assert p2["trust_badges"]["evidence_verified"]["level"] == "none"
    assert p2["trust_badges"]["student_reviewed"] is None
    assert p2["trust_badges"]["faculty_approved"] is True
    assert p2["revision_note"] is None

    p3 = tb.student_trust_payload("AIGEN_2_001", actions=actions)     # 조치 없음 → 미검토
    assert p3["trust_badges"]["student_reviewed"] is None
    assert p3["evidence"]["locators"] == ["Nelson 21e Ch.5"]

    assert tb.student_trust_payload("AIGEN_3_001", actions=actions) is None
    assert tb.student_trust_payload("HEME-001", actions=actions) is None


def test_student_trust_payload_reads_actions_file(tmp_path):
    gen = _write_sets(tmp_path)
    actions_path = tmp_path / "item_actions.json"
    actions_path.write_text(json.dumps({"1": "그대로"}), encoding="utf-8")
    payload = tb.student_trust_payload("AIGEN_1_001", generated_dir=gen, actions_path=actions_path)
    assert payload["trust_badges"]["student_reviewed"] == {"label": "졸업반 3인 검토 통과"}


# ── private 데이터 교차검증(있을 때만) ─────────────────────────────────────────
@pytest.mark.skipif(not REVIEWS.exists(), reason="private normalized reviews not present")
def test_actions_match_aggregate_script_per_item(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from scripts.aggregate_review_feedback import aggregate

    rows = json.loads(REVIEWS.read_text(encoding="utf-8"))
    by_item = {}
    for r in rows:
        by_item.setdefault(int(r["no"]), []).append(r)
    xlsx = tmp_path / "집계.xlsx"
    aggregate(by_item, xlsx)
    ws = openpyxl.load_workbook(xlsx, data_only=True).active
    header = [c.value for c in ws[1]]
    no_col, action_col = header.index("문항"), header.index("조치")
    script_actions = {int(r[no_col]): tb.normalize_action(r[action_col])
                      for r in ws.iter_rows(min_row=2, values_only=True) if r[no_col] is not None}

    ours = tb.build_item_actions(REVIEWS, tmp_path / "item_actions.json")["actions"]
    assert ours == script_actions
    assert len(ours) == len(by_item)


@pytest.mark.skipif(not _reviews_snapshot_matches(), reason="reviews_1cha_normalized.json 이 1차 검토 스냅샷과 다름")
def test_pinned_1cha_distribution(tmp_path):
    result = tb.build_item_actions(REVIEWS, tmp_path / "item_actions.json")
    assert result["items"] == 320
    assert result["counts"] == {"그대로": 129, "경미": 149, "수정필요": 38, "폐기": 4}


@pytest.mark.skipif(not (GENERATED / "set_1.json").exists(), reason="private generated sets not present")
def test_generated_global_no_matches_qid_formula():
    items = tb.load_generated_items()
    assert items, "generated sets loaded"
    for qid, item in items.items():
        assert tb.qid_to_global_no(qid) == item["global_no"]
        assert tb.global_no_to_qid(item["global_no"]) == qid
        assert item.get("no") == tb.parse_qid(qid)[1]
    # 학생 qbank 의 id 가 곧 AIGEN qid 인지(있을 때만)
    qbank = ROOT / "data_private" / "student" / "qbank.json"
    if qbank.exists():
        ids = [q.get("id") for q in json.loads(qbank.read_text(encoding="utf-8")).get("questions") or []]
        aigen_ids = [i for i in ids if tb.parse_qid(i)]
        assert aigen_ids and all(i in items for i in aigen_ids)
