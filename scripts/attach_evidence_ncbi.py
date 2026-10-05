#!/usr/bin/env python3
"""concept_tags → PubMed(NCBI E-utilities) 근거 자동 부착 (배치).

원칙:
- 외부로 나가는 것은 개념(concept_tags)뿐 — 문항 지문 원문은 보내지 않는다.
- 관련성 게이트: 논문 제목에 질환어가 실제로 포함될 때만 채택(자동 top-hit 오탐 방지).
- 가이드라인/리뷰 우선. 확신 매칭이 없으면 evidence_status="needs_review"로 플래그.
- 근거는 draft. 사람 검토 게이트 통과 전까지 확정 아님.
- 개념 단위 캐시로 중복 질의 방지.

사용:  python3 scripts/attach_evidence_ncbi.py [--domain heme|pma|all] [--limit N]
"""

import json
import glob
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

EXTRACT_DIR = Path("data_private/course_exams/extracted")
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# 약어·한글 → 표준 영문 질환명 (부분일치)
CANONICAL = [
    ("myelodysplastic", "myelodysplastic syndrome"), ("골수형성이상", "myelodysplastic syndrome"),
    ("mds", "myelodysplastic syndrome"),
    ("chronic myelomonocytic", "chronic myelomonocytic leukemia"), ("cmml", "chronic myelomonocytic leukemia"),
    ("acute myeloid", "acute myeloid leukemia"), ("aml", "acute myeloid leukemia"),
    ("acute lymphoblastic", "acute lymphoblastic leukemia"), ("acute_leukemia", "acute leukemia"),
    ("chronic myeloid", "chronic myeloid leukemia"), ("cml", "chronic myeloid leukemia"),
    ("chronic lymphocytic", "chronic lymphocytic leukemia"), ("cll", "chronic lymphocytic leukemia"),
    ("multiple myeloma", "multiple myeloma"),
    ("hodgkin", "hodgkin lymphoma"), ("lymphoma", "lymphoma"),
    ("von willebrand", "von willebrand disease"), ("vwd", "von willebrand disease"),
    ("hemophilia", "hemophilia"),
    ("immune thrombocytopenia", "immune thrombocytopenia"), ("itp", "immune thrombocytopenia"),
    ("thrombotic thrombocytopenic", "thrombotic thrombocytopenic purpura"), ("ttp", "thrombotic thrombocytopenic purpura"),
    ("disseminated intravascular", "disseminated intravascular coagulation"), ("dic", "disseminated intravascular coagulation"),
    ("aplastic anemia", "aplastic anemia"), ("aplastic anaemia", "aplastic anemia"),
    ("iron_deficiency", "iron deficiency anemia"), ("iron deficiency", "iron deficiency anemia"),
    ("hereditary_spherocytosis", "hereditary spherocytosis"), ("spherocytosis", "hereditary spherocytosis"),
    ("anemia_of_chronic_disease", "anemia of chronic disease"),
    ("ckd_anemia", "anemia of chronic kidney disease"),
    ("transfusion_reaction", "transfusion reaction"),
    ("infectious_mononucleosis", "infectious mononucleosis"),
    ("graves", "graves disease"),
    ("pulmonary_embolism", "pulmonary embolism"),
    ("abdominal_aortic_aneurysm", "abdominal aortic aneurysm"),
    ("bacterial_meningitis", "bacterial meningitis"),
    ("nephrotic_syndrome", "nephrotic syndrome"),
    ("cord_compression", "spinal cord compression"),
    ("cup", "carcinoma of unknown primary"),
    ("hepatoblastoma", "hepatoblastoma"), ("neuroblastoma", "neuroblastoma"),
]

# 질환이 아닌 개념(방사선물리·기전·방법·평가지표) — 근거 자동매칭 대상에서 제외 → 검토 필요.
NON_DISEASE = re.compile(
    r"\b(fractionation|hypofractionation|bragg|radon|dosimetry|linac|reoxygenation|5rs|"
    r"hepcidin|fibrinolysis|downstaging|neoadjuvant|adjuvant|recist|response_evaluation|"
    r"checkpoint|immunotherapy|pharmacokinetic|voriconazole|corticosteroid|"
    r"palliative_sedation|dose|gray|sievert)\b", re.I)

GENE_SCORE = re.compile(
    r"^[A-Z0-9]{2,}(_[A-Z0-9]+)+$|"
    r"\b(tet2|sf3b1|dnmt3a|flt3|npm1|jak2|bcr|abl1?|kras|nras|idh[12]|ipss|r[_ ]?ipss|"
    r"cytogenetics?|karyotype|blasts?|mutation|variant|threshold|score|antibody|receptor|"
    r"aptt|ptt|scan|level|marker|staging|점수|기준|평가|예후|유전자|변이|수치)\b", re.I)


def normalize(token):
    return re.sub(r"_", " ", str(token or "")).strip()


def is_gene_or_score(token):
    t = str(token or "").strip()
    return (not t) or bool(GENE_SCORE.search(t)) or bool(NON_DISEASE.search(t))


def canonical_name(tags):
    if not tags:
        return ""
    # 1) 첫 태그(primary concept) 우선 — 2차 태그의 약어가 주제를 가로채지 않게.
    primary = tags[0]
    s0 = normalize(primary).lower()
    for key, name in CANONICAL:
        if key in s0:
            return name
    if not is_gene_or_score(primary):
        return s0
    # 2) primary가 유전자/점수면 다음 질환 태그로.
    for cand in tags[1:]:
        s = normalize(cand).lower()
        for key, name in CANONICAL:
            if key in s:
                return name
        if not is_gene_or_score(cand):
            return s
    return ""


