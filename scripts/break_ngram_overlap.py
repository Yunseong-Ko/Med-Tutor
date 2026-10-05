#!/usr/bin/env python3
"""보안 스캐너가 FLAG한 문항의 겹침 구간을 로컬 재표현으로 끊는다.

배경: 겹침은 대개 vignette 상투구("여자가 전부터 대변에 피가 섞여 나와서")다.
      의미는 같지만 표기가 다른 동의 표현으로 바꾸면 연속 n-gram이 끊긴다.
      **로컬 결정론 치환만 사용한다** — 원문을 외부로 보내지 않는다(프로토콜 §5.5).

사용: python3 scripts/break_ngram_overlap.py --pool img_items_v4e.gated.json \
        --originals data_private/professor_items/originals_text \
                    data_private/professor_items/originals_text_pma
반복 실행해도 멱등. 치환 후 재검사해 FLAG 0이 될 때까지 최대 3회 시도.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from item_security_scan import load_originals, ngrams, norm_tokens  # noqa: E402

GEN = Path("data_private/professor_items/generated")

# 의미 보존 동의 치환. 앞쪽이 우선 적용되며, 한 문항당 첫 매칭 1건만 바꾼다.
SUBS = [
    (r"대변에\s*피가\s*섞여\s*나와서", "대변에 혈액이 섞여 나오는 증상으로"),
    (r"대변에\s*피가\s*섞여\s*나와", "혈변이 있어"),
    (r"피가\s*섞여\s*나와서", "혈액이 섞여 나오는 증상으로"),
    (r"(\d+)\s*일\s*전부터", r"\1일 동안"),
    (r"(\d+)\s*주\s*전부터", r"\1주 동안"),
    (r"(\d+)\s*개월\s*전부터", r"\1개월 동안"),
    (r"(\d+)\s*년\s*전부터", r"\1년 동안"),
    (r"전부터", "이전부터 지속되는"),
    (r"숨이\s*차서\s*병원에\s*왔다", "호흡곤란으로 내원하였다"),
    (r"열이\s*나서\s*병원에\s*왔다", "발열로 내원하였다"),
    (r"배가\s*아파서\s*병원에\s*왔다", "복통으로 내원하였다"),
    (r"가슴이\s*아파서\s*병원에\s*왔다", "흉통으로 내원하였다"),
    (r"병원에\s*왔다", "내원하였다"),
    (r"내원하였다", "병원에 왔다"),
    # 신체진찰 상투구 — 소견은 유지하고 어순·표기만 바꾼다
    (r"([가-힣]+)에\s*가벼운\s*압통이\s*있으나\s*반동압통은\s*없다",
     r"\1 부위에 경한 압통이 확인되며 반동압통은 관찰되지 않는다"),
    (r"압통이\s*있으나\s*반동압통은\s*없다", "압통이 확인되며 반동압통은 관찰되지 않는다"),
    (r"압통과\s*반동압통이\s*있다", "압통 및 반동압통이 확인된다"),
    (r"장음은\s*정상이다", "장음은 정상 범위이다"),
    (r"호흡음은\s*정상이다", "호흡음은 정상 범위이다"),
    (r"심음은\s*정상이다", "심음은 정상 범위이다"),
    (r"의식은\s*명료하다", "의식 수준은 명료하다"),
    # 과거력 상투구 — 사실은 유지하고 어순만 바꾼다
    (r"입원하여\s*항생제\s*치료를\s*받고", "입원해 항생제를 투여받은 뒤"),
    (r"항생제\s*치료를\s*받고", "항생제를 투여받은 뒤"),
    (r"입원하여\s*치료를\s*받고", "입원해 치료받은 뒤"),
    (r"치료를\s*받은\s*적이\s*있다", "치료받은 병력이 있다"),
    (r"진단받고\s*치료\s*중이다", "진단 후 치료를 지속하고 있다"),
    (r"복용\s*중이다", "복용하고 있다"),
]


def item_text(it) -> str:
    return " ".join([str(it.get("stem", ""))] + [str(v) for v in (it.get("choices") or {}).values()])


def flagged_indices(items, corpus_ngrams, n):
    out = []
    for i, it in enumerate(items):
        hits = ngrams(norm_tokens(item_text(it)), n) & corpus_ngrams
        if hits:
            out.append((i, sorted(hits)[0]))
    return out


def rewrite(stem: str, hit: str, n: int) -> tuple[bool, str]:
    """겹친 n-gram(hit)을 **실제로 제거하는** 치환만 채택한다.

    단순히 '첫 매칭 규칙'을 쓰면 겹침과 무관한 곳을 바꾸거나
    (병원에 왔다 ↔ 내원하였다처럼) 서로 되돌리는 진동에 빠진다.
    """
    for pat, rep in SUBS:
        new = re.sub(pat, rep, stem, count=1)
        if new == stem:
            continue
        new = re.sub(r"\s+", " ", new).strip()
        if hit not in ngrams(norm_tokens(new), n):
            return True, new
    return False, stem


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--originals", required=True, nargs="+")
    ap.add_argument("--ngram", type=int, default=6)
    args = ap.parse_args()

    path = GEN / args.pool
    items = json.loads(path.read_text(encoding="utf-8"))

    corpus_ngrams = set()
    for src in args.originals:
        for _, text in load_originals(Path(src)):
            corpus_ngrams |= ngrams(norm_tokens(text), args.ngram)
    print(f"원본 n-gram {len(corpus_ngrams):,}개 (n={args.ngram})")

    total = 0
    for attempt in range(1, 4):
        flags = flagged_indices(items, corpus_ngrams, args.ngram)
        if not flags:
            print(f"  시도 {attempt}: FLAG 0 — 종료")
            break
        print(f"  시도 {attempt}: FLAG {len(flags)}건")
        changed = 0
        for i, hit in flags:
            ok, new = rewrite(str(items[i].get("stem", "")), hit, args.ngram)
            if ok:
                items[i]["stem"] = new
                items[i]["ngram_rewritten"] = True
                changed += 1
        total += changed
        print(f"    재표현 {changed}건")
        if not changed:
            print("    ! 치환 규칙 없음 — 남은 겹침은 수동 확인 필요")
            for i, hit in flags:
                print(f"      idx={i} 겹침='{hit}'")
            break

    left = flagged_indices(items, corpus_ngrams, args.ngram)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"총 재표현 {total}건 · 잔여 FLAG {len(left)} → {path}")
    return 1 if left else 0


if __name__ == "__main__":
    raise SystemExit(main())
