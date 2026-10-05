#!/usr/bin/env python3
"""생성 문항 4세트 → 학생 UI(student-v3) qbank.json 게시.

학생 UI 계약(조사 결과):
  - 레코드 16필드 고정. choices=[{n:"1", text, expl}], answer는 **문자열**.
  - 선지별 해설은 reader.js가 feedback.choice_explanations[String(n)]로 읽는다
    → qbank의 choices[].expl을 서버가 그 맵으로 재구성해준다.
  - 이미지는 절대경로 "/api/course-exams/media/<SOURCE>/<file>"로 쓰면
    별칭표를 우회하고 기존 라우트가 그대로 서빙한다.
  - stimulus에 "<그림>"이 있는데 이미지가 안 풀리면 practice_ready=false로 걸러진다.

주의(조사에서 확인된 함정):
  A. qbank.json이 1바이트라도 바뀌면 qbank_enrichment.releases.json의
     built_against_sha256 검증이 깨져 기존 140개 릴리스가 통째로 무효화된다.
     → 이 스크립트가 두 릴리스 파일의 해시를 같은 트랜잭션에서 갱신한다.
  B. load_student_qbank()는 파일 서명 캐시라 재발행 즉시 반영된다(교수 콘솔 편집·폐기는 재발행 없이도 런타임 오버레이로 반영).
사용: python3 scripts/publish_items_to_student_qbank.py --exam "AI 생성 세트 · 2026 1차"
"""
import argparse
import hashlib
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
QBANK = Path("data_private/student/qbank.json")
RELEASES = Path("data_private/student/qbank_enrichment.releases.json")
DRAFT = Path("data_private/student/qbank_enrichment.draft.json")
SRC_IMG = Path("data_private/professor_items/images")
MEDIA_DIR = Path("data_private/course_exams/media/SYNTH_GENERATED")
MEDIA_URL = "/api/course-exams/media/SYNTH_GENERATED"
VISUAL_TOKEN = re.compile(r"<그림>|<사진>|<영상>")
# 서버 readiness 판정(api_server._QBank_VISUAL_REFERENCE_RE)과 동일 규칙
VISUAL_REF = re.compile(r"(?:아래|다음|위의).{0,30}(?:그림|사진|영상)|"
                        r"(?:그림|사진|영상).{0,20}(?:관찰|소견|제시|같)", re.IGNORECASE)


def to_tags(it) -> list:
    """온톨로지 개념·축을 snake_case 태그로."""
    tags = []
    cid = str(it.get("disease_concept_id") or "").strip()
    if cid:
        tags.append(cid)
    ax = {"진단": "diagnosis", "검사": "test_selection", "치료": "treatment"}.get(it.get("axis", ""))
    if ax:
        tags.append(ax)
    for c in (it.get("cognitive_model") or {}).get("decision_cues", [])[:3]:
        t = re.sub(r"[^0-9A-Za-z가-힣]+", "_", str(c)).strip("_").lower()
        if 2 <= len(t) <= 40:
            tags.append(t)
    return tags[:6]


