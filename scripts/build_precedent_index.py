"""소명 판례 근거(grounding) 모듈 — Phase 1 (공통 엔진, 검증 전 착수 안전).

입력(로컬, data_private/medlegal/processed/):
  - kmedi_precedents.json      : 상담 데이터에서 추출한 판례 인용 145건
  - kmedi_consultation.jsonl   : 케이스별 참고판례(ref1~3_title) 포함

출력:
  - precedent_index.json       : 인용 → {court, date, case_no, case_type, raw} 구조화
  - case_precedent_links.json  : 케이스(질문/진료과) ↔ 인용 판례 엣지(지식그래프)

법제처 판례 Open API 리졸버(선택): 무료 키(OC) 발급 후 --resolve.
  키 발급: https://open.law.go.kr → 오픈API → 신청(이메일 기반 OC 코드)
  검색: http://www.law.go.kr/DRF/lawSearch.do?OC=<KEY>&target=prec&query=<사건번호>&type=JSON
  본문: http://www.law.go.kr/DRF/lawService.do?OC=<KEY>&target=prec&ID=<판례일련번호>&type=JSON
  (data.go.kr 15057123/15059269와 동일 백엔드. korean-law-mcp로도 대체 가능.)
"""
from __future__ import annotations

import json, re, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data_private/medlegal/processed"

# 사건부호 → (심급, 사건종류)
CASE_CODES = {
    "가합": ("1심", "민사"), "가단": ("1심", "민사"), "가소": ("1심", "민사소액"),
    "나": ("2심(항소)", "민사"), "다": ("3심(상고)", "민사"),
    "고합": ("1심", "형사"), "고단": ("1심", "형사"), "고정": ("1심", "형사약식"),
    "노": ("2심(항소)", "형사"), "도": ("3심(상고)", "형사"),
    "구합": ("1심", "행정"), "구단": ("1심", "행정"),
    "누": ("2심(항소)", "행정"), "두": ("3심(상고)", "행정"),
    "헌마": ("헌재", "헌법"), "헌바": ("헌재", "헌법"), "헌가": ("헌재", "헌법"),
}
COURT_PAT = re.compile(r"(대법원|[가-힣]+고법|[가-힣]+지법|[가-힣]+가정법원|헌법재판소|[가-힣]+법원)")
DATE_PAT = re.compile(r"(\d{2,4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.")
CASENO_PAT = re.compile(r"(\d{2,4})([가-힣]{1,2})(\d+)(?:,\s*\d+)*")


def norm_year(y: str) -> str:
    y = int(y)
    if y < 100:  # "12" → 2012, "78" → 1978
        y += 2000 if y <= 30 else 1900
    return str(y)


def case_type(caseno: str):
    m = CASENO_PAT.search(caseno)
    if not m:
        return None, None
    code = m.group(2)
    for k, v in CASE_CODES.items():
        if code.startswith(k):
            return v
    return None, None


def parse_citation(raw: str) -> dict:
    raw = raw.strip()
    court = (COURT_PAT.search(raw) or [None, None])[0] if COURT_PAT.search(raw) else None
    court = COURT_PAT.search(raw).group(1) if COURT_PAT.search(raw) else None
    dm = DATE_PAT.search(raw)
    date = f"{norm_year(dm.group(1))}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}" if dm else None
    cm = CASENO_PAT.search(raw)
    caseno = cm.group(0) if cm else None
    simg, ctype = case_type(caseno) if caseno else (None, None)
    return {"raw": raw, "court": court, "date": date, "case_no": caseno,
            "simg": simg, "case_type": ctype, "resolved": None}


def build_index():
    cites = json.loads((PROC / "kmedi_precedents.json").read_text(encoding="utf-8"))
    index = [parse_citation(c) for c in cites]
    (PROC / "precedent_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    # 케이스 ↔ 판례 엣지
    cases = [json.loads(l) for l in (PROC / "kmedi_consultation.jsonl").open(encoding="utf-8")]
    links = []
    for c in cases:
        refs = [c.get(f"ref{i}_title", "").strip() for i in (1, 2, 3)]
        refs = [r for r in refs if r and COURT_PAT.search(r)]
        if refs:
            links.append({"case_title": c.get("title", ""), "dept": c.get("clinical_dept", ""),
                          "precedents": refs})
    (PROC / "case_precedent_links.json").write_text(
        json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
    return index, links


def resolve_all(index, oc_key):
    import urllib.request, urllib.parse
    base = "http://www.law.go.kr/DRF/lawSearch.do"
    ok = 0
    for rec in index:
        if not rec["case_no"]:
            continue
        q = urllib.parse.urlencode({"OC": oc_key, "target": "prec",
                                    "query": rec["case_no"], "type": "JSON"})
        try:
            with urllib.request.urlopen(f"{base}?{q}", timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            # 응답 구조에서 판례일련번호/사건명 추출 (키명은 응답에 맞춰 조정)
            rec["resolved"] = data
            ok += 1
        except Exception as e:
            rec["resolved"] = {"error": str(e)}
    (PROC / "precedent_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"resolved {ok}/{len(index)} via 법제처 API")


def main():
    index, links = build_index()
    import collections
    courts = collections.Counter(r["court"] for r in index)
    types = collections.Counter(r["case_type"] for r in index)
    parsed = sum(1 for r in index if r["court"] and r["date"] and r["case_no"])
    print(f"판례 인덱스: {len(index)}건 (완전파싱 {parsed})")
    print("  법원 top:", dict(courts.most_common(6)))
    print("  사건종류:", dict(types))
    print(f"케이스↔판례 엣지: {len(links)}건")
    print(f"wrote -> {PROC}/precedent_index.json, case_precedent_links.json")

    if "--resolve" in sys.argv:
        oc = os.environ.get("LAW_OC_KEY")
        if not oc:
            print("\n[--resolve] LAW_OC_KEY 환경변수 없음. open.law.go.kr에서 무료 OC 키 발급 후:")
            print("  LAW_OC_KEY=<키> python3 scripts/build_precedent_index.py --resolve")
            return
        resolve_all(index, oc)


if __name__ == "__main__":
    main()
