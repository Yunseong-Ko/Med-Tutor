#!/usr/bin/env python3
"""verify-cards-ontology 워크플로 결과를 카드 JSON에 반영(writeback).

입력(--results): [{"lecture_id","total","flagged":[{"index","verdict","dimension","issue","fix"}]}, ...]
동작: 각 lecture의 data_private/lecture_cards/cards_<lid>.json 을 열어
  - flagged 카드 cards[index]["verification"] = {status,dimension,issue,fix, verified_at}
  - 나머지 카드 = {"status":"ok", verified_at}
출력: in-place 갱신 + 요약 리포트(_verification_applied_YYYYMMDD.json)
익스포터가 verification.status ∈ {error,review} 를 읽어 '검토플래그' 태그·배지를 붙인다.
"""

import argparse
import json
import unicodedata
from datetime import datetime
from pathlib import Path

CARD_DIR = Path("data_private/lecture_cards")


def find_card_file(lid: str):
    lid_n = unicodedata.normalize("NFC", lid)
    for cand in (CARD_DIR / f"cards_{lid}.json", CARD_DIR / f"cards_{lid_n}.json"):
        if cand.exists():
            return cand
    # fallback: content match
    for f in CARD_DIR.glob("cards_*.json"):
        try:
            if unicodedata.normalize("NFC", json.loads(f.read_text(encoding="utf-8")).get("lecture_id") or "") == lid_n:
                return f
        except Exception:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="워크플로 per-lecture 결과 JSON")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    if isinstance(results, dict) and "per" in results:
        results = results["per"]
    stamp = datetime.now().strftime("%Y%m%d")
    now = datetime.now().isoformat(timespec="seconds")

    summary = {"generated_at": now, "lectures": 0, "cards_marked": 0,
               "errors": 0, "reviews": 0, "by_dimension": {}, "missing_files": [], "detail": []}

    for r in results:
        lid = r.get("lecture_id")
        flagged = {int(f["index"]): f for f in (r.get("flagged") or []) if "index" in f}
        cf = find_card_file(lid)
        if not cf:
            summary["missing_files"].append(lid)
            continue
        d = json.loads(cf.read_text(encoding="utf-8"))
        cards = d.get("cards") or []
        marked = 0
        for i, c in enumerate(cards):
            if i in flagged:
                f = flagged[i]
                verdict = f.get("verdict", "review")
                c["verification"] = {"status": verdict, "dimension": f.get("dimension"),
                                     "issue": f.get("issue"), "fix": f.get("fix"), "verified_at": now}
                marked += 1
                summary["cards_marked"] += 1
                if verdict == "error":
                    summary["errors"] += 1
                else:
                    summary["reviews"] += 1
                dim = f.get("dimension") or "기타"
                summary["by_dimension"][dim] = summary["by_dimension"].get(dim, 0) + 1
            else:
                c["verification"] = {"status": "ok", "verified_at": now}
        d["verification_applied_at"] = now
        if not args.dry_run:
            cf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["lectures"] += 1
        summary["detail"].append({"lecture_id": lid, "flagged": marked, "total": len(cards)})

    if not args.dry_run:
        (CARD_DIR / f"_verification_applied_{stamp}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"강의 {summary['lectures']} · 플래그 카드 {summary['cards_marked']} "
          f"(오류의심 {summary['errors']} · 검토 {summary['reviews']})")
    print("축별:", summary["by_dimension"])
    if summary["missing_files"]:
        print("파일 못찾음:", summary["missing_files"])
    if args.dry_run:
        print("(dry-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
