#!/usr/bin/env python3
"""4세트(80문항×4)를 **파이프라인 통과 문항만으로** 처음부터 재조립.

배경: 기존 set_*.json은 이미지 문항 30개(파이프라인)와 텍스트 문항 50개(파이프라인
미적용, 게이트·온톨로지 근거 없음)가 섞여 있었다. 여기서는 미적용분을 전량 폐기하고
게이트를 통과한 문항만으로 새로 짠다.

구성(세트당 80):
  - 이미지 문항 30 (img_items_selected.json, set_hint 배정 존중)
  - 텍스트 문항 50 (text_items.gated.json 중 하드룰 통과분, 분과·축 균형)
번호·관리번호는 새로 부여한다.
출력: generated/set_{1..4}.json (덮어쓰기)
"""
import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
DST_IMG = Path("data_private/professor_items/images")
SRC_IMG = Path("data_private/professor_items/pma_labels_v2/images")


def load_dept_by_concept() -> dict:
    """개념ID → 분과. 이미지 문항 subject가 진단명일 때 되돌리는 사전."""
    out = {}
    reg = Path("data_private/concept_registry.json")
    supp = Path("data_private/curriculum/specialty_supplement.json")
    try:
        for cid, c in json.loads(reg.read_text(encoding="utf-8"))["concepts"].items():
            sp = str(c.get("specialty") or "").split("/")[0].strip()
            if sp:
                out[cid] = sp
    except Exception:
        pass
    try:
        for cid, sp in json.loads(supp.read_text(encoding="utf-8")).items():
            out.setdefault(cid, str(sp).split("/")[0].strip())
    except Exception:
        pass
    return out


DEPT_BY_CONCEPT = load_dept_by_concept()