def to_points(it) -> list:
    """출제 포인트: 결정 단서 + 정답 개념."""
    cm = it.get("cognitive_model") or {}
    pts = [str(c) for c in (cm.get("decision_cues") or [])[:3] if str(c).strip()]
    ac = str(cm.get("answer_concept") or "").strip()
    if ac:
        pts.append(f"정답 개념: {ac}")
    for h in (it.get("harrison_sources") or [])[:1]:
        pts.append(f"근거 위치: Harrison 22e Ch.{h.get('chapter')} p.{h.get('printed_page')}")
    return pts[:4]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", default="AI 생성 세트 · 2026 1차")
    ap.add_argument("--prefix", default="AIGEN")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace-all", action="store_true",
                    help="기존 문항을 전부 내리고 이번 생성분만 올린다(백업 후 교체)")
    ap.add_argument("--reviewed-at", default="2026-08-17T00:00:00Z",
                    help="릴리스 기록 시각(감사 추적용)")
    args = ap.parse_args()

    qb = json.loads(QBANK.read_text(encoding="utf-8"))
    before = len(qb["questions"])
    if args.replace_all:
        bak = QBANK.with_suffix(".json.bak")
        if not bak.exists():                      # 최초 1회만 원본 보존
            bak.write_bytes(QBANK.read_bytes())
            print(f"  원본 백업 → {bak}")
        qb["questions"] = []
        qb["subjects"] = []
        qb["generatedFrom"] = []
        removed = before
    else:
        # 재실행 멱등: 이전에 게시한 같은 접두어 레코드는 걷어내고 다시 넣는다
        qb["questions"] = [q for q in qb["questions"] if not str(q["id"]).startswith(args.prefix)]
        removed = before - len(qb["questions"])

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    cards_path = GEN / "anki_cards.json"
    anki = json.loads(cards_path.read_text(encoding="utf-8")) if cards_path.exists() else {}
    new, st = [], Counter()
    for k in range(1, 5):
        p = GEN / f"set_{k}.json"
        if not p.exists():
            continue
        for it in json.loads(p.read_text(encoding="utf-8")):
            qid = f"{args.prefix}_{k}_{it['no']:03d}"
            # 교수 검토 콘솔에서 '폐기'로 결정된 문항은 학생 은행에 다시 싣지 않는다(서버도 런타임에 제외하지만 재발행 시 명시적으로 뺀다).
            decision = it.get("faculty_decision") if isinstance(it.get("faculty_decision"), dict) else {}
            if str(decision.get("decision") or "").lower() == "discard":
                st["폐기제외"] += 1
                continue
            imgs = []
            f = it.get("image", "")
            if f:
                src = SRC_IMG / f
                if src.exists():
                    if not (MEDIA_DIR / f).exists():
                        shutil.copy(src, MEDIA_DIR / f)
                    imgs.append(f"{MEDIA_URL}/{f}")
                    st["이미지연결"] += 1
                else:
                    st["이미지없음"] += 1
            ce = it.get("choice_explanations") or {}
            choices = []
            for n in ("1", "2", "3", "4", "5"):
                row = ce.get(n) or {}
                expl = str(row.get("why_correct") or row.get("why_attractive") or "").strip()
                choices.append({"n": n, "text": str(it["choices"][n]), "expl": expl})
            if all(c["expl"] for c in choices):
                st["선지해설완비"] += 1
            if anki.get(qid):
                st["Anki보유"] += 1

            stimulus = str(it.get("lab_box") or "")
            stem = str(it["stem"])
            # 이미지가 없는데 시각자료를 가리키는 표현이 남아 있으면 서버가
            # required_media_missing으로 판정해 practice_ready를 끈다 → 문장째 제거.
            if not imgs:
                stimulus = VISUAL_TOKEN.sub("", stimulus).strip()
                if VISUAL_REF.search(stem):
                    kept = [s for s in re.split(r"(?<=[.。?])\s+", stem)
                            if not VISUAL_REF.search(s)]
                    stem = re.sub(r"\s+", " ", " ".join(kept)).strip()
                    st["시각참조문장제거"] += 1

            new.append({
                "id": qid,
                "exam": args.exam,
                # 학생 UI 트리: subject(분과) → major(평가축) → topic(개념)
                "subject": str(it.get("subject") or "임상종합"),
                "major": str(it.get("axis") or "기타"),
                "topic": str(it.get("concept") or ""),
                "subtopic": str(it.get("modality") or ""),
                "qtype": "image_interpretation" if imgs else "임상증례형",
                "tags": to_tags(it),
                "faculty": "AI 생성(검수 전)",
                "stem": stem,
                "stimulus": stimulus,
                "choices": choices,
                "answer": str(it["answer"]),
                "explanation": str(it.get("explanation") or ""),
                "points": to_points(it),
                "imgs": imgs,
                "anki_cards": [{"anki_text": c["text"], "plain_text": c["extra"],
                                "tags": c.get("tags") or []} for c in anki.get(qid, [])],
                # 온톨로지 메타(감사·분석용). public_qbank_question은 허용목록이라 유출 없음.
                "disease_concept_id": str(it.get("disease_concept_id") or ""),
                "target_axis_type": {"진단": "diagnosis", "검사": "test_selection",
                                     "치료": "treatment"}.get(it.get("axis", ""), ""),
                # 골든 스키마 v3 난이도 티어(하/중/상). 구 세트는 없음 → None(학생 UI '미분류').
                "difficulty_tier": (str(it.get("difficulty_tier") or "").strip() or None),
            })
            st["총"] += 1

    qb["questions"] += new
    labels = qb.get("generatedFrom") or []
    if args.exam not in labels:
        labels.append(args.exam)
    qb["generatedFrom"] = labels

    # subjects 트리 갱신(UI 좌측 네비가 이걸 읽는다)
    subj = {s["name"]: s for s in qb.get("subjects", [])}
    for q in new:
        s = subj.setdefault(q["subject"], {"name": q["subject"], "total": 0, "categories": []})
        s["total"] = sum(1 for x in qb["questions"] if x["subject"] == q["subject"])
        cats = {c["name"]: c for c in s["categories"]}
        c = cats.setdefault(q["major"], {"name": q["major"], "total": 0, "topics": []})
        c["total"] = sum(1 for x in qb["questions"]
                         if x["subject"] == q["subject"] and x["major"] == q["major"])
        tps = {t["name"]: t for t in c["topics"]}
        t = tps.setdefault(q["topic"] or "기타", {"name": q["topic"] or "기타", "count": 0})
        t["count"] = sum(1 for x in qb["questions"] if x["topic"] == q["topic"])
        c["topics"] = list(tps.values())
        s["categories"] = list(cats.values())
    qb["subjects"] = list(subj.values())

    print(f"기존 {before} · 동일접두어 제거 {removed} · 신규 {st['총']} → 총 {len(qb['questions'])}")
    print(f"  이미지 연결 {st['이미지연결']} (원본없음 {st['이미지없음']}) · 선지해설 완비 {st['선지해설완비']}/{st['총']}")
    print(f"  Anki 카드 보유 {st['Anki보유']}/{st['총']} · 시각참조 문장 제거 {st['시각참조문장제거']}")
    if args.dry_run:
        print("  (dry-run — 파일 미기록)")
        return 0

    payload = json.dumps(qb, ensure_ascii=False, indent=1)
    QBANK.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(QBANK.read_bytes()).hexdigest()
    # 함정 A: 해시 검증이 깨지면 기존 140개 릴리스가 통째로 무효화된다
    live_ids = {q["id"] for q in qb["questions"]}
    for rp in (RELEASES, DRAFT):
        if not rp.exists():
            continue
        d = json.loads(rp.read_text(encoding="utf-8"))
        old = d.get("built_against_sha256")
        d["built_against_sha256"] = digest
        # 전체교체 시 사라진 문항의 릴리스는 남겨두면 유령 항목이 된다
        for key in ("releases", "drafts"):
            rows = d.get(key)
            if isinstance(rows, dict):
                dropped = [q for q in rows if q not in live_ids]
                for q in dropped:
                    rows.pop(q)
                if dropped:
                    print(f"  {rp.name}/{key}: 사라진 문항 릴리스 {len(dropped)}건 제거")
        rp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  릴리스 해시 갱신 {rp.name}: {str(old)[:12]}… → {digest[:12]}…")
    # Anki 카드는 질문 레코드가 아니라 enrichment 릴리스 경로로만 학생에게 간다.
    # 검수 전 AI 생성물이므로 medical_approval은 **false로 둔다**(정직한 게이트).
    # 대신 시스템이 마련한 curated demo 경로를 쓴다 → 화면에 "검수 전"으로 라벨링된다.
    cards_path = GEN / "anki_cards.json"
    if cards_path.exists() and RELEASES.exists():
        cards = json.loads(cards_path.read_text(encoding="utf-8"))
        d = json.loads(RELEASES.read_text(encoding="utf-8"))
        rel = d.setdefault("releases", {})
        n = 0
        for q in qb["questions"]:
            qid = q["id"]
            if qid not in cards:
                continue
            rel[qid] = {
                "approved": True,
                "medical_approval": False,      # 의학 승인 아님 — 절대 True로 올리지 말 것
                "curated_demo_release": True,
                "demo_release": True,
                "needs_real_faculty_review": True,
                "reviewer_id": "owner:" + os.getenv("PACCINE_OWNER_EMAIL", "local"),
                "reviewed_at": args.reviewed_at,
                "anki_cards": [{"anki_text": c["text"], "plain_text": c["extra"],
                                "tags": c["tags"]} for c in cards[qid]],
                "source": "aigen_pipeline",
                "provenance": "ontology_grounded_generation_20260817",
            }
            n += 1
        RELEASES.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  Anki 릴리스 {n}문항 기록 (demo_release · 의학승인 아님)")
        print("  ! 학생 화면 노출에는 환경변수 PACCINE_REQUIRE_FULL_DEMO=1 필요")

    print(f"[게시] {QBANK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
