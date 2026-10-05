#!/usr/bin/env python3
"""PMA 학생 해설(HWP) → 이미지 라벨 대장 구축 (로컬 전용, 비전송).

목적: 이미지에 **검증 가능한 진단명 라벨**을 붙여, 이미지 문항을 안전하게 생성할 근거를 만든다.
      (기존 실패: 라벨 없이 개념 단위로 이미지를 배정 → ECG가 담낭염 문항에 붙는 오류)

파일명 규약: {턴}_{교시}_{문항번호}_{작성자}.hwp  예) A턴_1교시_5번_곽민기.hwp
각 해설 파일에는 해당 문항의 그림/사진과 진단·해설 텍스트가 함께 들어 있으므로,
파일 단위로 (턴, 교시, 문항번호) ↔ 이미지 ↔ 텍스트에서 추출한 진단명 후보를 묶는다.

stdout: 통계만. 원문 문장은 출력하지 않는다.
출력: data_private/professor_items/pma_labels/
        images/{turn}_{period}_{qno}_{hash}.{ext}
        label_ledger.json  [{key, turn, period, qno, author, images[], dx_candidates[], modality_guess}]
        review_sheet.html  (사람 검수용 — 이미지+진단명 후보 나란히)
"""
import hashlib
import html
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

SRC_DIRS = [
    Path("data_private/professor_items/originals/pma"),        # A/B턴 262
    Path("data_private/professor_items/originals/pma_4gyosi"),  # 4교시 세트 98
]
OUT = Path("data_private/professor_items/pma_labels")
IMG_DIR = OUT / "images"

MODALITY = [
    ("ECG", r"심전도|ECG|EKG"),
    ("가슴X선", r"가슴\s*X\s*선|흉부\s*(방사선|X-?ray|촬영)|chest\s*(x-?ray|PA)"),
    ("복부CT", r"복부\s*(전산화단층|CT)|abdomen\s*CT"),
    ("가슴CT", r"가슴\s*(전산화단층|CT)|chest\s*CT"),
    ("뇌CT/MRI", r"뇌\s*(CT|자기공명|MRI)|brain\s*(CT|MRI)"),
    ("초음파", r"초음파|ultrasound|sonograph"),
    ("내시경", r"내시경|endoscop|위내시경|대장내시경"),
    ("혈액도말", r"말초혈액도말|말초혈액\s*도말|blood\s*smear|도말검사"),
    ("병리조직", r"조직\s*소견|병리|생검|H&E|현미경"),
    ("검사결과표", r"검사\s*결과|참고치|results?\s*table"),
]


def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


FULLW = str.maketrans("０１２３４５６７８９", "0123456789")


def parse_name(stem):
    """A턴_1교시_5번_곽민기 / 4교시_77번~80번_황유진 → (turn, period, [qnos], author)."""
    s = nfc(stem).translate(FULLW)
    turn = "A" if re.search(r"A\s*턴", s) else ("B" if re.search(r"B\s*턴", s) else "C")  # C=4교시세트
    pm = re.search(r"(\d)\s*교시", s)
    period = pm.group(1) if pm else "?"
    qs = []
    for m in re.finditer(r"(\d{1,3})\s*(?:번)?\s*[~\-]\s*(\d{1,3})\s*번", s):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b and b - a < 30:
            qs += list(range(a, b + 1))
    if not qs:
        seg = re.split(r"교시", s)[-1]
        nums = re.findall(r"(\d{1,3})\s*번", seg) or re.findall(r"[_,](\d{1,3})[,_번]", seg)
        qs = [int(x) for x in nums]
    author = s.split("_")[-1] if "_" in s else ""
    return turn, period, sorted(set(qs)), author


def hwp_convert(path: Path, key: str):
    """hwp5html 1회 변환으로 (텍스트, 이미지목록) 동시 회수.
    hwp5txt는 이 파일들에서 빈 출력을 내므로 xhtml 경로를 쓴다."""
    text, out = "", []
    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run(["hwp5html", "--output", td, str(path)],
                           capture_output=True, timeout=180)
        except Exception:
            return text, out
        x = Path(td) / "index.xhtml"
        if x.exists():
            raw = x.read_text(encoding="utf-8", errors="ignore")
            t = html.unescape(re.sub(r"<[^>]+>", " ", raw))
            text = re.sub(r"\s+", " ", t).strip()
        bd = Path(td) / "bindata"
        if not bd.exists():
            return text, out
        for f in sorted(bd.iterdir()):
            try:
                data = f.read_bytes()
            except Exception:
                continue
            if len(data) < 12_000:      # 로고·아이콘 제외
                continue
            ext = f.suffix.lstrip(".").lower() or "bin"
            if ext not in ("png", "jpg", "jpeg", "gif", "bmp"):
                continue
            h = hashlib.sha256(data).hexdigest()[:12]
            name = f"{key}_{h}.{ext}"
            (IMG_DIR / name).write_bytes(data)
            out.append({"file": name, "sha12": h, "bytes": len(data)})
    return text, out


