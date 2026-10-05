#!/usr/bin/env python3
"""v2 수정 결과(review/v2_results/*.result.json) → 세트 적용 + 재게이트 + 수정 보고서.

안전핀:
  - explanation은 원본의 60% 미만으로 축소되면 해당 필드만 거부(로그)
  - choices 변경 시 "1"~"5" 키 dict가 아니면 거부
  - answer 변경은 answer_changed=true 행만 허용, 보고서에 별도 표기
  - needs_professor는 내용 무변경 + professor_review_required 플래그만 부착
  - 적용 전 백업은 _backup_pre_v2_20260905에 이미 존재
적용 후: 전 320문항 하드룰 재계산 → 이전(3문항 실패)과 비교 보고.
"""
import json
import sys
from collections import Counter
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
RES = Path("data_private/professor_items/review/v2_results")
REPORT = Path("data_private/professor_items/review/v2_revision_report.md")

sys.path.insert(0, "scripts")


def main() -> int:
    rows = []
    for f in sorted(RES.glob("batch_*.result.json")):
        rows += json.loads(f.read_text(encoding="utf-8"))
    by_qid = {r["qid"]: r for r in rows}
    print(f"결과 행 {len(rows)} · 고유 qid {len(by_qid)}")

    sets = {k: json.loads((GEN / f"set_{k}.json").read_text(encoding="utf-8")) for k in range(1, 5)}
    st = Counter()
    report = {0: [], 1: [], 2: [], 3: [], 4: [], 5: []}
    answer_changes, rejected = [], []

    # 우선순위 조회용
    prio = {}
    for bf in sorted(Path("data_private/professor_items/review/v2_batches").glob("batch_*.json")):
        for b in json.loads(bf.read_text(encoding="utf-8")):
            prio[b["qid"]] = b["priority"]

    for k in range(1, 5):
        for it in sets[k]:
            qid = f"AIGEN_{k}_{it['no']:03d}"
            r = by_qid.get(qid)
            if not r:
                continue
            p = prio.get(qid, 5)
            if r["action"] == "needs_professor":
                it["professor_review_required"] = True
                it["professor_note"] = r.get("professor_note", "")
                st["교수판단"] += 1
                report[p].append(f"- **{qid}** (교수 판단 필요): {r.get('professor_note','')[:200]}")
                continue
            if r["action"] != "revised":
                st["유지"] += 1
                continue
            ch = r.get("changes") or {}
            applied = []
            if "explanation" in ch:
                new, old = str(ch["explanation"]), str(it.get("explanation") or "")
                if len(new) >= len(old) * 0.6:
                    it["explanation"] = new; applied.append("해설")
                else:
                    rejected.append(f"{qid}: 해설 축소 거부 ({len(new)}/{len(old)}자)")
            if "choices" in ch:
                c = ch["choices"]
                if isinstance(c, dict) and set(c.keys()) == {"1", "2", "3", "4", "5"}:
                    it["choices"] = {k2: str(v) for k2, v in c.items()}; applied.append("선지")
                else:
                    rejected.append(f"{qid}: 선지 구조 위반 거부")
            if "stem" in ch:
                it["stem"] = str(ch["stem"]); applied.append("문두")
            if "answer" in ch:
                if r.get("answer_changed") and str(ch["answer"]) in {"1", "2", "3", "4", "5"}:
                    old_a = str(it.get("answer"))
                    it["answer"] = str(ch["answer"]); applied.append("정답")
                    answer_changes.append(f"- **{qid}**: 정답 {old_a}→{ch['answer']} · {r.get('evidence_note','')[:200]}")
                else:
                    rejected.append(f"{qid}: 정답 변경 플래그 없이 시도 — 거부")
            if "choice_explanations" in ch and isinstance(ch["choice_explanations"], dict):
                ce = it.get("choice_explanations") or {}
                for n, row in ch["choice_explanations"].items():
                    if n in ce and isinstance(row, dict):
                        ce[n].update({kk: str(vv) for kk, vv in row.items() if kk in ("why_correct", "why_attractive")})
                applied.append("선지해설")
            if applied:
                it["v2_revision"] = {"date": "2026-09-05", "fields": applied,
                                     "log": r.get("change_log", []), "evidence": r.get("evidence_note", "")}
                st["수정"] += 1
                report[p].append(f"- **{qid}** [{'/'.join(applied)}]: " + " · ".join(r.get("change_log", [])[:3]))
            else:
                st["수정시도_전거부"] += 1

    for k in range(1, 5):
        (GEN / f"set_{k}.json").write_text(json.dumps(sets[k], ensure_ascii=False, indent=1), encoding="utf-8")
    print(dict(st))
    if rejected:
        print("안전핀 거부:", *rejected[:10], sep="\n  ")

    # 재게이트 (결정론 하드룰 — manual_review_rules 제외 기준은 기존 회귀 스크립트와 동일)
    from item_quality_check import validate_nbme_hard_rules
    fails = []
    for k in range(1, 5):
        for it in sets[k]:
            v = validate_nbme_hard_rules(it)
            manual = set(v.get("manual_review_rules") or [])
            hard = [r_ for r_ in (v.get("failed_rules") or []) if r_ not in manual]
            if hard:
                fails.append((f"AIGEN_{k}_{it['no']:03d}", hard))
    print(f"재게이트 하드룰 실패: {len(fails)}문항 (수정 전 3)")
    for q, h in fails[:10]:
        print(" ", q, h[:3])

    # 보고서
    P_NAMES = {0: "정답 무효 확정건", 1: "폐기 검토", 2: "정답 이의", 3: "의학 오류", 4: "이미지 불일치", 5: "형식·해설"}
    lines = ["# v2 수정 보고서 (2026-09-05)", "",
             f"- 적용: 수정 {st['수정']} · 유지 {st['유지']} · 교수 판단 필요 {st['교수판단']} · 안전핀 거부 {len(rejected)}",
             f"- 정답 변경 {len(answer_changes)}건 (아래 별도 목록) · 재게이트 하드룰 실패 {len(fails)}문항", ""]
    if answer_changes:
        lines += ["## ⚠ 정답 변경 목록 (교수 최우선 확인)", *answer_changes, ""]
    for p in range(6):
        if report[p]:
            lines += [f"## {P_NAMES[p]} ({len(report[p])}건)", *report[p], ""]
    if rejected:
        lines += ["## 안전핀 거부 내역", *[f"- {x}" for x in rejected], ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[보고서] {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