def significant_words(name):
    return [w for w in re.split(r"\s+", name.lower()) if len(w) >= 4
            and w not in {"disease", "syndrome", "anemia", "chronic", "acute"}]


def eutils_get(path, params):
    url = f"{EUTILS}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)


def fetch_evidence(disease):
    """질환명으로 PubMed 검색 → 관련성 필터 통과한 상위 1건 반환(없으면 None)."""
    term = f'{disease} AND (guideline[pt] OR review[pt] OR practice guideline[pt])'
    try:
        s = eutils_get("esearch.fcgi", {"db": "pubmed", "retmode": "json",
                                        "retmax": 6, "sort": "relevance", "term": term})
        ids = s.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return None
        time.sleep(0.34)
        summ = eutils_get("esummary.fcgi", {"db": "pubmed", "retmode": "json", "id": ",".join(ids)})
        result = summ.get("result", {})
        sig = significant_words(disease) or [disease.lower()]
        for pid in ids:
            art = result.get(pid, {})
            title = art.get("title", "")
            tl = title.lower()
            if not any(w in tl for w in sig):  # 관련성 게이트: 제목에 질환어 포함
                continue
            doi = ""
            for aid in art.get("articleids", []):
                if aid.get("idtype") == "doi":
                    doi = aid.get("value", "")
            year = (art.get("pubdate", "") or "").split(" ")[0][:4]
            types = [t.lower() for t in art.get("pubtype", [])]
            kind = "guideline" if any("guideline" in t for t in types) else "review"
            return {
                "source": "PubMed", "pmid": pid, "doi": doi, "title": title,
                "journal": art.get("fulljournalname") or art.get("source", ""),
                "year": year, "type": kind,
                "url": f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                "matched_concept": disease, "retrieved_via": "ncbi_auto", "status": "draft",
            }
        return None
    except Exception as exc:
        print(f"    [warn] {disease}: {exc}", file=sys.stderr)
        return None


def files_for(domain):
    all_files = glob.glob(str(EXTRACT_DIR / "*.json"))
    if domain.endswith(".json") or domain.startswith(("COURSE_", "PMA_", "COMPREHENSIVE_")):
        # 특정 파일 stem 지정.
        stem = domain[:-5] if domain.endswith(".json") else domain
        return [str(EXTRACT_DIR / f"{stem}.json")]
    if domain == "heme":
        return sorted(f for f in all_files if "HEMATOLOGY" in f)
    if domain == "pma":
        return sorted(f for f in all_files if "PMA_" in f)
    return sorted(f for f in all_files if "HEMATOLOGY" in f or "PMA_" in f)


def main():
    domain = "all"
    limit = None
    args = sys.argv[1:]
    if "--file" in args:
        domain = args[args.index("--file") + 1]
    if "--domain" in args:
        domain = args[args.index("--domain") + 1]
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    # 큐레이션 데모(검증 완료)는 보존.
    KEEP = {f"COURSE_2_20230308_HEMATOLOGY_ONCOLOGY_과정시험_Q00{n}" for n in (1, 3, 4, 5, 6)}
    if "--reset" in args:
        cleared = 0
        for f in files_for(domain):
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            ch = False
            for q in d.get("questions", []):
                if q.get("question_id") in KEEP:
                    continue
                ev = q.get("evidence") or []
                auto = bool(ev) or ("자동 매칭" in (q.get("evidence_note") or "")) or (
                    q.get("evidence_status") in ("draft", "needs_review"))
                if auto:
                    q.pop("evidence", None)
                    q.pop("evidence_status", None)
                    q.pop("evidence_note", None)
                    cleared += 1
                    ch = True
            if ch:
                Path(f).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[reset] 자동부착 근거 {cleared}건 제거 (큐레이션 근거는 보존)")
        return 0

    cache = {}  # disease -> evidence|None
    grand = {"q": 0, "attached": 0, "needs_review": 0, "already": 0}
    for f in files_for(domain):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        touched = 0
        for q in d.get("questions", []):
            tags = (q.get("labels") or {}).get("concept_tags") or []
            if not (q.get("stem") and tags):
                continue
            if q.get("evidence"):
                grand["already"] += 1
                continue
            grand["q"] += 1
            if limit and touched >= limit:
                continue
            disease = canonical_name(tags)
            if not disease:
                q["evidence"] = []
                q["evidence_status"] = "needs_review"
                q["evidence_note"] = "질환 개념을 특정할 수 없어 검토 필요"
                grand["needs_review"] += 1
                touched += 1
                continue
            if disease not in cache:
                cache[disease] = fetch_evidence(disease)
                time.sleep(0.34)
            ev = cache[disease]
            if ev:
                q["evidence"] = [dict(ev)]
                q["evidence_status"] = "draft"
                grand["attached"] += 1
            else:
                q["evidence"] = []
                q["evidence_status"] = "needs_review"
                q["evidence_note"] = f"'{disease}' 관련 가이드라인/리뷰 자동 매칭 실패 — 사람 확인 필요"
                grand["needs_review"] += 1
            touched += 1
        if touched:
            Path(f).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[set] {Path(f).name[:46]:<46} 처리 {touched}")
    print(f"[done] domain={domain} | 대상 {grand['q']} | 부착 {grand['attached']} | "
          f"검토필요 {grand['needs_review']} | 이미있음 {grand['already']} | 고유개념 {len(cache)}")


if __name__ == "__main__":
    raise SystemExit(main())
