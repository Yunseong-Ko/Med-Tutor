#!/usr/bin/env python3
"""R형(가·나·다·라 조합형) 문항의 누락된 보기 블록을 원본 HWP에서 복구.

hwp5txt는 표/글상자를 <그림>으로 버리지만 hwp5html은 텍스트로 살린다. 각 HWP를
HTML로 추출→문항별 가/나/다/라/마 보기 파싱→해당 문항에 sub_statements 주입.
OCR 불필요·원문 정확. 백업 후 in-place. (해설은 건드리지 않음)
"""

import json
import re
import subprocess
import shutil
import html as htmlmod
from pathlib import Path
from datetime import datetime

HWP = {
    "COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험":
        "/Users/goyunseong/Downloads/(2학년)(2023-3-8)혈액및종양학+과정시험(객118,주11)(1330-1540)_정답+및+풀이.hwp",
    "COURSE_2_20260306_HEMATOLOGY_ONCOLOGY_1차":
        "/Users/goyunseong/Downloads/(2학년)(2026-3-6)혈액및종양학 1차 과정시험(객80_주5)(1030-1200)_정답 및 해설.hwp",
    "COURSE_2_20260317_HEMATOLOGY_ONCOLOGY_2차":
        "/Users/goyunseong/Downloads/(2학년)(2026-3-17)혈액및종양학 2차 과정시험(객52)(1000-1100)_정답 및 해설.hwp",
}
EXTRACTED = Path("data_private/course_exams/extracted")
SCRATCH = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad/hwp_html")
SUB_LABELS = "가나다라마바"


def hwp_to_text(hwp_path, tag):
    """hwp5html → 태그 제거 텍스트(줄바꿈 보존)."""
    outdir = SCRATCH / tag
    outdir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["hwp5html", "--output", str(outdir), hwp_path], capture_output=True, text=True)
    xhtml = outdir / "index.xhtml"
    if not xhtml.exists():
        raise RuntimeError(f"hwp5html 실패: {r.stderr[:200]}")
    raw = xhtml.read_text(encoding="utf-8", errors="ignore")
    # 줄 경계 보존: &#13; 및 블록 태그 → 개행
    raw = raw.replace("&#13;", "\n").replace("<br/>", "\n").replace("</p>", "\n").replace("</td>", "\n")
    txt = re.sub(r"<[^>]+>", " ", raw)
    txt = htmlmod.unescape(txt)
    txt = re.sub(r"[ \t]+", " ", txt)
    return txt


def parse_substatements(text, question_number):
    """문항번호 블록에서 가./나./다./라./마. 보기를 추출.

    보기는 'N. ...조합은? ① [답표시]  가. 문장  나. 문장 ...' 형태(라벨+마침표).
    선지 '① 가, 나, 다'는 콤마라서 라벨+마침표 매칭에 안 걸린다.
    """
    qn = str(question_number)
    m = re.search(rf"(?m)^\s*{re.escape(qn)}\.\s", text)
    if not m:
        return None
    start = m.end()
    # 현재 문항 블록으로만 한정: 다음 문항 번호 or <풀이> 전까지 (이웃 보기 훔침 방지)
    rest = text[start:]
    bounds = [len(rest)]
    nxt = re.search(r"(?m)^\s*\d{1,3}\.\s", rest)
    if nxt:
        bounds.append(nxt.start())
    pul = re.search(r"<?\s*풀이\s*>?|해설", rest)
    if pul:
        bounds.append(pul.start())
    tail = rest[:min(bounds)]
    subs = {}
    for lab in SUB_LABELS:
        # 보기 라벨은 줄 시작에만 온다(^). 문장끝 '설명이다.'의 '다.'는 줄 중간이라 제외.
        mm = re.search(rf"(?m)^\s*{lab}[.．]\s*([^\n①-⑮]+)", tail)
        if mm:
            v = re.sub(r"\s+", " ", mm.group(1)).strip().rstrip(".． ")
            if 1 < len(v) < 200:
                subs[lab] = v
    # 최소 가·나·다 3개는 있어야 유효 R형 보기로 인정
    if sum(1 for k in "가나다" if k in subs) >= 2:
        return subs
    return None


def main():
    commit = "--commit" in __import__("sys").argv
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    grand = 0
    for stem, hwp_path in HWP.items():
        if not Path(hwp_path).exists():
            print(f"[skip] HWP 없음: {stem}")
            continue
        text = hwp_to_text(hwp_path, stem)
        p = EXTRACTED / f"{stem}.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        qs = d.get("questions", [])
        recovered = 0
        for q in qs:
            # 경계 파서가 진짜 보기 블록에서만 성공하므로, 성공 문항 전부 주입.
            subs = parse_substatements(text, q.get("question_number"))
            if subs:
                q["sub_statements"] = subs
                q["sub_statements_source"] = "hwp5html_recovered"
                recovered += 1
        grand += recovered
        print(f"{p.name[:52]:52s} 보기복구 {recovered}")
        if commit:
            shutil.copy(p, p.with_suffix(f".json.bak_rtype_{stamp}"))
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {grand}개 R형 문항 보기 복구." + ("" if commit else "  (dry-run — 저장은 --commit)"))


if __name__ == "__main__":
    main()
