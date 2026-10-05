"""교수 검토 콘솔 '원문 보기' — 인용된 교과서 쪽의 텍스트 발췌(교수 전용, 2026-09-27).

문항이 인용한 Harrison 22e 장·인쇄 쪽수로 `data_private/harrison/22e/pages.jsonl`(쪽 단위 텍스트, 함의 검증에 쓴 바로 그 자료)에서
해당 쪽과 앞뒤 쪽을 꺼내 돌려준다. 교수가 근거 위치만 보고 책을 펴는 대신 콘솔 옆 패널에서 바로 대조하게 하는 것이 목적이다.

경계:
- **교수 전용**. 학생 API·학생 화면 어디에도 이 모듈의 출력이 실리면 안 된다(학생에게는 근거 위치만 보여준다는 원칙).
- 쪽 이미지는 만들지 않는다. 텍스트 발췌 + 도서관/공개 검색 링크까지만.
- 과별 교과서(Sabiston·Speroff·Nelson 등)는 로컬 `data_private/textbooks/<book_id>/pages.jsonl`이 있을 때만 발췌한다(T-TBX-01, 2026-10-05).
  서버(배포 번들)에는 이 디렉터리가 없어 자동으로 장 정보만 돌려준다(available=False, reason="chapter_index_only").
- 도서관 프록시 접두어는 환경변수로만 설정한다(검증된 형식이 확인되기 전까지 기본값 없음).
"""

from __future__ import annotations

import bisect
import json
import os
import re
import unicodedata
import urllib.parse
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ENV_HARRISON_DIR = "PACCINE_HARRISON_DIR"
ENV_TEXTBOOKS_DIR = "PACCINE_TEXTBOOKS_DIR"                    # 과별 교과서 루트(<root>/<book_id>/pages.jsonl) 재정의
ENV_LIBRARY_PROXY_PREFIX = "PACCINE_LIBRARY_PROXY_PREFIX"      # 타 기관 EZproxy식 접두어(예: https://libproxy.example.ac.kr/login?url=). 부산대는 이 방식이 아님 → 아래 프로필
ENV_ACCESSMEDICINE_BOOKID = "PACCINE_ACCESSMEDICINE_BOOKID"    # 토픽 검색의 book 파라미터 재정의(기본 3541 = 22e)
ENV_LIBRARY_PROFILE = "PACCINE_LIBRARY_PROFILE"                 # "pnu"(기본) | "none" — 교외 접속 링크 프로필

# 2026-09-27 공개 페이지만으로 확인(로그인·본문 열람 없음):
#   - bookid 3541 = "Harrison's Principles of Internal Medicine, 22nd Edition"(페이지 제목), 3095 = 21e(sectionid 전혀 다름).
#   - 부산대 교외접속은 EZproxy(login?url=)가 아니라 경로 접두어형 lproxy이며, 도서관 로그인(returnUrl) 경유로만 세션이 생긴다.
#     lproxy URL 단독은 비로그인 시 원본으로 바운스되므로 배포 금지. 로그인 이후 hop은 도서관 SPA 코드로만 확인(미실측).
ACCESSMEDICINE_HARRISON_22E_BOOKID = "3541"
ACCESSMEDICINE_TOC_PATH = Path(__file__).resolve().parent / "reference" / "harrison22e_accessmedicine_toc.json"
PNU_LIBRARY_LOGIN_URL = "https://lib.pusan.ac.kr/login"
PNU_LIBRARY_PROXY_PREFIX = "https://lproxy.pusan.ac.kr/_Lib_Proxy_Url/"
HARRISON_DIR = ROOT / "data_private" / "harrison" / "22e"
TEXTBOOKS_DIR = ROOT / "data_private" / "textbooks"
MANIFEST_FILENAME = "manifest.json"
PAGES_FILENAME = "pages.jsonl"
CHAPTER_INDEX_FILENAME = "chapter_index.json"
QUALITY_FILENAME = "quality.json"               # scripts/audit_textbook_page_labels.py가 쓰는 본문 추출 품질 판정 — 없어도 동작
SECTION_INDEX_FILENAME = "section_index.json"   # scripts/build_textbook_sections.py가 만드는 절(section) 인덱스(T-TBX-03) — 없어도 동작

HARRISON_BOOK_ID = "harrison_22e"
HARRISON_TITLE = "Harrison's Principles of Internal Medicine, 22e"
ACCESSMEDICINE_BASE = "https://accessmedicine.mhmedical.com"
MSD_PROFESSIONAL_SEARCH = "https://www.msdmanuals.com/professional/SearchResults"

MAX_CONTEXT_PAGES = 2
MAX_QUOTES = 12
MAX_HIGHLIGHT_TERMS = 24
MIN_QUOTE_CHARS = 16
MAX_QUOTE_CHARS = 320

