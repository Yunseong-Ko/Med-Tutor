"""교수 문항 확정(adjudication)·편집 서비스 — 계약 §B (docs/api/Faculty_Student_Ops_API_Contract_20260906.md).

원천 데이터
  - 문항: data_private/professor_items/generated/set_{1..4}.json
          qid = AIGEN_{set}_{no:03d}, global_no = (set-1)*80 + no
  - 검토 원자료: review/reviews_1cha_normalized.json (문항당 3인: scores[3]·verdict·note)
  - 코딩된 의견: review/comments_1cha_coded.csv (global_no·who·note·all_themes)
  - 편집 이력: review/faculty_edits.jsonl (append-only: qid, editor, at, field, before, after)
  - 근거 책 목록: data_private/curriculum/evidence_routing.json → books

조치 등급은 scripts/aggregate_review_feedback.aggregate와 동일한 "최악값 기준 4등급"이다
(review/item_actions.json 캐시는 trust_badges.py가 소유·빌드한다 — 이 모듈은 쓰지 않는다).
세트 파일 쓰기는 tmp→rename 원자적, 세트 로드는 (mtime_ns, size) 시그니처 캐시.
이 모듈이 쓰는 파일은 set_{n}.json과 faculty_edits.jsonl 둘뿐이다.
api_server.py 배선은 통합 단계에서 한다(이 모듈은 라우터를 만들지 않는다).
"""
from __future__ import annotations

import copy
import csv
import json
import os
import re
import statistics as st
import tempfile
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.item_quality_check import validate_nbme_hard_rules

ROOT = Path(__file__).resolve().parents[2]

# 저장 경로: 모듈 상수(환경변수로 오버라이드) — 테스트는 monkeypatch 또는 AdjudicationPaths 인자로 바꾼다.
GENERATED_DIR = Path(
    os.environ.get("PACCINE_ADJ_GENERATED_DIR") or ROOT / "data_private" / "professor_items" / "generated"
)
REVIEW_DIR = Path(os.environ.get("PACCINE_ADJ_REVIEW_DIR") or ROOT / "data_private" / "professor_items" / "review")
EVIDENCE_ROUTING_PATH = Path(
    os.environ.get("PACCINE_ADJ_EVIDENCE_ROUTING") or ROOT / "data_private" / "curriculum" / "evidence_routing.json"
)

REVIEWS_FILENAME = "reviews_1cha_normalized.json"
COMMENTS_FILENAME = "comments_1cha_coded.csv"
EDITS_FILENAME = "faculty_edits.jsonl"
# 7지표 실측(세트 전체)·기준선 — 파이프라인 리포트에서 옮겨 적은 정적 파일. 없으면 summary.metrics=[].
QUALITY_METRICS_FILENAME = "quality_metrics.json"
ENTAILMENT_LEVELS = ("fully", "partially", "not", "unknown")

SET_COUNT = 4
ITEMS_PER_SET = 80
QID_RE = re.compile(r"^AIGEN_(\d+)_(\d{3})$")
HARRISON_BOOK_ID = "harrison_22e"
STEM_PREVIEW_CHARS = 120

# 검토 판정 서열(aggregate_review_feedback와 동일) → 조치 등급(계약 라벨)
VERDICT_ORDER = ["수정없이 사용", "소폭 수정하여 사용", "대폭 수정 필요", "사용 불가"]
VERDICT_RANK = {v: i for i, v in enumerate(VERDICT_ORDER)}
ACTION_KEEP, ACTION_MINOR, ACTION_REVISE, ACTION_DISCARD = "그대로", "경미", "수정필요", "폐기"
ACTION_KEYS = {ACTION_KEEP: "keep", ACTION_MINOR: "minor", ACTION_REVISE: "revise", ACTION_DISCARD: "discard"}

QUEUE_FILTERS = ("all", "needs_review", "revise", "discard", "answer_changed")
PRIORITY_LABELS = {0: "정답변경", 1: "폐기", 2: "수정필요", 3: "검토자불일치", 4: "기타"}
DECISIONS = ("approve", "revise", "discard")

CHOICE_KEYS = ("1", "2", "3", "4", "5")
ALLOWED_EDIT_FIELDS = (
    "stem",
    "choices",
    "answer",
    "explanation",
    "choice_explanations",
    "lab_box",
    "textbook_sources",
    "harrison_sources",
)
CHOICE_EXPLANATION_KEYS = ("why_correct", "why_attractive")
# validate_nbme_hard_rules가 돌려주는 값과 같다. 문항에 저장된 목록이 없을 때만 쓴다.
MANUAL_REVIEW_RULES_DEFAULT = ("14_homogeneous_choices", "16_lead_in_choice_consistent", "18_common_high_stakes_problem")


class AdjudicationError(ValueError):
    """입력 검증 실패(필터·결정값·편집 필드 등). 통합 시 400으로 매핑."""


class ItemNotFoundError(AdjudicationError, LookupError):
    """qid에 해당하는 문항이 없다. 통합 시 404로 매핑."""


class InvalidChangeError(AdjudicationError):
    """update_item 변경 페이로드가 허용 규격을 벗어났다."""


