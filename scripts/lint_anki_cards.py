#!/usr/bin/env python3
"""Anki 카드 품질 게이트(린터) — "효과적인 카드 만들기 10원칙" 자동검사.

data_private/lecture_cards/cards_*.json 의 각 Cloze 카드를 10원칙 중
**기계적으로 검사 가능한 규칙**으로만 점검한다. 표준 라이브러리만 사용하고,
같은 입력에는 항상 같은 결과를 내는 **결정론적** 도구다.

주의(휴리스틱 게이트):
    ERROR 는 카드가 Anki 에서 정상 동작하지 않거나 원칙을 명백히 위반하는
    "차단" 신호다. 반면 **WARN 은 실패가 아니라 '검토 제안'**이다. 길이·개방형
    어구·수치 검증 같은 항목은 문맥에 따라 정당할 수 있으므로, 사람이 최종
    판단한다. 이 린터는 사람 검토를 대체하지 않고 우선순위를 정해줄 뿐이다.

원칙 ↔ 검사 매핑:
    Cloze          → text 에 {{cN::...}} 존재 / 빈 cloze 금지
    최소화·트리거   → 단일 cloze 내용 길이 상한
    최적화          → text 가시 길이 상한(AnKing p90 163자 기준, 여유 180)
    개별화          → 카드당 cloze 개수 상한
    구체성          → 개방형 프롬프트 어구 탐지(정답이 하나로 좁혀지는가)
    반면교사        → 고위험 수치(용량/컷오프)는 extra 에 verify 플래그 필요
    쌍방향성/연합    → concept 기반 sibling 추정(집계, 점수 아님)

입력 구조:
    {lecture_id, source_name, harrison:[...], cards:[
        {text, extra, mnemonic, concept, system, tags:[...]}
    ]}

사용 예:
    python3 scripts/lint_anki_cards.py
    python3 scripts/lint_anki_cards.py --dir data_private/lecture_cards --sample 10
    python3 scripts/lint_anki_cards.py --json           # 기본 경로에 리포트 저장
    python3 scripts/lint_anki_cards.py --json out.json   # 지정 경로에 저장

종료 코드: ERROR 가 하나라도 있으면 1, 아니면 0.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data_private" / "lecture_cards"
STAMP = datetime.now().strftime("%Y%m%d")

# --- 임계값(상수로 노출해 근거를 명시) --------------------------------------
TEXT_MAX = 180          # 가시 길이 상한(최적화). AnKing p90 163자 기준에 여유
CLOZE_MAX = 4           # 카드당 cloze 개수 상한(개별화)
CLOZE_INNER_MAX = 60    # 단일 cloze 내용 글자수 상한(트리거·최소화)
EXTRA_MAX = 200         # extra 길이 상한

# 개방형(정답이 하나로 좁혀지지 않는) 프롬프트 후보 어구(구체성 위반)
OPEN_ENDED = ["무엇인가", "무엇", "설명하시오", "기술하시오", "what is", "explain", "list "]

# 고위험 수치(용량/컷오프) 패턴: 숫자 + 단위. verify 없으면 '반면교사' WARN.
NUM_UNIT = re.compile(
    r"\d[\d,.]*\s*"
    r"(?:mg/dL|g/dL|ng/mL|µg|μg|mcg|mg|g/L|mmol/L|mmol|mEq|IU|U/L|"
    r"mL|dL|/µL|/μL|/uL|cGy|Gy|%|일|주|개월|년|mm|cm|°C|℃|kg)",
    re.I,
)
# extra 안의 검증 플래그(작성자가 남긴 확인 표시)
VERIFY = re.compile(r"verify|확인필요|확인\s*요|⚠", re.I)

# Anki cloze 매칭. 빈 cloze도 잡도록 .*? (비탐욕) 사용.
CLOZE = re.compile(r"\{\{c(\d+)::(.*?)\}\}", re.DOTALL)
HTML_TAG = re.compile(r"<[^>]+>")

# 심각도
ERROR = "ERROR"
WARN = "WARN"


# --- 헬퍼 -------------------------------------------------------------------
def strip_html(s: str) -> str:
    """HTML 태그 제거 + 공백 정규화(가시 길이 측정용)."""
    s = s.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    s = HTML_TAG.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def cloze_answers(text: str) -> list[tuple[str, str]]:
    """카드 text 에서 (cloze_index, answer_content) 목록. hint(::뒤)는 제외."""
    out = []
    for idx, inner in CLOZE.findall(text):
        answer = inner.split("::", 1)[0]  # {{cN::answer::hint}} → answer
        out.append((idx, answer))
    return out


def plain_text(text: str) -> str:
    """cloze 를 정답으로 치환하고 태그 제거 → 학습자가 보는 문장 근사."""
    replaced = CLOZE.sub(lambda m: m.group(2).split("::", 1)[0], text)
    return strip_html(replaced)


def lecture_label(lid: str, source_name: str | None) -> str:
    """lecture_id → 사람이 읽는 강의 라벨(export 스크립트와 동일 규칙)."""
    m = re.match(r"(\d{4})(\d{2})(\d{2})_([\d_]+교시)_(.+)", str(lid or ""))
    if m:
        _, mo, da, gy, title = m.groups()
        base = (source_name or title).replace("_", " ").replace(".pdf", "").replace(".docx", "").strip()
        return f"{int(mo)}·{int(da)} {gy.replace('_', '·')} {base}"
    return (source_name or lid or "?").replace(".pdf", "").strip()


def load_allow(card_dir: Path):
    """_include_lids.json 이 있으면 허용 lecture_id 집합, 없으면 None."""
    p = card_dir / "_include_lids.json"
    if not p.exists():
        return None
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None


# --- 카드 단위 검사 ---------------------------------------------------------
def check_card(card: dict) -> list[dict]:
    """카드 하나를 검사해 findings(list of dict) 반환. dict: {severity, code, msg}."""
    findings: list[dict] = []
    text = card.get("text") or ""
    extra = card.get("extra") or ""

    # --- ERROR: 카드 존립 자체 ---
    if not text.strip():
        findings.append({"severity": ERROR, "code": "E_BLANK_TEXT", "msg": "text 공백"})
        return findings  # 본문이 없으면 이후 검사 무의미

    answers = cloze_answers(text)
    if not answers:
        findings.append({"severity": ERROR, "code": "E_NO_CLOZE",
                         "msg": "cloze 없음 ({{cN::...}} 최소 1개 필요)"})
    else:
        empty = sum(1 for _, a in answers if not a.strip())
        if empty:
            findings.append({"severity": ERROR, "code": "E_EMPTY_CLOZE",
                             "msg": f"빈 cloze {empty}개(내용 없음)"})

    # --- WARN: 검토 제안 ---
    vis = plain_text(text)
    if len(vis) > TEXT_MAX:
        findings.append({"severity": WARN, "code": "W_TEXT_LONG",
                         "msg": f"가시 길이 {len(vis)}자 > {TEXT_MAX}(최적화 검토)"})

    if len(answers) > CLOZE_MAX:
        findings.append({"severity": WARN, "code": "W_TOO_MANY_CLOZE",
                         "msg": f"cloze {len(answers)}개 > {CLOZE_MAX}(개별화 검토)"})

    for idx, a in answers:
        alen = len(strip_html(a))
        if alen > CLOZE_INNER_MAX:
            findings.append({"severity": WARN, "code": "W_CLOZE_LONG",
                             "msg": f"c{idx} 내용 {alen}자 > {CLOZE_INNER_MAX}(트리거·최소화 검토)"})

    low = vis.lower()
    hits = [p for p in OPEN_ENDED if p.lower() in low]
    if hits:
        findings.append({"severity": WARN, "code": "W_OPEN_ENDED",
                         "msg": f"개방형 어구 {hits}(구체성 검토)"})

    if NUM_UNIT.search(text) and not VERIFY.search(extra):
        findings.append({"severity": WARN, "code": "W_NUM_UNVERIFIED",
                         "msg": "고위험 수치(용량/컷오프) 포함, extra verify 플래그 없음"})

    if len(strip_html(extra)) > EXTRA_MAX:
        findings.append({"severity": WARN, "code": "W_EXTRA_LONG",
                         "msg": f"extra {len(strip_html(extra))}자 > {EXTRA_MAX}"})

    return findings


# --- 집계 & 리포트 ----------------------------------------------------------
def build_report(card_dir: Path, allow) -> dict:
    lectures = []                 # 강의별 요약
    card_rows = []                # 위반 카드(정렬·샘플용)
    totals = Counter()            # error/warn/cards/files/lectures
    code_counts = Counter()       # 코드별 빈도
    system_counts = Counter()     # system별 카드수
    cloze_dist = Counter()        # 카드당 cloze 개수 분포
    have_mnemonic = 0
    have_extra = 0
    sibling_groups = 0            # 같은 concept 2+ 카드(쌍방향 추정)
    sibling_cards = 0

    for f in sorted(card_dir.glob("cards_*.json"), key=lambda p: p.name):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        lid = data.get("lecture_id")
        if allow is not None and lid not in allow:
            continue
        cards = data.get("cards") or []
        if not cards:
            continue
        totals["files"] += 1
        totals["lectures"] += 1
        label = lecture_label(lid, data.get("source_name"))

        lec_err = lec_warn = 0
        concept_bucket = defaultdict(int)  # 강의 내 concept별 카드수

        for i, c in enumerate(cards, 1):
            totals["cards"] += 1
            if (c.get("mnemonic") or "").strip():
                have_mnemonic += 1
            if (c.get("extra") or "").strip():
                have_extra += 1
            if (c.get("system") or "").strip():
                system_counts[c["system"]] += 1
            if (c.get("concept") or "").strip():
                concept_bucket[c["concept"].strip()] += 1
            cloze_dist[len(cloze_answers(c.get("text") or ""))] += 1

            findings = check_card(c)
            n_err = sum(1 for x in findings if x["severity"] == ERROR)
            n_warn = sum(1 for x in findings if x["severity"] == WARN)
            lec_err += n_err
            lec_warn += n_warn
            for x in findings:
                code_counts[x["code"]] += 1
            if findings:
                card_rows.append({
                    "lecture_id": lid, "label": label, "index": i,
                    "n_err": n_err, "n_warn": n_warn,
                    "findings": findings,
                    "text": c.get("text") or "",
                    "concept": c.get("concept") or "",
                    "system": c.get("system") or "",
                })

        # 쌍방향(sibling) 추정: 같은 concept 에 카드 2개 이상 → 정/역 후보
        for _concept, cnt in concept_bucket.items():
            if cnt >= 2:
                sibling_groups += 1
                sibling_cards += cnt

        totals["errors"] += lec_err
        totals["warnings"] += lec_warn
        lectures.append({"lecture_id": lid, "label": label, "cards": len(cards),
                         "errors": lec_err, "warnings": lec_warn})

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "card_dir": str(card_dir),
        "allowlist_applied": allow is not None,
        "thresholds": {"text_max": TEXT_MAX, "cloze_max": CLOZE_MAX,
                       "cloze_inner_max": CLOZE_INNER_MAX, "extra_max": EXTRA_MAX},
        "totals": {
            "files": totals["files"], "lectures": totals["lectures"],
            "cards": totals["cards"], "errors": totals["errors"],
            "warnings": totals["warnings"],
        },
        "code_counts": dict(sorted(code_counts.items())),
        "info": {
            "system_counts": dict(system_counts.most_common()),
            "cloze_count_distribution": {str(k): v for k, v in sorted(cloze_dist.items())},
            "mnemonic_rate": round(have_mnemonic / totals["cards"], 3) if totals["cards"] else 0.0,
            "extra_rate": round(have_extra / totals["cards"], 3) if totals["cards"] else 0.0,
            "sibling_concept_groups": sibling_groups,
            "sibling_cards": sibling_cards,
        },
        "lectures": lectures,
        # card_rows 는 콘솔/샘플용 내부 자료(리포트 저장 시엔 축약)
        "_card_rows": card_rows,
    }


def print_console(rep: dict, sample: int) -> None:
    t = rep["totals"]
    print("=" * 72)
    print("Anki 카드 품질 게이트 (효과적인 카드 10원칙 · 휴리스틱)")
    print("=" * 72)
    print(f"경로       : {rep['card_dir']}")
    print(f"allowlist  : {'적용됨' if rep['allowlist_applied'] else '없음(전체)'}")
    print(f"강의/카드  : {t['lectures']}강의 · {t['cards']}카드 ({t['files']}파일)")
    print(f"ERROR      : {t['errors']}")
    print(f"WARN(검토) : {t['warnings']}")
    print()

    if rep["code_counts"]:
        print("[규칙별 카운트]")
        for code, n in rep["code_counts"].items():
            print(f"  {code:<18} {n}")
        print()

    print("[강의별 표]  (E=ERROR, W=WARN 검토제안)")
    print(f"  {'강의':<34} {'카드':>4} {'E':>4} {'W':>5}")
    for lec in rep["lectures"]:
        label = lec["label"]
        if len(label) > 33:
            label = label[:32] + "…"
        print(f"  {label:<34} {lec['cards']:>4} {lec['errors']:>4} {lec['warnings']:>5}")
    print()

    info = rep["info"]
    print("[INFO 집계]")
    print(f"  mnemonic 보유율 : {info['mnemonic_rate']*100:.1f}%")
    print(f"  extra 보유율    : {info['extra_rate']*100:.1f}%")
    print(f"  쌍방향 추정     : concept {info['sibling_concept_groups']}그룹 / {info['sibling_cards']}카드")
    print(f"  cloze 개수 분포 : {info['cloze_count_distribution']}")
    if info["system_counts"]:
        top = list(info["system_counts"].items())[:8]
        print("  system별 카드수 : " + ", ".join(f"{k}={v}" for k, v in top))
    print()

    if sample and sample > 0:
        rows = sorted(rep["_card_rows"], key=lambda r: (r["n_err"], r["n_warn"]), reverse=True)
        rows = rows[:sample]
        print(f"[위반 카드 상위 {len(rows)}개]")
        for r in rows:
            print("-" * 72)
            print(f"  {r['label']} · #{r['index']}  (E{r['n_err']} W{r['n_warn']})")
            for x in r["findings"]:
                print(f"    [{x['severity']}] {x['code']}: {x['msg']}")
            snippet = r["text"].strip().replace("\n", " ")
            if len(snippet) > 220:
                snippet = snippet[:220] + "…"
            print(f"    text: {snippet}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Anki 카드 품질 린터(10원칙 자동검사·휴리스틱)")
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="카드 디렉터리(기본 data_private/lecture_cards)")
    ap.add_argument("--sample", type=int, default=0,
                    help="위반 카드 상위 N개를 실제 text와 함께 출력")
    ap.add_argument("--json", nargs="?", const="__DEFAULT__", default=None,
                    help="리포트 JSON 저장(값 생략 시 카드 디렉터리에 기본 파일명으로)")
    ap.add_argument("--ignore-allowlist", action="store_true",
                    help="_include_lids.json 을 무시하고 전체 카드 검사")
    args = ap.parse_args()

    card_dir = Path(args.dir)
    if not card_dir.exists():
        print(f"[error] 카드 디렉터리 없음: {card_dir}", file=sys.stderr)
        return 2

    allow = None if args.ignore_allowlist else load_allow(card_dir)
    rep = build_report(card_dir, allow)

    print_console(rep, args.sample)

    if args.json is not None:
        if args.json == "__DEFAULT__":
            out_path = card_dir / f"_lint_report_{STAMP}.json"
        else:
            out_path = Path(args.json)
        # 저장본에는 위반 카드 원문(사생활)을 코드/위치 요약으로 축약해 남긴다.
        saved = {k: v for k, v in rep.items() if k != "_card_rows"}
        saved["violations"] = [
            {"lecture_id": r["lecture_id"], "index": r["index"],
             "n_err": r["n_err"], "n_warn": r["n_warn"],
             "codes": [x["code"] for x in r["findings"]]}
            for r in rep["_card_rows"]
        ]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[json] 리포트 저장: {out_path}")

    return 1 if rep["totals"]["errors"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