# 큰따옴표 인용: 안의 아포스트로피(Crohn's 등)는 허용한다(T-TBX-02). 작은따옴표 인용은 기존대로 안에 따옴표류를 허용하지 않는다.
_DQUOTE_RE = re.compile(r"\"([^\"]{%d,%d})\"|“([^“”]{%d,%d})”" % ((MIN_QUOTE_CHARS, MAX_QUOTE_CHARS) * 2))
_QUOTE_RE = re.compile(r"[\"“‘']([^\"“”‘’']{%d,%d})[\"”’']" % (MIN_QUOTE_CHARS, MAX_QUOTE_CHARS))
_NUMERIC_TERM_RE = re.compile(r"\d[\d,.]*(?:\s?[–-]\s?\d[\d,.]*)?\s?(?:%|mmHg|mEq/L|mg/dL|g/dL|U/L|IU/L|mmol/L|/μL|/µL|/mm³|mL|mg|g)")


# ── 경로·캐시 ────────────────────────────────────────────────────────────────────
def _harrison_dir(explicit: str | os.PathLike | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get(ENV_HARRISON_DIR)
    return Path(env) if env else HARRISON_DIR


def _signature(path: Path) -> tuple[str, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=2)
def _pages_snapshot(signature: tuple[str, int, int]) -> dict[str, Any]:
    """pages.jsonl → {(chapter, printed_page): rec} + {printed_page: [rec…]}. 파일 서명으로 캐시."""
    path = Path(signature[0])
    by_key: dict[tuple[int, int], dict[str, Any]] = {}
    by_page: dict[int, list[dict[str, Any]]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            chapter = _as_int(row.get("chapter"))
            page = _as_int(row.get("printed_page"))
            text = str(row.get("segment_text") or "")
            if chapter is None or page is None or not text:
                continue
            rec = {"chapter": chapter, "printed_page": page, "pdf_page": _as_int(row.get("pdf_page")), "text": text}
            by_key.setdefault((chapter, page), rec)
            by_page.setdefault(page, []).append(rec)
    return {"by_key": by_key, "by_page": by_page}


@lru_cache(maxsize=2)
def _chapter_titles(signature: tuple[str, int, int]) -> dict[int, str]:
    payload = json.loads(Path(signature[0]).read_text(encoding="utf-8"))
    chapters = payload.get("chapters") if isinstance(payload, dict) else payload
    out: dict[int, str] = {}
    for row in chapters or []:
        if not isinstance(row, dict):
            continue
        number = _as_int(row.get("chapter"))
        title = str(row.get("filename_title") or row.get("title") or "").strip()
        if number is not None and title:
            out[number] = title
    return out


def clear_caches() -> None:
    _quality_snapshot.cache_clear()
    _pages_snapshot.cache_clear()
    _textbook_snapshot.cache_clear()
    _textbook_title.cache_clear()
    _section_snapshot.cache_clear()
    _chapter_titles.cache_clear()
    _accessmedicine_toc.cache_clear()


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def load_pages(harrison_dir: str | os.PathLike | None = None) -> dict[str, Any]:
    signature = _signature(_harrison_dir(harrison_dir) / PAGES_FILENAME)
    if not signature:
        return {"by_key": {}, "by_page": {}}
    return _pages_snapshot(signature)


def chapter_title(chapter: int | None, harrison_dir: str | os.PathLike | None = None) -> str | None:
    if chapter is None:
        return None
    signature = _signature(_harrison_dir(harrison_dir) / CHAPTER_INDEX_FILENAME)
    if not signature:
        return None
    return _chapter_titles(signature).get(int(chapter))


# ── 발췌 ────────────────────────────────────────────────────────────────────────
def harrison_excerpt(
    chapter: Any,
    printed_page: Any,
    *,
    context: int = 1,
    harrison_dir: str | os.PathLike | None = None,
) -> dict[str, Any] | None:
    """인용 쪽(±context) 텍스트. 같은 장의 쪽을 우선하고, 없으면 같은 인쇄 쪽수의 다른 장 세그먼트를 쓴다(chapter_mismatch 표시)."""
    chapter_no = _as_int(chapter)
    page_no = _as_int(printed_page)
    if page_no is None:
        return None
    pages = load_pages(harrison_dir)
    by_key, by_page = pages["by_key"], pages["by_page"]
    context = max(0, min(int(context or 0), MAX_CONTEXT_PAGES))

    def _pick(page: int) -> dict[str, Any] | None:
        if chapter_no is not None and (chapter_no, page) in by_key:
            return by_key[(chapter_no, page)]
        candidates = by_page.get(page) or []
        return candidates[0] if candidates else None

    cited = _pick(page_no)
    if cited is None:
        return None
    rows = []
    for page in range(page_no - context, page_no + context + 1):
        rec = _pick(page)
        if rec is None:
            continue
        rows.append(
            {
                "printed_page": rec["printed_page"],
                "pdf_page": rec["pdf_page"],
                "chapter": rec["chapter"],
                "text": rec["text"],
                "is_cited": page == page_no,
            }
        )
    return {
        "book_id": HARRISON_BOOK_ID,
        "book_title": HARRISON_TITLE,
        "chapter": chapter_no if chapter_no is not None else cited["chapter"],
        "chapter_title": chapter_title(chapter_no if chapter_no is not None else cited["chapter"], harrison_dir),
        "requested_page": page_no,
        "chapter_mismatch": bool(chapter_no is not None and cited["chapter"] != chapter_no),
        "pages": rows,
        "available": True,
    }


# ── 과별 교과서(로컬 전용) ───────────────────────────────────────────────────────
def _textbooks_dir(explicit: str | os.PathLike | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get(ENV_TEXTBOOKS_DIR)
    return Path(env) if env else TEXTBOOKS_DIR


def _norm_label(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split()).lower()


_SOFT_HYPHEN_RE = re.compile("[\u00ad\u200b]")
_EOL_HYPHEN_RE = re.compile(r"(\w)-[ \t]*\r?\n\s*(?=[a-z])")
_QUOTE_FOLD = {ord(c): "'" for c in "‘’‚‛′`´"} | {ord(c): '"' for c in "“”„‟″"}
_DASH_FOLD = {ord(c): "-" for c in "‐‑‒–—―−﹣－"}


def _match_norm(value: Any) -> str:
    """매칭 전용 정규화(T-TBX-02) — 본문과 인용문 양쪽에 똑같이 적용하고, 표시용 텍스트는 건드리지 않는다.
    NFKC(ﬁ/ﬂ 합자 풀기) → 소프트 하이픈 제거 → 줄 끝 하이픈 분철 결합(하이픈+개행+소문자) → 굽은 따옴표·대시 통일 → 공백 축약 → 소문자."""
    text = unicodedata.normalize("NFKC", str(value if value is not None else ""))
    text = _SOFT_HYPHEN_RE.sub("", text)
    text = _EOL_HYPHEN_RE.sub(r"\1", text)
    text = text.translate(_QUOTE_FOLD).translate(_DASH_FOLD)
    return " ".join(text.lower().split())



@lru_cache(maxsize=8)
def _textbook_snapshot(signature: tuple[str, int, int]) -> dict[str, Any]:
    """과별 교과서 pages.jsonl → 쪽 목록(pdf_page순) + 장별/인쇄 라벨별 색인. 본문이 빈 쪽은 뺀다. 파일 서명으로 캐시."""
    path = Path(signature[0])
    recs: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "")
            pdf_page = _as_int(row.get("pdf_page"))
            if not text.strip() or pdf_page is None:
                continue
            label = row.get("printed_label")
            label = str(label).strip() if label is not None and str(label).strip() else None
            recs.append(
                {
                    "pdf_page": pdf_page,
                    "printed_label": label,
                    "chapter": _as_int(row.get("chapter")),
                    "chapter_title": str(row.get("chapter_title") or "").strip() or None,
                    "text": text,
                }
            )
    recs.sort(key=lambda r: r["pdf_page"])
    by_chapter: dict[int, list[int]] = {}
    by_label: dict[str, list[int]] = {}
    for index, rec in enumerate(recs):
        if rec["chapter"] is not None:
            by_chapter.setdefault(rec["chapter"], []).append(index)
        if rec["printed_label"] is not None:
            by_label.setdefault(_norm_label(rec["printed_label"]), []).append(index)
    return {"recs": recs, "by_chapter": by_chapter, "by_label": by_label}


@lru_cache(maxsize=8)
def _textbook_title(signature: tuple[str, int, int]) -> str | None:
    try:
        payload = json.loads(Path(signature[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    title = str(payload.get("title") or "").strip() if isinstance(payload, dict) else ""
    return title or None


@lru_cache(maxsize=8)
def _section_snapshot(signature: tuple[str, int, int]) -> dict[str, Any] | None:
    """section_index.json → 절 목록 + id/제목/장별 색인(제목 비교는 매칭 정규화 사용). 파일 서명으로 캐시. 깨진 파일은 None."""
    try:
        payload = json.loads(Path(signature[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    sections: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        start, chapter = _as_int(row.get("pdf_page_start")), _as_int(row.get("chapter"))
        title = str(row.get("title") or "").strip()
        if start is None or chapter is None or not title:
            continue
        path = [str(p) for p in (row.get("path") or [])] or [title]
        sections.append(
            {
                "section_id": str(row.get("section_id") or ""),
                "chapter": chapter,
                "level": _as_int(row.get("level")),
                "title": title,
                "path": path,
                "path_norm": [_match_norm(p) for p in path],
                "citable": row.get("citable") is not False,   # 필드가 없는 옛 인덱스는 인용 가능으로 본다
                "pdf_page_start": start,
                "pdf_page_end": _as_int(row.get("pdf_page_end")) or start,
            }
        )
    by_id: dict[str, int] = {}
    by_title: dict[str, list[int]] = {}
    by_chapter: dict[int, list[int]] = {}
    for index, sec in enumerate(sections):
        if sec["section_id"]:
            by_id.setdefault(sec["section_id"], index)
        by_title.setdefault(_match_norm(sec["title"]), []).append(index)
        by_chapter.setdefault(sec["chapter"], []).append(index)
    starts = {ch: [sections[i]["pdf_page_start"] for i in idxs] for ch, idxs in by_chapter.items()}
    return {"sections": sections, "by_id": by_id, "by_title": by_title, "by_chapter": by_chapter, "starts": starts}


@lru_cache(maxsize=8)
def _quality_snapshot(signature: tuple[str, int, int]) -> dict[str, Any] | None:
    try:
        payload = json.loads(Path(signature[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("usable_for_evidence"), bool):
        return None
    return {"usable_for_evidence": payload["usable_for_evidence"], "reasons": [str(r) for r in (payload.get("reasons") or [])]}


def load_textbook(book_id: str, textbooks_dir: str | os.PathLike | None = None) -> dict[str, Any] | None:
    """책 디렉터리·쪽 파일이 없으면 None(→ 호출부가 chapter_index_only). book_id는 경로 탈출 방지를 위해 단순 식별자만 허용."""
    book_id = str(book_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", book_id) or book_id.startswith("."):
        return None
    book_dir = _textbooks_dir(textbooks_dir) / book_id
    signature = _signature(book_dir / PAGES_FILENAME)
    if not signature:
        return None
    try:
        snapshot = _textbook_snapshot(signature)
    except (OSError, ValueError):
        return None
    manifest_signature = _signature(book_dir / MANIFEST_FILENAME)
    title = _textbook_title(manifest_signature) if manifest_signature else None
    section_signature = _signature(book_dir / SECTION_INDEX_FILENAME)
    sections = _section_snapshot(section_signature) if section_signature else None
    quality_signature = _signature(book_dir / QUALITY_FILENAME)
    quality = _quality_snapshot(quality_signature) if quality_signature else None
    return {**snapshot, "title": title or book_id, "sections": sections, "quality": quality}


def section_path_for_page(book: dict[str, Any], chapter: int | None, pdf_page: int) -> list[str] | None:
    """쪽이 속한 절의 경로 — 그 장에서 시작 쪽이 이 쪽 이하인 가장 마지막 절(첫 절 이전 쪽은 None)."""
    sec = book.get("sections")
    if not sec or chapter is None or chapter not in sec["by_chapter"]:
        return None
    position = bisect.bisect_right(sec["starts"][chapter], pdf_page) - 1
    if position < 0:
        return None
    return list(sec["sections"][sec["by_chapter"][chapter][position]]["path"])


_SECTION_ID_RE = re.compile(r"\d+\.\d+")


def resolve_section(book: dict[str, Any], section: Any, chapter: int | None = None) -> dict[str, Any]:
    """절 해석 → {"section": 절|None, "ambiguous": bool, "not_citable": bool}.
    - section_id("12.3")는 그대로 조회. 인용 불가(참고문헌류) 절이면 section=None, not_citable=True.
    - 경로형 "A › B › C"(구분자는 "›"만)는 저장된 경로가 이 단계들로 **끝나는** 절만 후보(정규화 비교) — 엉뚱한 상위 단계면 못 찾음.
    - 제목 하나는 마지막 단계만 비교: 요청 장 안의 후보를 우선하고 같은 장에 여럿이면 첫 절(ambiguous)."""
    sec = book.get("sections")
    text = str(section).strip() if section is not None else ""
    result: dict[str, Any] = {"section": None, "ambiguous": False, "not_citable": False}
    if not sec or not text:
        return result
    if _SECTION_ID_RE.fullmatch(text):
        index = sec["by_id"].get(text)
        if index is not None:
            hit = sec["sections"][index]
            if hit["citable"]:
                result["section"] = hit
            else:
                result["not_citable"] = True
        return result
    steps = [_match_norm(part) for part in text.split("›")]
    steps = [part for part in steps if part]
    if not steps:
        return result
    candidates = sec["by_title"].get(steps[-1]) or []
    if len(steps) > 1:
        candidates = [i for i in candidates if sec["sections"][i]["path_norm"][-len(steps):] == steps]
    if not candidates:
        return result
    citable = [i for i in candidates if sec["sections"][i]["citable"]]
    if not citable:
        result["not_citable"] = True
        return result
    in_chapter = [i for i in citable if chapter is not None and sec["sections"][i]["chapter"] == chapter]
    scope = in_chapter or citable
    result["section"], result["ambiguous"] = sec["sections"][scope[0]], len(scope) > 1
    return result


def find_section(book: dict[str, Any], section: Any, chapter: int | None = None) -> tuple[dict[str, Any] | None, bool]:
    """절 제목·경로·section_id로 절을 찾는다 → (절, 모호 여부). 규칙은 resolve_section 참고(인용 불가 절은 None)."""
    resolved = resolve_section(book, section, chapter)
    return resolved["section"], resolved["ambiguous"]


def _rec_norm(rec: dict[str, Any]) -> tuple[str, str]:
    """쪽 본문의 정규화본과 하이픈 제거본(지연 계산·스냅샷 캐시에 함께 보관). 표시용 text는 그대로 둔다."""
    norm = rec.get("_norm")
    if norm is None:
        full = _match_norm(rec["text"])
        norm = rec["_norm"] = (full, full.replace("-", ""))
    return norm


def _term_score(rec: dict[str, Any], needles: list[tuple[str, str]]) -> int:
    """정규화 일치 개수. 줄 끝 분철에서 잘린 인용(끝이 '-')도 잡도록 하이픈 제거본끼리의 일치를 2차로 인정한다."""
    full, bare = _rec_norm(rec)
    return sum(1 for needle, needle_bare in needles if needle in full or (needle_bare and needle_bare in bare))


def textbook_excerpt(
    book_id: str,
    chapter: Any,
    page: Any = None,
    *,
    terms: list[str] | None = None,
    context: int = 1,
    section: Any = None,
    textbooks_dir: str | os.PathLike | None = None,
) -> dict[str, Any] | None:
    """과별 교과서 발췌. 책이 로컬에 없으면 None.

    - 쪽이 주어지고 그 책에 printed_label이 있으면 라벨로 찾는다(page_locator="printed_page"); 못 찾으면 장 기준으로 넘어간다.
    - 쪽 라벨로 못 찾았고 section(절 제목 또는 section_id)이 주어지면 그 절의 시작 쪽을 연다(page_locator="section"); 못 찾으면 section_not_found.
    - 장만 있으면 그 장의 쪽 중 인용문 조각·하이라이트 용어가 가장 많이 맞는 쪽(chapter_term_match), 하나도 안 맞으면 장 첫 쪽(chapter_start).
    - 돌려주는 쪽은 선택 쪽 ±context(MAX_CONTEXT_PAGES 한도)뿐이다. 장 전체를 돌려주지 않는다.
    - 못 찾으면 {"available": False, "reason": ...}(책은 있으나 해당 장·쪽이 없음).
    """
    book = load_textbook(book_id, textbooks_dir)
    if book is None:
        return None
    recs: list[dict[str, Any]] = book["recs"]
    context = max(0, min(int(context or 0), MAX_CONTEXT_PAGES))
    chapter_no = _as_int(chapter)
    requested = str(page).strip() if page is not None and str(page).strip() else None
    chapter_indexes: list[int] = book["by_chapter"].get(chapter_no, []) if chapter_no is not None else []

    chosen: int | None = None
    locator = ""
    matched_terms = 0
    tie_candidates = 1
    page_ignored = bool(requested is not None and not book["by_label"])   # 이 책엔 쪽 라벨이 없음 → 요청 쪽 무시
    page_not_found = False
    if requested is not None and book["by_label"]:
        candidates = book["by_label"].get(_norm_label(requested)) or []
        in_chapter = [i for i in candidates if chapter_no is not None and recs[i]["chapter"] == chapter_no]
        picked = in_chapter or candidates
        if picked:
            chosen, locator = picked[0], "printed_page"
        else:
            page_not_found = True
    section_hit: dict[str, Any] | None = None
    section_ambiguous = False
    section_not_found = False
    section_not_citable = False
    if chosen is None and section is not None and str(section).strip():
        resolved = resolve_section(book, section, chapter_no)
        section_hit, section_ambiguous, section_not_citable = resolved["section"], resolved["ambiguous"], resolved["not_citable"]
        if section_hit is not None:
            pdf_pages = [r["pdf_page"] for r in recs]
            position = bisect.bisect_left(pdf_pages, section_hit["pdf_page_start"])    # 시작 쪽 본문이 비었으면 다음 본문 쪽
            if position < len(recs) and recs[position]["pdf_page"] <= max(section_hit["pdf_page_end"], section_hit["pdf_page_start"]) and recs[position]["chapter"] == section_hit["chapter"]:
                chosen, locator = position, "section"
            else:
                section_hit = None
        section_not_found = chosen is None
    if chosen is None and chapter_indexes:
        needles = [(n, n.replace("-", "")) for n in (_match_norm(t) for t in (terms or [])) if n]
        scored = [(_term_score(recs[i], needles), i) for i in chapter_indexes] if needles else []
        best = max(scored, key=lambda t: (t[0], -t[1]), default=(0, chapter_indexes[0]))
        if best[0] > 0:
            chosen, locator, matched_terms = best[1], "chapter_term_match", best[0]
            tie_candidates = sum(1 for score, _i in scored if score == best[0])   # 최고점이 여러 쪽이면 가장 앞 쪽을 쓰되 표시
        else:
            chosen, locator = chapter_indexes[0], "chapter_start"
    if chosen is None:
        if requested is None and chapter_no is None:
            reason = "chapter_missing"
        elif chapter_no is not None and not chapter_indexes:
            reason = "chapter_text_not_indexed"
        else:
            reason = "page_text_not_indexed"
        return {"available": False, "reason": reason, "book_title": book["title"]}

    # 이웃 쪽: 라벨 조회는 PDF 순서상 이웃, 장 기준 선택은 같은 장 안의 이웃만
    if locator == "printed_page":
        window = range(max(0, chosen - context), min(len(recs), chosen + context + 1))
    else:
        window_chapter = recs[chosen]["chapter"] if locator == "section" else chapter_no
        window = [i for i in range(max(0, chosen - context), min(len(recs), chosen + context + 1)) if recs[i]["chapter"] == window_chapter]
    has_sections = bool(book.get("sections"))
    rows = []
    for i in window:
        row = {
            "pdf_page": recs[i]["pdf_page"],
            "printed_label": recs[i]["printed_label"],
            "chapter": recs[i]["chapter"],
            "text": recs[i]["text"],
            "is_cited": i == chosen,
        }
        if has_sections:   # 절 인덱스가 있는 책만(없으면 응답 모양 불변)
            row["section_path"] = section_path_for_page(book, recs[i]["chapter"], recs[i]["pdf_page"])
        rows.append(row)
    cited = recs[chosen]
    # 쪽 라벨(또는 절)은 찾았는데 그 쪽의 장이 요청 장과 다르면 숨기지 않고 표시한다(chapter는 요청값 유지)
    chapter_mismatch = bool(locator in {"printed_page", "section"} and chapter_no is not None and cited["chapter"] != chapter_no)
    title = cited["chapter_title"]
    if chapter_mismatch:
        requested_rows = book["by_chapter"].get(chapter_no) or []
        title = recs[requested_rows[0]]["chapter_title"] if requested_rows else None
    result = {
        "book_id": str(book_id),
        "book_title": book["title"],
        "chapter": chapter_no if chapter_no is not None else cited["chapter"],
        "chapter_title": title,
        "requested_page": requested,
        "page_locator": locator,
        "matched_terms": matched_terms,
        "chapter_mismatch": chapter_mismatch,
        "resolved_chapter": cited["chapter"] if chapter_mismatch else None,
        "page_ignored": page_ignored,
        "page_not_found": page_not_found,
        "resolved_chapter_title": cited["chapter_title"] if chapter_mismatch else None,
        "section_not_found": section_not_found,
        "section_not_citable": section_not_citable,
        "section_ambiguous": bool(locator == "section" and section_ambiguous),
        "pages": rows,
        "available": True,
    }
    if locator == "chapter_term_match":
        result["term_match_ambiguous"] = tie_candidates > 1
        result["term_match_candidates"] = tie_candidates
    if book.get("quality") is not None:
        result["text_quality"] = dict(book["quality"])
    if locator == "section" and section_hit is not None:
        result["section"] = {k: section_hit[k] for k in ("section_id", "title", "path", "pdf_page_start", "pdf_page_end")}
    return result


def resolve_citation(
    book_id: str,
    chapter: Any,
    page: Any = None,
    section: Any = None,
    *,
    textbooks_dir: str | os.PathLike | None = None,
) -> dict[str, Any]:
    """인용 해석 → {"label", "section_id", "resolved"}. label: 쪽 라벨이 있는 책은 "Ch.N p.N", 절이 풀리면 "Ch.N › 전체 경로"(" › "로 이음).
    절이 주어졌는데 풀리지 않으면(책 없음·절 없음·인용 불가) 장만 쓴 "Ch.N"을 돌려주고 resolved=False — 확인 안 된 절 제목으로 깨끗한 인용을 꾸며내지 않는다.
    resolved: True(절이 풀림) / False(절이 주어졌으나 풀리지 않음) / None(절 없이 쪽·장만으로 만든 라벨)."""
    chapter_no = _as_int(chapter)
    head = f"Ch.{chapter_no}" if chapter_no is not None else ""
    page_text = str(page).strip() if page is not None and str(page).strip() else ""
    book = load_textbook(book_id, textbooks_dir)
    has_labels = bool(book["by_label"]) if book else bool(page_text)
    if page_text and has_labels:
        return {"label": f"{head} p.{page_text}".strip(), "section_id": None, "resolved": None}
    section_text = str(section).strip() if section is not None else ""
    if not section_text:
        return {"label": head, "section_id": None, "resolved": None}
    hit = resolve_section(book, section_text, chapter_no)["section"] if book else None
    if hit is None:
        return {"label": head, "section_id": None, "resolved": False}
    path_text = " › ".join(hit["path"])
    return {"label": f"{head} › {path_text}" if head else path_text, "section_id": hit["section_id"] or None, "resolved": True}


def citation_label(
    book_id: str,
    chapter: Any,
    page: Any = None,
    section: Any = None,
    *,
    textbooks_dir: str | os.PathLike | None = None,
) -> str:
    """resolve_citation의 label만(문자열). 풀리지 않은 절은 장만("Ch.N") — 풀렸는지는 resolve_citation으로 확인."""
    return resolve_citation(book_id, chapter, page, section, textbooks_dir=textbooks_dir)["label"]


# ── 인용문·하이라이트 ────────────────────────────────────────────────────────────
def extract_quotes(item: dict[str, Any]) -> list[str]:
    """v2 검증 메모(`v2_revision.evidence`)와 `evidence` 문자열에서 따옴표로 묶인 원문 인용을 뽑는다(영문 원문과 대조용)."""
    texts: list[str] = []
    v2 = item.get("v2_revision") if isinstance(item.get("v2_revision"), dict) else {}
    for value in (v2.get("evidence"), item.get("evidence")):
        if isinstance(value, str) and value.strip():
            texts.append(value)
        elif isinstance(value, list):
            texts.extend(str(v) for v in value if isinstance(v, str))
    quotes: list[str] = []
    for text in texts:
        found: list[tuple[int, str]] = []
        masked = text
        for match in _DQUOTE_RE.finditer(text):      # 큰따옴표 인용(아포스트로피 허용) — 찾은 구간은 가리고 작은따옴표 탐색
            found.append((match.start(), match.group(1) or match.group(2)))
            masked = masked[: match.start()] + " " * (match.end() - match.start()) + masked[match.end():]
        for match in _QUOTE_RE.finditer(masked):
            found.append((match.start(), match.group(1)))
        for _, raw in sorted(found, key=lambda t: t[0]):
            quote = " ".join(raw.split())
            if quote and quote not in quotes:
                quotes.append(quote)
            if len(quotes) >= MAX_QUOTES:
                return quotes
    return quotes


_ELLIPSIS_RE = re.compile(r"\s*(?:…|\.\.\.|\[\.\.\.\]|\[…\])\s*")
MIN_FRAGMENT_CHARS = 12


def quote_fragments(quotes: list[str]) -> list[str]:
    """검증 메모의 인용문은 '…'로 줄여 적힌 경우가 많다 → 생략 부호 기준으로 잘라 조각별로 대조한다."""
    fragments: list[str] = []
    for quote in quotes:
        for part in _ELLIPSIS_RE.split(quote):
            part = part.strip(" ,;:")
            if len(part) >= MIN_FRAGMENT_CHARS and part not in fragments:
                fragments.append(part)
    return fragments


def highlight_terms(item: dict[str, Any], quotes: list[str] | None = None) -> list[str]:
    """원문에서 형광펜 칠할 문자열: 인용문 조각 + 해설의 수치 표현(단위 포함). 긴 것부터."""
    terms: list[str] = quote_fragments(list(quotes if quotes is not None else extract_quotes(item)))
    explanation = str(item.get("explanation") or "")
    for match in _NUMERIC_TERM_RE.finditer(explanation):
        token = match.group(0).strip()
        if len(token) >= 3 and token not in terms:
            terms.append(token)
    terms.sort(key=len, reverse=True)
    return terms[:MAX_HIGHLIGHT_TERMS]


# ── 열람 링크 ───────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _accessmedicine_toc() -> dict[int, dict[str, str]]:
    """공개 목차에서 실제로 읽은 chapter→sectionid(추측값 없음). 파일이 없거나 book_id가 다르면 빈 dict."""
    try:
        data = json.loads(ACCESSMEDICINE_TOC_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or str(data.get("book_id")) != ACCESSMEDICINE_HARRISON_22E_BOOKID:
        return {}
    toc: dict[int, dict[str, str]] = {}
    for key, row in (data.get("chapters") or {}).items():
        chapter = _as_int(key)
        section_id = str((row or {}).get("sectionid") or "").strip()
        if chapter and section_id.isdigit():
            toc[chapter] = {"sectionid": section_id, "title": str((row or {}).get("title") or "")}
    return toc


def accessmedicine_chapter_url(chapter: Any) -> str | None:
    """장 본문 딥링크 — 공개 목차에서 확인된 sectionid가 있는 장만(없으면 None → 토픽 검색으로 폴백)."""
    row = _accessmedicine_toc().get(_as_int(chapter) or -1)
    if not row:
        return None
    return f"{ACCESSMEDICINE_BASE}/content.aspx?bookid={ACCESSMEDICINE_HARRISON_22E_BOOKID}&sectionid={row['sectionid']}"


def accessmedicine_search_url(query: str) -> str:
    """AccessMedicine 토픽 검색. book 파라미터는 확인된 22e(3541)이 기본, 환경변수로 재정의."""
    params = {"q": query, "searchType": "1"}
    book_id = os.environ.get(ENV_ACCESSMEDICINE_BOOKID, "").strip() or ACCESSMEDICINE_HARRISON_22E_BOOKID
    params["book"] = book_id
    return f"{ACCESSMEDICINE_BASE}/SearchResults.aspx?{urllib.parse.urlencode(params)}"


def proxied(url: str) -> str | None:
    """타 기관용 일반 접두어(EZproxy `login?url=` 은 인코딩, 경로형은 그대로 이어붙임)."""
    prefix = os.environ.get(ENV_LIBRARY_PROXY_PREFIX, "").strip()
    if not prefix:
        return None
    if prefix.endswith("="):
        return prefix + urllib.parse.quote(url, safe="")
    return prefix.rstrip("/") + "/" + url.lstrip("/")


def library_profile() -> str:
    return (os.environ.get(ENV_LIBRARY_PROFILE) or "pnu").strip().lower()


def pnu_offcampus_url(url: str) -> str:
    """부산대 교외접속 체인: 도서관 로그인(returnUrl=lproxy 접두어+원본 URL) → 로그인 후 SPA가 proxy-redirect(&at=토큰) → lproxy 세션.
    관찰된 도서관 자체 DB 클릭 흐름과 같은 형식. 로그인 이후 hop은 미실측이므로 응답에 verified="partial"로 표시한다."""
    return f"{PNU_LIBRARY_LOGIN_URL}?returnUrl={urllib.parse.quote(PNU_LIBRARY_PROXY_PREFIX + url, safe='')}"


PNU_OFFCAMPUS_NOTE = (
    "도서관 로그인 페이지 도달·프록시 형식은 확인됨. 로그인 후 이 장으로 자동 이동하는지는 미실측 — "
    "안 되면 도서관 홈 → 학술DB → AccessMedicine 경로로 진입한 뒤 장 검색."
)


def library_links(chapter_title_text: str | None, fallback_query: str | None = None, chapter: Any = None) -> list[dict[str, str]]:
    query = (chapter_title_text or fallback_query or "").strip()
    chapter_url = accessmedicine_chapter_url(chapter)
    if not query and not chapter_url:
        return []
    links: list[dict[str, str]] = []
    if chapter_url:
        links.append(
            {
                "kind": "accessmedicine_chapter",
                "label": f"AccessMedicine Ch.{_as_int(chapter)} 본문 (교내·VPN)",
                "url": chapter_url,
                "verified": "public_toc_2026-09-27",
            }
        )
    direct = accessmedicine_search_url(query) if query else None
    if direct:
        links.append({"kind": "accessmedicine_topic_search", "label": "AccessMedicine에서 장 검색 (교내·VPN)", "url": direct})
    target = chapter_url or direct or ""
    via_proxy = proxied(target)
    if via_proxy:
        links.insert(0, {"kind": "library_proxy", "label": "도서관 프록시로 열기", "url": via_proxy})
    elif library_profile() == "pnu":
        links.append(
            {
                "kind": "pnu_offcampus_login",
                "label": "교외: 부산대 도서관 로그인 경유",
                "url": pnu_offcampus_url(target),
                "verified": "partial",
                "note": PNU_OFFCAMPUS_NOTE,
            }
        )
    if query:
        links.append(
            {
                "kind": "msd_professional_search",
                "label": "MSD 매뉴얼(공개) 검색",
                "url": f"{MSD_PROFESSIONAL_SEARCH}?{urllib.parse.urlencode({'query': query})}",
            }
        )
    return links


# ── 문항 단위 조립 ──────────────────────────────────────────────────────────────
def source_texts_for_item(
    item: dict[str, Any],
    *,
    context: int = 1,
    harrison_dir: str | os.PathLike | None = None,
    textbooks_dir: str | os.PathLike | None = None,
) -> dict[str, Any]:
    """GET /api/faculty/adjudication/items/{qid}/source-text 응답. 교수 전용."""
    quotes = extract_quotes(item)
    terms = highlight_terms(item, quotes)
    sources: list[dict[str, Any]] = []
    first_title: str | None = None
    first_chapter: int | None = None
    for src in item.get("harrison_sources") or []:
        if not isinstance(src, dict):
            continue
        excerpt = harrison_excerpt(src.get("chapter"), src.get("printed_page"), context=context, harrison_dir=harrison_dir)
        entry: dict[str, Any] = {
            "book_id": HARRISON_BOOK_ID,
            "chapter": _as_int(src.get("chapter")),
            "printed_page": _as_int(src.get("printed_page")),
            "source_id": src.get("source_id"),
            "entailment_status": src.get("entailment_status"),
            "accessmedicine_url": accessmedicine_chapter_url(src.get("chapter")),
        }
        first_chapter = first_chapter or entry["chapter"]
        if excerpt:
            entry.update(excerpt)
            first_title = first_title or excerpt.get("chapter_title")
        else:
            entry.update(
                {
                    "available": False,
                    "reason": "page_text_not_indexed" if _as_int(src.get("printed_page")) is not None else "printed_page_missing",
                    "chapter_title": chapter_title(_as_int(src.get("chapter")), harrison_dir),
                }
            )
            first_title = first_title or entry.get("chapter_title")
        sources.append(entry)
    for src in item.get("textbook_sources") or []:
        if not isinstance(src, dict):
            continue
        base = {
            "book_id": str(src.get("book_id") or ""),
            "chapter": src.get("chapter"),
            "printed_page": src.get("page"),
        }
        if src.get("section") or src.get("section_id"):
            base["section"] = src.get("section") or src.get("section_id")
        excerpt = textbook_excerpt(base["book_id"], src.get("chapter"), src.get("page"), terms=terms, context=context, section=src.get("section") or src.get("section_id"), textbooks_dir=textbooks_dir)
        if excerpt and excerpt.get("available"):
            sources.append({**base, "source_id": src.get("source_id"), "entailment_status": src.get("entailment_status"), **excerpt})
        elif excerpt:   # 책은 로컬에 있으나 해당 장·쪽 텍스트가 없음 → 구체 사유
            sources.append({**base, "source_id": src.get("source_id"), "entailment_status": src.get("entailment_status"), "available": False, "reason": excerpt["reason"], "book_title": excerpt["book_title"]})
        else:
            sources.append({**base, "available": False, "reason": "chapter_index_only"})
    return {
        "qid": item.get("qid"),
        "policy": "faculty_only_verification_excerpt",
        "quotes": quotes,
        "highlight_terms": terms,
        "sources": sources,
        "library_links": library_links(first_title, fallback_query=str(item.get("concept") or item.get("topic") or ""), chapter=first_chapter),
    }


__all__ = [
    "ACCESSMEDICINE_HARRISON_22E_BOOKID",
    "ACCESSMEDICINE_TOC_PATH",
    "ENV_ACCESSMEDICINE_BOOKID",
    "ENV_HARRISON_DIR",
    "ENV_LIBRARY_PROFILE",
    "ENV_LIBRARY_PROXY_PREFIX",
    "ENV_TEXTBOOKS_DIR",
    "HARRISON_BOOK_ID",
    "PNU_LIBRARY_LOGIN_URL",
    "PNU_LIBRARY_PROXY_PREFIX",
    "accessmedicine_chapter_url",
    "accessmedicine_search_url",
    "library_profile",
    "pnu_offcampus_url",
    "chapter_title",
    "citation_label",
    "clear_caches",
    "extract_quotes",
    "find_section",
    "harrison_excerpt",
    "highlight_terms",
    "library_links",
    "load_pages",
    "load_textbook",
    "proxied",
    "resolve_citation",
    "resolve_section",
    "quote_fragments",
    "section_path_for_page",
    "source_texts_for_item",
    "textbook_excerpt",
]
