#!/usr/bin/env python3
"""
근거 점프 (Evidence Jump) — 배치 러너
라벨링된 문항 은행(혈액종양 과정시험)에 Harrison Part 4 근거 연결을 자동 부착한다.

출력 계약(학생 화면):
  1) 근거 해설  — 기존 라벨링의 answer_rationale 재사용(새로 작성된 설명, 원문 복붙 아님)
  2) 정확한 위치 — Harrison Part 4 Ch/페이지 (retrieval 후보 + 신뢰도)
  3) 짧은 인용   — HIGH 신뢰도일 때만, 가드레일(길이·출처) 통과분
  4) 열람 링크   — AccessMedicine 토픽검색(오링크 없음, 부산대 프록시 슬롯) + MSD 공개자료

안전 규칙(Evidence_Jump_Spec 준수):
  - AccessMedicine 딥링크(sectionid) **추측 금지** → 토픽검색 URL만 사용(오라우팅 없음).
  - retrieval 챕터는 '후보 위치'. 점수 임계값 미만이면 needs_review=true(학생 노출 전 검토).
  - 인용 길이 상한/출처 필수(G1/G2). 전체 단락 미출력(G3).
  - Harrison 원문은 grounding 입력으로만; 사이드카에도 원문 단락 통째 저장 안 함.

프라이버시: 입출력 모두 data_private/ 내부. git 미추적.

사용법:
  python3 scripts/build_evidence_jump_batch.py \
      data_private/course_exams/extracted/COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험.json
  python3 scripts/build_evidence_jump_batch.py --all-heme
  python3 scripts/build_evidence_jump_batch.py <exam.json> --preview   # HTML 미리보기도 생성
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, quote_plus

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evidence_jump_poc import (  # noqa: E402
    enforce_quote_guardrails,
    _extract_short_quote_from_passage,
    retrieve_passages,
)

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

# 부산대 접근(2026-07-01 사용자 확인):
#   - 교내접속(campus network) 시 accessmedicine.mhmedical.com 이 기관 인증으로 '직접' 열람됨(프록시 불필요).
#   - 교외접속은 부산대 도서관 discovery에서 로그인 후 AccessMedicine으로 진입.
# 2026-09-27 확인: 부산대는 EZproxy(login?url=)가 아니다. libproxy.pusan.ac.kr 같은 호스트는 존재하지 않고,
#   실제 교외접속은 도서관 로그인(https://lib.pusan.ac.kr/login?returnUrl=…) → 경로 접두어형 lproxy
#   (https://lproxy.pusan.ac.kr/_Lib_Proxy_Url/<원본 URL, 인코딩 없음>) 체인이다. lproxy URL 단독은 비로그인 시 원본으로 바운스.
#   교외 링크가 필요하면 src/services/textbook_evidence.pnu_offcampus_url() 을 쓰고, 이 접두어는 타 기관 EZproxy용으로만 남긴다.
PNU_PROXY_PREFIX = ""

# AccessMedicine(해리슨 온라인). 부산대 구독 Harrison = bookId 3541 (사용자 교내접속으로 확인).
AM_BASE = "https://accessmedicine.mhmedical.com"
AM_HARRISON_BOOKID = "3541"
# 교외접속 진입점: 부산대 도서관 discovery의 Harrison 검색(로그인 후 전자자료로 진입).
PNU_DISCOVERY_HARRISON = (
    "https://lib.pusan.ac.kr/search/i-discovery?tabIndex=4"
    "&search=Harrison%27s%20principles%20of%20internal%20medicine"
    "&resourceType=book&resourceType=book%20series"
)
# MSD Manual Professional(공개자료) 검색.
MSD_BASE = "https://www.msdmanuals.com/professional/SearchResults"

# 신뢰도 임계값(전체 116문항 점수 분포로 보정: 중앙값 28, 오링크는 <16에 집중).
SCORE_HIGH = 24.0   # 이상 → 검토 우선순위 낮음(그래도 사람 검증 필수: HIGH도 오링크 20%)
SCORE_MED = 16.0    # 이상~미만 → 검토 우선순위 중
# 미만 → 검토 우선순위 높음, 후보 장 숨김

# 의학검토(2026-07-01)로 확인된 구조적 오매칭 카테고리 — 점수와 무관하게 needs_review 강제.
# Harrison Part 4는 성인 내과 질환 중심 교과서라 아래 주제는 구조적으로 미커버/오매칭.
STRUCTURAL_EXCLUDE_KEYWORDS = (
    # 소아 고형종양/소아 혈액 (Harrison 성인서라 얇게 다룸)
    "neuroblastoma", "wilms", "retinoblastoma", "hepatoblastoma", "medulloblastoma",
    "pediatric_cbc", "pediatric_reference", "age_specific_reference", "pediatric",
    # 비질환형(약물 계열 정의·규제/GCP·방사선 기법·검사장비·기초 조직/생리)
    "gcp", "good_clinical_practice", "ind_", "clinical_trial", "regulatory",
    "drug_approval", "first_in_human", "dossier", "phase_1", "phase1",
    "itv", "ctv", "gtv", "ptv", "sbrt", "vmat", "imrt", "radiotherapy_planning",
    "digital_morphology", "instrument", "analyzer", "analyser",
    "granulopoiesis", "promyelocyte", "morphology_recognition",
)
# 림프종 아형 충돌(호지킨 단서 + 후보 챕터가 Non-Hodgkin, 또는 반대) 감지용.
_HODGKIN_TERMS = ("hodgkin", "reed_sternberg", "reed-sternberg")

OUT_DIR = ROOT / "data_private" / "course_exams" / "evidence_jump"


# ---------------------------------------------------------------------------
# 링크 생성 (오링크 없는 검색 URL만)
# ---------------------------------------------------------------------------

def _wrap_proxy(url: str) -> str:
    """EZproxy식 접두어(login?url=)가 설정돼 있으면 인코딩해 감싼다. 부산대 lproxy(경로형·비인코딩)에는 맞지 않으니 비워 둔다."""
    if PNU_PROXY_PREFIX:
        return PNU_PROXY_PREFIX + quote(url, safe="")
    return url


def build_access_links(topic_ko: str, concept_tags: list[str]) -> dict:
    """열람 링크 묶음. 모두 '검색/랜딩' URL이라 sectionid 추측 오링크가 없다.

    - accessmedicine: 교내직접접속용, 토픽 검색(해리슨 결과 상단에 노출).
    - harrison_book : 해리슨 목차 랜딩(bookid=3541).
    - pnu_offcampus : 교외접속용, 부산대 도서관 discovery(로그인 후 진입) — 고정.
    - msd_open      : 공개자료(MSD) 토픽 검색.
    """
    en_q = " ".join(t.replace("_", " ") for t in concept_tags[:3])
    am_q = topic_ko or en_q  # 해리슨 검색은 한글 토픽 우선
    am_search = _wrap_proxy(f"{AM_BASE}/searchresults.aspx?q={quote_plus(am_q)}")
    harrison_book = _wrap_proxy(f"{AM_BASE}/book.aspx?bookid={AM_HARRISON_BOOKID}")
    pnu_offcampus = PNU_DISCOVERY_HARRISON
    msd_open = f"{MSD_BASE}?query={quote_plus(en_q or topic_ko)}"
    return {
        "accessmedicine_search": am_search,
        "harrison_book": harrison_book,
        "pnu_offcampus": pnu_offcampus,
        "msd_open": msd_open,
    }


# ---------------------------------------------------------------------------
# 문항 1건 → 근거 점프 레코드
# ---------------------------------------------------------------------------

def _query_for(question: dict) -> str:
    tags = (question.get("labels", {}) or {}).get("concept_tags") or []
    ki = question.get("key_info", {}) or {}
    topic = ki.get("topic") or ""
    head = re.split(r"[.。]", question.get("answer_rationale", "") or "")[0][:80]
    return " ".join(tags[:4]) + " " + topic + " " + head


def build_record(question: dict) -> dict:
    qid = question.get("question_id")
    qnum = question.get("question_number")
    tags = (question.get("labels", {}) or {}).get("concept_tags") or []
    ki = question.get("key_info", {}) or {}
    topic_ko = ki.get("topic") or ki.get("major_category") or ""
    rationale = (question.get("answer_rationale") or "").strip()

    passages = retrieve_passages(_query_for(question), top_k=3)
    top = passages[0] if passages else {}
    score = float(top.get("score", 0.0))

    if score >= SCORE_HIGH:
        confidence = "high"
    elif score >= SCORE_MED:
        confidence = "medium"
    else:
        confidence = "low"

    review_reasons: list[str] = []
    tags_l = " ".join(tags).lower()
    cand_title_l = (top.get("chapter_title") or "").lower()

    # 규칙 1: 구조적 제외 카테고리 — 점수 무관 강제 검토(장 미표기).
    structural_excluded = any(kw in tags_l for kw in STRUCTURAL_EXCLUDE_KEYWORDS)
    # 규칙 2: 림프종 아형 충돌(호지킨 단서인데 후보가 Non-Hodgkin, 또는 반대).
    hodgkin_clue = any(t in tags_l for t in _HODGKIN_TERMS)
    lymphoma_conflict = (hodgkin_clue and "non-hodgkin" in cand_title_l) or (
        (not hodgkin_clue) and "hodgkin" in tags_l and "non-hodgkin" not in cand_title_l
        and "hodgkin" in cand_title_l
    )
    # 규칙 3: 원문 문항이 '정답키/내용 불확실' 사유로 플래그된 경우만 근거 카드 전체 차단.
    # (이미지 자산 대기·보기추출 등은 근거해설 타당성과 무관하므로 차단하지 않음.)
    _BLOCK_REASONS = (
        "answer_not_extracted", "answer_key", "정답키", "answer_key_vs",
        "uncertain", "불확실", "differential", "generated_answer",
    )
    src_reasons = " ".join(question.get("review_reasons") or []).lower()
    source_flagged = bool(question.get("needs_review")) and (
        any(b in src_reasons for b in _BLOCK_REASONS) or not question.get("answer")
    )

    # 검토 우선순위(사람 검토 시간 배분용): 낮을수록 확인 빠름.
    if structural_excluded:
        review_priority = "exclude"       # Harrison 구조적 미커버 → 다른 소스로 큐레이션
    elif confidence == "high" and not lymphoma_conflict:
        review_priority = "low"
    elif confidence == "medium":
        review_priority = "medium"
    else:
        review_priority = "high"

    # 후보 위치: 제외/저점수는 파트 수준만, 그 외는 후보 장/페이지 표기.
    if not structural_excluded and confidence in ("high", "medium") and top:
        ch = top.get("chapter_num")
        title = (top.get("chapter_title") or "").strip()
        page = top.get("printed_page")
        loc_bits = ["Harrison Part 4 (Oncology and Hematology)"]
        if ch:
            loc_bits.append(f"Ch.{ch}: {title}")
        elif title:
            loc_bits.append(title)
        if page:
            loc_bits.append(f"~p.{page}")
        location = ", ".join(loc_bits)
    elif structural_excluded:
        location = "Harrison Part 4는 이 주제(소아종양/비질환형)를 미커버 — 다른 소스 큐레이션 필요"
    else:
        location = "Harrison Part 4 (Oncology and Hematology) — 정확한 장 검토 필요"

    # 핵심: 자동 부착된 위치는 어떤 것도 아직 사람 검증 전 → 항상 미큐레이션 초안.
    # (의학검토: HIGH도 오링크 20% → 점수만으로 학생 노출 불가.)
    location_curated = False

    # 위치는 언제나 검토 필요(미큐레이션). 사유를 우선순위/카테고리별로 명시.
    needs_review = True
    if source_flagged:
        review_reasons.append("원문 문항이 needs_review(정답키/내용 불확실) — 근거 카드 전체 노출 차단")
    if structural_excluded:
        review_reasons.append("구조적 제외(소아종양/규제·방사선기법·검사장비·기초조직 등) — Harrison Part 4 미커버")
    elif lymphoma_conflict:
        review_reasons.append("림프종 아형 충돌(호지킨 단서 vs 후보 챕터) — 위치 재확인 필요")
    else:
        review_reasons.append(
            f"위치 미큐레이션(retrieval {confidence}, score={score:.1f}) — 사람 검증 후 학생 노출"
        )

    # 짧은 인용: 자동 OCR 인용은 학생 미표시. 검토 우선순위 낮은(HIGH·비제외) 건만 초안 보관.
    candidate_quote = ""
    if review_priority == "low" and top.get("_raw_text"):
        raw = _extract_short_quote_from_passage(top["_raw_text"])
        safe_quote, _q_nr, q_reasons = enforce_quote_guardrails(raw, location)
        candidate_quote = safe_quote
        review_reasons.extend(q_reasons)

    if not rationale:
        review_reasons.append("근거 해설(answer_rationale) 없음 — 라벨링 보완 필요")

    links = build_access_links(topic_ko, tags)

    # 학생 즉시 노출 가능 여부: 근거해설+검색링크는 안전. 단, 원문 문항이 플래그면 전체 차단.
    student_ready = bool(rationale) and not source_flagged

    return {
        "question_id": qid,
        "question_number": qnum,
        "topic": topic_ko,
        "concept_tags": tags[:6],
        # 출력 계약
        "rationale": rationale,                     # (1) 근거 해설 — 기존 라벨 재사용(학생용 안전)
        "harrison_location": location,              # (2) 위치(후보·미큐레이션)
        "location_curated": location_curated,       # 사람 검증 여부(현재 전부 False)
        # (4) 열람 링크 — 오링크 없는 검색/랜딩
        "access_accessmedicine_search": links["accessmedicine_search"],  # 교내 직접접속
        "access_harrison_book": links["harrison_book"],                  # 해리슨 목차(bookid 3541)
        "access_pnu_offcampus": links["pnu_offcampus"],                  # 교외: 부산대 도서관 로그인
        "access_open_msd": links["msd_open"],                            # 공개자료
        # 내부 메타 / 검토
        "student_ready": student_ready,             # 근거해설+링크 즉시 노출 가능
        "block_evidence_display": source_flagged,   # 원문 플래그 시 카드 전체 차단
        "review_priority": review_priority,         # exclude / high / medium / low
        "structural_excluded": structural_excluded,
        "lymphoma_conflict": lymphoma_conflict,
        "retrieval_score": round(score, 2),
        "retrieval_confidence": confidence,
        "candidate_chapter": top.get("chapter_num"),
        "candidate_chapter_title": (top.get("chapter_title") or "").strip(),
        "candidate_printed_page": top.get("printed_page"),
        "candidate_quote_draft": candidate_quote,   # 내부 초안(OCR·미검증) — 학생 미표시
        "needs_review": needs_review,
        "review_reasons": review_reasons,
        "proxy_configured": bool(PNU_PROXY_PREFIX),
    }


# ---------------------------------------------------------------------------
# 시험 1개 처리
# ---------------------------------------------------------------------------

def process_exam(exam_path: Path, *, make_preview: bool = False) -> dict:
    data = json.load(open(exam_path, encoding="utf-8"))
    questions = data.get("questions", []) if isinstance(data, dict) else data
    exam_id = exam_path.stem

    records = [build_record(q) for q in questions]

    conf = {"high": 0, "medium": 0, "low": 0}
    prio = {"exclude": 0, "high": 0, "medium": 0, "low": 0}
    for r in records:
        conf[r["retrieval_confidence"]] += 1
        prio[r["review_priority"]] += 1
    nr = sum(1 for r in records if r["needs_review"])
    student_ready = sum(1 for r in records if r["student_ready"])
    blocked = sum(1 for r in records if r["block_evidence_display"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "exam_id": exam_id,
        "source_file": str(exam_path.relative_to(ROOT)),
        "textbook": "Harrison's Principles of Internal Medicine — Part 4 (Oncology and Hematology)",
        "grounding_index": "data_private/rag/harrison_part4/rag_index.json",
        "proxy_configured": bool(PNU_PROXY_PREFIX),
        "score_thresholds": {"high": SCORE_HIGH, "medium": SCORE_MED},
        "policy_note": (
            "Harrison 위치는 전부 미큐레이션 초안(location_curated=false). "
            "학생 즉시 노출 = 근거해설 + 검색링크(student_ready). "
            "챕터/페이지는 review_priority 순으로 사람 검증 후 노출."
        ),
        "summary": {
            "questions": len(records),
            "retrieval_confidence": conf,
            "review_priority": prio,
            "needs_review_location": nr,
            "student_ready_now": student_ready,
            "blocked_by_source_flag": blocked,
        },
        "records": records,
    }
    out_path = OUT_DIR / f"{exam_id}__evidence.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if make_preview:
        _write_preview(exam_id, out, records)

    print(
        f"[{exam_id}] {len(records)}문항 → {out_path.relative_to(ROOT)}  "
        f"| 검토우선순위 exclude={prio['exclude']} high={prio['high']} med={prio['medium']} low={prio['low']} "
        f"| 학생즉시노출(해설+링크)={student_ready} 차단={blocked}"
        f"{' | proxy=SET' if PNU_PROXY_PREFIX else ' | proxy=EMPTY(부산대 URL 미설정)'}"
    )
    return out


# ---------------------------------------------------------------------------
# 학생 화면 미리보기(HTML) — '근거 보기' 카드 데모
# ---------------------------------------------------------------------------

def _write_preview(exam_id: str, out: dict, records: list[dict], limit: int = 12) -> None:
    # 학생용 미리보기는 '안전한 부분'만 노출: 근거해설 + 검색링크(오링크 없음).
    # Harrison 후보 장/페이지는 '검토 전 후보'로만 표기하고, 자동 OCR 인용은 표시하지 않는다
    # (OCR 잡음 + 오매칭 위험 → 의학검토 큐레이션 후에만 학생 노출).
    cards = []
    for r in records[:limit]:
        if r["block_evidence_display"]:
            cards.append(f"""
        <div class="card blocked">
          <div class="qh">Q{r['question_number']} · <span class="topic">{html.escape(r['topic'] or '')}</span>
            <span class="conf" style="background:#6e7781">차단</span></div>
          <div class="sec">원문 문항이 검토 필요(정답키/내용 불확실) 상태 — 근거 카드 노출 보류.</div>
        </div>""")
            continue
        loc_tag = "검토 완료" if r["location_curated"] else "후보 · 검토 전"
        loc_color = "#1a7f37" if r["location_curated"] else "#9a6700"
        cards.append(f"""
        <div class="card">
          <div class="qh">Q{r['question_number']} · <span class="topic">{html.escape(r['topic'] or '')}</span>
            <span class="conf" style="background:#57606a">검토우선순위 {r['review_priority']}</span></div>
          <div class="sec"><b>근거 해설</b> <span style="color:#1a7f37;font-size:12px">[학생용 확정]</span><br>{html.escape(r['rationale'] or '(없음)')}</div>
          <div class="sec"><b>교과서 위치</b> <span class="loctag" style="color:{loc_color}">[{loc_tag}]</span><br>
            {html.escape(r['harrison_location'])}</div>
          <div class="sec links"><b>원문 열람</b> <span style="color:#1a7f37;font-size:12px">[오링크 없는 검색/랜딩]</span><br>
            <a href="{html.escape(r['access_accessmedicine_search'])}" target="_blank">📖 해리슨 검색(교내 직접접속)</a> ·
            <a href="{html.escape(r['access_harrison_book'])}" target="_blank">📕 해리슨 목차</a> ·
            <a href="{html.escape(r['access_pnu_offcampus'])}" target="_blank">🏛 교외: 부산대 도서관</a> ·
            <a href="{html.escape(r['access_open_msd'])}" target="_blank">🔓 MSD(공개)</a>
          </div>
        </div>""")
    s = out["summary"]
    proxy_note = ("부산대 프록시 설정됨" if out["proxy_configured"]
                  else "⚠ 부산대 EZproxy URL 미설정 — 링크는 AccessMedicine 직접(도서관 로그인 별도)")
    doc = f"""<!doctype html><meta charset="utf-8"><title>근거 점프 미리보기 · {html.escape(exam_id)}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:24px auto;padding:0 16px;color:#1f2328}}
