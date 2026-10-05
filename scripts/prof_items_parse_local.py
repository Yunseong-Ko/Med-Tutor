#!/usr/bin/env python3
"""교수 기출 HML 문항은행 → 시드 초안 CSV + 이미지 대장 (로컬 전용, 비전송).

⚠️ 보안 규칙(Secure_Item_Generation_Protocol): 이 스크립트는 로컬에서만 실행.
   stdout에는 통계만 출력한다(원문 문장·이미지 내용 미출력).
   산출 CSV의 원문발췌 열은 **사용자 검수 전용** — AI는 읽지 않는다.
   AI 입력은 검수 후 prof_seeds_strip.py 가 만든 seeds_approved.csv 만.

입력: data_private/professor_items/originals/2024년/**/*.hml (문항당 1파일, 파일명=관리번호)
출력: seeds/seeds_draft_review.csv  (사람 검수용 — 원문발췌·선지 포함)
      images/ledger.json + images/*.png|jpg  (해시 대장)
"""
import base64
import csv
import glob
import hashlib
import html
import json
import re
import sys
import unicodedata
import zlib
from pathlib import Path

BASE = Path("data_private/professor_items")
SRC = BASE / "originals"
IMG_DIR = BASE / "images"
SEED_DIR = BASE / "seeds"

CIRC = "①②③④⑤⑥⑦⑧⑨"
LEADIN = [
    (r"진단[은명]?[은는]?\s*\??|가장\s*가능성\s*(높|있)|의심되는\s*질환|무슨\s*병", "진단"),
    (r"검사[는를]?\s*\??|시행(해야|할)\s*검사|우선\s*시행|확진.*검사|필요한\s*검사", "검사"),
    (r"치료[는를]?\s*\??|처치[는를]?|투여할\s*약|적절한\s*(치료|처치|약물)|수술|다음\s*단계", "치료"),
]


def read_hml(p: Path) -> str:
    """HML 인코딩 혼재(euc-kr/UTF-8) 대응: XML 선언 → cp949 → utf-8 → ignore 순."""
    head = p.read_bytes()[:200]
    m = re.search(rb'encoding="([^"]+)"', head)
    decl = (m.group(1).decode("ascii", "ignore").lower() if m else "")
    encs = []
    if "euc" in decl or "949" in decl or "ksc" in decl or "ks_c" in decl:
        encs = ["cp949", "utf-8"]
    elif "utf-16" in decl:
        encs = ["utf-16", "cp949", "utf-8"]
    elif "utf" in decl:
        encs = ["utf-8", "cp949"]
    else:
        encs = ["cp949", "utf-8"]
    for e in encs:
        try:
            return p.read_bytes().decode(e)
        except Exception:
            continue
    return p.read_bytes().decode(encs[0], errors="ignore")


def strip_html_text(raw: str) -> str:
    """HML(XML)에서 표시 텍스트만 회수."""
    # BinData 블록 제거(대용량)
    raw = re.sub(r"<BINDATA[^>]*>[^<]*</BINDATA>", " ", raw, flags=re.S)
    chars = re.findall(r"<CHAR[^>]*>([^<]*)</CHAR>", raw)
    if not chars:  # fallback: 태그 제거
        chars = [re.sub(r"<[^>]+>", " ", raw)]
    text = " ".join(html.unescape(c) for c in chars)
    return re.sub(r"\s+", " ", text).strip()


def paragraphs_of(raw: str):
    """HML <P>블록별 표시 텍스트 목록."""
    out = []
    for pm in re.finditer(r"<P [^>]*>(.*?)</P>", raw, flags=re.S):
        chars = re.findall(r"<CHAR[^>]*>([^<]*)</CHAR>", pm.group(1))
        t = re.sub(r"\s+", " ", " ".join(html.unescape(c) for c in chars)).strip()
        if t:
            out.append(t)
    return out


