#!/usr/bin/env python3
"""Step 2 writeback — 청크별 생성 해설(chunk_NN_out.json)을 원본 3개 파일에 병합.

원본 해설은 original_explanation으로 보존(최초 1회), 새 Ontology 근거 해설을
explanation/answer_rationale/choice_explanations/key_learning_points/harrison_anchor에
기록한다. 매칭은 (file, idx) 기준. 백업 후 in-place.
"""

import json
import glob
import shutil
from pathlib import Path
from datetime import datetime

CH = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad/hemeonc_chunks")


def load_outputs():
    by_file = {}
    total = 0
    missing = []
    for n in range(19):
        p = CH / f"chunk_{n:02d}_out.json"
        if not p.exists():
            missing.append(f"chunk_{n:02d}")
            continue
        try:
            recs = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            missing.append(f"chunk_{n:02d}(parse:{e})")
            continue
        for r in recs:
            by_file.setdefault(r["file"], {})[int(r["idx"])] = r
            total += 1
    return by_file, total, missing


def main():
    commit = "--commit" in __import__("sys").argv
    by_file, total, missing = load_outputs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"수집된 해설 레코드: {total} | 누락 청크: {missing or '없음'}")
    updated_all = 0
    for fp, recs in by_file.items():
        p = Path(fp)
        d = json.loads(p.read_text(encoding="utf-8"))
        qs = d.get("questions", [])
        upd = 0
        for idx, r in recs.items():
            if idx >= len(qs):
                continue
            q = qs[idx]
            # preserve original once
            if q.get("original_explanation") in (None, "") and q.get("explanation"):
                q["original_explanation"] = q["explanation"]
            q["explanation"] = r.get("explanation") or q.get("explanation")
            if r.get("answer_rationale"):
                q["answer_rationale"] = r["answer_rationale"]
            if r.get("choice_explanations"):
                q["choice_explanations"] = r["choice_explanations"]
            if r.get("key_learning_points"):
                q["key_learning_points"] = r["key_learning_points"]
            q["harrison_anchor"] = r.get("harrison_anchor")
            q["rewrite_status"] = r.get("rewrite_status", "ontology_grounded_v1")
            q["needs_review"] = True
            upd += 1
        updated_all += upd
        print(f"{p.name[:52]:52s} 업데이트 {upd}/{len(qs)}")
        if commit:
            shutil.copy(p, p.with_suffix(f".json.bak_expl_{stamp}"))
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {updated_all}문항 해설 갱신." + ("" if commit else "  (dry-run — 저장은 --commit)"))


if __name__ == "__main__":
    main()
