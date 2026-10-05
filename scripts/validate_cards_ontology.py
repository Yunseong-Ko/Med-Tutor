#!/usr/bin/env python3
"""AnKing식 cloze 카드 ↔ 온톨로지(concept_registry) 검증·부착 파이프라인.

강의노트에서 생성한 cloze 카드가 우리 온톨로지에 **근거를 두고 있는지** 결정론적으로 검증한다.
LLM 미사용·환각 0 (의미적 사실검증은 별도 워크플로 verify_cards_ontology_wf 가 담당).

각 카드에 대해:
  1) card.concept / text / tags 를 registry 한글·영문 alias와 대조 → disease_concept_id 부여
  2) 매칭 개념의 Harrison 근거 + 타입드 엣지(감별/치료/진단/발현)를 card["ontology"] 로 부착
  3) 플래그: coverage_gap(레지스트리 밖 개념) · no_evidence(근거 없음) · num_unverified(고위험 수치 verify 누락)
  4) edge 용어가 카드 본문에 등장하면 corroborated 표시(정성 신호)

입력:  data_private/lecture_cards/cards_*.json  (allowlist _include_lids.json 존중)
출력:  각 카드에 ontology 블록 추가(--commit 시 in-place, 기본 dry-run)
       + data_private/lecture_cards/_ontology_validation_YYYYMMDD.json (리포트)
사용:  python3 scripts/validate_cards_ontology.py            # dry-run 요약
       python3 scripts/validate_cards_ontology.py --commit   # 카드에 부착 저장
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

REG = json.loads(Path("data_private/concept_registry.json").read_text(encoding="utf-8"))["concepts"]
DISEASE_NODES = {"disorder", "neoplasm", "disease", "syndrome", "infection"}

NUM_UNIT = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:mg|g|µg|ug|mcg|IU|단위|정|mL|L|/µL|/uL|/mm3|×10\d|x10\d|%|일|주|개월|시간|분|"
    r"cGy|Gy|mmHg|mEq|mmol|mIU|ng|pg|fL|년|회)", re.I)
VERIFY = re.compile(r"verify|확인필요|확인\s*요|⚠", re.I)
CLOZE = re.compile(r"\{\{c\d+::(.*?)\}\}", re.DOTALL)


def norm(s: str) -> str:
    # 공백·언더스코어·하이픈 제거 → 영문 slug(follicular_lymphoma)와 alias(follicular lymphoma) 정렬
    return re.sub(r"[\s_\-]+", "", str(s or "")).lower()


# ---- alias index (attach_hemeonc_ontology.py 와 동일 규약) ----
ALIAS_INDEX = []  # (norm_alias, cid, is_disease, len, is_ko)
for cid, c in REG.items():
    is_disease = (c.get("node_type") or "") in DISEASE_NODES
    for a in [cid.replace("_", " ")] + list(c.get("aliases") or []):
        na = norm(a)
        if len(na) < 2:
            continue
        is_ko = bool(re.search(r"[가-힣]", a))
        if not is_ko and len(na) < 4 and not (a.isupper() and len(a) >= 3):
            continue
        ALIAS_INDEX.append((na, cid, is_disease, len(na), is_ko))
ALIAS_INDEX.sort(key=lambda x: (x[2], x[3]), reverse=True)


def plain(text: str) -> str:
    return CLOZE.sub(lambda m: m.group(1), text or "")


def match_concept(card: dict):
    concept = card.get("concept") or ""
    tags = card.get("tags") or []
    body = plain(card.get("text") or "") + " " + (card.get("extra") or "")
    hay_concept = norm(concept)
    hay_tags = "|".join(norm(t) for t in tags)
    hay_body = norm(body)

    # 1) concept 필드가 개념 alias와 정확 일치(질환 우선)
    for na, cid, is_dis, ln, is_ko in ALIAS_INDEX:
        if is_dis and na == hay_concept:
            return cid, "concept_exact"
    # 2) concept 필드가 disease alias를 포함
    for na, cid, is_dis, ln, is_ko in ALIAS_INDEX:
        if not is_dis:
            continue
        if (is_ko and ln >= 3 or (not is_ko) and ln >= 4) and hay_concept and na in hay_concept:
            return cid, "concept_contains"
    # 3) tag가 disease alias와 일치
    for na, cid, is_dis, ln, is_ko in ALIAS_INDEX:
        if is_dis and hay_tags and na in hay_tags.split("|"):
            return cid, "tag_exact"
    # 4) 본문에 distinctive disease alias(ko>=4 / en>=5)
    for na, cid, is_dis, ln, is_ko in ALIAS_INDEX:
        if not is_dis:
            continue
        if (is_ko and ln >= 4 or (not is_ko) and ln >= 5) and na in hay_body:
            return cid, "text_alias"
    return None, None


def grounding_for(cid: str) -> dict:
    c = REG[cid]
    ev = c.get("evidence") or {}
    edges = c.get("edges") or {}
    def eids(rel):
        return [e.get("id") for e in (edges.get(rel) or []) if e.get("id")]
    ko = next((a for a in (c.get("aliases") or []) if re.search(r"[가-힣]", a)), cid.replace("_", " "))
    return {
        "disease_concept_id": cid,
        "label": ko,
        "node_type": c.get("node_type"),
        "harrison": ev.get("harrison"),
        "differentials": eids("differential_of"),
        "treated_with": eids("treated_with"),
        "diagnosed_by": eids("diagnosed_by"),
        "presents_with": eids("presents_with"),
        "grounding_source": "concept_registry_v602_deterministic",
        "needs_review": True,
    }


def corroborate(card: dict, g: dict) -> list:
    """엣지 id의 핵심 토큰이 카드 본문/보충에 등장하면 corroborated 표시(정성)."""
    hay = norm(plain(card.get("text") or "") + " " + (card.get("extra") or ""))
    hits = []
    for rel in ("treated_with", "diagnosed_by", "differentials", "presents_with"):
        for eid in g.get(rel) or []:
            for tok in re.split(r"[ ,/()]+", str(eid)):
                nt = norm(tok)
                if len(nt) >= 4 and nt in hay:
                    hits.append(f"{rel}:{tok}")
                    break
    return sorted(set(hits))


def load_allow(card_dir: Path):
    p = card_dir / "_include_lids.json"
    if p.exists():
        try:
            return set(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="카드 ↔ 온톨로지 검증·부착")
    ap.add_argument("--dir", default="data_private/lecture_cards")
    ap.add_argument("--commit", action="store_true", help="카드 JSON에 ontology 블록 저장(in-place)")
    ap.add_argument("--ignore-allowlist", action="store_true")
    args = ap.parse_args()

    card_dir = Path(args.dir)
    allow = None if args.ignore_allowlist else load_allow(card_dir)
    stamp = datetime.now().strftime("%Y%m%d")

    rep = {"generated_at": datetime.now().isoformat(timespec="seconds"), "dir": str(card_dir),
           "totals": {}, "by_method": {}, "by_system": {}, "top_concepts": {},
           "flags": {"coverage_gap": 0, "no_evidence": 0, "num_unverified": 0},
           "coverage_gap_samples": [], "lectures": []}
    tot = grounded = evid = corrob = 0

    for f in sorted(card_dir.glob("cards_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        lid = d.get("lecture_id")
        if allow is not None and lid not in allow:
            continue
        cards = d.get("cards") or []
        lg = le = lgap = 0
        for card in cards:
            tot += 1
            cid, method = match_concept(card)
            sysk = card.get("system") or "기타"
            rep["by_system"].setdefault(sysk, {"cards": 0, "grounded": 0})
            rep["by_system"][sysk]["cards"] += 1
            if cid:
                g = grounding_for(cid)
                g["match_method"] = method
                g["corroborated"] = corroborate(card, g)
                card["ontology"] = g
                grounded += 1
                lg += 1
                rep["by_system"][sysk]["grounded"] += 1
                rep["by_method"][method] = rep["by_method"].get(method, 0) + 1
                rep["top_concepts"][cid] = rep["top_concepts"].get(cid, 0) + 1
                if g["harrison"]:
                    evid += 1
                else:
                    rep["flags"]["no_evidence"] += 1
                    le += 1
                if g["corroborated"]:
                    corrob += 1
            else:
                card["ontology"] = None
                rep["flags"]["coverage_gap"] += 1
                lgap += 1
                if len(rep["coverage_gap_samples"]) < 30:
                    rep["coverage_gap_samples"].append(
                        {"lid": lid, "concept": card.get("concept"), "text": plain(card.get("text") or "")[:100]})
            # 고위험 수치 verify 누락
            if NUM_UNIT.search(card.get("text") or "") and not VERIFY.search(card.get("extra") or ""):
                rep["flags"]["num_unverified"] += 1
        rep["lectures"].append({"lecture_id": lid, "cards": len(cards),
                                "grounded": lg, "no_evidence": le, "coverage_gap": lgap})
        if args.commit:
            d["ontology_validated_at"] = rep["generated_at"]
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    rep["totals"] = {"cards": tot, "grounded": grounded, "grounded_pct": round(100 * grounded / max(1, tot), 1),
                     "with_evidence": evid, "corroborated": corrob,
                     "corroborated_pct": round(100 * corrob / max(1, grounded), 1) if grounded else 0}
    rep["top_concepts"] = dict(sorted(rep["top_concepts"].items(), key=lambda x: -x[1])[:20])

    out = card_dir / f"_ontology_validation_{stamp}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    t = rep["totals"]
    print("=" * 64)
    print("카드 ↔ 온톨로지 검증", "(COMMIT)" if args.commit else "(dry-run)")
    print("=" * 64)
    print(f"카드 {t['cards']} · 온톨로지 매칭 {t['grounded']} ({t['grounded_pct']}%)")
    print(f"  Harrison 근거부착 {t['with_evidence']} · 엣지 corroborated {t['corroborated']} ({t['corroborated_pct']}%)")
    print(f"플래그: coverage_gap {rep['flags']['coverage_gap']} · no_evidence {rep['flags']['no_evidence']} · num_unverified {rep['flags']['num_unverified']}")
    print("\n[계통별 커버리지]")
    for s, v in sorted(rep["by_system"].items(), key=lambda x: -x[1]["cards"]):
        pct = round(100 * v["grounded"] / max(1, v["cards"]))
        print(f"  {s:10s} {v['grounded']:4d}/{v['cards']:<4d} ({pct}%)")
    print("\n[매칭 방법]", rep["by_method"])
    print(f"\n[리포트] {out}")
    if not args.commit:
        print("\n(dry-run — 부착 계산만. 저장하려면 --commit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
