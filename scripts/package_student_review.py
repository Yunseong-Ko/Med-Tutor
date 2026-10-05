#!/usr/bin/env python3
"""학생 배포 패키지 조립 — 학생별로 [해설집 + 검토표]를 한 폴더에 묶는다.

두 파일을 따로 배포하면 학생이 짝을 잘못 찾는 사고가 난다(31명 × 2파일).
학생당 폴더 하나에 자기 것만 들어가게 하고, 안내서는 최상위에 1부 둔다.
출력: exports/배포_학생검토/  + 같은 이름의 zip
"""
import argparse
import shutil
import zipfile
from pathlib import Path

BOOKS = Path("data_private/professor_items/exports/student_review_books")
OUT = Path("data_private/professor_items/exports/배포_학생검토")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets-zip", required=True, help="교수님 배포 검토표 zip")
    ap.add_argument("--guide", help="학생용 안내서 docx")
    ap.add_argument("--plan", help="피드백 수집·집계 계획 문서(선택)")
    args = ap.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    z = zipfile.ZipFile(args.sheets_zip)
    sheets = {}
    for n in z.namelist():
        if not n.endswith(".xlsx"):
            continue
        digits = "".join(ch for ch in Path(n).stem if ch.isdigit())
        if digits:
            sheets[digits.zfill(2)] = n

    made, missing = 0, []
    # Word가 열어둔 파일에 만드는 잠금파일(~$…)이 섞이면 폴더가 하나 더 생긴다
    for book in sorted(b for b in BOOKS.glob("*.docx") if not b.name.startswith("~$")):
        idx = "".join(ch for ch in book.stem if ch.isdigit()).zfill(2)
        folder = OUT / f"학생_{idx}"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(book, folder / book.name)
        src = sheets.get(idx)
        if src:
            (folder / Path(src).name).write_bytes(z.read(src))
        else:
            missing.append(idx)
        made += 1

    for extra in (args.guide, args.plan):
        if extra and Path(extra).exists():
            shutil.copy2(extra, OUT / Path(extra).name)

    zip_path = OUT.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as out:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                out.write(p, p.relative_to(OUT.parent))

    size = zip_path.stat().st_size / 1024 / 1024
    print(f"학생 폴더 {made}개 · 검토표 누락 {len(missing)}")
    if missing:
        print("  누락:", missing)
    print(f"[패키지] {zip_path}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
