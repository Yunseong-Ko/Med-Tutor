#!/usr/bin/env python3
"""UWorld/USMLE PDF → item_anatomy '구조 통계'만 추출 (저작권 안전).

원문 문항 텍스트는 저장/재현하지 않는다. 각 문항의 lead-in 유형·비네트 길이·
분과노출 여부·추론단계 heuristic만 집계해 '좋은 문항의 형식 통계'를 만든다.
출력: data_private/usmle_structure/lead_in_stats.json (집계값만)
"""

import re
import sys
import json
import collections
from pathlib import Path

import fitz

OUT = Path("data_private/usmle_structure/lead_in_stats.json")

# lead-in 유형 분류 규칙 (질문 문장 패턴)
LEAD_IN = [
    ("next_best_step", r"most appropriate (next step|management|treatment|therapy|pharmacotherapy)|best next step|next best step|most appropriate initial"),
    ("mechanism_cause", r"most likely cause|underlying (cause|mechanism|etiology)|responsible for|contributing factor|best explains|mechanism of|pathophysiolog|due to which"),
    ("diagnosis", r"most likely diagnosis|most likely to be|which of the following (conditions|disorders|diagnoses)|best explains .*presentation"),
    ("interpretation_finding", r"most likely (finding|to show|reveal)|would (most likely )?show|expected (finding|result)|most likely associated|consistent with"),
    ("prognosis_risk", r"most likely to (prevent|develop|occur)|greatest risk|prognosis|most likely outcome|risk of|likely to reduce|complication"),
    ("best_test", r"most appropriate (test|investigation|study|imaging|diagnostic)|most likely to confirm|best (initial|confirmatory) test|which .*test"),
]
SPECIALTY = re.compile(r"\b(cardiolog|neurolog|psychiatr|nephrolog|endocrinolog|dermatolog|rheumatolog|oncolog|pulmonolog|gastroenterolog|ophthalmolog)", re.I)


def classify_lead(q):
    ql = q.lower()
    for name, pat in LEAD_IN:
        if re.search(pat, ql):
            return name
    return "other"


BOUNDARY = re.compile(r"Item[\s_]+\d+\s+of\s+\d+|Question Id:\s*\d+")
PAGE_CAP = int(__import__("os").environ.get("PAGE_CAP", "500"))  # 파일당 페이지 상한(샘플)


def iter_items(pdf):
    """페이지를 스트리밍하며 문항 경계로 blob을 잘라 yield. 전 문서를 메모리에 올리지 않는다."""
    doc = fitz.open(pdf)
    npages = min(doc.page_count, PAGE_CAP)
    buf = []
    for i in range(npages):
        txt = doc[i].get_text()
        if not txt:
            continue
        parts = BOUNDARY.split(txt)
        if len(parts) == 1:
            buf.append(txt)
            continue
        # 첫 조각은 직전 buf에 이어 붙여 문항 하나로 마감
        buf.append(parts[0])
        yield "".join(buf)
        for mid in parts[1:-1]:
            yield mid
        buf = [parts[-1]]
    if buf:
        yield "".join(buf)
    doc.close()


def process(pdf):
    stats = collections.Counter()
    hops = collections.Counter()
    spec_named = 0
    vig_lens = []
    n = 0
    for blob in iter_items(pdf):
        # lead-in = 'Which of the following ... ?' 문장(첫 등장)
        m = re.search(r"(Which of the following[^?]{0,220}\?)", blob, re.S)
        if not m:
            m = re.search(r"([A-Z][^?]{20,220}\?)\s*$", blob[:2000], re.S)
        if not m:
            continue
        lead = re.sub(r"\s+", " ", m.group(1))
        # 비네트 = lead-in 앞부분(길이만 측정, 텍스트 미저장)
        vig = blob[:m.start()]
        vlen = len(re.sub(r"\s+", " ", vig).strip())
        if vlen < 120 or vlen > 4000:
            continue
        n += 1
        stats[classify_lead(lead)] += 1
        vig_lens.append(vlen)
        # 추론단계 heuristic: 검사수치/영상 언급 + 다단계 처치 lead → hops↑
        h = 1
        if re.search(r"laborator|shows|reveals|mmHg|mg/dL|/µL|biopsy|imaging|CT|MRI", vig):
            h = 2
        if classify_lead(lead) in ("next_best_step", "prognosis_risk", "mechanism_cause"):
            h = max(h, 2)
        hops[h] += 1
        if SPECIALTY.search(vig):
            spec_named += 1
    return {"items": n, "lead_in": dict(stats), "hops": dict(hops),
            "specialty_named": spec_named,
            "vignette_len_avg": round(sum(vig_lens) / len(vig_lens)) if vig_lens else 0}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        base = Path("/Users/goyunseong/Documents/USMLE/Uworld/Uworld step 1")
        # OCR 표기 유무 무관하게 UW 2024 계열 전부 (다 하고 보고)
        args = sorted(str(p) for p in base.glob("*.pdf")
                      if re.search(r"UW[_ ]2024", p.name))
    print(f"대상 {len(args)}개 PDF · 파일당 최대 {PAGE_CAP}p 샘플", flush=True)
    per = {}
    agg = {"items": 0, "lead_in": collections.Counter(), "hops": collections.Counter(),
           "specialty_named": 0, "vlen_sum": 0}
    for idx, pdf in enumerate(args, 1):
        subj = re.sub(r".*UW[_ ]2024[_ -]+|[_ ]+\d.*|OCR.*|\.pdf", "", Path(pdf).name).strip(" _-")
        print(f"[{idx}/{len(args)}] 처리중: {subj[:40]} …", flush=True)
        try:
            r = process(pdf)
        except Exception as e:
            print(f"    건너뜀({type(e).__name__}): {e}", flush=True)
            continue
        per[subj or Path(pdf).stem[:24]] = r
        agg["items"] += r["items"]
        for k, v in r["lead_in"].items():
            agg["lead_in"][k] += v
        for k, v in r["hops"].items():
            agg["hops"][k] += v
        agg["specialty_named"] += r["specialty_named"]
        agg["vlen_sum"] += r["vignette_len_avg"] * r["items"]
        print(f"{subj[:34]:34s} n={r['items']:3d} lead-in={r['lead_in']} spec_named={r['specialty_named']}")
    tot = agg["items"] or 1
    print("\n=== 집계 ===")
    print("총 문항(구조):", agg["items"])
    print("lead-in 유형 %:", {k: f"{100*v/tot:.0f}%" for k, v in agg["lead_in"].most_common()})
    print("추론단계 %:", {k: f"{100*v/tot:.0f}%" for k, v in sorted(agg["hops"].items())})
    print(f"분과명 노출 문항: {agg['specialty_named']} ({100*agg['specialty_named']/tot:.0f}%) — 낮을수록 undifferentiated")
    print(f"비네트 평균 길이: {round(agg['vlen_sum']/tot)}자")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"per_subject": per,
                               "aggregate": {"items": agg["items"],
                                             "lead_in": dict(agg["lead_in"]),
                                             "hops": dict(agg["hops"]),
                                             "specialty_named": agg["specialty_named"]}},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n저장(집계만):", OUT)


if __name__ == "__main__":
    raise SystemExit(main())