def load_alias_index():
    idx = []
    try:
        reg = json.loads(Path("data_private/concept_registry.json").read_text(encoding="utf-8"))["concepts"]
        for cid, c in reg.items():
            for a in [cid.replace("_", " ")] + list(c.get("aliases") or []):
                na = re.sub(r"[\s_\-]+", "", str(a)).lower()
                if len(na) >= 3:
                    idx.append((na, cid, len(na)))
    except Exception:
        pass
    sup = Path("data_private/professor_items/seeds/alias_supplement.json")
    if sup.exists():
        for cid, aliases in json.loads(sup.read_text(encoding="utf-8")).items():
            for a in aliases:
                na = re.sub(r"[\s_\-.'’]+", "", str(a)).lower()
                if len(na) >= 2:
                    idx.append((na, cid, len(na)))
    idx.sort(key=lambda x: -x[2])
    return idx


def dx_candidates(text, idx, topn=4):
    hay = re.sub(r"[\s_\-.'’]+", "", text).lower()
    hits, seen = [], set()
    for na, cid, _ in idx:
        if na in hay and cid not in seen:
            seen.add(cid); hits.append(cid)
        if len(hits) >= topn:
            break
    return hits


def modality_of(text):
    for name, pat in MODALITY:
        if re.search(pat, text, re.I):
            return name
    return ""


def main() -> int:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    idx = load_alias_index()
    files = []
    for d in SRC_DIRS:
        if d.exists():
            files += sorted(list(d.rglob("*.hwp")) + list(d.rglob("*.hwpx")))
    ledger, stats = [], Counter()
    for p in files:
        turn, period, qs, author = parse_name(p.stem)
        key = f"{turn}{period}_{('-'.join(map(str, qs)) or 'x')}"
        text, imgs = hwp_convert(p, key)
        dxs = dx_candidates(text, idx) if text else []
        mod = modality_of(text) if text else ""
        stats["files"] += 1
        stats["with_text"] += 1 if text else 0
        stats["with_img"] += 1 if imgs else 0
        stats["images"] += len(imgs)
        stats["with_dx"] += 1 if dxs else 0
        if mod:
            stats[f"mod:{mod}"] += 1
        ledger.append({"key": key, "turn": turn, "period": period, "qnos": qs,
                       "author": author, "src": p.name, "images": imgs,
                       "dx_candidates": dxs, "modality_guess": mod,
                       "verified": False})
    (OUT / "label_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")

    # 검수 시트
    cards = []
    for r in ledger:
        if not r["images"]:
            continue
        dx = " / ".join(r["dx_candidates"]) if r["dx_candidates"] else "<i>후보 없음</i>"
        for im in r["images"]:
            cards.append(
                f'<div class="c"><img src="images/{html.escape(im["file"])}" loading="lazy">'
                f'<div class="k">{html.escape(r["turn"])}턴 {html.escape(r["period"])}교시 · '
                f'{html.escape("-".join(map(str, r["qnos"])) or "?")}번</div>'
                f'<div class="m">{html.escape(r["modality_guess"] or "모달리티?")}</div>'
                f'<div class="d">{dx}</div></div>')
    doc = ("<!doctype html><meta charset='utf-8'><title>PMA 이미지 라벨 검수</title>"
           "<style>body{font-family:sans-serif;background:#f5f5f5;padding:16px}"
           ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}"
           ".c{background:#fff;border:1px solid #ddd;border-radius:8px;padding:8px}"
           ".c img{width:100%;max-height:220px;object-fit:contain}"
           ".k{font-size:12px;font-weight:800;color:#334155;margin-top:4px}"
           ".m{font-size:11px;color:#b45309;font-weight:700}"
           ".d{font-size:13px;color:#0b5450;font-weight:800}</style>"
           f"<h2>PMA 이미지 ↔ 진단명 라벨 검수 ({len(cards)}장)</h2>"
           "<p>진단명이 틀리거나 비면 label_ledger.json에서 수정하세요. verified:true 로 바꾼 것만 문항 생성에 사용합니다.</p>"
           f"<div class='g'>{''.join(cards)}</div>")
    (OUT / "review_sheet.html").write_text(doc, encoding="utf-8")

    print(f"PMA 해설 {stats['files']}개 처리")
    print(f"  텍스트 추출 {stats['with_text']} · 이미지 보유 {stats['with_img']} · 이미지 {stats['images']}장")
    print(f"  진단명 후보 확보 {stats['with_dx']}")
    mods = {k[4:]: v for k, v in stats.items() if k.startswith("mod:")}
    print(f"  모달리티 추정: {mods}")
    print(f"[대장] {OUT/'label_ledger.json'}\n[검수시트] {OUT/'review_sheet.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
