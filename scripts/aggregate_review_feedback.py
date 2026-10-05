#!/usr/bin/env python3
"""학생 검토표(엑셀) 회수분 → 문항별 집계 + 조치 우선순위.

입력: 학생들이 채워 보낸 `학생_NN_AI필기문항_검토.xlsx` 들이 있는 디렉터리
      (교수님 배포 양식: 4행 헤더, 5~35행 문항, B/C/D=1~5점, E=종합판정, F=의견)

집계 원칙:
  - 문항당 검토자 3명 → 평균만 보면 "2명 만족·1명 사용불가"를 놓친다.
    **최저점과 판정 불일치를 함께** 본다.
  - 조치 등급: 한 명이라도 '사용 불가' → 폐기검토 / '대폭 수정' 또는 최저 ≤2 → 수정필요
  - 검토자 간 불일치(점수 범위 ≥2)는 별도 표시 — 문항이 애매하다는 신호다.
출력: review/집계_문항별.xlsx (전체) + 콘솔 요약
"""
import argparse
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill

VERDICT_ORDER = ["수정없이 사용", "소폭 수정하여 사용", "대폭 수정 필요", "사용 불가"]
VERDICT_RANK = {v: i for i, v in enumerate(VERDICT_ORDER)}


def read_sheet(path: Path):
    """(문항번호, 점수3, 판정, 의견) 목록. 미기입 행은 건너뛴다."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    who = re.sub(r"[^0-9]", "", path.stem) or path.stem
    rows = []
    for r in ws.iter_rows(min_row=5, values_only=True):
        if not r or r[0] is None:
            continue
        try:
            no = int(r[0])
        except (TypeError, ValueError):
            continue
        scores = []
        for v in r[1:4]:
            try:
                scores.append(int(v))
            except (TypeError, ValueError):
                pass
        verdict = str(r[4] or "").strip()
        note = str(r[5] or "").strip()
        if not scores and not verdict and not note:
            continue          # 미기입
        rows.append((no, who, scores, verdict, note))
    return rows


def aggregate(by_item, out):
    """문항별 집계 워크북 저장. 구글폼 CSV 경로(aggregate_gform_csv.py)와 공유.

    by_item: {문항번호: [{who, scores, verdict, note}, ...]}
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "문항별 집계"
    header = ["문항", "응답자수", "의학적정확성", "명확성", "정답해설", "평균",
              "최저점", "점수범위", "판정(최악)", "판정 분포", "조치", "의견"]
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True)

    RED = PatternFill("solid", fgColor="F8D7DA")
    YEL = PatternFill("solid", fgColor="FFF3CD")
    counts = defaultdict(int)

    for no in sorted(by_item):
        rows = by_item[no]
        cols = [[], [], []]
        for r in rows:
            for i, v in enumerate(r["scores"][:3]):
                cols[i].append(v)
        allsc = [v for c in cols for v in c]
        worst = min(allsc) if allsc else None
        rng = (max(allsc) - min(allsc)) if allsc else 0
        verdicts = [r["verdict"] for r in rows if r["verdict"]]
        worst_v = max(verdicts, key=lambda v: VERDICT_RANK.get(v, -1)) if verdicts else ""
        dist = " / ".join(f"{v}×{verdicts.count(v)}" for v in VERDICT_ORDER if v in verdicts)

        if worst_v == "사용 불가":
            action = "폐기 검토"
        elif worst_v == "대폭 수정 필요" or (worst is not None and worst <= 2):
            action = "수정 필요"
        elif worst_v == "소폭 수정하여 사용" or rng >= 2:
            action = "경미 수정"
        else:
            action = "그대로 사용"
        counts[action] += 1

        notes = " | ".join(f"[{r['who']}] {r['note']}" for r in rows if r["note"])
        ws.append([no, len(rows),
                   round(st.mean(cols[0]), 2) if cols[0] else None,
                   round(st.mean(cols[1]), 2) if cols[1] else None,
                   round(st.mean(cols[2]), 2) if cols[2] else None,
                   round(st.mean(allsc), 2) if allsc else None,
                   worst, rng, worst_v, dist, action, notes])
        row = ws[ws.max_row]
        if action == "폐기 검토":
            for c in row:
                c.fill = RED
        elif action == "수정 필요":
            for c in row:
                c.fill = YEL

    ws.freeze_panes = "A2"
    for col, w in zip("ABCDEFGHIJKL", (7, 9, 13, 10, 10, 8, 8, 9, 16, 26, 11, 70)):
        ws.column_dimensions[col].width = w

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)

    print(f"응답 문항 {len(by_item)}/320")
    short = [n for n, v in by_item.items() if len(v) < 3]
    if short:
        print(f"  검토자 3명 미만 문항 {len(short)}개 (예: {sorted(short)[:8]})")
    print("  조치 분포:", dict(counts))
    print(f"[집계] {out}")
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="회수한 검토표 디렉터리")
    ap.add_argument("--out", default="data_private/professor_items/review/집계_문항별.xlsx")
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("*.xlsx"))
    if not files:
        print(f"! xlsx 없음: {args.dir}")
        return 1

    by_item = defaultdict(list)
    submitted = []
    for f in files:
        rows = read_sheet(f)
        if rows:
            submitted.append(f.name)
        for no, who, scores, verdict, note in rows:
            by_item[no].append({"who": who, "scores": scores, "verdict": verdict, "note": note})

    print(f"회수 {len(submitted)}/{len(files)}개 파일")
    aggregate(by_item, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