def split_item(text: str, paras=None):
    """stem / choices 분리. 1) ①~⑨ 문자 2) 문단구조 폴백(끝의 짧은 문단 연속 ≥4 = 선지)."""
    first = None
    for c in CIRC:
        i = text.find(c)
        if i >= 0 and (first is None or i < first):
            first = i
    if first is not None:
        stem, rest = text[:first].strip(), text[first:]
        parts = re.split(r"([" + CIRC + r"])", rest)
        choices, cur = {}, None
        for p in parts:
            if p in CIRC:
                cur = str(CIRC.index(p) + 1)
                choices[cur] = ""
            elif cur:
                choices[cur] += p
        return stem, {k: re.sub(r"\s+", " ", v).strip() for k, v in choices.items() if v.strip()}
    # 폴백: 문단 구조 — 끝에서부터 짧은 문단(<100자) 연속 구간을 선지로
    if paras and len(paras) >= 5:
        j = len(paras)
        while j > 0 and len(paras[j - 1]) < 100:
            j -= 1
        tail = paras[j:]
        if 4 <= len(tail) <= 9:
            stem = " ".join(paras[:j]).strip()
            return stem, {str(i + 1): t for i, t in enumerate(tail)}
    return text, {}


def guess_axis(stem: str):
    tail = stem[-80:]
    for pat, axis in LEADIN:
        if re.search(pat, tail):
            return axis
    for pat, axis in LEADIN:
        if re.search(pat, stem):
            return axis
    return ""


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
    # 소화기 등 보강 사전(의학 상식 기반, 원본 무관)
    sup_p = Path("data_private/professor_items/seeds/alias_supplement.json")
    if sup_p.exists():
        sup = json.loads(sup_p.read_text(encoding="utf-8"))
        for cid, aliases in sup.items():
            for a in aliases:
                na = re.sub(r"[\s_\-.'’]+", "", str(a)).lower()
                if len(na) >= 2:
                    idx.append((na, cid, len(na)))
    idx.sort(key=lambda x: -x[2])
    return idx


def suggest_concept(text, idx, topn=3):
    hay = re.sub(r"[\s_\-.'’]+", "", text).lower()
    hits = []
    for na, cid, ln in idx:
        if na in hay and cid not in hits:
            hits.append(cid)
        if len(hits) >= topn:
            break
    return " / ".join(hits)


TEST_KW = re.compile(r"검사|촬영|조영|CT|MRI|초음파|내시경|조직검사|생검|배양|항원|항체|PCR|X-?선|X-?ray|스캔|신티|측정|도말")
TX_KW = re.compile(r"투여|절제|수술|치료|요법|항생제|차단제|억제제|이식|경화요법|결찰|스텐트|배액|중단|교체|mg|처방")


def guess_axis_v2(stem, choices, idx):
    """선지 내용 기반 판정 → 실패 시 stem lead-in."""
    if choices:
        vals = list(choices.values())
        dz = sum(1 for v in vals if suggest_concept(v, idx, topn=1))
        te = sum(1 for v in vals if TEST_KW.search(v))
        tx = sum(1 for v in vals if TX_KW.search(v))
        best = max(("진단", dz), ("검사", te), ("치료", tx), key=lambda x: x[1])
        if best[1] >= 2:
            return best[0]
    return guess_axis(stem)


def extract_images(raw: str, item_id: str):
    """BinData → 파일 저장, (개수, 해시목록) 반환. 10KB 미만은 로고 취급 제외."""
    out = []
    for m in re.finditer(r"<BINDATA([^>]*)>([A-Za-z0-9+/=\s]{100,})</BINDATA>", raw):
        attrs, b64 = m.group(1), m.group(2)
        try:
            data = base64.b64decode(re.sub(r"\s+", "", b64))
        except Exception:
            continue
        if "Compress" in attrs and '"false"' not in attrs.lower():
            try:
                data = zlib.decompress(data, -15)
            except Exception:
                try:
                    data = zlib.decompress(data)
                except Exception:
                    pass
        if len(data) < 10_000:
            continue
        if data[:3] == b"\xff\xd8\xff":
            ext = "jpg"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            ext = "png"
        elif data[:2] == b"BM":
            ext = "bmp"
        elif data[:4] in (b"GIF8",):
            ext = "gif"
        else:
            ext = "bin"
        h = hashlib.sha256(data).hexdigest()[:12]
        name = f"{item_id}_{h}.{ext}"
        (IMG_DIR / name).write_bytes(data)
        out.append({"file": name, "sha12": h, "bytes": len(data), "ext": ext})
    return out


