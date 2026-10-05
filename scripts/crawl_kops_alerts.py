"""KOPS(환자안전보고학습시스템) 환자안전 주의경보 목록 인덱스 크롤러.

목적: 각 주의경보(실제 사고→예방지침)를 소명 훈련케이스 소재로 매핑하기 위한 '인덱스'(번호·제목·날짜) 수집.
페이징: 폼필드 `page`(pageIndex 아님) POST 제출, totalPage=6.
주의: KOPS 콘텐츠 재사용 라이선스 미확인 — 본 스크립트는 목록 메타데이터(사실정보)만 수집.
      본문 전문의 제품 내 재배포는 KOPS 이용허락 확인 후 진행. 산출물은 data_private(로컬)만.
"""
from __future__ import annotations

import os, re, json, time, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_private/medlegal/imports/kops"
URL = "https://www.kops.or.kr/portal/aam/atent/atentAlarmCntrmsrList.do"
_CONTACT = os.getenv("PACCINE_CONTACT_EMAIL", "")   # 연락처는 환경변수로만
UA = {"User-Agent": "Mozilla/5.0 (research index" + (f"; contact: {_CONTACT}" if _CONTACT else "") + ")"}
ROW = re.compile(r"fnMoveDetail\((\d+)\)[^>]*>([\s\S]*?)</a>([\s\S]{0,300}?)(20\d\d\.\d\d\.\d\d)")


def fetch(page: int) -> str:
    data = urllib.parse.urlencode({"page": page}).encode()
    req = urllib.request.Request(URL, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "replace")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items, seen = [], set()
    for p in range(1, 7):
        for m in ROW.finditer(fetch(p)):
            no = m.group(1)
            if no in seen:
                continue
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
            title = title.lstrip("알림").strip()
            seen.add(no)
            items.append({"atentAlarmNo": no, "title": title, "date": m.group(4)})
        print(f"page {p}: 누적 {len(items)}")
        time.sleep(0.4)
    (OUT / "kops_alerts_index.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"총 {len(items)}건 → {OUT}/kops_alerts_index.json")


if __name__ == "__main__":
    main()
