#!/usr/bin/env python3
"""생성 문항 ↔ 원본 기출 텍스트 겹침 전수검사 (보안 게이트, 로컬 전용).

⚠️ 이 스크립트는 로컬에서만 실행된다. 원본 원문은 stdout에 출력하지 않는다
   (겹친 구간만 최소 표시 — 겹침 자체가 이미 생성문항에 존재하는 텍스트임).

검사:
  1) 연속 어절 n-gram 겹침: 생성 문항(stem+선지)과 원본 전체 텍스트 사이
     연속 N어절(기본 6) 이상 일치 → FLAG(재작성 대상)
  2) 정답 위치 분포(①~⑤ 균형), 선지 길이 편향(정답=최장 비율)

입력:
  --originals  원본 텍스트 파일/디렉터리 (txt — 로컬 파서가 추출해 둔 것)
  --generated  생성 문항 JSON [{no, stem, choices{}, answer}, ...] 또는 {items:[...]}
  --ngram      연속 어절 임계 (기본 6)
출력: 콘솔 요약 + <generated>.security_report.json
종료코드: FLAG 있으면 1 (CI 게이트 사용 가능)
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


BOILER = {
    "혈압","맥박","호흡","체온","mmhg","회","분","참고치","정상",
    "g","dl","mg","mm","l","iu","u","kg","cm","백혈구","혈색소","혈소판",
    "다음과","같다","같은","결과는","결과","검사","소견은","소견",
    "병원에","왔다","내원하였다","위해","가장","적절한","것은","진단은",
}


def norm_tokens(text: str):
    t = re.sub(r"\s+", " ", str(text or ""))
    t = re.sub(r"[\u2460-\u246E()\[\]{}.,;:?!'\"\u201c\u201d\u2018\u2019\u00b7%/\\-]", " ", t)
    out = []
    for w in t.split():
        if not w or re.fullmatch(r"\d+([.,]\d+)?", w):
            continue
        if re.fullmatch(r"\d+(회|세|일|주|개월|년|시간)", w):
            continue
        if w.lower() in BOILER:
            continue
        out.append(w)
    return out


def ngrams(tokens, n):
    return {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def load_originals(path: Path) -> list:
    files = []
    if path.is_dir():
        files = sorted(p for p in path.rglob("*.txt"))
    elif path.exists():
        files = [path]
    corpus = []
    for f in files:
        corpus.append((f.name, norm_tokens(f.read_text(encoding="utf-8", errors="ignore"))))
    return corpus


def max_overlap(gen_tokens, orig_tokens, start_n):
    """생성 토큰과 원본 토큰 사이 최장 연속 일치 어절 수(임계 이상만 탐색)."""
    if len(gen_tokens) < start_n or len(orig_tokens) < start_n:
        return 0, ""
    best, best_s = 0, ""
    orig_sets = {}
    n = start_n
    g = ngrams(gen_tokens, n)
    o = ngrams(orig_tokens, n)
    hits = g & o
    if not hits:
        return 0, ""
    # escalate n until no hit → last hit length is max
    while hits:
        best = n
        best_s = next(iter(hits))
        n += 1
        if len(gen_tokens) < n or len(orig_tokens) < n:
            break
        g = ngrams(gen_tokens, n)
        o = ngrams(orig_tokens, n)
        hits = g & o
    return best, best_s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--originals", required=True)
    ap.add_argument("--generated", required=True)
    ap.add_argument("--ngram", type=int, default=6)
    args = ap.parse_args()

    corpus = load_originals(Path(args.originals))
    if not corpus:
        print("[!] 원본 텍스트 없음 — 로컬 파서로 originals/*.txt 를 먼저 추출하세요.")
        return 2
    gen = json.loads(Path(args.generated).read_text(encoding="utf-8"))
    items = gen.get("items") if isinstance(gen, dict) else gen

    flags, rows = [], []
    ans_pos = Counter()
    longest_is_answer = 0
    n_with_choices = 0
    for it in items:
        text = str(it.get("stem", "")) + " " + " ".join(str(v) for v in (it.get("choices") or {}).values())
        gt = norm_tokens(text)
        worst, worst_s, worst_src = 0, "", ""
        for name, ot in corpus:
            ov, s = max_overlap(gt, ot, args.ngram)
            if ov > worst:
                worst, worst_s, worst_src = ov, s, name
        row = {"no": it.get("no"), "max_overlap_tokens": worst, "source": worst_src if worst else None,
               "snippet": worst_s if worst else None, "flag": worst >= args.ngram}
        rows.append(row)
        if row["flag"]:
            flags.append(row)
        a = str(it.get("answer", ""))
        if a:
            ans_pos[a] += 1
        ch = it.get("choices") or {}
        if ch and a in ch:
            n_with_choices += 1
            if max(ch, key=lambda k: len(str(ch[k]))) == a:
                longest_is_answer += 1

    report = {"n_items": len(items), "ngram_threshold": args.ngram,
              "flags": len(flags), "flagged": flags,
              "answer_position": dict(sorted(ans_pos.items())),
              "answer_is_longest_pct": round(100 * longest_is_answer / max(1, n_with_choices), 1)}
    out = Path(args.generated).with_suffix(".security_report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 56)
    print("문항 보안 스캔 (원본 겹침 전수검사)")
    print("=" * 56)
    print(f"생성 문항 {len(items)} · 원본 파일 {len(corpus)} · 임계 연속 {args.ngram}어절")
    print(f"FLAG(임계 이상 겹침): {len(flags)}")
    for f in flags[:10]:
        print(f"  · 문항 {f['no']} — {f['max_overlap_tokens']}어절 겹침 ← {f['source']}")
    print(f"정답 위치 분포: {dict(sorted(ans_pos.items()))}")
    print(f"정답=최장선지 비율: {report['answer_is_longest_pct']}% (40% 초과 시 편향 의심)")
    print(f"[report] {out}")
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main())