def main() -> int:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    idx = load_alias_index()
    files = sorted(glob.glob(str(SRC / "2024년" / "**" / "*.hml"), recursive=True))
    rows, ledger = [], {}
    stats = {"files": 0, "with_choices": 0, "axis": {}, "concept_suggested": 0, "images": 0, "img_items": 0}
    for f in files:
        p = Path(f)
        item_id = p.stem.split("_")[-1]
        subject = unicodedata.normalize("NFC", p.parent.name)
        raw = read_hml(p)
        raw_nobin = re.sub(r"<BINDATA[^>]*>[^<]*</BINDATA>", " ", raw, flags=re.S)
        text = strip_html_text(raw)
        stem, choices = split_item(text, paragraphs_of(raw_nobin))
        axis = guess_axis_v2(stem, choices, idx)
        concept = suggest_concept(stem + " " + " ".join(choices.values()), idx)
        imgs = extract_images(raw, item_id)
        stats["files"] += 1
        if choices:
            stats["with_choices"] += 1
        if axis:
            stats["axis"][axis] = stats["axis"].get(axis, 0) + 1
        if concept:
            stats["concept_suggested"] += 1
        if imgs:
            stats["img_items"] += 1
            stats["images"] += len(imgs)
            ledger[item_id] = imgs
        rows.append({
            "seed_id": item_id, "subject": subject,
            "질환개념(제안)": concept, "평가축(제안)": axis,
            "정답번호(입력)": "", "정답개념(입력)": "", "오답감별군(입력)": "",
            "난이도(상중하)": "중", "사용(Y/N)": "Y",
            "이미지수": len(imgs), "이미지파일": ";".join(i["file"] for i in imgs),
            "이미지핵심소견(입력)": "",
            "원문발췌_검수전용": stem[:150],
            "선지_검수전용": " | ".join(f"{k}){v[:40]}" for k, v in sorted(choices.items())),
            "비고": "",
        })
    out_csv = SEED_DIR / "seeds_draft_review.csv"
    with out_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # 셀 구조 확인용 CSV (사람 전용): 파일당 28셀을 열로 — 사용자가 "몇 번 셀=무엇"만 알려주면 확정 파싱
    cell_rows = []
    for f in files:
        p = Path(f)
        raw = read_hml(p)
        raw = re.sub(r"<BINDATA[^>]*>[^<]*</BINDATA>", " ", raw, flags=re.S)
        cells = []
        for cm in re.finditer(r"<CELL[^>]*>(.*?)</CELL>", raw, flags=re.S):
            chars = re.findall(r"<CHAR[^>]*>([^<]*)</CHAR>", cm.group(1))
            t = re.sub(r"\s+", " ", " ".join(html.unescape(c) for c in chars)).strip()
            cells.append(t[:120])
        row = {"seed_id": p.stem.split("_")[-1], "subject": unicodedata.normalize("NFC", p.parent.name)}
        for i in range(28):
            row[f"cell_{i+1:02d}"] = cells[i] if i < len(cells) else ""
        cell_rows.append(row)
    cells_csv = SEED_DIR / "cells_review.csv"
    with cells_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cell_rows[0].keys()))
        w.writeheader()
        w.writerows(cell_rows)
    print(f"[셀구조 CSV] {cells_csv}  ← 사람 전용, 처음 2~3행만 보고 셀 번호 역할만 알려주세요")
    (IMG_DIR / "ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    # stdout: 통계만
    print(f"HML {stats['files']}개 파싱 → 시드 초안 {len(rows)}행")
    print(f"  선지 분리 성공: {stats['with_choices']}/{stats['files']}")
    print(f"  평가축 자동제안: {dict(stats['axis'])} (빈칸 {stats['files']-sum(stats['axis'].values())})")
    print(f"  질환개념 자동제안: {stats['concept_suggested']}개 행")
    print(f"  이미지: {stats['images']}개 추출({stats['img_items']}개 문항) → images/")
    print(f"[검수용 CSV] {out_csv}  ← 사람 전용, AI는 읽지 않음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