@dataclass(frozen=True)
class AdjudicationPaths:
    generated_dir: Path
    review_dir: Path
    evidence_routing_path: Path

    @classmethod
    def resolve(
        cls,
        generated_dir: Path | str | None = None,
        review_dir: Path | str | None = None,
        evidence_routing_path: Path | str | None = None,
    ) -> "AdjudicationPaths":
        # 인자가 없으면 호출 시점의 모듈 상수를 읽는다(monkeypatch 오버라이드가 먹도록).
        # 생성 세트 디렉터리는 학생 배지(trust_badges, PACCINE_PROFESSOR_GENERATED_DIR)와 같은 곳을 봐야 한다 —
        # 두 env 가 갈리면 콘솔 저장과 학생 배지가 다른 파일을 읽는다(감사 2026-09-05).
        return cls(
            generated_dir=Path(
                generated_dir
                or os.environ.get("PACCINE_ADJ_GENERATED_DIR")
                or os.environ.get("PACCINE_PROFESSOR_GENERATED_DIR")
                or GENERATED_DIR
            ),
            review_dir=Path(review_dir or REVIEW_DIR),
            evidence_routing_path=Path(evidence_routing_path or EVIDENCE_ROUTING_PATH),
        )

    @property
    def reviews_path(self) -> Path:
        return self.review_dir / REVIEWS_FILENAME

    @property
    def comments_path(self) -> Path:
        return self.review_dir / COMMENTS_FILENAME

    @property
    def edits_path(self) -> Path:
        return self.review_dir / EDITS_FILENAME

    @property
    def quality_metrics_path(self) -> Path:
        return self.review_dir / QUALITY_METRICS_FILENAME

    def set_path(self, set_no: int) -> Path:
        return self.generated_dir / f"set_{set_no}.json"


