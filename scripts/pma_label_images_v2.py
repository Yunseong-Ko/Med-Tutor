#!/usr/bin/env python3
"""PMA 해설 HWP → **문항 자료 이미지만** 라벨링 (v2, 위치 기반).

v1 실패: 문서의 모든 이미지를 수집 → 풀이(해설) 파트의 참고사진(교과서 그림·도표)이 섞임.
v2 규칙: 문서는 [헤더행] → [문항본문행] → [풀이 (작성자)행] → [풀이내용행] 의 반복 구조.
  - 헤더행: `2026_6월_4학년_PMA NN교시 MM번 (분과)`
  - **문항 자료 = 헤더행 다음 ~ '풀이' 행 이전의 행에 있는 이미지만** 채택.
  - '풀이' 행 이후 이미지는 레퍼런스이므로 전량 제외.
진단명: 문항 본문 + 풀이 텍스트에서 추출(라벨링 근거는 풀이가 더 정확).
stdout: 통계만. 원문 미출력.
출력: pma_labels_v2/{images/, label_ledger.json, review_sheet.html}
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
    Path("data_private/professor_items/originals/pma"),
    Path("data_private/professor_items/originals/pma_4gyosi"),
]
OUT = Path("data_private/professor_items/pma_labels_v2")
IMG_DIR = OUT / "images"

# 주의: hwp5html 출력은 '2026_6 월 _4 학년 _PMA 01 교시 10번' 처럼 토큰 사이 공백이 섞인다.
HEADER = re.compile(r"PMA[\s_]*(\d{1,2})\s*교시\s*(\d{1,3})\s*번\s*[\(（]?\s*([^)）\n]{0,20})")
SOLUTION = re.compile(r"^\s*풀이\s*[\(（]|^\s*풀이\s*[:：]|^\s*해설\s*[\(（:：]")
MODALITY = [
    ("ECG", r"심전도|ECG|EKG"),
    ("가슴X선", r"가슴\s*X\s*선|흉부\s*(방사선|X-?ray|촬영)|chest\s*(x-?ray|PA)|단순\s*흉부"),
    ("가슴CT", r"가슴\s*(전산화단층|CT)|chest\s*CT|흉부\s*CT"),
    ("복부CT", r"복부\s*(전산화단층|CT)|abdomen\s*CT|배\s*CT"),
    ("뇌CT/MRI", r"뇌\s*(CT|자기공명|MRI)|brain\s*(CT|MRI)|머리\s*(CT|MRI)"),
    ("초음파", r"초음파|ultrasound|sonograph|심장초음파"),
    ("내시경", r"내시경|endoscop"),
    ("혈액도말", r"말초혈액\s*도말|blood\s*smear|도말검사"),
    ("병리조직", r"조직\s*소견|병리|생검|현미경|H&E"),
    ("검사결과표", r"검사\s*결과|참고치"),
]
FULLW = str.maketrans("０１２３４５６７８９", "0123456789")


def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def row_text(row_html):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", row_html))).strip()


def parse_doc(path: Path):
    """(헤더 문항번호, 교시, 분과, 문항텍스트, 풀이텍스트, 문항이미지 bytes목록) 리스트."""
    out = []
    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run(["hwp5html", "--output", td, str(path)], capture_output=True, timeout=180)
        except Exception:
            return out
        x = Path(td) / "index.xhtml"
        if not x.exists():
            return out
        raw = x.read_text(encoding="utf-8", errors="ignore")
        bindir = Path(td) / "bindata"
        rows = re.findall(r"<tr.*?</tr>", raw, re.S)
        cur = None
        for r in rows:
            t = row_text(r)
            imgs = re.findall(r'<img[^>]*src="bindata/([^"]+)"', r)
            hm = HEADER.search(t.translate(FULLW))
            if hm:
                if cur:
                    out.append(cur)
                cur = {"period": hm.group(1).lstrip("0") or "0", "qno": int(hm.group(2)),
                       "subject": hm.group(3).strip(), "q_text": "", "sol_text": "",
                       "q_imgs": [], "in_solution": False}
                continue
            if cur is None:
                continue
            if SOLUTION.match(t) or t.startswith("풀이"):
                cur["in_solution"] = True
            if cur["in_solution"]:
                cur["sol_text"] += " " + t
            else:
                cur["q_text"] += " " + t
                for name in imgs:   # 문항 영역 이미지만 채택
                    f = bindir / name
                    if f.exists():
                        try:
                            cur["q_imgs"].append(f.read_bytes())
                        except Exception:
                            pass
        if cur:
            out.append(cur)
    return out


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


def dx_candidates(text, idx, topn=3):
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
    ledger, st = [], Counter()
    for p in files:
        turn = "A" if re.search(r"A\s*턴", nfc(p.stem)) else ("B" if re.search(r"B\s*턴", nfc(p.stem)) else "C")
        for q in parse_doc(p):
            st["items"] += 1
            if not q["q_imgs"]:
                st["no_qimg"] += 1
                continue
            st["with_qimg"] += 1
            key = f"{turn}{q['period']}_{q['qno']}"
            saved = []
            for data in q["q_imgs"]:
                if len(data) < 8000:
                    continue
                ext = ("jpg" if data[:3] == b"\xff\xd8\xff" else
                       "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else
                       "bmp" if data[:2] == b"BM" else
                       "gif" if data[:4] == b"GIF8" else "bin")
                if ext == "bin":
                    continue
                h = hashlib.sha256(data).hexdigest()[:12]
                name = f"{key}_{h}.{ext}"
                (IMG_DIR / name).write_bytes(data)
                saved.append({"file": name, "sha12": h, "bytes": len(data)})
            if not saved:
                continue
            st["images"] += len(saved)
            full = q["q_text"] + " " + q["sol_text"]
            dxs = dx_candidates(full, idx)
            mod = modality_of(q["q_text"]) or modality_of(full)
            if dxs:
                st["with_dx"] += 1
            if mod:
                st[f"mod:{mod}"] += 1
            ledger.append({"key": key, "turn": turn, "period": q["period"], "qno": q["qno"],
                           "subject_hint": q["subject"], "src": p.name, "images": saved,
                           "dx_candidates": dxs, "modality_guess": mod, "verified": False,
                           "q_text": re.sub(r"\s+", " ", q["q_text"]).strip()[:1500],
                           "sol_text": re.sub(r"\s+", " ", q["sol_text"]).strip()[:3000]})
    (OUT / "label_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")

    cards = []
    for r in ledger:
        dx = " / ".join(r["dx_candidates"]) if r["dx_candidates"] else "<i>후보 없음</i>"
        for im in r["images"]:
            cards.append(f'<div class="c"><img src="images/{html.escape(im["file"])}" loading="lazy">'
                         f'<div class="k">{html.escape(r["turn"])}턴 {html.escape(r["period"])}교시 {r["qno"]}번 '
                         f'· {html.escape(r["subject_hint"])}</div>'
                         f'<div class="m">{html.escape(r["modality_guess"] or "모달리티?")}</div>'
                         f'<div class="d">{dx}</div></div>')
    (OUT / "review_sheet.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>PMA 문항자료 이미지 검수 v2</title>"
        "<style>body{font-family:sans-serif;background:#f5f5f5;padding:16px}"
        ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}"
        ".c{background:#fff;border:1px solid #ddd;border-radius:8px;padding:8px}"
        ".c img{width:100%;max-height:220px;object-fit:contain}"
        ".k{font-size:12px;font-weight:800;color:#334155;margin-top:4px}"
        ".m{font-size:11px;color:#b45309;font-weight:700}"
        ".d{font-size:13px;color:#0b5450;font-weight:800}</style>"
        f"<h2>PMA <b>문항 자료</b> 이미지만 ({len(cards)}장) — 풀이 참고사진 제외</h2>"
        f"<div class='g'>{''.join(cards)}</div>", encoding="utf-8")

    print(f"문항 블록 {st['items']} · 문항이미지 보유 {st['with_qimg']} · 이미지 없음 {st['no_qimg']}")
    print(f"  채택 이미지 {st['images']}장 · 진단후보 {st['with_dx']}")
    print("  모달리티:", {k[4:]: v for k, v in st.items() if k.startswith("mod:")})
    print(f"[대장] {OUT/'label_ledger.json'}\n[검수] {OUT/'review_sheet.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
