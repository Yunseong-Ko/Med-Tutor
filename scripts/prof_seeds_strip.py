#!/usr/bin/env python3
"""검수 완료된 seeds_all_review → 원문 열 제거한 승인본 생성 (AI 입력 허용본).

사용: 검수 끝난 뒤  python3 scripts/prof_seeds_strip.py
입력: data_private/professor_items/seeds/seeds_all_review.xlsx (있으면) 또는 .csv
출력: seeds_approved.csv — 원문발췌/선지 열 제거, 사용(Y)만.  ← 이것만 AI가 읽음
"""
import csv
import sys
from pathlib import Path

SEEDS = Path("data_private/professor_items/seeds")
DROP = ["원문발췌_검수전용", "선지_검수전용"]


def load_rows():
    x = SEEDS / "seeds_all_review.xlsx"
    if x.exists():
        import openpyxl
        ws = openpyxl.load_workbook(x, read_only=True).active
        it = ws.iter_rows(values_only=True)
        header = [str(h or "") for h in next(it)]
        return [dict(zip(header, [("" if v is None else str(v)) for v in r])) for r in it]
    with open(SEEDS / "seeds_all_review.csv", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    rows = load_rows()
    kept, dropped_n = [], 0
    for r in rows:
        if str(r.get("사용(Y/N)", "Y")).strip().upper().startswith("N"):
            dropped_n += 1
            continue
        kept.append({k: v for k, v in r.items() if k not in DROP})
    out = SEEDS / "seeds_approved.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(kept[0].keys()))
        w.writeheader(); w.writerows(kept)
    n_ans = sum(1 for r in kept if str(r.get("정답번호(입력)", "")).strip())
    n_con = sum(1 for r in kept if str(r.get("질환개념(제안)", "")).strip() or str(r.get("정답개념(입력)", "")).strip())
    print(f"승인 시드 {len(kept)} (제외 {dropped_n}) · 정답 있음 {n_ans} · 개념 있음 {n_con}")
    print(f"[approved] {out}  ← 원문 열 제거 완료, AI 입력 허용본")
    return 0


if __name__ == "__main__":
    sys.exit(main())
