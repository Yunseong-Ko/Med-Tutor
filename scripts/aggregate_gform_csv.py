#!/usr/bin/env python3
"""구글폼 응답 CSV → 기존 집계 파이프라인 연결.

입력: 응답 스프레드시트에서 탭별로 내려받은 CSV
  --review-csv : 폼1(문항별 검토) 응답 — 타임스탬프·검토자·문항번호·점수3·종합판정·의견
  --survey-csv : 폼2(종합 설문) 응답 — 타임스탬프·검토자·q1~q9·종합의견
  --assign     : (선택) 교수님 배정표 xlsx — 배정 외 문항 응답을 경고로 표시

같은 (검토자, 문항) 중복 제출은 마지막 타임스탬프만 채택(수정 재제출 허용).
집계 로직·출력 형식은 xlsx 경로와 동일:
  aggregate_review_feedback.aggregate() → 집계_문항별.xlsx
  aggregate_survey.write_outputs()      → survey_summary.md + survey_responses.csv
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aggregate_review_feedback import aggregate  # noqa: E402
from aggregate_survey import write_outputs  # noqa: E402


def col_index(header, *keywords):
    """헤더에서 키워드가 모두 포함된 첫 열 번호(구글이 제목을 살짝 바꿔도 견딤)."""
    for i, h in enumerate(header):
        if all(k in h for k in keywords):
            return i
    return None


def who_digits(v):
    return (re.sub(r"[^0-9]", "", str(v)) or str(v)).zfill(2)


def load_review(path):
    rows = list(csv.reader(Path(path).open(encoding="utf-8-sig")))
    hd = rows[0]
    ix = {
        "who": col_index(hd, "검토자"),
        "no": col_index(hd, "문항", "번호"),
        "s1": col_index(hd, "의학적"),
        "s2": col_index(hd, "명확성"),
        "s3": col_index(hd, "정답", "해설"),
        "verdict": col_index(hd, "종합판정"),
        "note": col_index(hd, "의견"),
    }
    missing = [k for k, v in ix.items() if v is None]
    if missing:
        raise SystemExit(f"! 검토 CSV 헤더에서 열을 못 찾음: {missing} / 헤더={hd}")

    latest = {}  # (who, no) → row  (파일이 타임스탬프 순이므로 뒤가 최신)
    for r in rows[1:]:
        if not any(x.strip() for x in r):
            continue
        try:
            no = int(float(r[ix["no"]]))
        except (TypeError, ValueError):
            continue
        latest[(who_digits(r[ix["who"]]), no)] = r

    by_item = defaultdict(list)
    for (who, no), r in sorted(latest.items(), key=lambda kv: kv[0][1]):
        scores = []
        for k in ("s1", "s2", "s3"):
            try:
                scores.append(int(float(r[ix[k]])))
            except (TypeError, ValueError):
                pass
        by_item[no].append({
            "who": who, "scores": scores,
            "verdict": str(r[ix["verdict"]] or "").strip(),
            "note": str(r[ix["note"]] or "").strip(),
        })
    dup = len(rows) - 1 - len(latest)
    return by_item, dup


def load_survey(path):
    rows = list(csv.reader(Path(path).open(encoding="utf-8-sig")))
    hd = rows[0]
    who_i = col_index(hd, "검토자")
    q_ix = []
    for q in range(1, 10):
        i = col_index(hd, f"{q}. ")
        if i is None:
            raise SystemExit(f"! 설문 CSV에서 {q}번 문항 열을 못 찾음 / 헤더={hd}")
        q_ix.append(i)
    open_i = col_index(hd, "종합 의견") or col_index(hd, "10.")

    latest = {}
    for r in rows[1:]:
        if not any(x.strip() for x in r):
            continue
        latest[who_digits(r[who_i])] = r
    out_rows, comments = [], []
    for who, r in sorted(latest.items()):
        rec = {"respondent": who}
        for q, i in enumerate(q_ix, 1):
            try:
                v = int(float(r[i]))
                rec[f"q{q}"] = v if 1 <= v <= 5 else None
            except (TypeError, ValueError):
                rec[f"q{q}"] = None
        out_rows.append(rec)
        txt = str(r[open_i] or "").strip() if open_i is not None else ""
        if txt:
            comments.append((who, txt))
    return out_rows, comments


def check_assignment(by_item, assign_path):
    import openpyxl
    ws = openpyxl.load_workbook(assign_path)["학생별 배정"]
    assigned = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0] or not row[2]:
            continue
        who = who_digits(row[0])
        assigned[who] = {int(x) for x in str(row[2]).split(",") if str(x).strip()}
    bad = []
    for no, entries in by_item.items():
        for e in entries:
            if e["who"] in assigned and no not in assigned[e["who"]]:
                bad.append((e["who"], no))
    if bad:
        print(f"  ! 배정 외 문항 응답 {len(bad)}건 (번호 오기입 의심): {sorted(bad)[:10]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review-csv", help="폼1 문항별 검토 응답 CSV")
    ap.add_argument("--survey-csv", help="폼2 종합 설문 응답 CSV")
    ap.add_argument("--assign", help="전체_문항검토_배정표.xlsx (선택, 오기입 검출)")
    ap.add_argument("--out", default="data_private/professor_items/review/집계_문항별.xlsx")
    args = ap.parse_args()
    if not args.review_csv and not args.survey_csv:
        ap.error("--review-csv 또는 --survey-csv 중 하나는 필요")

    if args.review_csv:
        by_item, dup = load_review(args.review_csv)
        n_resp = sum(len(v) for v in by_item.values())
        print(f"문항별 검토 응답 {n_resp}건 (중복 재제출 정리 {dup}건)")
        if args.assign:
            check_assignment(by_item, args.assign)
        aggregate(by_item, args.out)

    if args.survey_csv:
        rows, comments = load_survey(args.survey_csv)
        write_outputs(rows, comments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