h1{{font-size:18px}} .meta{{color:#57606a;font-size:13px;margin-bottom:16px}}
.card{{border:1px solid #d0d7de;border-radius:10px;padding:14px 16px;margin:14px 0;background:#fff}}
.qh{{font-weight:600;margin-bottom:8px}} .topic{{color:#57606a;font-weight:400}}
.conf{{color:#fff;font-size:11px;padding:2px 7px;border-radius:10px;margin-left:6px}}
.sec{{font-size:14px;margin:8px 0;line-height:1.5}} .links a{{color:#0969da;text-decoration:none}}
.quote{{background:#f6f8fa;border-left:3px solid #d0d7de;padding:8px 12px;font-size:13px;margin:8px 0}}
.qsrc{{color:#57606a;font-size:12px;margin-top:4px}} .flag{{color:#b42318;font-size:12px}}
</style>
<h1>근거 점프 (Evidence Jump) — {html.escape(exam_id)}</h1>
<div class="meta">Harrison Part 4 grounding · {s['questions']}문항 · 학생즉시노출(해설+링크) {s['student_ready_now']} · 위치 검토우선순위 exclude {s['review_priority']['exclude']}/high {s['review_priority']['high']}/med {s['review_priority']['medium']}/low {s['review_priority']['low']}<br>{proxy_note} · 상위 {limit}문항 미리보기 · <b>Harrison 위치는 전부 검토 전 초안</b></div>
{''.join(cards)}
"""
    p = OUT_DIR / f"{exam_id}__preview.html"
    p.write_text(doc, encoding="utf-8")
    print(f"    미리보기: {p.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# 엔트리
# ---------------------------------------------------------------------------

HEME_GLOB = str(
    ROOT / "data_private" / "course_exams" / "extracted"
    / "COURSE_2_*HEMATOLOGY_ONCOLOGY*.json"
)


def main() -> None:
    ap = argparse.ArgumentParser(description="근거 점프 배치 러너 (Harrison Part 4)")
    ap.add_argument("exam", nargs="?", help="시험 JSON 경로")
    ap.add_argument("--all-heme", action="store_true", help="혈액종양 과정시험 전체 처리")
    ap.add_argument("--preview", action="store_true", help="학생 화면 HTML 미리보기 생성")
    args = ap.parse_args()

    targets: list[Path] = []
    if args.all_heme:
        targets = [Path(p) for p in sorted(glob.glob(HEME_GLOB)) if ".bak" not in p]
    elif args.exam:
        targets = [Path(args.exam)]
    else:
        ap.error("시험 경로 또는 --all-heme 필요")

    for t in targets:
        if not t.exists():
            print(f"[skip] 없음: {t}", file=sys.stderr)
            continue
        process_exam(t, make_preview=args.preview)


if __name__ == "__main__":
    main()
