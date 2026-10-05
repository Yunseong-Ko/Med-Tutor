#!/usr/bin/env python3
"""종합설문(구글폼 응답 xlsx) → 논문용 비식별 데이터셋 + 기술통계.

입력: 구글폼 '응답' xlsx (타임스탬프·학번·이름·q1~q9·개방형)
출력: data_private/professor_items/exports/paper/
  - survey_deid.csv        R01.. 식별자만, 학번·이름·타임스탬프 제거
  - survey_table4.md       9문항 평균·SD·중앙값·분포 (논문 Table 4)
  - open_comments_deid.txt 개방형 응답 (응답자 ID만)
제외 규칙: 학번이 20으로 시작하지 않는 행(테스트 제출)은 사전 제외.
"""
import argparse
import csv
import re
import statistics
from collections import Counter
from pathlib import Path

import openpyxl

OUT = Path("data_private/professor_items/exports/paper")
AREAS = ["안면타당도", "내용 포괄성", "임상적 관련성", "임상추론 평가 적절성",
         "난이도 적절성", "문항 완성도", "정답·해설의 교육적 유용성",
         "평가도구 활용 가능성", "학습도구 활용 가능성"]


def likert(v):
    m = re.match(r"\s*([1-5])", str(v))
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    rows = list(openpyxl.load_workbook(a.xlsx, data_only=True).worksheets[0].iter_rows(values_only=True))
    data = [r for r in rows[1:] if r and r[0]]
    kept, excluded = [], []
    for r in data:
        (kept if str(r[1] or "").startswith("20") else excluded).append(r)

    with (out / "survey_deid.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["respondent_id"] + [f"q{i+1}" for i in range(9)] + ["open_comment"])
        for i, r in enumerate(kept, 1):
            w.writerow([f"R{i:02d}"] + [likert(r[3 + j]) for j in range(9)] + [str(r[12] or "").strip()])

    lines = [f"# 종합설문 기술통계 (n={len(kept)}, 테스트 제출 {len(excluded)}건 제외)", "",
             "| # | 평가 항목 | n | 평균 | SD | 중앙값 | 1 | 2 | 3 | 4 | 5 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for j, name in enumerate(AREAS):
        vs = [v for v in (likert(r[3 + j]) for r in kept) if v]
        d = Counter(vs)
        lines.append(f"| {j+1} | {name} | {len(vs)} | {statistics.mean(vs):.2f} | "
                     f"{statistics.stdev(vs):.2f} | {statistics.median(vs):.0f} | "
                     + " | ".join(str(d.get(k, 0)) for k in range(1, 6)) + " |")
    allv = [v for r in kept for v in (likert(r[3 + j]) for j in range(9)) if v]
    lines += ["", f"전체 평정 평균 {statistics.mean(allv):.2f} (평정 {len(allv)}건)"]
    (out / "survey_table4.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with (out / "open_comments_deid.txt").open("w", encoding="utf-8") as f:
        for i, r in enumerate(kept, 1):
            t = str(r[12] or "").strip()
            if t and t not in {".", "-"}:
                f.write(f"[R{i:02d}] {t}\n\n")
    print(f"n={len(kept)} 제외={len(excluded)} → {out}")


if __name__ == "__main__":
    main()
