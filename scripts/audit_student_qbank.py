#!/usr/bin/env python3
"""학생 공개 문항은행(278) 학습콘텐츠 보강 감사 — read-only.

api_server의 정본 로직(practice_readiness·visual·이미지 해석)과 온톨로지
question_links를 재사용해 각 문항의 보강 상태를 한 행으로 산출하고,
검수 큐 2종을 emit한다. 원본 qbank.json을 절대 수정하지 않는다.

용법:
  python3 scripts/audit_student_qbank.py                 # 요약 표 출력
  python3 scripts/audit_student_qbank.py --report out.json --worklists
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import api_server  # 정본 로직 재사용 (부작용 없이 import 됨)

QBANK_PATH = ROOT / "data_private" / "student" / "qbank.json"
QUESTION_LINKS_PATH = ROOT / "data_private" / "ontology" / "question_links.json"
ENRICH_WORKLIST = ROOT / "reports" / "student_qbank_enrichment_worklist.jsonl"
MEDIA_WORKLIST = ROOT / "reports" / "student_qbank_media_match_worklist.jsonl"
COURSE_EXAM_EXTRACTED_DIR = ROOT / "data_private" / "course_exams" / "extracted"
COURSE_EXAM_MEDIA_DIR = ROOT / "data_private" / "course_exams" / "media"

# question_blueprint의 canonical 10 Axis (허용 타입).
CANONICAL_AXES = (
    "symptom", "diagnosis", "pathophysiology", "etiology", "risk_factor",
    "prognosis", "epidemiology", "treatment", "indication", "contraindication",
)
_VISUAL_TOKENS = ("<그림>", "<사진>", "<영상>")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_question_links() -> dict:
    if not QUESTION_LINKS_PATH.exists():
        return {}
    payload = json.loads(QUESTION_LINKS_PATH.read_text(encoding="utf-8"))
    return payload.get("questions") if isinstance(payload.get("questions"), dict) else {}


def audit_question(q: dict, links: dict) -> dict:
    qid = str(q.get("id") or "")
    choices = [c for c in (q.get("choices") or []) if isinstance(c, dict)]
    choice_total = len(choices)
    choice_with_expl = sum(1 for c in choices if str(c.get("expl") or "").strip())
    stimulus = str(q.get("stimulus") or "")
    stem = str(q.get("stem") or "")
    requires_visual = any(t in stimulus for t in _VISUAL_TOKENS) or bool(
        api_server._QBank_VISUAL_REFERENCE_RE.search(stem)
    )
    connected_media = [i for i in (q.get("imgs") or []) if i and api_server.resolve_student_qbank_image(i)[1]]
    readiness = api_server.qbank_question_practice_readiness(q)
    link = links.get(qid) if isinstance(links.get(qid), dict) else None

    review: list[str] = []
    if not str(q.get("explanation") or "").strip():
        review.append("explanation_missing")
    if choice_total and choice_with_expl < choice_total:
        review.append("choice_explanation_incomplete")
    if not (q.get("points") or []):
        review.append("points_missing")
    if link is None:
        review.append("concept_link_missing")
    if not q.get("target_axis_type"):
        review.append("axis_unassigned")
    if not q.get("anki"):
        review.append("anki_absent")
    if requires_visual and not connected_media:
        review.append("required_media_missing")

    return {
        "question_id": qid,
        "exam": q.get("exam"),
        "course": api_server.canonical_student_course(q) if hasattr(api_server, "canonical_student_course") else q.get("subject"),
        "topic": q.get("topic"),
        "explanation_status": "present" if str(q.get("explanation") or "").strip() else "missing",
        "choice_explanation_coverage": f"{choice_with_expl}/{choice_total}",
        "choice_explanation_complete": bool(choice_total) and choice_with_expl == choice_total,
        "points_status": "present" if (q.get("points") or []) else "missing",
        # 개념 연결은 별도 링크파일이 1순위지만, 문항 자체가 온톨로지 개념ID를
        # 들고 있으면(생성 파이프라인 산출물) 그것도 연결로 인정한다.
        "concept_link_status": "linked" if (link or q.get("disease_concept_id")) else "unlinked",
        "concept_id": (link or {}).get("concept") or q.get("disease_concept_id"),
        "target_axis_type": q.get("target_axis_type"),
        "target_axis_ids": q.get("target_axis_ids") or [],
        # 필드명은 anki_cards(학생 payload 계약). 구 데이터의 'anki'도 함께 인정.
        "anki_status": "present" if (q.get("anki_cards") or q.get("anki")) else "absent",
        "requires_visual": requires_visual,
        "connected_media_count": len(connected_media),
        "practice_ready": bool(readiness["practice_ready"]),
        "review_reasons": review,
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "total": n,
        "explanation_present": sum(r["explanation_status"] == "present" for r in rows),
        "explanation_missing": sum(r["explanation_status"] == "missing" for r in rows),
        "all_choice_explanations_complete": sum(r["choice_explanation_complete"] for r in rows),
        "choice_explanations_present": sum(int(r["choice_explanation_coverage"].split("/")[0]) for r in rows),
        "choice_explanations_total": sum(int(r["choice_explanation_coverage"].split("/")[1]) for r in rows),
        "points_present": sum(r["points_status"] == "present" for r in rows),
        "anki_present": sum(r["anki_status"] == "present" for r in rows),
        "axis_assigned": sum(bool(r["target_axis_type"]) for r in rows),
        "concept_linked": sum(r["concept_link_status"] == "linked" for r in rows),
        "requires_visual": sum(r["requires_visual"] for r in rows),
        "media_connected": sum(r["connected_media_count"] > 0 for r in rows),
        "media_missing_blocked": sum(r["requires_visual"] and r["connected_media_count"] == 0 for r in rows),
        "practice_ready": sum(r["practice_ready"] for r in rows),
    }


def run_audit() -> dict:
    qbank = json.loads(QBANK_PATH.read_text(encoding="utf-8"))
    questions = qbank.get("questions") if isinstance(qbank, dict) else qbank
    links = load_question_links()
    rows = [audit_question(q, links) for q in questions]
    return {
        "source_qbank_sha256": sha256_of(QBANK_PATH),
        "summary": summarize(rows),
        "rows": rows,
    }


def extracted_media_review_context(question_id: str) -> dict:
    """원 추출기가 남긴 이미지 후보를 검수 정보로만 반환한다.

    confidence나 파일 존재만으로 자동 승인하지 않는다. 기존 추출 결과가
    ``needs_review=true``이면 그대로 review candidate로 유지한다.
    """
    prefix = str(question_id or "").rsplit("_Q", 1)[0]
    extracted_path = COURSE_EXAM_EXTRACTED_DIR / f"{prefix}.json"
    if not prefix or not extracted_path.exists():
        return {"extracted_record_found": False, "candidates": [], "authored_media_refs": []}
    try:
        payload = json.loads(extracted_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"extracted_record_found": False, "candidates": [], "authored_media_refs": []}
    questions = payload.get("questions") if isinstance(payload, dict) else []
    question = next(
        (
            row for row in questions or []
            if isinstance(row, dict) and str(row.get("question_id") or "") == str(question_id)
        ),
        None,
    )
    if not isinstance(question, dict):
        return {"extracted_record_found": False, "candidates": [], "authored_media_refs": []}
    refs = (question.get("media") or {}).get("media_refs") or []
    media_dir = COURSE_EXAM_MEDIA_DIR / prefix
    candidates = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        storage_id = str(ref.get("storage_id") or "").strip()
        matches = sorted(
            p.name for p in media_dir.iterdir()
            if p.is_file() and p.stem == storage_id
        ) if storage_id and media_dir.exists() else []
        candidates.append({
            "media_id": ref.get("media_id"),
            "storage_id": storage_id,
            "files": matches,
            "file_exists": bool(matches),
            "match_method": ref.get("match_method"),
            "match_confidence": ref.get("match_confidence"),
            "needs_review": ref.get("needs_review") is not False,
        })
    return {
        "extracted_record_found": True,
        "candidates": candidates,
        "authored_media_refs": question.get("authored_media_refs") or [],
    }


def emit_worklists(result: dict) -> tuple[int, int]:
    ENRICH_WORKLIST.parent.mkdir(parents=True, exist_ok=True)
    enrich = 0
    with ENRICH_WORKLIST.open("w", encoding="utf-8") as fh:
        for r in result["rows"]:
            gaps = [x for x in r["review_reasons"] if x != "required_media_missing"]
            if gaps:
                fh.write(json.dumps({
                    "question_id": r["question_id"], "exam": r["exam"], "topic": r["topic"],
                    "gaps": gaps, "concept_id": r["concept_id"],
                    "choice_explanation_coverage": r["choice_explanation_coverage"],
                    "needs_review": True,
                }, ensure_ascii=False) + "\n")
                enrich += 1
    media = 0
    with MEDIA_WORKLIST.open("w", encoding="utf-8") as fh:
        for r in result["rows"]:
            if r["requires_visual"] and r["connected_media_count"] == 0:
                candidate_context = extracted_media_review_context(r["question_id"])
                fh.write(json.dumps({
                    "question_id": r["question_id"], "exam": r["exam"], "topic": r["topic"],
                    "reason": "required_visual_not_connected", "status": "blocked",
                    "match": "review_candidates_available" if candidate_context["candidates"] else "source_manifest_required",
                    "candidate_media": candidate_context["candidates"],
                    "authored_media_refs": candidate_context["authored_media_refs"],
                    "auto_link_allowed": False,
                    "needs_review": True,
                }, ensure_ascii=False) + "\n")
                media += 1
    return enrich, media


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=str, default="")
    ap.add_argument("--worklists", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = run_audit()
    s = result["summary"]
    if args.report:
        Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.worklists:
        e, m = emit_worklists(result)
        print(f"worklists: enrichment {e} → {ENRICH_WORKLIST.name}, media {m} → {MEDIA_WORKLIST.name}")
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0

    print(f"=== 학생 문항은행 보강 감사 (read-only) · sha256 {result['source_qbank_sha256'][:12]} ===")
    print(f"전체 문항: {s['total']}")
    print(f"해설: 있음 {s['explanation_present']} / 없음 {s['explanation_missing']}")
    print(f"모든 선지풀이 완비: {s['all_choice_explanations_complete']}")
    print(f"선지풀이: {s['choice_explanations_present']}/{s['choice_explanations_total']}")
    print(f"출제 포인트: {s['points_present']}")
    print(f"Anki: {s['anki_present']} · canonical Axis: {s['axis_assigned']}")
    print(f"concept link: {s['concept_linked']}")
    print(f"시각자료 필요 {s['requires_visual']} · 연결 {s['media_connected']} · 미연결차단 {s['media_missing_blocked']}")
    print(f"practice-ready: {s['practice_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