# ---------------------------------------------------------------------------
# 파일 캐시 · 원자적 쓰기
# ---------------------------------------------------------------------------
_LOCK = threading.RLock()
_FILE_CACHE: dict[tuple[Path, str], tuple[tuple[int, int], Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _cached_load(path: Path, kind: str, parser: Callable[[Path], Any], missing: Any = None) -> Any:
    """파일 시그니처(mtime_ns, size)가 같으면 파싱 결과를 재사용한다."""
    path = Path(path).resolve()
    signature = _signature(path)
    if signature is None:
        _FILE_CACHE.pop((path, kind), None)
        if missing is not None:
            return missing
        raise FileNotFoundError(path)
    cached = _FILE_CACHE.get((path, kind))
    if cached and cached[0] == signature:
        return cached[1]
    with _LOCK:
        cached = _FILE_CACHE.get((path, kind))
        if cached and cached[0] == signature:
            return cached[1]
        parsed = parser(path)
        _FILE_CACHE[(path, kind)] = (signature, parsed)
    return parsed


def _parse_set(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise AdjudicationError(f"세트 파일이 배열이 아닙니다: {path}")
    return data


def _load_set(path: Path) -> list[dict[str, Any]]:
    return _cached_load(path, "set", _parse_set)


def _write_set(path: Path, items: list[dict[str, Any]]) -> None:
    """tmp→rename 원자적 저장. 포맷은 apply_v2_revisions와 동일(indent=1, ensure_ascii=False)."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(json.dumps(items, ensure_ascii=False, indent=1))
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    signature = _signature(path)
    if signature is not None:
        _FILE_CACHE[(path, "set")] = (signature, items)


def _parse_reviews(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _parse_comments(path: Path) -> list[dict[str, Any]]:
    # 원본 CSV는 BOM으로 시작한다 → utf-8-sig
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _parse_edits(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # 손상된 줄은 건너뛴다(append-only 로그)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _parse_routing(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _load_edits(paths: AdjudicationPaths) -> list[dict[str, Any]]:
    return _cached_load(paths.edits_path, "edits", _parse_edits, missing=[])


def _append_edits(paths: AdjudicationPaths, rows: list[dict[str, Any]]) -> None:
    paths.edits_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.edits_path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _load_routing(paths: AdjudicationPaths) -> dict[str, Any]:
    return _cached_load(paths.evidence_routing_path, "routing", _parse_routing, missing={})


def _load_books(paths: AdjudicationPaths) -> dict[str, dict[str, Any]]:
    books = _load_routing(paths).get("books")
    return {str(k): v for k, v in books.items() if isinstance(v, dict)} if isinstance(books, dict) else {}


def clear_caches() -> None:
    """테스트·긴급 재로드용. 다음 호출부터 모든 파일을 다시 읽는다."""
    with _LOCK:
        _FILE_CACHE.clear()


# ---------------------------------------------------------------------------
# qid · 검토 집계
# ---------------------------------------------------------------------------
def parse_qid(qid: str) -> tuple[int, int]:
    """'AIGEN_{set}_{no:03d}' → (set, no). 형식이 아니면 ItemNotFoundError."""
    match = QID_RE.match(str(qid or "").strip())
    if not match:
        raise ItemNotFoundError(f"qid 형식이 아닙니다: {qid!r}")
    set_no, no = int(match.group(1)), int(match.group(2))
    if set_no < 1 or no < 1:
        raise ItemNotFoundError(f"qid 범위 밖: {qid!r}")
    return set_no, no


def make_qid(set_no: int, no: int) -> str:
    return f"AIGEN_{int(set_no)}_{int(no):03d}"


def global_no_of(set_no: int, no: int) -> int:
    return (int(set_no) - 1) * ITEMS_PER_SET + int(no)


def _int_scores(values: Any) -> list[int]:
    scores: list[int] = []
    for value in (values or [])[:3]:
        try:
            scores.append(int(value))
        except (TypeError, ValueError):
            pass
    return scores


def aggregate_reviews(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """검토 원자료(no·who·scores·verdict·note 행) → {global_no: review}.

    조치 규칙은 aggregate_review_feedback.aggregate와 동일:
      한 명이라도 '사용 불가' → 폐기 / '대폭 수정 필요' 또는 최저점 ≤2 → 수정필요
      / '소폭 수정하여 사용' 또는 점수범위 ≥2 → 경미 / 나머지 → 그대로.
    """
    by_item: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        try:
            no = int(row.get("no") if row.get("no") is not None else row.get("global_no"))
        except (TypeError, ValueError):
            continue
        by_item[no].append(row)

    out: dict[int, dict[str, Any]] = {}
    for no, reviews in by_item.items():
        cols: list[list[int]] = [[], [], []]
        ratings = []
        for review in reviews:
            scores = _int_scores(review.get("scores"))
            ratings.append(scores)
            for i, value in enumerate(scores):
                cols[i].append(value)
        allsc = [v for c in cols for v in c]
        worst = min(allsc) if allsc else None
        rng = (max(allsc) - min(allsc)) if allsc else 0
        verdicts = [str(r.get("verdict") or "").strip() for r in reviews]
        present = [v for v in verdicts if v]
        worst_v = max(present, key=lambda v: VERDICT_RANK.get(v, -1)) if present else ""

        if worst_v == "사용 불가":
            action = ACTION_DISCARD
        elif worst_v == "대폭 수정 필요" or (worst is not None and worst <= 2):
            action = ACTION_REVISE
        elif worst_v == "소폭 수정하여 사용" or rng >= 2:
            action = ACTION_MINOR
        else:
            action = ACTION_KEEP

        out[no] = {
            "reviewer_count": len(reviews),
            "reviewers": [str(r.get("who") or "") for r in reviews],
            "ratings": ratings,
            "verdicts": verdicts,
            "verdict_worst": worst_v,
            "verdict_distribution": {v: present.count(v) for v in VERDICT_ORDER if v in present},
            "score_mean": round(st.mean(allsc), 2) if allsc else None,
            "score_worst": worst,
            "score_range": rng,
            "disagreement": rng >= 2,
            "action": action,
            "action_key": ACTION_KEYS[action],
            "comments": [
                {"who": str(r.get("who") or ""), "note": str(r.get("note") or "").strip(), "themes": []}
                for r in reviews
                if str(r.get("note") or "").strip()
            ],
        }
    return out


def _merge_coded_comments(review_index: dict[int, dict[str, Any]], coded_rows: list[dict[str, Any]]) -> None:
    """코딩 CSV(주제 태그 포함)를 우선하고, CSV에 없는 검토자 note는 원자료 것을 남긴다."""
    coded: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in coded_rows:
        try:
            no = int(str(row.get("global_no") or "").strip())
        except ValueError:
            continue
        who = str(row.get("who") or "").strip()
        themes = [t.strip() for t in re.split(r"[;,/| ]+", str(row.get("all_themes") or "")) if t.strip()]
        coded[no][who] = {
            "who": who,
            "note": str(row.get("note") or "").strip(),
            "themes": themes,
            "primary_theme": str(row.get("primary_theme") or "").strip() or None,
        }
    for no, review in review_index.items():
        merged = dict(coded.get(no, {}))
        for comment in review["comments"]:
            merged.setdefault(comment["who"], comment)
        review["comments"] = [merged[who] for who in sorted(merged)]


def build_review_index(paths: AdjudicationPaths | None = None) -> dict[int, dict[str, Any]]:
    """{global_no: review}. 검토 파일이 없으면 빈 dict."""
    paths = paths or AdjudicationPaths.resolve()
    rows = _cached_load(paths.reviews_path, "reviews", _parse_reviews, missing=[])
    index = aggregate_reviews(rows)
    coded = _cached_load(paths.comments_path, "comments", _parse_comments, missing=[])
    _merge_coded_comments(index, coded)
    return index


# ---------------------------------------------------------------------------
# 문항 조회 보조
# ---------------------------------------------------------------------------
def _available_sets(paths: AdjudicationPaths) -> list[int]:
    return [k for k in range(1, SET_COUNT + 1) if paths.set_path(k).exists()]


def _locate(qid: str, paths: AdjudicationPaths) -> tuple[int, int, Path, int, list[dict[str, Any]]]:
    """qid → (set, no, 세트 경로, 인덱스, 세트 항목 리스트). 없으면 ItemNotFoundError."""
    set_no, no = parse_qid(qid)
    path = paths.set_path(set_no)
    if not path.exists():
        raise ItemNotFoundError(f"세트 파일 없음: {qid}")
    items = _load_set(path)
    for idx, item in enumerate(items):
        try:
            if int(item.get("no")) == no:
                return set_no, no, path, idx, items
        except (TypeError, ValueError):
            continue
    raise ItemNotFoundError(f"문항 없음: {qid}")


def _hard_rule_failures(item: dict[str, Any]) -> list[str]:
    """저장된 하드룰 결과에서 manual_review_rules를 뺀 실패 목록."""
    quality = item.get("item_quality") if isinstance(item.get("item_quality"), dict) else {}
    manual = set(quality.get("manual_review_rules") or MANUAL_REVIEW_RULES_DEFAULT)
    return [rule for rule in (quality.get("hard_rule_failures") or []) if rule not in manual]


def _answer_changed(item: dict[str, Any], edits: list[dict[str, Any]]) -> bool:
    revision = item.get("v2_revision") if isinstance(item.get("v2_revision"), dict) else {}
    if "정답" in (revision.get("fields") or []):
        return True
    return any(edit.get("field") == "answer" for edit in edits)


def _source_locators(item: dict[str, Any], books: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """harrison_sources + textbook_sources → 사람이 읽는 locator 목록."""
    out: list[dict[str, Any]] = []
    for src in item.get("harrison_sources") or []:
        if not isinstance(src, dict):
            continue
        chapter, page = src.get("chapter"), src.get("printed_page")
        label = "Harrison 22e"
        if chapter:
            label += f" Ch.{chapter}"
        if page:
            label += f" p.{page}"
        out.append(
            {
                "book_id": HARRISON_BOOK_ID,
                "locator": label,
                "chapter": chapter,
                "page": page,
                "entailment_status": src.get("entailment_status"),
            }
        )
    for src in item.get("textbook_sources") or []:
        if not isinstance(src, dict):
            continue
        book_id = str(src.get("book_id") or "")
        title = (books.get(book_id) or {}).get("title") or book_id
        label = title + (f" Ch.{src['chapter']}" if src.get("chapter") else "")
        if src.get("page"):
            label += f" p.{src['page']}"
        out.append(
            {
                "book_id": book_id,
                "locator": label,
                "chapter": src.get("chapter"),
                "page": src.get("page"),
                "entailment_status": src.get("entailment_status"),
            }
        )
    return out


def _badge(item: dict[str, Any], books: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"entailment_verdict": item.get("entailment_verdict"), "sources": _source_locators(item, books)}


def _stem_preview(stem: Any) -> str:
    text = re.sub(r"\s+", " ", str(stem or "")).strip()
    return text if len(text) <= STEM_PREVIEW_CHARS else text[:STEM_PREVIEW_CHARS].rstrip() + "…"


def _priority(entry: dict[str, Any]) -> int:
    # 계약: 정답변경 → 폐기 → 수정필요 → 검토자 불일치(점수범위≥2) → 나머지
    if entry.get("answer_changed"):
        return 0
    review = entry.get("review") or {}
    if review.get("action") == ACTION_DISCARD:
        return 1
    if review.get("action") == ACTION_REVISE:
        return 2
    if review.get("disagreement"):
        return 3
    return 4


def _queue_entry(
    set_no: int,
    item: dict[str, Any],
    review_index: dict[int, dict[str, Any]],
    edits_by_qid: dict[str, list[dict[str, Any]]],
    books: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    no = int(item.get("no"))
    qid = make_qid(set_no, no)
    global_no = global_no_of(set_no, no)
    edits = edits_by_qid.get(qid, [])
    entry: dict[str, Any] = {
        "qid": qid,
        "global_no": global_no,
        "set": set_no,
        "no": no,
        "mgmt_no": item.get("mgmt_no"),
        "subject": item.get("subject"),
        "axis": item.get("axis"),
        "concept": item.get("concept") or item.get("disease_concept_id"),
        "image": str(item.get("image") or ""),
        "modality": str(item.get("modality") or ""),
        "cognitive_level": str(item.get("cognitive_level") or ""),
        "has_lab_box": bool(str(item.get("lab_box") or "").strip()),
        "difficulty_tier": item.get("difficulty_tier"),
        "stem_preview": _stem_preview(item.get("stem")),
        "badge": _badge(item, books),
        "review": review_index.get(global_no),
        "answer_changed": _answer_changed(item, edits),
        "hard_rule_failures": _hard_rule_failures(item),
        "edit_count": len([e for e in edits if e.get("field") != "faculty_decision"]),
    }
    revision = item.get("v2_revision")
    if isinstance(revision, dict):
        entry["v2_revision"] = {
            "date": revision.get("date"),
            "fields": list(revision.get("fields") or []),
            "log": list(revision.get("log") or []),
        }
    if item.get("professor_review_required") is True:
        entry["professor_review_required"] = True
    if item.get("professor_note"):
        entry["professor_note"] = item.get("professor_note")
    if isinstance(item.get("faculty_decision"), dict):
        entry["faculty_decision"] = copy.deepcopy(item["faculty_decision"])
    if item.get("faculty_edited") is True:
        entry["faculty_edited"] = True
        entry["faculty_edited_at"] = item.get("faculty_edited_at")
    if item.get("medical_approval") is True:
        entry["medical_approval"] = True
    entry["priority"] = _priority(entry)
    entry["priority_label"] = PRIORITY_LABELS[entry["priority"]]
    return entry


def _all_entries(paths: AdjudicationPaths) -> list[dict[str, Any]]:
    review_index = build_review_index(paths)
    books = _load_books(paths)
    edits_by_qid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edit in _load_edits(paths):
        edits_by_qid[str(edit.get("qid") or "")].append(edit)
    entries: list[dict[str, Any]] = []
    for set_no in _available_sets(paths):
        for item in _load_set(paths.set_path(set_no)):
            if not isinstance(item, dict) or item.get("no") is None:
                continue
            entries.append(_queue_entry(set_no, item, review_index, edits_by_qid, books))
    return entries


def _matches_filter(entry: dict[str, Any], flt: str) -> bool:
    review = entry.get("review") or {}
    if flt == "all":
        return True
    if flt == "needs_review":
        return entry.get("professor_review_required") is True
    if flt == "revise":
        return review.get("action") == ACTION_REVISE
    if flt == "discard":
        return review.get("action") == ACTION_DISCARD
    if flt == "answer_changed":
        return bool(entry.get("answer_changed"))
    raise AdjudicationError(f"알 수 없는 filter: {flt!r} (허용: {', '.join(QUEUE_FILTERS)})")


def _counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {flt: sum(1 for e in entries if _matches_filter(e, flt)) for flt in QUEUE_FILTERS}
    actions = Counter((e.get("review") or {}).get("action") for e in entries)
    decided = sum(1 for e in entries if e.get("faculty_decision"))
    counts.update(
        {
            "keep": actions.get(ACTION_KEEP, 0),
            "minor": actions.get(ACTION_MINOR, 0),
            "unreviewed": sum(1 for e in entries if not e.get("review")),
            "disagreement": sum(1 for e in entries if (e.get("review") or {}).get("disagreement")),
            "decided": decided,
            "pending": len(entries) - decided,
            "faculty_edited": sum(1 for e in entries if e.get("faculty_edited")),
            "hard_rule_failures": sum(1 for e in entries if e.get("hard_rule_failures")),
        }
    )
    return counts


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def build_queue(filter: str = "all", *, paths: AdjudicationPaths | None = None) -> dict[str, Any]:  # noqa: A002
    """GET /api/faculty/adjudication/queue?filter= → {items, counts, filter}.

    items는 우선순위(정답변경→폐기→수정필요→검토자불일치→나머지) 후 global_no 순.
    counts는 필터와 무관하게 전체 기준(탭 배지용).
    """
    flt = str(filter or "all").strip().lower()
    if flt not in QUEUE_FILTERS:
        raise AdjudicationError(f"알 수 없는 filter: {filter!r} (허용: {', '.join(QUEUE_FILTERS)})")
    paths = paths or AdjudicationPaths.resolve()
    entries = _all_entries(paths)
    selected = [e for e in entries if _matches_filter(e, flt)]
    selected.sort(key=lambda e: (e["priority"], e["global_no"]))
    return {"filter": flt, "items": selected, "counts": _counts(entries)}


def get_item(qid: str, *, paths: AdjudicationPaths | None = None) -> dict[str, Any]:
    """GET /api/faculty/adjudication/items/{qid} → 문항 전체 + review + edit_history + available_books."""
    paths = paths or AdjudicationPaths.resolve()
    set_no, no, _path, idx, items = _locate(qid, paths)
    item = items[idx]
    books = _load_books(paths)
    routes = _load_routing(paths).get("routes") or {}
    edits = [e for e in _load_edits(paths) if e.get("qid") == qid]
    review_index = build_review_index(paths)

    payload = copy.deepcopy(item)
    payload.setdefault("textbook_sources", [])
    payload.update(
        {
            "qid": qid,
            "global_no": global_no_of(set_no, no),
            "set": set_no,
            "no": no,
            "badge": _badge(item, books),
            "review": review_index.get(global_no_of(set_no, no)),
            "edit_history": edits,
            "available_books": [
                {"book_id": book_id, "title": str(meta.get("title") or book_id)} for book_id, meta in books.items()
            ],
            "recommended_book_ids": list(routes.get(str(item.get("subject") or ""), []) or []),
            "answer_changed": _answer_changed(item, edits),
            "hard_rule_failures": _hard_rule_failures(item),
        }
    )
    return payload


def _require_text(field: str, value: Any, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise InvalidChangeError(f"{field}: 문자열이어야 합니다")
    text = value.strip()
    if not text and not allow_empty:
        raise InvalidChangeError(f"{field}: 비울 수 없습니다")
    return text


def _normalize_choices(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise InvalidChangeError("choices: {'1'~'5': 문자열} dict여야 합니다")
    normalized = {str(k).strip(): v for k, v in value.items()}
    if set(normalized) != set(CHOICE_KEYS):
        raise InvalidChangeError("choices: 키는 정확히 '1'~'5'여야 합니다")
    return {key: _require_text(f"choices[{key}]", normalized[key]) for key in CHOICE_KEYS}


def _normalize_answer(value: Any) -> str:
    answer = str(value if value is not None else "").strip()
    if answer not in CHOICE_KEYS:
        raise InvalidChangeError("answer: '1'~'5' 중 하나여야 합니다")
    return answer


def _normalize_choice_explanations(value: Any, current: dict[str, Any]) -> dict[str, Any]:
    """기존 선지해설에 why_correct/why_attractive만 병합한다(apply_v2_revisions와 같은 규칙)."""
    if not isinstance(value, dict):
        raise InvalidChangeError("choice_explanations: {'1'~'5': {why_correct?, why_attractive?}} dict여야 합니다")
    existing = current.get("choice_explanations")
    merged: dict[str, Any] = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    for raw_key, row in value.items():
        key = str(raw_key).strip()
        if key not in CHOICE_KEYS:
            raise InvalidChangeError(f"choice_explanations: 선지 키 '{key}'는 '1'~'5'가 아닙니다")
        if not isinstance(row, dict):
            raise InvalidChangeError(f"choice_explanations[{key}]: dict여야 합니다")
        extra = sorted(set(row) - set(CHOICE_EXPLANATION_KEYS))
        if extra:
            raise InvalidChangeError(f"choice_explanations[{key}]: 허용되지 않은 키 {extra}")
        target = merged.get(key) if isinstance(merged.get(key), dict) else {}
        for sub_key, text in row.items():
            target[sub_key] = _require_text(f"choice_explanations[{key}].{sub_key}", text, allow_empty=True)
        merged[key] = target
    return merged


def _normalize_textbook_sources(value: Any, books: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise InvalidChangeError("textbook_sources: [{book_id, chapter}] 목록이어야 합니다")
    out: list[dict[str, Any]] = []
    for src in value:
        if not isinstance(src, dict):
            raise InvalidChangeError("textbook_sources: 각 항목은 dict여야 합니다")
        book_id = str(src.get("book_id") or "").strip()
        if book_id not in books:
            raise InvalidChangeError(f"textbook_sources: 알 수 없는 book_id {book_id!r} (evidence_routing books 밖)")
        chapter = src.get("chapter")
        if isinstance(chapter, str):
            chapter = chapter.strip()
        if chapter in (None, ""):
            raise InvalidChangeError(f"textbook_sources[{book_id}]: chapter가 필요합니다")
        row: dict[str, Any] = {"book_id": book_id, "chapter": chapter}
        if src.get("page") not in (None, ""):
            row["page"] = src.get("page")
        out.append(row)
    return out


def _normalize_harrison_sources(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise InvalidChangeError("harrison_sources: [{chapter, printed_page?, …}] 목록이어야 합니다")
    out: list[dict[str, Any]] = []
    for src in value:
        if not isinstance(src, dict):
            raise InvalidChangeError("harrison_sources: 각 항목은 dict여야 합니다")
        try:
            chapter = int(src.get("chapter"))
        except (TypeError, ValueError) as exc:
            raise InvalidChangeError("harrison_sources: chapter는 정수여야 합니다") from exc
        row = dict(src)
        row["chapter"] = chapter
        row.setdefault("source_id", f"H{chapter}")
        if row.get("printed_page") not in (None, ""):
            try:
                row["printed_page"] = int(row["printed_page"])
            except (TypeError, ValueError) as exc:
                raise InvalidChangeError("harrison_sources: printed_page는 정수여야 합니다") from exc
        out.append(row)
    return out


def _normalize_change(
    field: str, value: Any, current: dict[str, Any], books: dict[str, dict[str, Any]]
) -> Any:
    if field in ("stem", "explanation"):
        return _require_text(field, value)
    if field == "lab_box":
        return _require_text(field, value, allow_empty=True)
    if field == "choices":
        return _normalize_choices(value)
    if field == "answer":
        return _normalize_answer(value)
    if field == "choice_explanations":
        return _normalize_choice_explanations(value, current)
    if field == "textbook_sources":
        return _normalize_textbook_sources(value, books)
    if field == "harrison_sources":
        return _normalize_harrison_sources(value)
    raise InvalidChangeError(f"허용되지 않은 필드: {field}")


def _apply_gate(item: dict[str, Any]) -> dict[str, Any]:
    """하드룰 재계산 → item_quality의 hard_rule_* 키 갱신, manual_review_rules 제외 실패 목록 반환."""
    result = validate_nbme_hard_rules(item)
    manual = set(result.get("manual_review_rules") or MANUAL_REVIEW_RULES_DEFAULT)
    failed_all = list(result.get("failed_rules") or [])
    quality = item.get("item_quality") if isinstance(item.get("item_quality"), dict) else {}
    quality.update(
        {
            "hard_rule_checklist": result.get("checklist") or {},
            "hard_rule_failures": failed_all,
            "hard_rule_passed": result.get("passed_count"),
            "hard_rule_total": result.get("total_count"),
            "manual_review_rules": sorted(manual),
        }
    )
    item["item_quality"] = quality
    return {
        "failed_rules": [rule for rule in failed_all if rule not in manual],
        "manual_review_rules": [rule for rule in failed_all if rule in manual],
        "passed_count": result.get("passed_count"),
        "total_count": result.get("total_count"),
    }


def update_item(
    qid: str, changes: dict[str, Any], editor: str, *, paths: AdjudicationPaths | None = None
) -> dict[str, Any]:
    """PUT /api/faculty/adjudication/items/{qid}.

    허용 필드(ALLOWED_EDIT_FIELDS)만 받고, 실제로 달라진 필드만 faculty_edits.jsonl에 append,
    문항에 faculty_edited/faculty_edited_at 스탬프. 저장 후 하드룰 재계산 결과를
    gate.failed_rules(manual_review_rules 제외)로 돌려준다 — 실패해도 저장은 유지(경고).
    """
    if not isinstance(changes, dict):
        raise InvalidChangeError("changes는 dict여야 합니다")
    editor = str(editor or "").strip()
    if not editor:
        raise InvalidChangeError("editor가 필요합니다")
    unknown = sorted(set(map(str, changes)) - set(ALLOWED_EDIT_FIELDS))
    if unknown:
        raise InvalidChangeError(f"허용되지 않은 필드: {unknown}")
    if not changes:
        raise InvalidChangeError("변경할 필드가 없습니다")

    paths = paths or AdjudicationPaths.resolve()
    books = _load_books(paths)
    with _LOCK:
        set_no, no, path, idx, items = _locate(qid, paths)
        current = items[idx]
        normalized = {field: _normalize_change(field, value, current, books) for field, value in changes.items()}

        stamp = _now()
        updated = copy.deepcopy(current)
        diffs: list[dict[str, Any]] = []
        for field, after in normalized.items():
            before = current.get(field)
            if before == after:
                continue
            updated[field] = after
            diffs.append(
                {
                    "qid": qid,
                    "editor": editor,
                    "at": stamp,
                    "field": field,
                    "before": copy.deepcopy(before),
                    "after": copy.deepcopy(after),
                }
            )
        if not diffs:
            # 무변경 요청: 저장·이력 없이 현재 상태의 게이트만 알려준다.
            gate = _apply_gate(updated)
            return {
                "qid": qid,
                "saved": False,
                "changed_fields": [],
                "faculty_edited_at": current.get("faculty_edited_at"),
                "gate": gate,
            }

        updated["faculty_edited"] = True
        updated["faculty_edited_at"] = stamp
        # 학생 화면 개정 이력(trust_badges.revision_note)용 — 지금까지 교수가 손댄 필드의 합집합
        updated["faculty_edited_fields"] = sorted(
            set(str(f) for f in (current.get("faculty_edited_fields") or [])) | {d["field"] for d in diffs}
        )
        gate = _apply_gate(updated)
        # 캐시된 리스트는 건드리지 않고 새 리스트로 저장 → 쓰기 실패 시 메모리/디스크 불일치 없음
        new_items = list(items)
        new_items[idx] = updated
        _write_set(path, new_items)
        _append_edits(paths, diffs)

    return {
        "qid": qid,
        "saved": True,
        "changed_fields": [d["field"] for d in diffs],
        "faculty_edited_at": stamp,
        "gate": gate,
        "item": get_item(qid, paths=paths),
    }


def record_decision(
    qid: str, decision: str, by: str, note: str = "", *, paths: AdjudicationPaths | None = None
) -> dict[str, Any]:
    """POST /api/faculty/adjudication/items/{qid}/decision.

    문항에 faculty_decision:{decision,by,at,note} 기록. approve면 professor_review_required 제거 +
    medical_approval=True(학생 배포 신뢰 배지 3단 조건), 그 외는 medical_approval=False.
    결정도 faculty_edits.jsonl에 field="faculty_decision"으로 남긴다(감사 추적).
    """
    decision = str(decision or "").strip().lower()
    if decision not in DECISIONS:
        raise AdjudicationError(f"decision은 {', '.join(DECISIONS)} 중 하나여야 합니다: {decision!r}")
    by = str(by or "").strip()
    if not by:
        raise AdjudicationError("by(결정자)가 필요합니다")

    paths = paths or AdjudicationPaths.resolve()
    with _LOCK:
        _set_no, _no, path, idx, items = _locate(qid, paths)
        current = items[idx]
        stamp = _now()
        record = {"decision": decision, "by": by, "at": stamp, "note": str(note or "").strip()}
        updated = copy.deepcopy(current)
        updated["faculty_decision"] = record
        if decision == "approve":
            updated.pop("professor_review_required", None)
            updated["medical_approval"] = True
        else:
            updated["medical_approval"] = False
        new_items = list(items)
        new_items[idx] = updated
        _write_set(path, new_items)
        _append_edits(
            paths,
            [
                {
                    "qid": qid,
                    "editor": by,
                    "at": stamp,
                    "field": "faculty_decision",
                    "before": copy.deepcopy(current.get("faculty_decision")),
                    "after": record,
                }
            ],
        )
    return {
        "qid": qid,
        "faculty_decision": record,
        "medical_approval": updated["medical_approval"],
        "professor_review_required": updated.get("professor_review_required", False),
    }


def _entailment_level(entry: dict[str, Any]) -> str:
    verdict = str(((entry.get("badge") or {}).get("entailment_verdict")) or "").strip()
    return verdict if verdict in ENTAILMENT_LEVELS[:3] else "unknown"


def _distribution(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """리포트 탭(F3)용 분포 — 전체와 세트별에 같은 모양으로 쓴다."""
    decided = Counter(
        str((e.get("faculty_decision") or {}).get("decision") or "") for e in entries if e.get("faculty_decision")
    )
    actions = Counter((e.get("review") or {}).get("action") for e in entries)
    entailment = Counter(_entailment_level(e) for e in entries)
    axis = Counter(str(e.get("axis") or "기타") for e in entries)
    cognitive = Counter(str(e.get("cognitive_level") or "미기재") for e in entries)
    return {
        "items": len(entries),
        "decided": {d: decided.get(d, 0) for d in DECISIONS},
        "pending": len(entries) - sum(decided.values()),
        "answer_changed": sum(1 for e in entries if e.get("answer_changed")),
        "hard_rule_failures": sum(1 for e in entries if e.get("hard_rule_failures")),
        "professor_review_required": sum(1 for e in entries if e.get("professor_review_required")),
        "faculty_edited": sum(1 for e in entries if e.get("faculty_edited")),
        "medical_approved": sum(1 for e in entries if e.get("medical_approval")),
        "review_actions": {a: actions.get(a, 0) for a in (ACTION_KEEP, ACTION_MINOR, ACTION_REVISE, ACTION_DISCARD)},
        "unreviewed": sum(1 for e in entries if not e.get("review")),
        "disagreement": sum(1 for e in entries if (e.get("review") or {}).get("disagreement")),
        "entailment": {level: entailment.get(level, 0) for level in ENTAILMENT_LEVELS},
        "axis": dict(sorted(axis.items())),
        "cognitive_level": dict(sorted(cognitive.items())),
        "lab_box": sum(1 for e in entries if e.get("has_lab_box")),
        "image": sum(1 for e in entries if e.get("image")),
    }


def _parse_metrics(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("metrics") if isinstance(payload, dict) else payload
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict) or row.get("value") is None:
            continue
        try:
            value = float(row["value"])
            baseline = float(row.get("baseline")) if row.get("baseline") is not None else None
        except (TypeError, ValueError):
            continue
        op = str(row.get("op") or ">=")
        passed = None
        if baseline is not None:
            passed = value <= baseline if op == "<=" else value >= baseline
        out.append(
            {
                "key": str(row.get("key") or row.get("name") or ""),
                "name": str(row.get("name") or row.get("key") or ""),
                "value": value,
                "baseline": baseline,
                "op": op,
                "pass": passed,
                "unit": str(row.get("unit") or "%"),
                "note": str(row.get("note") or ""),
            }
        )
    return out


def load_quality_metrics(paths: AdjudicationPaths | None = None) -> dict[str, Any]:
    """review/quality_metrics.json → {metrics:[...], source, measured_at}. 파일이 없으면 빈 목록."""
    paths = paths or AdjudicationPaths.resolve()
    path = paths.quality_metrics_path
    if not path.exists():
        return {"metrics": [], "source": None, "measured_at": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"metrics": [], "source": None, "measured_at": None}
    meta = payload if isinstance(payload, dict) else {}
    return {
        "metrics": _cached_load(path, "metrics", _parse_metrics, missing=[]),
        "source": meta.get("source"),
        "measured_at": meta.get("measured_at"),
    }


def summary(*, paths: AdjudicationPaths | None = None) -> dict[str, Any]:
    """GET /api/faculty/adjudication/summary.

    최상위는 전체(320) 분포, sets[]는 세트별 같은 모양(F3 세트 탭용), metrics는 7지표 정적 파일.
    이전 계약 키(total/decided/pending/answer_changed/hard_rule_failures/professor_review_required/
    faculty_edited/medical_approved/review_actions/unreviewed)는 그대로 유지한다.
    """
    paths = paths or AdjudicationPaths.resolve()
    entries = _all_entries(paths)
    overall = _distribution(entries)
    per_set: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        per_set[int(entry["set"])].append(entry)
    payload: dict[str, Any] = {"total": len(entries)}
    payload.update({k: v for k, v in overall.items() if k != "items"})
    payload["sets"] = [{"set": set_no, **_distribution(per_set[set_no])} for set_no in sorted(per_set)]
    payload["quality_metrics"] = load_quality_metrics(paths)
    return payload


__all__ = [
    "ALLOWED_EDIT_FIELDS",
    "AdjudicationError",
    "AdjudicationPaths",
    "DECISIONS",
    "InvalidChangeError",
    "ItemNotFoundError",
    "QUEUE_FILTERS",
    "aggregate_reviews",
    "build_queue",
    "build_review_index",
    "clear_caches",
    "get_item",
    "global_no_of",
    "load_quality_metrics",
    "make_qid",
    "parse_qid",
    "record_decision",
    "summary",
    "update_item",
]
