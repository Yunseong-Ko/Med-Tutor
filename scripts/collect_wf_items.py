#!/usr/bin/env python3
"""워크플로 journal.jsonl에서 생성 문항을 모아 풀 JSON으로 저장 + 1차 자동검수.

워크플로 반환값이 아니라 저널을 읽는 이유: 배치가 부분 실패해도 성공분을 온전히 건진다.

검수(로컬, 결정론):
  - 스키마 필수 필드 / 선지 5개 / 정답 1~5
  - 이미지 파일 실존
  - 라벨(진단·검사종류) 일치 — 모델이 concept을 임의로 바꿨는지
  - 문두-라벨 modality 하드 대조 — modality_lexicon 동의어 사전 기반(설문 T2:
    "초음파라 해놓고 CT/내시경" 방지). 불일치는 치명적 → 폐기
  - 이미지 소견 서술 금지 위반(문두에 좌/우·소견 단어)
  - 정답 최장선지 편향, 정답 위치 분포
  - 문두 중복(동일 문두 재사용)
출력: generated/<out>.json + 콘솔 통계
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from modality_lexicon import match_modality, normalize_modality

GEN = Path("data_private/professor_items/generated")
IMGDIR = Path("data_private/professor_items/pma_labels_v2/images")
LABELS = Path("data_private/professor_items/pma_labels_v2/labels_manual.json")

# 문두가 이미지 소견을 글로 말해버리면 이미지가 결정타가 아니게 된다.
FINDING_WORDS = re.compile(
    r"우측\s*폐|좌측\s*폐|양측\s*폐야|ST\s*분절\s*(상승|하강)|ST\s*(상승|하강)|"
    r"벌집\s*모양|honeycomb|경화\s*소견|음영\s*증가|종괴가\s*보이|"
    r"결절이\s*보이|침윤이\s*보이|확장되어\s*있|협착\s*소견|"
    r"P\s*파가\s*(없|소실)|QRS가\s*넓|불규칙한\s*R-?R"
)
# A형 규격: [vignette] + "…은 다음과 같다." (이미지 지시문) + lead-in 질문("…은?")으로 끝난다.
IMG_SENTENCE = re.compile(r"다음과\s*같다\s*[.。]")
LEADIN_TAIL = re.compile(r"[은는것]\s*(무엇)?[은인]?\s*\?\s*$|[은는]\?\s*$|\?\s*$")
# 문두 중간에 박힌 질문 문장(…은? / …것은?)을 찾아 끝으로 옮기기 위한 패턴
MID_QUESTION = re.compile(r"([가-힣A-Za-z0-9 ,·()%/~\-]{4,60}\?)\s*")
AXIS_LEADIN = {"진단": "가장 가능성 있는 진단은?",
               "검사": "진단을 위하여 다음에 시행할 검사는?",
               "치료": "가장 적절한 치료는?"}


def repair_leadin(stem: str, axis: str):
    """lead-in 질문 누락/위치 오류를 결정론적으로 수리. (수리 여부, 새 문두) 반환."""
    s = stem.rstrip()
    if LEADIN_TAIL.search(s):
        return False, stem
    m = list(MID_QUESTION.finditer(s))
    if m:                       # 중간에 질문이 있음 → 끝으로 이동
        q = m[-1].group(1).strip()
        s2 = (s[:m[-1].start()] + s[m[-1].end():]).strip()
        s2 = re.sub(r"\s+", " ", s2).rstrip()
        if not s2.endswith((".", "。")):
            s2 += "."
        return True, f"{s2} {q}"
    return True, f"{s} {AXIS_LEADIN.get(axis, '가장 적절한 것은?')}"


def load_items(wf_dir: Path):
    items, batches = [], 0
    jp = wf_dir / "journal.jsonl"
    for line in jp.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        r = d.get("result")
        if isinstance(r, dict) and isinstance(r.get("items"), list):
            batches += 1
            items += r["items"]
    return items, batches


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf-dir", required=True)
    ap.add_argument("--out", default="img_items_v3.json")
    args = ap.parse_args()

    items, batches = load_items(Path(args.wf_dir))
    labels = {r["image"]: r for r in json.loads(LABELS.read_text(encoding="utf-8"))}
    # 같은 (dx, modality)의 다른 이미지들 — 대표 이미지로 만든 문항에 재배분할 후보
    by_dx = defaultdict(list)
    for r in labels.values():
        by_dx[(r["dx"], r["modality"])].append(r["image"])

    st, keep, bad = Counter(), [], []
    seen_stem = set()
    for it in items:
        st["raw"] += 1
        img = it.get("image", "")
        prob = []
        ch = it.get("choices") or {}
        if sorted(ch) != ["1", "2", "3", "4", "5"] or any(not str(ch[k]).strip() for k in ch):
            prob.append("선지불완전")
        if not isinstance(it.get("answer"), int) or not 1 <= it["answer"] <= 5:
            prob.append("정답범위")
        if img not in labels:
            prob.append("라벨없는이미지")
        elif not (IMGDIR / img).exists():
            prob.append("이미지파일없음")
        stem = str(it.get("stem", "")).strip()
        fixed, stem = repair_leadin(stem, str(it.get("axis", "")))
        if fixed:
            it["stem"] = stem
            st["leadin수리"] += 1
        if len(stem) < 30:
            prob.append("문두짧음")
        if FINDING_WORDS.search(stem):
            prob.append("문두에소견서술")
        if not IMG_SENTENCE.search(stem):
            prob.append("이미지지시문없음")
        if not LEADIN_TAIL.search(stem):
            prob.append("leadin질문없음")
        # 문두 검사종류 vs 라벨 modality — 동의어 사전 기반 하드 대조.
        # 문두에 언급이 없으면 통과(과잉 탈락 방지). 과거력 언급("3년 전 CT…")은
        # 집합에 같이 잡혀 통과되므로, 라벨이 집합에 **없을 때만** 탈락시킨다.
        # 라벨 modality가 미상/기타/needs_fix면 대조 불가 → 건너뜀(하위호환).
        L0 = labels.get(img) or {}
        lab_mod = "" if L0.get("needs_fix") else normalize_modality(str(L0.get("modality", "")))
        if lab_mod and lab_mod != "기타":
            said = match_modality(stem)
            if said and lab_mod not in said:
                prob.append("modality불일치")
        nk = re.sub(r"\s+", "", stem)
        if nk in seen_stem:
            prob.append("문두중복")
        seen_stem.add(nk)
        if len(str(it.get("explanation", ""))) < 80:
            prob.append("해설부실")
        if prob:
            st["flagged"] += 1
            bad.append({"image": img, "axis": it.get("axis"), "why": prob, "stem": stem[:60]})
            for p in prob:
                st[f"why:{p}"] += 1
            if {"선지불완전", "정답범위", "라벨없는이미지", "이미지파일없음",
                "modality불일치"} & set(prob):
                continue        # 치명적 → 폐기
        L = labels.get(img, {})
        it["label_key"] = it.get("label_key") or L.get("key", "")
        it["dx"] = L.get("dx", it.get("concept", ""))
        it["modality"] = L.get("modality", it.get("modality", ""))
        it["alt_images"] = [x for x in by_dx.get((it["dx"], it["modality"]), []) if x != img]
        it["quality_flags"] = prob
        keep.append(it)
        st["kept"] += 1

    # 정답 편향 통계
    ansdist = Counter(it["answer"] for it in keep)
    longest = sum(1 for it in keep
                  if max(it["choices"], key=lambda k: len(it["choices"][k])) == str(it["answer"]))
    axes = Counter(it.get("axis") for it in keep)
    kinds = Counter(it.get("kind") for it in keep)

    (GEN / args.out).write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"배치 {batches} · 문항 {st['raw']} → 채택 {st['kept']} (경고 {st['flagged']} · lead-in 수리 {st['leadin수리']})")
    print("  경고 사유:", {k[4:]: v for k, v in sorted(st.items()) if k.startswith("why:")})
    print(f"  축: {dict(axes)} · 유형: {dict(kinds)}")
    print(f"  정답 분포: {dict(sorted(ansdist.items()))} · 정답=최장선지 "
          f"{longest}/{len(keep)} ({longest*100//max(1,len(keep))}%)")
    print(f"  고유 이미지 {len({it['image'] for it in keep})} · 고유 진단 {len({it['dx'] for it in keep})}")
    if bad:
        print("  경고 샘플:")
        for b in bad[:12]:
            print(f"    - {b['image']} {b['axis']} {b['why']} | {b['stem']}")
    print(f"[출력] {GEN/args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
