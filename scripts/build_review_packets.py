#!/usr/bin/env python3
"""4학년 학생 31명 검수용 배포 묶음 생성 (문항당 3명 교차검수).

설계: 320문항 × 3중검수 = 960 검수건. 31명 × 31문항 = 961 ≈ 960.
배정 규칙(결정론):
  - 학생 i는 문항 (i + k*31) mod 320 … 방식이 아니라, **3라운드 라틴방격**을 쓴다.
    라운드 r에서 학생 i가 맡는 문항 블록을 offset r로 회전 → 같은 문항을 서로 다른
    3명이 보되, 두 학생이 같은 문항 집합을 통째로 공유하지 않는다.
  - 배정표는 재현 가능(난수 없음)해야 재배포·감사가 된다.
출력:
  review/assignment.csv          — 문항↔검수자 매핑(감사용)
  review/packets/<학생>.docx     — 개인별 31문항 검토지(해설 포함 + 의견란)
  review/item_feedback_sheet.csv — 문항별 의견시트 템플릿
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
OUT = Path("data_private/professor_items/review")
CIRCLED = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}


def load_items() -> list:
    items = []
    for k in range(1, 5):
        p = GEN / f"set_{k}.json"
        if not p.exists():
            continue
        for it in json.loads(p.read_text(encoding="utf-8")):
            it["set"] = k
            it["uid"] = f"S{k}-{it['no']:02d}"
            items.append(it)
    return items


def assign(items: list, reviewers: list):
    """문항당 3명 · 1인당 문항 수를 균등하게.

    (문항 i, 라운드 r)을 검수자 (i + r*step) mod N 에 배정한다.
    step을 N과 서로소로 잡으면 세 라운드의 검수자가 서로 달라 3명 중복이 없고,
    각 검수자가 받는 문항 수도 자동으로 균등해진다(앞선 blockwise 배정은
    마지막 사람에게 3문항만 몰리는 쏠림이 있었다).
    """
    n_rev = len(reviewers)
    step = max(1, n_rev // 3)
    while step > 1 and math.gcd(step, n_rev) != 1:
        step += 1
    if math.gcd(step, n_rev) != 1:
        step = 1
    plan = defaultdict(list)
    for i, item in enumerate(items):
        for r in range(3):
            who = reviewers[(i + r * step) % n_rev]
            if any(x["uid"] == item["uid"] for x in plan[who]):
                who = reviewers[(i + r * step + 1) % n_rev]
            plan[who].append(item)
    for who in reviewers:
        plan.setdefault(who, [])
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviewers", type=int, default=31)
    ap.add_argument("--names", help="검수자 이름 목록 파일(줄바꿈 구분). 없으면 검수자01~NN")
    args = ap.parse_args()

    items = load_items()
    if not items:
        print("! set_*.json 없음")
        return 1
    if args.names:
        names = [l.split(",", 1)[0].strip()
                 for l in Path(args.names).read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
    else:
        names = [f"r{i+1:02d}" for i in range(args.reviewers)]
    plan = assign(items, names)
    per = max((len(v) for v in plan.values()), default=0)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "packets").mkdir(exist_ok=True)

    with (OUT / "assignment.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["문항ID", "세트", "번호", "분과", "축", "검수자"])
        for who, rows in plan.items():
            for it in rows:
                w.writerow([it["uid"], it["set"], it["no"], it.get("subject", ""),
                            it.get("axis", ""), who])

    cover = defaultdict(int)
    for rows in plan.values():
        for it in rows:
            cover[it["uid"]] += 1
    print(f"문항 {len(items)} · 검수자 {len(names)}명 · 1인당 {per}문항")
    print(f"  검수 배정 총 {sum(len(v) for v in plan.values())}건 "
          f"· 문항당 검수자 수 분포 {dict(sorted({v: list(cover.values()).count(v) for v in set(cover.values())}.items()))}")
    print(f"[배정표] {OUT/'assignment.csv'}")

    with (OUT / "item_feedback_sheet.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["문항ID", "검수자", "정답 동의(Y/N)", "해설 정확(1-5)", "난이도(1-5)",
                    "임상적 타당성(1-5)", "선지 적절성(1-5)", "용어 오류", "수정 제안", "기타 의견"])
        for who, rows in sorted(plan.items()):
            for it in rows:
                w.writerow([it["uid"], who, "", "", "", "", "", "", "", ""])
    print(f"[의견시트] {OUT/'item_feedback_sheet.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