def passes(it) -> bool:
    q = it.get("item_quality") or {}
    return not q.get("hard_rule_failures") and not q.get("flaw_count")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default="img_items_selected.json")
    ap.add_argument("--texts", default="text_items.gated.json")
    ap.add_argument("--per-set", type=int, default=80)
    ap.add_argument("--img-per-set", type=int, default=30)
    args = ap.parse_args()
    DST_IMG.mkdir(parents=True, exist_ok=True)

    imgs = json.loads((GEN / args.images).read_text(encoding="utf-8"))
    texts = json.loads((GEN / args.texts).read_text(encoding="utf-8"))

    clean = [t for t in texts if passes(t)]
    partial = [t for t in texts if not passes(t)]
    n_text = (args.per_set - args.img_per_set) * 4
    print(f"텍스트 풀 {len(texts)} · 완전클린 {len(clean)} · 필요 {n_text}")
    pool = clean + sorted(partial, key=lambda t: (
        len((t.get("item_quality") or {}).get("hard_rule_failures") or []),
        (t.get("item_quality") or {}).get("flaw_count", 0)))
    if len(pool) < n_text:
        print(f"  ! 텍스트 부족 {len(pool)}/{n_text} — 세트당 문항 수를 줄여 조립한다")

    # 축 균형 선발: 진단·검사·치료를 고르게 뽑되, **클린 문항이 남아 있는 한
    # 결함 문항을 먼저 끌어오지 않는다**. (축 쿼터를 무조건 채우면 특정 축의 클린 재고가
    # 부족할 때 결함 문항이 섞여 들어온다 — 실측 312/320 사례.)
    source = clean if len(clean) >= n_text else pool
    per_axis = n_text // 3
    by_axis = defaultdict(list)
    for t in source:
        by_axis[t.get("axis", "")].append(t)
    picked, seen = [], set()
    for ax in ("진단", "검사", "치료"):
        for t in by_axis.get(ax, [])[:per_axis]:
            picked.append(t)
            seen.add(id(t))
    for t in source:                    # 잔여분은 같은 소스에서 채운다
        if len(picked) >= n_text:
            break
        if id(t) not in seen:
            picked.append(t)
            seen.add(id(t))
    for t in pool:                      # 그래도 모자랄 때만 결함 문항 허용
        if len(picked) >= n_text:
            break
        if id(t) not in seen:
            picked.append(t)
            seen.add(id(t))
    print(f"  축 선발: {dict(Counter(t.get('axis') for t in picked))}")

    # 분과 라운드로빈으로 세트에 분배(한 세트에 같은 분과가 몰리지 않게)
    by_dept = defaultdict(list)
    for t in picked:
        by_dept[t.get("subject", "")].append(t)
    tsets = {k: [] for k in range(4)}
    i = 0
    for dept in sorted(by_dept, key=lambda d: -len(by_dept[d])):
        for t in by_dept[dept]:
            for _ in range(4):
                k = i % 4
                i += 1
                if len(tsets[k]) < (args.per_set - args.img_per_set):
                    tsets[k].append(t)
                    break

    isets = {k: [it for it in imgs if it.get("set_hint") == k + 1] for k in range(4)}

    for k in range(4):
        rows = []
        # 이미지 문항과 텍스트 문항을 번갈아 배치해 한쪽에 몰리지 않게
        im, tx = isets[k][:args.img_per_set], tsets[k]
        step = max(1, len(tx) // max(1, len(im))) if im else 1
        merged, ii = [], 0
        for n, t in enumerate(tx):
            merged.append(t)
            if ii < len(im) and (n + 1) % step == 0:
                merged.append(im[ii]); ii += 1
        merged += im[ii:]

        for n, it in enumerate(merged, 1):
            f = it.get("image", "")
            if f and (SRC_IMG / f).exists() and not (DST_IMG / f).exists():
                shutil.copy(SRC_IMG / f, DST_IMG / f)
            # subject는 **분과**여야 한다(학생 UI 좌측 트리의 1레벨).
            # 이미지 문항은 라벨에서 온 subject가 진단명인 경우가 있어, 분과 사전으로 되돌린다.
            dept = it.get("department") or ""
            subj = it.get("subject") or ""
            # 이미지 문항은 subject/department가 비어 있고 개념ID만 있다 → 사전으로 분과 복원
            if not subj or not str(subj).endswith(("과", "내과", "외과", "의학")):
                subj = dept or DEPT_BY_CONCEPT.get(
                    str(it.get("disease_concept_id") or ""), "") or "임상종합"
            rows.append({
                "no": n, "mgmt_no": f"M{k+1}-{n:02d}",
                "subject": subj or dept or "임상종합",
                "concept": it.get("concept") or it.get("dx", ""),
                "axis": it.get("axis", ""),
                "stem": it["stem"], "lab_box": it.get("lab_box", ""),
                "image": f,
                "choices": it["choices"], "answer": str(it["answer"]),
                "explanation": it.get("explanation", ""),
                "evidence": it.get("evidence", ""),
                "modality": it.get("modality", ""),
                "disease_concept_id": it.get("disease_concept_id", ""),
                "harrison_sources": it.get("harrison_sources") or [],
                "choice_explanations": it.get("choice_explanations") or {},
                "reasoning_hops": it.get("reasoning_hops"),
                "cognitive_level": it.get("cognitive_level", ""),
                "item_quality": it.get("item_quality") or {},
                # 게이트 rule 16/17/18이 읽는 모델 주장 — 누락되면 재게이트 시 전량 탈락한다
                "self_check": it.get("self_check") or {},
                "cognitive_model": it.get("cognitive_model") or {},
                "source": it.get("source", ""),
                "needs_review": True,
            })
        (GEN / f"set_{k+1}.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        nimg = sum(1 for r in rows if r["image"])
        npass = sum(1 for r in rows if not (r["item_quality"].get("hard_rule_failures")))
        print(f"세트{k+1}: {len(rows)}문항 (이미지 {nimg} · 텍스트 {len(rows)-nimg}) "
              f"· 하드룰통과 {npass} · 축 {dict(Counter(r['axis'] for r in rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
