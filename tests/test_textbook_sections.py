"""절(section) 앵커(T-TBX-03) — 합성 PDF·픽스처만 사용(실제 교과서 미접근)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import fitz
import pytest

from src.services import textbook_evidence as te

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("build_textbook_sections", ROOT / "scripts" / "build_textbook_sections.py")
bts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bts)  # type: ignore[union-attr]


# ── 합성 책 만들기 ────────────────────────────────────────────────────────────────
def _make_book(root: Path, book_id: str, pages_per_chapter: dict[int, tuple[int, int]]) -> Path:
    book = root / book_id
    book.mkdir(parents=True)
    rows = []
    for chapter, (start, end) in pages_per_chapter.items():
        for pno in range(start, end + 1):
            text = f"synthetic body of page {pno}"
            rows.append({"pdf_page": pno, "printed_label": None, "chapter": chapter, "chapter_title": f"Chapter {chapter}", "chars": len(text), "text": text, "text_sha256": "x"})
    (book / "pages.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (book / "chapter_index.json").write_text(
        json.dumps({"chapters": [{"chapter": c, "title": f"Chapter {c}", "pdf_page_start": s, "pdf_page_end": e} for c, (s, e) in pages_per_chapter.items()]}),
        encoding="utf-8",
    )
    return book


def _run_builder(monkeypatch, root: Path, book_id: str, pdf: Path, *extra: str) -> dict:
    monkeypatch.setattr(sys, "argv", ["build_textbook_sections.py", "--book-id", book_id, "--pdf", str(pdf), "--textbooks-dir", str(root), *extra])
    assert bts.main() == 0
    return json.loads((root / book_id / "section_index.json").read_text(encoding="utf-8"))


# ── 목차 기반 ────────────────────────────────────────────────────────────────────
def test_builder_toc_path(tmp_path, monkeypatch):
    root = tmp_path / "tb"
    _make_book(root, "toc_book", {1: (2, 5), 2: (6, 8)})
    doc = fitz.open()
    for _ in range(8):
        doc.new_page()
    doc.set_toc(
        [
            [1, "Part I", 1],
            [2, "Chapter 1: Alpha", 2],
            [3, "First Topic", 3],
            [4, "Sub A", 3],
            [4, "Sub B", 4],
            [3, "Second Topic", 5],
            [2, "Chapter 2: Beta", 6],
            [3, "Beta Topic", 7],
        ]
    )
    pdf = tmp_path / "toc.pdf"
    doc.save(str(pdf))
    payload = _run_builder(monkeypatch, root, "toc_book", pdf)
    assert payload["source"] == "toc"
    sections = payload["sections"]
    assert [s["section_id"] for s in sections] == ["1.1", "1.2", "1.3", "1.4", "2.1"]
    assert payload["source_info"]["toc_deeper_entries"] == len(sections) == 5       # 장 아래 목차 항목이 빠짐없이 절로 들어감
    sub_b = sections[2]
    assert sub_b["title"] == "Sub B" and sub_b["path"] == ["First Topic", "Sub B"] and sub_b["level"] == 2
    assert (sections[0]["pdf_page_start"], sections[0]["pdf_page_end"]) == (3, 4)   # 다음 같은/상위 단계 항목 전까지
    assert sections[3]["pdf_page_end"] == 5 and sections[4]["pdf_page_end"] == 8     # 장 끝으로 제한
    assert payload["summary"]["chapters_with_zero_sections"] == 0
    assert "synthetic body" not in json.dumps(payload)


# ── 글꼴 기반 ────────────────────────────────────────────────────────────────────
def _font_pdf(path: Path) -> None:
    doc = fitz.open()

    def page(chapter_label=None, chapter_title=None, bold=(), body=3):
        pg = doc.new_page()
        pg.insert_text((72, 20), "RUNNING HEAD", fontsize=17.2, fontname="hebo")   # 머리말(모든 쪽 되풀이)
        y = 90.0
        if chapter_label:
            pg.insert_text((72, y), chapter_label, fontsize=17.2, fontname="hebo"); y += 40
            pg.insert_text((72, y), chapter_title, fontsize=24.7, fontname="hebo"); y += 40
        for text, x, *gap in bold:
            pg.insert_text((x, y), text, fontsize=17.2, fontname="hebo"); y += gap[0] if gap else 60
        for i in range(body):
            pg.insert_text((72, y), f"ordinary body sentence number {i} for the synthetic page", fontsize=13.5, fontname="helv"); y += 20
        return pg

    page("CHAPTER 1", "Synthetic Chapter", bold=[("MAIN HEADING", 72)])
    page(bold=[("Plain Subheading", 72), ("FIGURE 1-1 A caption", 72), ("AB", 72)])
    page(bold=[("Wrapped Heading That Continues", 72, 20), ("onto Second Line", 80)])
    page("CHAPTER 2", "Second Chapter", bold=[("OTHER HEADING", 72), (" Bulleted Heading", 83)])
    page()
    doc.save(str(path))


def test_builder_font_path(tmp_path, monkeypatch):
    monkeypatch.setattr(bts, "HEADER_REPEAT_PAGES", 3)
    root = tmp_path / "tb"
    _make_book(root, "font_book", {1: (1, 3), 2: (4, 5)})
    pdf = tmp_path / "font.pdf"
    _font_pdf(pdf)
    payload = _run_builder(monkeypatch, root, "font_book", pdf)
    assert payload["source"] == "font"
    titles = [(s["chapter"], s["title"], s["level"], s["pdf_page_start"]) for s in payload["sections"]]
    assert titles == [
        (1, "MAIN HEADING", 1, 1),
        (1, "Plain Subheading", 3, 2),
        (1, "Wrapped Heading That Continues onto Second Line", 3, 3),
        (2, "OTHER HEADING", 1, 4),
        (2, "Bulleted Heading", 2, 4),
    ]
    info = payload["source_info"]
    assert info["excluded_chapter_label"] == 2 and info["excluded_caption"] == 1 and info["excluded_too_short"] == 1 and info["excluded_running_header"] == 5
    by_id = {s["section_id"]: s for s in payload["sections"]}
    assert by_id["2.2"]["path"] == ["OTHER HEADING", "Bulleted Heading"]
    assert payload["summary"]["chapters_with_zero_sections"] == 0


# ── 발췌 쪽 ────────────────────────────────────────────────────────────────────
@pytest.fixture
def section_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "textbooks"
    book = _make_book(root, "sec_book", {1: (10, 16), 2: (17, 20)})
    (book / "manifest.json").write_text(json.dumps({"title": "Section Book"}), encoding="utf-8")
    sections = [
        {"section_id": "1.1", "chapter": 1, "level": 1, "title": "Ovarian Cycle", "path": ["Ovarian Cycle"], "pdf_page_start": 11, "pdf_page_end": 13},
        {"section_id": "1.2", "chapter": 1, "level": 2, "title": "Follicular Phase", "path": ["Ovarian Cycle", "Follicular Phase"], "pdf_page_start": 12, "pdf_page_end": 13},
        {"section_id": "1.3", "chapter": 1, "level": 1, "title": "Management", "path": ["Management"], "pdf_page_start": 14, "pdf_page_end": 16},
        {"section_id": "2.1", "chapter": 2, "level": 1, "title": "Management", "path": ["Management"], "pdf_page_start": 18, "pdf_page_end": 20},
    ]
    (book / "section_index.json").write_text(json.dumps({"sections": sections}), encoding="utf-8")
    _make_book(root, "plain_book", {1: (1, 3)})
    monkeypatch.setenv(te.ENV_TEXTBOOKS_DIR, str(root))
    te.clear_caches()
    yield root
    te.clear_caches()


def test_section_lookup_opens_start_page_with_paths(section_dir):
    ex = te.textbook_excerpt("sec_book", 1, None, section="follicular   phase", context=1)   # 정규화 비교(대소문자·공백)
    assert ex["page_locator"] == "section" and ex["section_not_found"] is False and ex["section_ambiguous"] is False
    assert [p["pdf_page"] for p in ex["pages"]] == [11, 12, 13]
    assert next(p for p in ex["pages"] if p["is_cited"])["pdf_page"] == 12
    assert ex["section"]["section_id"] == "1.2" and ex["section"]["path"] == ["Ovarian Cycle", "Follicular Phase"]
    # 쪽 → 절 경로 부착: 각 쪽이 속한 가장 최근 시작 절
    assert [p["section_path"] for p in ex["pages"]] == [["Ovarian Cycle"], ["Ovarian Cycle", "Follicular Phase"], ["Ovarian Cycle", "Follicular Phase"]]
    # section_id·경로형 문자열도 허용
    assert te.textbook_excerpt("sec_book", 1, None, section="1.3", context=0)["pages"][0]["pdf_page"] == 14
    assert te.textbook_excerpt("sec_book", 1, None, section="Ovarian Cycle › Follicular Phase", context=0)["section"]["section_id"] == "1.2"


def test_section_scope_ambiguity_and_chapter_mismatch(section_dir):
    in_two = te.textbook_excerpt("sec_book", 2, None, section="Management", context=0)
    assert in_two["section"]["section_id"] == "2.1" and in_two["section_ambiguous"] is False   # 요청 장 안 후보 우선
    both = te.textbook_excerpt("sec_book", None, None, section="Management", context=0)
    assert both["section"]["section_id"] == "1.3" and both["section_ambiguous"] is True
    wrong = te.textbook_excerpt("sec_book", 2, None, section="Follicular Phase", context=0)   # 다른 장의 절 → 숨기지 않고 표시
    assert wrong["chapter"] == 2 and wrong["resolved_chapter"] == 1 and wrong["chapter_mismatch"] is True and wrong["page_locator"] == "section"


def test_section_not_found_falls_back_to_chapter(section_dir):
    ex = te.textbook_excerpt("sec_book", 1, None, section="No Such Heading", terms=["page 15"], context=0)
    assert ex["section_not_found"] is True and ex["page_locator"] == "chapter_term_match" and ex["pages"][0]["pdf_page"] == 15
    # 절 인덱스가 없는 책도 not_found + 장 기반 폴백, 발췌 쪽에 section_path 키 없음(응답 모양 불변)
    plain = te.textbook_excerpt("plain_book", 1, None, section="Anything", context=0)
    assert plain["section_not_found"] is True and plain["page_locator"] == "chapter_start" and "section_path" not in plain["pages"][0]
    # 절을 주지 않으면 not_found가 아님
    assert te.textbook_excerpt("sec_book", 1, None, context=0)["section_not_found"] is False


def test_pages_before_first_section_have_no_path_and_printed_page_wins(section_dir):
    ex = te.textbook_excerpt("sec_book", 1, None, section="Ovarian Cycle", context=2)
    assert ex["page_locator"] == "section" and [p["pdf_page"] for p in ex["pages"]] == [10, 11, 12, 13]
    assert ex["pages"][0]["section_path"] is None      # 장 표지 쪽(첫 절 이전)


def test_source_texts_pass_section_and_citation_label(section_dir):
    item = {"qid": "X", "textbook_sources": [{"book_id": "sec_book", "chapter": 1, "section": "Management"}, {"book_id": "nope_book", "chapter": 3, "section": "Anything"}]}
    first, second = te.source_texts_for_item(item, context=0)["sources"]
    assert first["page_locator"] == "section" and first["section"]["section_id"] == "1.3" and first["pages"][0]["pdf_page"] == 14
    assert second == {"book_id": "nope_book", "chapter": 3, "printed_page": None, "available": False, "reason": "chapter_index_only"} or second["reason"] == "chapter_index_only"
    # 인용 문자열: 쪽 라벨 없는 책은 "Ch.N › 절 제목", 쪽 라벨 있는 책은 "Ch.N p.N"
    assert te.citation_label("sec_book", 1, None, "1.2") == "Ch.1 › Ovarian Cycle › Follicular Phase"   # 전체 경로
    assert te.citation_label("sec_book", 1, None, "Ovarian Cycle") == "Ch.1 › Ovarian Cycle"
    assert te.citation_label("sec_book", 1) == "Ch.1"
    root = section_dir
    _make_book(root, "labelled_book", {3: (1, 2)})
    rows = [json.loads(l) for l in (root / "labelled_book" / "pages.jsonl").read_text().splitlines()]
    for i, r in enumerate(rows):
        r["printed_label"] = str(100 + i)
    (root / "labelled_book" / "pages.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    te.clear_caches()
    assert te.citation_label("labelled_book", 3, 101, "Anything") == "Ch.3 p.101"
    # 풀리지 않는 절(책 없음)은 장만 — 깨끗한 인용을 꾸며내지 않고 resolved=False로 감지 가능
    assert te.citation_label("absent_book", 4, None, "Some Heading") == "Ch.4"
    assert te.resolve_citation("absent_book", 4, None, "Some Heading") == {"label": "Ch.4", "section_id": None, "resolved": False}
    assert te.resolve_citation("sec_book", 1, None, "No Such") == {"label": "Ch.1", "section_id": None, "resolved": False}
    assert te.resolve_citation("sec_book", 1, None, "1.2") == {"label": "Ch.1 › Ovarian Cycle › Follicular Phase", "section_id": "1.2", "resolved": True}
    assert te.resolve_citation("sec_book", 1)["resolved"] is None


# ── QA 후속(A·B·F·G·I) ────────────────────────────────────────────────────────────
def test_path_must_end_with_given_segments(section_dir):
    ok = te.textbook_excerpt("sec_book", 1, None, section="Ovarian Cycle › Follicular Phase", context=0)
    assert ok["section"]["section_id"] == "1.2"
    bad = te.textbook_excerpt("sec_book", 1, None, section="Management › Follicular Phase", context=0)   # 마지막 제목은 있으나 상위가 틀림
    assert bad["section_not_found"] is True and bad["page_locator"] == "chapter_start"
    assert te.textbook_excerpt("sec_book", 1, None, section="Ovarian Cycle > Follicular Phase", context=0)["section_not_found"] is True   # ">"는 구분자 아님
    assert te.textbook_excerpt("sec_book", 1, None, section="OVARIAN   cycle › follicular phase", context=0)["section"]["section_id"] == "1.2"


def test_non_citable_section_is_not_resolved(section_dir):
    book = section_dir / "sec_book"
    sections = json.loads((book / "section_index.json").read_text())["sections"]
    sections.append({"section_id": "1.4", "chapter": 1, "level": 1, "title": "References", "path": ["References"], "pdf_page_start": 16, "pdf_page_end": 16, "citable": False})
    (book / "section_index.json").write_text(json.dumps({"sections": sections}), encoding="utf-8")
    te.clear_caches()
    for ref in ("References", "1.4"):
        ex = te.textbook_excerpt("sec_book", 1, None, section=ref, terms=["page 12"], context=0)
        assert ex["section_not_found"] is True and ex["section_not_citable"] is True and ex["page_locator"] == "chapter_term_match"
    assert te.resolve_citation("sec_book", 1, None, "1.4")["resolved"] is False
    ok = te.textbook_excerpt("sec_book", 1, None, section="Management", context=0)
    assert ok["section_not_citable"] is False and ok["page_locator"] == "section"
    # 쪽 → 경로에는 인용 불가 절도 그대로 나온다
    assert te.textbook_excerpt("sec_book", 1, None, context=0, terms=["page 16"])["pages"][0]["section_path"] == ["References"]


def test_builder_marks_reference_sections_non_citable():
    for title in ("References", " references. ", "Suggested Readings", "Further Reading", "BIBLIOGRAPHY"):
        assert bts.is_citable_title(title) is False
    assert bts.is_citable_title("Reference Ranges") is True
    raw = [{"chapter": 1, "level": 1, "title": "Topic", "start": 2}, {"chapter": 1, "level": 1, "title": "References", "start": 3}]
    out = bts.finalize(raw, [{"chapter": 1, "title": "Chapter 1", "start": 1, "end": 4}])
    assert [s["citable"] for s in out] == [True, False]


def test_clean_title_does_not_truncate_before_safety_cap():
    long_title = " ".join(["word"] * 40)      # 199자
    assert bts.clean_title(long_title) == long_title
    huge = " ".join(["abcdefghi"] * 60)
    cut = bts.clean_title(huge)
    assert len(cut) <= bts.MAX_TITLE_CHARS and cut.endswith("abcdefghi") and huge.startswith(cut)


def test_mismatch_header_reports_resolved_chapter_title(section_dir):
    wrong = te.textbook_excerpt("sec_book", 2, None, section="Follicular Phase", context=0)
    assert wrong["chapter_mismatch"] is True and wrong["resolved_chapter"] == 1
    assert wrong["resolved_chapter_title"] == "Chapter 1" and wrong["chapter_title"] == "Chapter 2"
    fine = te.textbook_excerpt("sec_book", 1, None, section="Follicular Phase", context=0)
    assert fine["resolved_chapter_title"] is None


def test_term_match_tie_flag(section_dir):
    tie = te.textbook_excerpt("sec_book", 1, None, terms=["synthetic body"], context=0)   # 모든 쪽이 같은 점수
    assert tie["page_locator"] == "chapter_term_match" and tie["term_match_ambiguous"] is True and tie["term_match_candidates"] == 7
    assert tie["pages"][0]["pdf_page"] == 10
    unique = te.textbook_excerpt("sec_book", 1, None, terms=["page 13"], context=0)
    assert unique["term_match_ambiguous"] is False and unique["term_match_candidates"] == 1


def test_text_quality_field_follows_quality_json(section_dir):
    assert "text_quality" not in te.textbook_excerpt("sec_book", 1, None, context=0)
    (section_dir / "sec_book" / "quality.json").write_text(json.dumps({"usable_for_evidence": False, "reasons": ["garbled_ratio_median>=0.02"], "garbled_ratio_median": 0.05}), encoding="utf-8")
    te.clear_caches()
    ex = te.textbook_excerpt("sec_book", 1, None, context=0)
    assert ex["text_quality"] == {"usable_for_evidence": False, "reasons": ["garbled_ratio_median>=0.02"]}
