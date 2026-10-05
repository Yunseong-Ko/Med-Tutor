#!/usr/bin/env python3
"""검증된 이미지 문항을 4세트에 재삽입 (기존 텍스트형 문항 일부와 교체).

원칙:
- 세트당 이미지 문항 목표 개수만큼 삽입(기본 15) — 같은 label_key(=같은 이미지)는 세트 간 분산.
- 교체 대상: 기존 세트에서 image_pending 있던 문항(원래 이미지형이었던 것) 우선, 부족하면 뒤쪽 텍스트 문항.
- 이미지 파일은 pma_labels/images → professor_items/images 로 복사(익스포터가 참조).
입력: generated/set_{1..4}.json + generated/img_items_all.json (해설 재작성본 반영 후 실행 권장)
출력: 동일 파일 갱신 + 통계 stdout
"""
import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

GEN = Path("data_private/professor_items/generated")
DST_IMG = Path("data_private/professor_items/images")


def finish(assign: dict, args, src_img: Path) -> int:
    """세트별 배정을 실제 set_*.json에 삽입하고 이미지를 복사한다."""
    total_img = 0
    for k in range(4):
        p = GEN / f"set_{k+1}.json"
        items = json.loads(p.read_text(encoding="utf-8"))
        newimgs = assign[k][:args.per_set]
        # 교체 대상 우선순위:
        #  1) 이전 런에서 삽입된 이미지 문항 — 사람 검증 전 자동라벨 기반이라 이미지-진단이
        #     어긋나 있다(실측 60개 중 52개 불일치). 반드시 최우선으로 덮어쓴다.
        #  2) image_pending(원래 이미지형이었던 자리)
        #  3) 뒤쪽 텍스트 문항
        cand = [i for i, it in enumerate(items)
                if str(it.get("source", "")).startswith("pma_image_item")]
        cand += [i for i, it in enumerate(items) if it.get("image_pending") and i not in cand]
        cand += [i for i in range(len(items) - 1, -1, -1) if i not in cand]
        for n, img_it in enumerate(newimgs):
            if n >= len(cand):
                break
            old = items[cand[n]]
            f = img_it["image"]
            if (src_img / f).exists() and not (DST_IMG / f).exists():
                shutil.copy(src_img / f, DST_IMG / f)
            items[cand[n]] = {
                "no": old["no"], "mgmt_no": old["mgmt_no"],
                "subject": img_it.get("dx", old.get("subject", "")),
                "concept": img_it.get("dx", ""), "axis": img_it.get("axis", ""),
                "stem": img_it["stem"], "lab_box": "", "image": f,
                "choices": img_it["choices"], "answer": str(img_it["answer"]),
                "explanation": img_it.get("explanation", ""),
                "evidence": img_it.get("evidence", ""),
                "modality": img_it.get("modality", ""),
                "disease_concept_id": img_it.get("disease_concept_id", ""),
                "harrison_sources": img_it.get("harrison_sources") or [],
                "choice_explanations": img_it.get("choice_explanations") or {},
                "source": "pma_image_item", "needs_review": True,
            }
            total_img += 1
        p.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        n_img = sum(1 for it in items if it.get("image"))
        print(f"세트{k+1}: 이미지 문항 {n_img}개 (신규 삽입 {min(len(newimgs), len(cand))})")
    print(f"총 삽입 {total_img} · 이미지 파일 {len(list(DST_IMG.glob('*')))}개 보유")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-set", type=int, default=15)
    ap.add_argument("--pool", default="img_items_all.json",
                    help="generated/ 아래 문항 풀 파일명")
    ap.add_argument("--src-img", default="data_private/professor_items/pma_labels/images",
                    help="라벨 이미지 원본 디렉터리")
    args = ap.parse_args()
    SRC_IMG = Path(args.src_img)
    DST_IMG.mkdir(parents=True, exist_ok=True)

    pool = json.loads((GEN / args.pool).read_text(encoding="utf-8"))
    # label_key별로 묶어 세트 간 분산 배치
    # 선별기(select_best_image_items)가 set_hint로 세트를 이미 배정했으면 그대로 따른다.
    # 그 배정은 축 쿼터·진단 중복 제한을 이미 만족하므로 여기서 다시 섞으면 균형이 깨진다.
    if all(isinstance(it.get("set_hint"), int) for it in pool) and pool:
        assign = {k: [it for it in pool if it["set_hint"] == k + 1] for k in range(4)}
        return finish(assign, args, SRC_IMG)

    by_label = defaultdict(list)
    for it in pool:
        by_label[it["label_key"]].append(it)
    labels = sorted(by_label)

    assign = {k: [] for k in range(4)}
    li = 0
    while any(len(v) < args.per_set for v in assign.values()) and li < len(labels) * 4:
        lab = labels[li % len(labels)]
        variants = by_label[lab]
        for j, it in enumerate(variants):
            k = (li + j) % 4
            if len(assign[k]) < args.per_set and it not in assign[k]:
                assign[k].append(it)
        li += 1

    return finish(assign, args, SRC_IMG)


if __name__ == "__main__":
    raise SystemExit(main())
