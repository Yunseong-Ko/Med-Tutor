#!/usr/bin/env python3
"""검수 참여자 계정표 생성 — 이메일 + 파생 비밀번호 + 개인 검수 링크.

비밀번호는 저장하지 않는다. (APP_ROSTER_SECRET, 이메일)에서 서버가 매번 계산하고,
이 스크립트가 같은 규칙으로 배포표를 만든다. 명단이나 시크릿이 바뀌면 표를 다시 뽑으면 된다.

입력: 명단 파일(줄바꿈 구분). 형식은 둘 다 허용
        r01,강민석          ← 아이디,이름 (이름은 배포용 참고, 로그인엔 아이디만 쓴다)
        r01
사용:
  APP_ROSTER_SECRET=... python3 scripts/build_roster_credentials.py \
      --names data_private/professor_items/review/roster.txt \
      --base-url https://<railway-domain>
출력: review/roster_credentials.csv  (교수님께 전달 → 학생 개별 배포)
      review/roster_emails.txt       (Railway APP_ROSTER_EMAILS 에 붙여넣을 한 줄)
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api_server import derive_roster_password  # noqa: E402

OUT = Path("data_private/professor_items/review")


def load_roster(path: Path) -> list[tuple[str, str]]:
    """(아이디, 이름) 목록. 로그인 아이디는 번호이고 이름은 배포표 참고용이다."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            uid, name = (part.strip() for part in line.split(",", 1))
        else:
            uid, name = line, ""
        if uid:
            rows.append((uid.lower(), name))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", required=True, help="명단 파일")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--secret", default=os.environ.get("APP_ROSTER_SECRET", ""))
    args = ap.parse_args()
    if not args.secret:
        print("! APP_ROSTER_SECRET 이 필요합니다 (환경변수 또는 --secret)")
        return 1

    roster = load_roster(Path(args.names))
    if not roster:
        print("! 명단이 비어 있습니다")
        return 1

    # 문항 배정표가 있으면 개인 링크를 붙인다
    assign = defaultdict(list)
    ap_path = OUT / "assignment.csv"
    if ap_path.exists():
        for r in csv.DictReader(ap_path.open(encoding="utf-8-sig")):
            assign[r["검수자"]].append(f"AIGEN_{int(r['세트'])}_{int(r['번호']):03d}")
    slots = sorted(assign) or []

    OUT.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    with (OUT / "roster_credentials.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["아이디", "이름", "비밀번호", "배정 문항수", "검수 링크"])
        for i, (uid, name) in enumerate(roster):
            pw = derive_roster_password(uid, args.secret)
            ids = assign[slots[i]] if i < len(slots) else []
            link = (f"{base}/student/reader.html?ids={','.join(ids)}"
                    f"&count={len(ids)}&mode=study") if ids else f"{base}/student/"
            w.writerow([uid, name, pw, len(ids), link])

    (OUT / "roster_emails.txt").write_text(
        ",".join(uid for uid, _ in roster), encoding="utf-8")

    print(f"참여자 {len(roster)}명 · 배정표 슬롯 {len(slots)}개")
    if slots and len(roster) != len(slots):
        print(f"  ! 인원({len(roster)})과 배정 슬롯({len(slots)}) 수가 다릅니다 — 앞에서부터 매칭했습니다")
    print(f"[계정표] {OUT/'roster_credentials.csv'}  ← 교수님 전달용")
    print(f"[명단]   {OUT/'roster_emails.txt'}       ← Railway APP_ROSTER_EMAILS 값")
    print("  비밀번호는 파일에 보관하지 않아도 됩니다 — 시크릿+명단으로 언제든 재생성됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
