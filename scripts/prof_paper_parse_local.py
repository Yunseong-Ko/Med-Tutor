#!/usr/bin/env python3
"""2024 임상의학종합시험 2교시 시험지(HWP→xhtml 로컬변환) → 시드 행 + 이미지 대장 (로컬 전용).

특징: 문두 '?' 직후 원문자 = 인라인 정답 표기 → 정답 자동 추출.
출력: seeds/seeds_paper_review.csv (80행, 정답 포함) · images/P2_*.png + ledger 병합
stdout: 통계만.
"""
import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from prof_items_parse_local import load_alias_index, suggest_concept, guess_axis_v2  # noqa: E402

BASE = Path("data_private/professor_items")
TXT = BASE / "originals_hwp_extract" / "paper2" / "text_local.txt"
BIN = BASE / "originals_hwp_extract" / "paper2" / "bindata"
IMG_DIR = BASE / "images"
SEEDS = BASE / "seeds"
CIRC = "①②③④⑤"


def main() -> int:
    text = TXT.read_text(encoding="utf-8")
    # 정답 앵커: '?' + 원문자
    anchors = [(m.start(), m.group(1)) for m in re.finditer(r"\?\s*([①-⑤])", text)]
    idx = load_alias_index()
    rows = []
    ledger_path = IMG_DIR / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}
    n_img_items = 0
    prev_end = 0
    for i, (pos, ans_circ) in enumerate(anchors, 1):
        # 이 문항 블록: 이전 문항의 선지 끝 ~ 다음 앵커 직전
        nxt = anchors[i][0] if i < len(anchors) else len(text)
        stem = text[prev_end:pos + 1]
        block = text[pos:nxt]
        # 선지: 앵커 뒤 ①..⑤
        body = block[1:]
        parts = re.split(r"([①-⑤])", body)
        choices, cur = {}, None
        for p in parts:
            if p in CIRC:
                k = str(CIRC.index(p) + 1)
                if k == "1" and cur is None:
                    cur = k; choices[cur] = ""
                elif cur is not None:
                    cur = k; choices[cur] = ""
            elif cur:
                choices[cur] += p
        choices = {k: re.sub(r"\s+", " ", v).strip()[:200] for k, v in choices.items() if v.strip()}
        # 이미지: stem/block 내 placeholder
        imgs = re.findall(r"〔IMG:([^〕]+)〕", stem + block)
        stem_clean = re.sub(r"〔IMG:[^〕]+〕", " ", stem)
        stem_clean = re.sub(r"\s+", " ", stem_clean).strip()
        # 문항번호 프리픽스(예: '5.') 제거 흔적 정리
        stem_clean = re.sub(r"^\W*\d+\s*[.)]\s*", "", stem_clean)
        seed_id = f"P2-{i:02d}"
        saved = []
        for name in imgs:
            src = BIN / name
            if not src.exists() or src.stat().st_size < 10_000:
                continue
            data = src.read_bytes()
            h = hashlib.sha256(data).hexdigest()[:12]
            ext = src.suffix.lstrip(".") or "bin"
            out = f"{seed_id}_{h}.{ext}"
            shutil.copy(src, IMG_DIR / out)
            saved.append({"file": out, "sha12": h, "bytes": len(data), "ext": ext})
        if saved:
            ledger[seed_id] = saved
            n_img_items += 1
        fulltext = stem_clean + " " + " ".join(choices.values())
        rows.append({
            "seed_id": seed_id, "subject": "2교시시험지",
            "질환개념(제안)": suggest_concept(fulltext, idx),
            "평가축(제안)": guess_axis_v2(stem_clean, choices, idx),
            "정답번호(입력)": str(CIRC.index(ans_circ) + 1),
            "정답개념(입력)": "", "오답감별군(입력)": "",
            "난이도(상중하)": "중", "사용(Y/N)": "Y",
            "이미지수": len(saved), "이미지파일": ";".join(s["file"] for s in saved),
            "이미지핵심소견(입력)": "",
            "원문발췌_검수전용": stem_clean[:150],
            "선지_검수전용": " | ".join(f"{k}){v[:40]}" for k, v in sorted(choices.items())),
            "비고": "정답=시험지 인라인 표기 자동추출",
        })
        prev_end = nxt
    out_csv = SEEDS / "seeds_paper_review.csv"
    with out_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    n_c = sum(1 for r in rows if r["질환개념(제안)"])
    ax = {}
    for r in rows:
        a = r["평가축(제안)"]
        if a: ax[a] = ax.get(a, 0) + 1
    print(f"시험지 문항 {len(rows)}행 · 정답 자동추출 {sum(1 for r in rows if r['정답번호(입력)'])}")
    print(f"  개념제안 {n_c} · 평가축 {ax} · 이미지 문항 {n_img_items}")
    print(f"[CSV] {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
