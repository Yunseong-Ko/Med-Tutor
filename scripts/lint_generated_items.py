#!/usr/bin/env python3
"""재실행 가능한 생성문항 결정론 린터 — 저장된 생성 산출물의 item-writing 결함을 측정.

기존 scripts/item_quality_check.py 의 scan_item(항목단위 결함)을 재사용하고,
여기에 배치단위 검사(정답 위치 편중·근사중복)를 추가한다. 모델 호출 없음, 결정론적.

용법:
  python3 scripts/lint_generated_items.py                    # data_private/lecture_questions/q_*.json 기본
  python3 scripts/lint_generated_items.py <files...> [--json] [--report out.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from item_quality_check import NEG as IQ_NEG  # noqa: E402
from item_quality_check import normalize_choices, scan_item  # noqa: E402

# 항목단위 결함 중 '테스트와이즈에게 정답 단서를 주는' 구조 결함(하드).
STRUCTURAL_HARD = {
    "negative_stem",
    "longest_is_key",
    "shortest_is_key",
    "most_components_is_key",
    "urgency_adverb_only_in_key",
    "clang_cue_stem_option",
    "duplicate_choices",
    "all_or_none_of_above",
    "absolute_term_in_option",
    "covers_the_options",
    "fewer_than_5_choices",
    "answer_key_explanation_mismatch",
    # 케이스 스펙(PACCINE_Case_Item_Writing_Spec) §6 하드결함
    "stem_fact_repeat_in_option",
    "negative_or_open_leadin_in_case",
}

# 케이스 문항 결정론 검사(스펙 §6) — 결함별 severity.
CASE_CHECK_SEVERITY = {
    "stem_fact_repeat_in_option": "high",
    "negative_or_open_leadin_in_case": "high",
    "nonstandard_terminology": "medium",
    "case_missing_required_element": "medium",
    "lab_value_without_reference_range": "medium",
}

# Ontology/RAG integrity failures.  Answer/explanation disagreement is a hard
# structural error; retrieval membership without verified entailment remains a
# review-blocking evidence error rather than being promoted by model confidence.
ONTOLOGY_RAG_CHECK_SEVERITY = {
    "answer_key_explanation_mismatch": "high",
    "distractor_not_ontology_grounded": "medium",
    "explanation_missing_source": "medium",
    "explanation_source_unverified": "medium",
    "syndrome_vs_disease_heterogeneous": "medium",
}

# 제6판 표준↔legacy 용어 매핑(어색→표준). substring 정확일치로 탐지.
TERMINOLOGY_MAP = {
    "대소부동": "적혈구크기부동",
    "철적모구": "철적혈모구",
    "적아구": "적혈모구",
    "갑상선": "갑상샘",
    "내원하였다": "병원에 왔다",
    "내원한": "병원에 온",
    "기대되는": "예상되는",
    "simvasatin": "simvastatin",
}
COMPOUND_SPACE = {"과분엽 호중구": "과분엽호중구"}
_GENE_TOKEN = re.compile(r"[A-Z][A-Z0-9]{1,}(?:::[A-Z0-9]+)?")
_AGE = re.compile(r"\d+\s*세")
_VITALS = re.compile(r"혈압|맥박|호흡|체온|mmHg", re.IGNORECASE)
_PE_KW = re.compile(r"진찰|촉지|만져|청진|시진|타진|압통|촉진|관찰되")
_LAB_VALUE = re.compile(r"\d[\d,.]*\s*(?:mg/dL|g/dL|ng/mL|µg/dL|U/L|fL|pg|mmol|IU|×10)", re.IGNORECASE)
_REF_RANGE = re.compile(r"정상|참고|reference|\(\s*[\d.<>]")
_DESC_LAB = re.compile(r"(?:감소|증가|저하|상승)되어\s*있")
_OPEN_LEADIN = re.compile(r"좋을까|고르(?:시오|세요)|무엇일까|골라")
# 내용적 부정형(리드인이 '가장 적은/낮은/작은/관련이 없는'을 물음).
_CONTENT_NEG = re.compile(r"가장\s*(?:적은|낮은|작은|먼)|관련이?\s*(?:적은|없는)")


def _last_sentence(text: str) -> str:
    parts = re.split(r"(?<=[?.])\s+", str(text or "").strip())
    return parts[-1] if parts else ""


def classify_item_kind(item: dict) -> str:
    """결정론 분류: 나이 오프닝 + (활력징후/진찰/검사) = case, 아니면 concept."""
    stem = str(item.get("stem") or "")
    full = f"{stem} {item.get('lead_in') or ''}"
    has_age = bool(_AGE.search(stem))
    has_clinical = bool(_VITALS.search(full) or _PE_KW.search(full) or _LAB_VALUE.search(full))
    return "case" if (has_age and has_clinical) else "concept"


def analyze_case_quality(item: dict) -> dict:
    """스펙 §6 케이스 검사 6종. flags + item_kind + terminology_hits 반환."""
    stem = str(item.get("stem") or "")
    lead = str(item.get("lead_in") or "") or _last_sentence(stem)
    full = f"{stem} {lead}"
    choices = normalize_choices(item)
    kind = classify_item_kind(item)
    flags: list[str] = []

    # 1) stem_fact_repeat_in_option — 줄기 개체명(유전자/변이)이 2개 이상 선지에 반복
    for token in set(_GENE_TOKEN.findall(stem)):
        if sum(1 for v in choices.values() if token in v) >= 2:
            flags.append("stem_fact_repeat_in_option")
            break

    # 2) negative_or_open_leadin_in_case — case인데 부정형/구어·명령형 리드인
    if kind == "case" and (IQ_NEG.search(full) or _OPEN_LEADIN.search(lead) or _CONTENT_NEG.search(lead)):
        flags.append("negative_or_open_leadin_in_case")

    # 3) nonstandard_terminology — 제6판 비표준/어색 용어
    term_hits: list[str] = []
    haystack = full + " " + " ".join(choices.values())
    for legacy, pref in {**TERMINOLOGY_MAP, **COMPOUND_SPACE}.items():
        if legacy in haystack:
            term_hits.append(f"{legacy}→{pref}")
    if _DESC_LAB.search(full):
        term_hits.append("수치없는 감소/증가 서술→수치+참고치")
    if term_hits:
        flags.append("nonstandard_terminology")

    # 4) case_missing_required_element — case+진단/검사 리드인인데 진찰/검사 누락
    if kind == "case" and re.search(r"진단|검사", lead):
        if not _PE_KW.search(full) or not _LAB_VALUE.search(full):
            flags.append("case_missing_required_element")

    # 5) lab_value_without_reference_range — 수치+단위 있으나 참고치 없음
    if (_LAB_VALUE.search(full) and not _REF_RANGE.search(full)) or _DESC_LAB.search(full):
        flags.append("lab_value_without_reference_range")

    return {"item_kind": kind, "case_flags": list(dict.fromkeys(flags)), "terminology_hits": term_hits}


def _load_items(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    for key in ("questions", "items"):
        if isinstance(data.get(key), list):
            return [x for x in data[key] if isinstance(x, dict)]
    return [data] if isinstance(data, dict) and data.get("stem") else []


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _near_duplicate_pairs(items: list[dict], threshold: float = 0.8) -> list[tuple[int, int]]:
    """문두 단어집합 Jaccard로 근사중복 탐지(배치 위생)."""
    from difflib import SequenceMatcher

    stems = [_norm_text(it.get("stem") or "")[:400] for it in items]
    pairs = []
    for i in range(len(stems)):
        for j in range(i + 1, len(stems)):
            if not stems[i] or not stems[j]:
                continue
            if abs(len(stems[i]) - len(stems[j])) > max(len(stems[i]), len(stems[j])) * 0.5:
                continue
            ratio = SequenceMatcher(None, stems[i], stems[j]).ratio()
            if ratio >= threshold:
                pairs.append((i, j))
    return pairs


def lint_batch(items: list[dict]) -> dict:
    n = len(items)
    flaw_counts: collections.Counter = collections.Counter()
    structural_flagged = 0
    ungated = 0
    longest_is_key = 0
    negative = 0
    answer_positions: collections.Counter = collections.Counter()
    kind_counts: collections.Counter = collections.Counter()
    per_item = []
    for it in items:
        quality = scan_item(it)
        case = analyze_case_quality(it)
        flaws = list(quality.get("flaws") or []) + case["case_flags"]
        kind_counts[case["item_kind"]] += 1
        for f in flaws:
            flaw_counts[f] += 1
        if quality.get("cognitive_low_suspect"):
            flaw_counts["cognitive_low_suspect"] += 1
        if any(f in STRUCTURAL_HARD for f in flaws):
            structural_flagged += 1
        if "longest_is_key" in flaws:
            longest_is_key += 1
        if "negative_stem" in flaws:
            negative += 1
        if not it.get("item_quality") and not it.get("self_check"):
            ungated += 1
        ans = str(it.get("answer") or "")
        if ans:
            answer_positions[ans] += 1
        per_item.append({
            "topic": it.get("topic"),
            "item_kind": case["item_kind"],
            "flaws": flaws,
            "case_flags": case["case_flags"],
            "terminology_hits": case["terminology_hits"],
            "structural": [f for f in flaws if f in STRUCTURAL_HARD],
            "key_length_rank": quality.get("key_length_rank"),
        })
    # 정답 위치 편중: 균등(각 20%) 대비 카이제곱
    chi2 = None
    if n >= 10 and answer_positions:
        expected = n / 5.0
        chi2 = sum((answer_positions.get(str(k), 0) - expected) ** 2 / expected for k in range(1, 6))
    dupes = _near_duplicate_pairs(items)
    return {
        "n_items": n,
        "ungated_items": ungated,
        "structural_flagged": structural_flagged,
        "structural_flagged_pct": round(100 * structural_flagged / n, 1) if n else 0,
        "longest_is_key": longest_is_key,
        "longest_is_key_pct": round(100 * longest_is_key / n, 1) if n else 0,
        "negative_stem": negative,
        "answer_position_distribution": dict(sorted(answer_positions.items())),
        "answer_position_chi2_vs_uniform": round(chi2, 2) if chi2 is not None else None,
        "near_duplicate_pairs": len(dupes),
        "item_kind_distribution": dict(kind_counts),
        "case_flag_distribution": {k: flaw_counts[k] for k in CASE_CHECK_SEVERITY if flaw_counts.get(k)},
        "ontology_rag_flag_distribution": {
            k: flaw_counts[k] for k in ONTOLOGY_RAG_CHECK_SEVERITY if flaw_counts.get(k)
        },
        "flaw_distribution": dict(flaw_counts.most_common()),
        "per_item": per_item,
    }


def rebalance_answer_positions(items: list[dict]) -> tuple[list[dict], int]:
    """정답 위치를 결정론적으로 균등화(round-robin target).  의미 보존 —
    선지 텍스트/선지별 해설을 함께 재배치하고 answer만 옮긴다. 모델 호출 없음.

    반환: (수정된 items, 변경된 문항 수). 원본은 변경하지 않고 얕은 복사본을 만든다.
    """
    out: list[dict] = []
    changed = 0
    for idx, it in enumerate(items):
        item = dict(it)
        choices = normalize_choices(item)
        cur = str(item.get("answer") or "")
        if len(choices) != 5 or cur not in choices:
            out.append(item)
            continue
        target = str((idx % 5) + 1)
        if target == cur:
            out.append(item)
            continue
        new_choices = dict(choices)
        new_choices[cur], new_choices[target] = choices[target], choices[cur]
        item["choices"] = new_choices
        # 선지별 해설 키도 함께 스왑(있으면).
        for field in ("choice_explanations",):
            ce = item.get(field)
            if isinstance(ce, dict):
                ce = dict(ce)
                a = ce.get(cur, ce.get(int(cur)))
                b = ce.get(target, ce.get(int(target)))
                # 정수/문자 키 혼용 방어: 문자열 키로 정규화해 스왑.
                norm = {str(k): v for k, v in ce.items()}
                if str(cur) in norm or str(target) in norm:
                    norm[str(cur)], norm[str(target)] = b if b is not None else norm.get(str(cur)), a if a is not None else norm.get(str(target))
                    item[field] = norm
        item["answer"] = int(target)
        item.setdefault("_rebalanced", True)
        changed += 1
        out.append(item)
    return out, changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report", type=str, default="")
    ap.add_argument("--fix-positions", type=str, default="", metavar="OUTDIR",
                    help="정답 위치를 균등화한 사본을 OUTDIR에 저장(원본 미변경).")
    args = ap.parse_args()

    if args.fix_positions:
        outdir = Path(args.fix_positions)
        outdir.mkdir(parents=True, exist_ok=True)
        src_files = [Path(f) for f in args.files] or sorted((ROOT / "data_private/lecture_questions").glob("q_*.json"))
        before = collections.Counter()
        after = collections.Counter()
        total_changed = 0
        for fp in src_files:
            items = _load_items(fp)
            if not items:
                continue
            for it in items:
                if str(it.get("answer") or ""):
                    before[str(it["answer"])] += 1
            fixed, changed = rebalance_answer_positions(items)
            total_changed += changed
            for it in fixed:
                if str(it.get("answer") or ""):
                    after[str(it["answer"])] += 1
            (outdir / fp.name).write_text(json.dumps(fixed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"정답 위치 균등화: {total_changed}문항 재배치 → {outdir}")
        print(f"  before 분포: {dict(sorted(before.items()))}")
        print(f"  after  분포: {dict(sorted(after.items()))}")
        return 0

    files = [Path(f) for f in args.files]
    if not files:
        files = sorted((ROOT / "data_private/lecture_questions").glob("q_*.json"))

    all_items: list[dict] = []
    per_file = []
    for fp in files:
        try:
            items = _load_items(fp)
        except (json.JSONDecodeError, OSError):
            continue
        if not items:
            continue
        all_items.extend(items)
        res = lint_batch(items)
        per_file.append({"file": fp.name, **{k: res[k] for k in (
            "n_items", "ungated_items", "structural_flagged", "structural_flagged_pct",
            "longest_is_key_pct", "negative_stem", "near_duplicate_pairs")}})

    overall = lint_batch(all_items)
    summary = {"total_files": len(per_file), "overall": {k: v for k, v in overall.items() if k != "per_item"}, "per_file": per_file}

    if args.report:
        Path(args.report).write_text(json.dumps({"summary": summary, "overall_per_item": overall["per_item"]}, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    o = overall
    print(f"=== 생성문항 결정론 린터: {o['n_items']}문항 / {len(per_file)}파일 ===")
    print(f"게이트 미적용 문항: {o['ungated_items']}/{o['n_items']} ({round(100*o['ungated_items']/max(1,o['n_items']),1)}%)")
    print(f"구조적 하드결함 보유: {o['structural_flagged']}/{o['n_items']} ({o['structural_flagged_pct']}%)")
    print(f"정답=최장선지: {o['longest_is_key']}/{o['n_items']} ({o['longest_is_key_pct']}%)")
    print(f"부정형 stem: {o['negative_stem']}/{o['n_items']}")
    print(f"정답 위치 분포: {o['answer_position_distribution']}  (χ² vs 균등={o['answer_position_chi2_vs_uniform']})")
    print(f"근사중복 쌍: {o['near_duplicate_pairs']}")
    print(f"문항유형(case/concept): {o['item_kind_distribution']}")
    if o["case_flag_distribution"]:
        print("케이스 스펙 결함(§6):")
        for f, c in o["case_flag_distribution"].items():
            print(f"  {c:4}  {f} [{CASE_CHECK_SEVERITY[f]}]")
    if o["ontology_rag_flag_distribution"]:
        print("Ontology/RAG 무결성 결함:")
        for f, c in o["ontology_rag_flag_distribution"].items():
            print(f"  {c:4}  {f} [{ONTOLOGY_RAG_CHECK_SEVERITY[f]}]")
    print("\n=== 결함 분포 ===")
    for f, c in o["flaw_distribution"].items():
        print(f"  {c:4}  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
