"""교수 전용 '원문 보기' 발췌 서비스(src/services/textbook_evidence) — 합성 쪽 인덱스로만 검사한다(실 Harrison 텍스트 미접근)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services import textbook_evidence as te


@pytest.fixture
def harrison_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "harrison22e"
    root.mkdir()
    rows = [
        {"chapter": 10, "printed_page": 99, "pdf_page": 120, "segment_text": "Page ninety-nine text about fever onset."},
        {"chapter": 10, "printed_page": 100, "pdf_page": 121, "segment_text": "Fever in adults: the case-fatality rate is 1-2% and up to 10-20% in pregnant women. Dose 500 mg twice daily."},
        {"chapter": 10, "printed_page": 101, "pdf_page": 122, "segment_text": "Continuation page one hundred one."},
        {"chapter": 11, "printed_page": 102, "pdf_page": 123, "segment_text": "Next chapter starts here."},
        {"chapter": 12, "printed_page": 100, "pdf_page": 900, "segment_text": "Different chapter sharing printed page 100 (should not win when chapter 10 exists)."},
    ]
    (root / te.PAGES_FILENAME).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (root / te.CHAPTER_INDEX_FILENAME).write_text(
        json.dumps({"chapters": [{"chapter": 10, "filename_title": "Fever"}, {"chapter": 11, "filename_title": "Chills"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv(te.ENV_HARRISON_DIR, str(root))
    monkeypatch.delenv(te.ENV_LIBRARY_PROXY_PREFIX, raising=False)
    monkeypatch.delenv(te.ENV_ACCESSMEDICINE_BOOKID, raising=False)
    monkeypatch.delenv(te.ENV_LIBRARY_PROFILE, raising=False)
    te.clear_caches()
    yield root
    te.clear_caches()


def _item(**extra):
    item = {
        "qid": "AIGEN_1_001",
        "concept": "fever_unknown_origin",
        "explanation": "임신부 치명률은 10-20%로 높고 용량은 500 mg이다. 참고치 7.35–7.45.",
        "harrison_sources": [{"source_id": "H10", "chapter": 10, "printed_page": 100, "entailment_status": "partially_supported"}],
        "textbook_sources": [{"book_id": "nelson_21e", "chapter": 5}],
        "v2_revision": {"evidence": "Harrison 22e Ch.10 원문 확인: 'the case-fatality rate is 1-2% and up to 10-20% in pregnant women' 그리고 \"Dose 500 mg twice daily\"."},
    }
    item.update(extra)
    return item


def test_excerpt_prefers_same_chapter_and_returns_context(harrison_dir):
    excerpt = te.harrison_excerpt(10, 100, context=1)
    assert excerpt["available"] is True and excerpt["chapter_title"] == "Fever" and excerpt["chapter_mismatch"] is False
    assert [p["printed_page"] for p in excerpt["pages"]] == [99, 100, 101]
    cited = next(p for p in excerpt["pages"] if p["is_cited"])
    assert cited["chapter"] == 10 and cited["pdf_page"] == 121 and "case-fatality" in cited["text"]
    # context 상한(2)과 하한(0)
    assert [p["printed_page"] for p in te.harrison_excerpt(10, 100, context=9)["pages"]] == [99, 100, 101, 102]
    assert [p["printed_page"] for p in te.harrison_excerpt(10, 100, context=0)["pages"]] == [100]


def test_excerpt_falls_back_across_chapters_and_handles_missing(harrison_dir):
    # 장 번호가 인덱스와 다르면 같은 인쇄 쪽수의 세그먼트를 쓰되 불일치를 표시한다
    fallback = te.harrison_excerpt(99, 102, context=0)
    assert fallback["chapter_mismatch"] is True and fallback["pages"][0]["chapter"] == 11
    assert te.harrison_excerpt(10, 555) is None
    assert te.harrison_excerpt(10, None) is None
    assert te.harrison_excerpt(10, "abc") is None


def test_quotes_and_highlight_terms(harrison_dir):
    item = _item()
    quotes = te.extract_quotes(item)
    assert quotes == ["the case-fatality rate is 1-2% and up to 10-20% in pregnant women", "Dose 500 mg twice daily"]
    terms = te.highlight_terms(item, quotes)
    assert terms[0] == quotes[0]                    # 긴 것부터
    assert "10-20%" in terms and "500 mg" in terms  # 해설의 수치 표현
    assert all(len(t) >= 3 for t in terms)


def test_quote_fragments_split_on_ellipsis(harrison_dir):
    quotes = ["The diagnosis is best made on CT scan... colon cancer is low (<2%) but higher … with complicated diverticulitis (6-8%)", "short"]
    fragments = te.quote_fragments(quotes)
    assert fragments == ["The diagnosis is best made on CT scan", "colon cancer is low (<2%) but higher", "with complicated diverticulitis (6-8%)"]
    terms = te.highlight_terms(_item(v2_revision={"evidence": "'The diagnosis is best made on CT scan... colon cancer is low (<2%)'"}), None)
    assert "The diagnosis is best made on CT scan" in terms and "colon cancer is low (<2%)" in terms


def test_source_texts_for_item_shape_and_links(harrison_dir, monkeypatch):
    payload = te.source_texts_for_item(_item(), context=1)
    assert payload["policy"] == "faculty_only_verification_excerpt" and payload["qid"] == "AIGEN_1_001"
    harrison, nelson = payload["sources"]
    assert harrison["available"] is True and harrison["chapter_title"] == "Fever" and len(harrison["pages"]) == 3
    assert nelson == {"book_id": "nelson_21e", "chapter": 5, "printed_page": None, "available": False, "reason": "chapter_index_only"}
    links = payload["library_links"]
    kinds = [link["kind"] for link in links]
    # 기본(부산대 프로필): 장 본문 딥링크(공개 목차 sectionid) → 토픽 검색(book=3541) → 교외 도서관 로그인 경유 → MSD 공개
    assert kinds == ["accessmedicine_chapter", "accessmedicine_topic_search", "pnu_offcampus_login", "msd_professional_search"]
    assert links[0]["url"] == te.accessmedicine_chapter_url(10) and "bookid=3541&sectionid=" in links[0]["url"]
    assert harrison["accessmedicine_url"] == links[0]["url"]
    assert "q=Fever" in links[1]["url"] and "book=3541" in links[1]["url"]
    # 교외 링크 = 도서관 로그인?returnUrl=ENCODE(lproxy 접두어 + 장 URL); lproxy 단독 URL은 절대 내보내지 않는다
    assert links[2]["url"] == "https://lib.pusan.ac.kr/login?returnUrl=" + __import__("urllib.parse").parse.quote("https://lproxy.pusan.ac.kr/_Lib_Proxy_Url/" + links[0]["url"], safe="")
    assert links[2]["verified"] == "partial" and "미실측" in links[2]["note"]
    assert not any(link["url"].startswith("https://lproxy.pusan.ac.kr") for link in links)
    # 목차에 없는 장은 딥링크 없이 검색으로 폴백
    fallback = te.source_texts_for_item(_item(harrison_sources=[{"chapter": 999, "printed_page": 100}]))["library_links"]
    assert [l["kind"] for l in fallback] == ["accessmedicine_topic_search", "pnu_offcampus_login", "msd_professional_search"]
    # 프로필 끄기
    monkeypatch.setenv(te.ENV_LIBRARY_PROFILE, "none")
    assert "pnu_offcampus_login" not in [l["kind"] for l in te.source_texts_for_item(_item())["library_links"]]
    # 타 기관 EZproxy식 접두어가 있으면 그것이 맨 앞, 부산대 링크는 빠진다; book id 재정의는 검색에만 적용(딥링크는 3541 고정)
    monkeypatch.delenv(te.ENV_LIBRARY_PROFILE)
    monkeypatch.setenv(te.ENV_LIBRARY_PROXY_PREFIX, "https://libproxy.example.ac.kr/login?url=")
    monkeypatch.setenv(te.ENV_ACCESSMEDICINE_BOOKID, "1234")
    links = te.source_texts_for_item(_item())["library_links"]
    assert [l["kind"] for l in links] == ["library_proxy", "accessmedicine_chapter", "accessmedicine_topic_search", "msd_professional_search"]
    assert links[0]["url"].startswith("https://libproxy.example.ac.kr/login?url=https%3A%2F%2Faccessmedicine.mhmedical.com%2Fcontent.aspx")
    assert "book=1234" in links[2]["url"] and "bookid=3541" in links[1]["url"]


def test_accessmedicine_toc_reference_is_verified_shape():
    """공개 목차에서 읽은 sectionid만 담는 참조 파일 — 추측값·중복·타 판(bookid) 금지."""
    data = json.loads(te.ACCESSMEDICINE_TOC_PATH.read_text(encoding="utf-8"))
    assert data["schema"] == "paccine.accessmedicine_toc.v1" and data["book_id"] == "3541" == te.ACCESSMEDICINE_HARRISON_22E_BOOKID
    chapters = data["chapters"]
    assert len(chapters) >= 81
    section_ids = [row["sectionid"] for row in chapters.values()]
    assert all(key.isdigit() and sid.isdigit() and row["title"] for key, row in chapters.items() for sid in [row["sectionid"]])
    assert len(set(section_ids)) == len(section_ids)
    assert te.accessmedicine_chapter_url(73) == "https://accessmedicine.mhmedical.com/content.aspx?bookid=3541&sectionid=295692059"
    assert te.accessmedicine_chapter_url("no-such") is None and te.accessmedicine_chapter_url(None) is None


def test_missing_chapter_no_reports_reason(harrison_dir):
    payload = te.source_texts_for_item(_item(harrison_sources=[{"chapter": 10, "printed_page": 777}, {"chapter": 11}], textbook_sources=[]))
    first, second = payload["sources"]
    assert first["available"] is False and first["reason"] == "page_text_not_indexed" and first["chapter_title"] == "Fever"
    assert second["available"] is False and second["reason"] == "printed_page_missing" and second["chapter_title"] == "Chills"


def test_missing_index_directory_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv(te.ENV_HARRISON_DIR, str(tmp_path / "nope"))
    te.clear_caches()
    assert te.harrison_excerpt(10, 100) is None
    assert te.chapter_title(10) is None
    assert te.source_texts_for_item(_item())["sources"][0]["available"] is False


# ── 과별 교과서 발췌(T-TBX-01) — 합성 픽스처만 사용 ────────────────────────────────────
def _write_book(root: Path, book_id: str, rows: list[dict], title: str | None = "Synthetic Book") -> None:
    book = root / book_id
    book.mkdir(parents=True)
    (book / te.PAGES_FILENAME).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    if title:
        (book / te.MANIFEST_FILENAME).write_text(json.dumps({"book_id": book_id, "title": title}), encoding="utf-8")


def _row(pdf_page, label, chapter, text):
    return {"pdf_page": pdf_page, "printed_label": label, "chapter": chapter, "chapter_title": f"Ch{chapter}" if chapter else None, "chars": len(text), "text": text, "text_sha256": "x"}


@pytest.fixture
def textbooks_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "textbooks"
    _write_book(root, "labeled_book", [
        _row(1, "Cover", None, "cover"),
        _row(10, "101", 3, "alpha page one hundred one"),
        _row(11, "102", 3, "beta page with ovulation induction clomiphene"),
        _row(12, "103", 3, "gamma page"),
        _row(13, "104", 4, "delta next chapter"),
        _row(14, "105", 4, ""),
    ])
    _write_book(root, "chapter_only_book", [
        _row(1, None, 5, "first page of chapter five"),
        _row(2, None, 5, "second page"),
        _row(3, None, 5, "third page mentions Zebra Stripe Sign twice and Zebra Stripe Sign"),
        _row(4, None, 5, "fourth page"),
        _row(5, None, 5, "fifth page"),
        _row(6, None, 6, "other chapter"),
    ], title=None)
    monkeypatch.setenv(te.ENV_TEXTBOOKS_DIR, str(root))
    te.clear_caches()
    yield root
    te.clear_caches()


def test_textbook_excerpt_by_printed_label(textbooks_dir):
    ex = te.textbook_excerpt("labeled_book", 3, "102", context=1)
    assert ex["available"] is True and ex["page_locator"] == "printed_page" and ex["book_title"] == "Synthetic Book"
    assert [(p["pdf_page"], p["printed_label"], p["is_cited"]) for p in ex["pages"]] == [(10, "101", False), (11, "102", True), (12, "103", False)]
    assert all(set(p) == {"pdf_page", "printed_label", "chapter", "text", "is_cited"} for p in ex["pages"])
    # 장 번호가 없어도 라벨만으로 찾는다 / 숫자 입력도 허용
    assert te.textbook_excerpt("labeled_book", None, 103, context=0)["pages"][0]["pdf_page"] == 12
    # 없는 라벨 → 장 기준 폴백(장 첫 쪽)
    fallback = te.textbook_excerpt("labeled_book", 3, "999", context=0)
    assert fallback["page_locator"] == "chapter_start" and fallback["pages"][0]["pdf_page"] == 10
    # 장도 없으면 사유와 함께 불가
    missing = te.textbook_excerpt("labeled_book", None, "999")
    assert missing["available"] is False and missing["reason"] == "page_text_not_indexed"


def test_textbook_excerpt_chapter_term_match_and_start_fallback(textbooks_dir):
    ex = te.textbook_excerpt("chapter_only_book", 5, None, terms=["zebra stripe sign", "absent term"], context=0)
    assert ex["page_locator"] == "chapter_term_match" and ex["matched_terms"] == 1 and ex["pages"][0]["pdf_page"] == 3
    assert ex["pages"][0]["printed_label"] is None and ex["book_title"] == "chapter_only_book"   # manifest 없으면 book_id
    # 책에 라벨이 없으면 쪽이 주어져도 장 기준
    assert te.textbook_excerpt("chapter_only_book", 5, 77, terms=["zebra stripe sign"], context=0)["page_locator"] == "chapter_term_match"
    # 하나도 안 맞음 → 장 첫 쪽
    start = te.textbook_excerpt("chapter_only_book", 5, None, terms=["nothing matches"], context=0)
    assert start["page_locator"] == "chapter_start" and start["pages"][0]["pdf_page"] == 1
    assert te.textbook_excerpt("chapter_only_book", 5, None)["page_locator"] == "chapter_start"
    assert te.textbook_excerpt("chapter_only_book", 99, None)["reason"] == "chapter_text_not_indexed"
    assert te.textbook_excerpt("chapter_only_book", None, None)["reason"] == "chapter_missing"


def test_textbook_excerpt_page_cap_and_chapter_boundary(textbooks_dir):
    ex = te.textbook_excerpt("chapter_only_book", 5, None, terms=["third page"], context=9)
    assert len(ex["pages"]) == 2 * te.MAX_CONTEXT_PAGES + 1 and [p["pdf_page"] for p in ex["pages"]] == [1, 2, 3, 4, 5]
    assert sum(p["is_cited"] for p in ex["pages"]) == 1
    # 장 경계를 넘는 쪽(6쪽, 다른 장)은 장 기준 발췌에 포함되지 않는다
    edge = te.textbook_excerpt("chapter_only_book", 5, None, terms=["fifth page"], context=2)
    assert [p["pdf_page"] for p in edge["pages"]] == [3, 4, 5]


def test_source_texts_attach_specialty_excerpt(textbooks_dir, harrison_dir):
    item = _item(textbook_sources=[
        {"source_id": "T1", "book_id": "labeled_book", "chapter": 3, "page": "102", "entailment_status": "unverified"},
        {"book_id": "chapter_only_book", "chapter": 5},
        {"book_id": "nelson_21e", "chapter": 5},
    ])
    payload = te.source_texts_for_item(item, context=0)
    harrison, labeled, chapter_only, absent = payload["sources"]
    assert harrison["available"] is True and "pages" in harrison and "page_locator" not in harrison   # Harrison 불변
    assert labeled["available"] is True and labeled["page_locator"] == "printed_page" and labeled["source_id"] == "T1" and labeled["printed_page"] == "102"
    assert chapter_only["available"] is True and chapter_only["page_locator"] in {"chapter_term_match", "chapter_start"}
    assert absent == {"book_id": "nelson_21e", "chapter": 5, "printed_page": None, "available": False, "reason": "chapter_index_only"}


def test_source_texts_without_textbooks_dir_keeps_legacy_shape(tmp_path, monkeypatch, harrison_dir):
    monkeypatch.setenv(te.ENV_TEXTBOOKS_DIR, str(tmp_path / "nope"))
    te.clear_caches()
    nelson = te.source_texts_for_item(_item())["sources"][1]
    assert nelson == {"book_id": "nelson_21e", "chapter": 5, "printed_page": None, "available": False, "reason": "chapter_index_only"}
    assert te.textbook_excerpt("../etc", 1) is None and te.textbook_excerpt("", 1) is None


def test_source_texts_unavailable_local_book_keeps_source_id_and_entailment(textbooks_dir, harrison_dir):
    item = _item(textbook_sources=[
        {"source_id": "T9", "book_id": "chapter_only_book", "chapter": 99, "entailment_status": "unverified"},
        {"source_id": "T8", "book_id": "labeled_book", "entailment_status": "verified"},
    ])
    payload = te.source_texts_for_item(item, context=0)
    missing_chapter, missing_chapter_no = payload["sources"][1:]
    assert missing_chapter["available"] is False and missing_chapter["reason"] == "chapter_text_not_indexed"
    assert missing_chapter["source_id"] == "T9" and missing_chapter["entailment_status"] == "unverified"
    assert missing_chapter_no["available"] is False and missing_chapter_no["reason"] == "chapter_missing"
    assert missing_chapter_no["source_id"] == "T8" and missing_chapter_no["entailment_status"] == "verified"


# ── 매칭 정규화 + 불일치 경고(T-TBX-02) — 합성 픽스처만 사용 ─────────────────────────────
def test_match_norm_folds_typography_but_display_text_is_untouched(tmp_path, monkeypatch):
    soft = "The oo­phorectomy of the ﬁbrous tissue — note the con-\ntraction and the “Crohn’s” sign"
    norm = te._match_norm(soft)
    assert "oophorectomy" in norm and "fibrous" in norm and "contraction" in norm   # 소프트 하이픈·합자·줄 끝 분철
    assert "crohn's" in norm and '"' in norm and "-" in norm                          # 굽은 따옴표·대시 통일
    assert te._match_norm("Well-\nKnown") == "well-\nknown".replace("\n", " ")        # 대문자 앞 하이픈은 합치지 않음
    root = tmp_path / "tb"
    _write_book(root, "typo_book", [
        _row(1, None, 7, "intro page"),
        _row(2, None, 7, "The oo­phorectomy of ﬁbrous tissue and the con-\ntraction of the Crohn’s lesion"),
        _row(3, None, 7, "other page"),
    ])
    monkeypatch.setenv(te.ENV_TEXTBOOKS_DIR, str(root))
    te.clear_caches()
    item = {"evidence": 'Quote: "the oophorectomy of fibrous tissue and the contraction of the Crohn\'s lesion"', "textbook_sources": [{"book_id": "typo_book", "chapter": 7}]}
    src = te.source_texts_for_item(item, context=0)["sources"][0]
    assert src["page_locator"] == "chapter_term_match" and src["pages"][0]["pdf_page"] == 2
    assert "­" in src["pages"][0]["text"] and "ﬁ" in src["pages"][0]["text"]     # 표시용 텍스트는 원문 그대로
    te.clear_caches()


def test_extract_quotes_allows_apostrophes_in_double_quotes():
    item = {"evidence": "Ref: \"Crohn's disease affects the terminal ileum\" and 'a single quoted passage here' and “Parkinson’s disease is common”"}
    quotes = te.extract_quotes(item)
    assert "Crohn's disease affects the terminal ileum" in quotes
    assert "a single quoted passage here" in quotes
    assert "Parkinson’s disease is common" in quotes
    assert not any(q.startswith("s ") for q in quotes)


def test_textbook_excerpt_mismatch_and_page_flags(textbooks_dir):
    ok = te.textbook_excerpt("labeled_book", 3, "102", context=0)
    assert (ok["chapter_mismatch"], ok["resolved_chapter"], ok["page_ignored"], ok["page_not_found"]) == (False, None, False, False)
    # 쪽 라벨은 있으나 장이 다름 → chapter는 요청값 유지, resolved_chapter에 실제 장
    wrong = te.textbook_excerpt("labeled_book", 4, "102", context=0)
    assert wrong["page_locator"] == "printed_page" and wrong["chapter_mismatch"] is True
    assert wrong["chapter"] == 4 and wrong["resolved_chapter"] == 3 and wrong["pages"][0]["pdf_page"] == 11
    # 쪽 라벨이 책에 없음 → 장 기반 폴백 + page_not_found
    nf = te.textbook_excerpt("labeled_book", 3, "999", context=0)
    assert nf["page_locator"] == "chapter_start" and nf["page_not_found"] is True and nf["page_ignored"] is False
    # 책에 쪽 라벨이 없는데 쪽을 줌 → page_ignored
    ig = te.textbook_excerpt("chapter_only_book", 5, 77, context=0)
    assert ig["page_ignored"] is True and ig["page_not_found"] is False
    none = te.textbook_excerpt("chapter_only_book", 5, None, context=0)
    assert none["page_ignored"] is False and none["page_not_found"] is False


def test_textbook_snapshot_cache_holds_eight_books():
    assert te._textbook_snapshot.cache_info().maxsize == 8
