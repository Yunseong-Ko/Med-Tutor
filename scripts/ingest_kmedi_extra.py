"""Ingest the two sibling 중재원 datasets that complement 조정분석 현황:
  - 3049717  의료분쟁 상담분석 현황   (CP949)  : 질문 → 답변 → 참고 판례(precedent citations)
  - 15025792 의료분쟁 감정분석 현황   (UTF-8)  : 양측 쟁점 + 감정결과 + 의료사고예방팁

Emits normalized JSONL per dataset + a deduped precedent-citation list (the legal
grounding layer that can later be verified via korean-law-mcp).
All outputs under data_private/medlegal/processed/ (gitignored). KOGL source.
"""
from __future__ import annotations

import csv, json, re, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMP = ROOT / "data_private/medlegal/imports"
OUT = ROOT / "data_private/medlegal/processed"

CONSULT_MAP = [
    ("과목별 순번", "dept_seq"), ("순번", "serial_no"), ("제목", "title"),
    ("진료과목", "clinical_dept"), ("질문-제목", "q_title"), ("질문-내용", "q_body"),
    ("답변-제목", "a_title"), ("답변-내용", "a_body"),
    ("참고1-제목", "ref1_title"), ("참고1-내용", "ref1_body"),
    ("참고2-제목", "ref2_title"), ("참고2-내용", "ref2_body"),
    ("참고3-제목", "ref3_title"), ("참고-3내용", "ref3_body"),
]
GAMJEONG_MAP = [
    ("순번", "serial_no"), ("구분", "category"), ("진료과목", "clinical_dept"),
    ("제목", "title"), ("키워드", "keywords"), ("사건개요", "case_summary"),
    ("치료과정", "treatment_course"), ("분쟁쟁점(환자측)", "issue_patient"),
    ("분쟁쟁점(병원측)", "issue_hospital"), ("감정결과", "expert_opinion"),
    ("조정결과", "mediation_result"), ("의료사고예방팁", "prevention_tip"),
]
# precedent citation like: 서울지법 1993. 9. 22. 선고 92가합49237 판결
PRECEDENT_PAT = re.compile(r"(법원|지법|고법|대법).{0,40}?(선고).{0,30}?(판결|결정)")


def read_rows(path: Path):
    for enc in ("utf-8-sig", "cp949"):
        try:
            return list(csv.reader(path.open(encoding=enc, newline=""))), enc
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"decode failed: {path}")


def normalize(path: Path, colmap):
    rows, enc = read_rows(path)
    keys = [k for _, k in colmap]
    recs = []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        rec = {key: (row[i].strip() if i < len(row) else "") for i, (_, key) in enumerate(colmap)}
        dept = rec.get("clinical_dept", "")
        rec["is_ortho"], rec["is_plastic"] = "정형" in dept, "성형" in dept
        recs.append(rec)
    return recs, enc


def write_jsonl(recs, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    # consultations
    consult, enc1 = normalize(IMP / "kmedi_consultation_analysis_3049717.csv", CONSULT_MAP)
    write_jsonl(consult, OUT / "kmedi_consultation.jsonl")

    # precedents from the 참고 title fields
    precedents = []
    for r in consult:
        for t in (r["ref1_title"], r["ref2_title"], r["ref3_title"]):
            t = t.strip()
            if t and PRECEDENT_PAT.search(t):
                precedents.append(t)
    uniq = sorted(set(precedents))
    (OUT / "kmedi_precedents.json").write_text(
        json.dumps(uniq, ensure_ascii=False, indent=2), encoding="utf-8")

    # 감정 analyses
    gam, enc2 = normalize(IMP / "kmedi_gamjeong_analysis_15025792.csv", GAMJEONG_MAP)
    write_jsonl(gam, OUT / "kmedi_gamjeong.jsonl")
    has_tip = sum(1 for r in gam if r["prevention_tip"] and "해당사항없음" not in r["prevention_tip"])
    cat = collections.Counter(r["category"] for r in gam)

    print(f"[상담] enc={enc1} n={len(consult)}  precedent citations: {len(precedents)} ({len(uniq)} unique)")
    print(f"[감정] enc={enc2} n={len(gam)}  구분={dict(cat)}  예방팁 보유={has_tip}")
    print("sample precedents:")
    for p in uniq[:6]:
        print("   -", p[:70])
    print(f"wrote -> {OUT}/kmedi_consultation.jsonl, kmedi_gamjeong.jsonl, kmedi_precedents.json")


if __name__ == "__main__":
    main()
