#!/usr/bin/env python3
"""Harrison 22e 목차 → concept_tag 매핑 테이블 생성 + 문항에 harrison_ref 부착.

- ~/Downloads/Database/04_Contents.pdf 목차 파싱 → 챕터(번호·제목·페이지·PART·PDF파일)
- concept_tag(영어 snake_case) ↔ 챕터 제목 토큰 매칭
- 부산대 AccessMedicine 토픽검색(Harrison 22e bookid=3541, 사용자 교내접속 확인) 포함
"""

import re
import json
import sys
import urllib.parse
from pathlib import Path

import fitz

DB = Path("/Users/goyunseong/Downloads/Database")
CONTENTS = DB / "04_Contents.pdf"
EXTRACTED = Path("data_private/course_exams/extracted")
OUT_MAP = Path("data_private/harrison/concept_to_harrison.json")
ACCESSMED = "https://accessmedicine.mhmedical.com"
BOOKID = "3541"  # Harrison's Principles of Internal Medicine, 22e

# PART 번호 → PDF 파일명
PART_PDF = {
    1: "08_PART 1 The Profession of Medicine.pdf",
    2: "09_PART 2 Cardinal Manifestations and Presentation of Diseases.pdf",
    3: "10_PART 3 Pharmacology.pdf",
    4: "11_PART 4 Oncology and Hematology.pdf",
    5: "12_PART 5 Infectious Diseases.pdf",
    6: "13_PART 6 Disorders of the Cardiovascular System.pdf",
    7: "14_PART 7 Disorders of the Respiratory System.pdf",
    8: "15_PART 8 Critical Care Medicine.pdf",
    9: "16_PART 9 Disorders of the Kidney and Urinary Tract.pdf",
    10: "17_PART 10 Disorders of the Gastrointestinal System.pdf",
    11: "18_PART 11 Immune-Mediated, Inflammatory, and Rheumatologic Disorders.pdf",
    12: "19_PART 12 Endocrinology and Metabolism.pdf",
    13: "20_PART 13 Neurologic Disorders.pdf",
    14: "21_PART 14 Poisoning, Drug Overdose, and Envenomation.pdf",
    15: "22_PART 15 Disorders Associated with Environmental Exposures.pdf",
    16: "23_PART 16 Genes, the Environment, and Disease.pdf",
    17: "24_PART 17 Global Medicine.pdf",
    18: "25_PART 18 Aging.pdf",
    19: "26_PART 19 Consultative Medicine.pdf",
    20: "27_PART 20 Emerging Topics in Clinical Medicine.pdf",
}

STOP = {"the", "of", "and", "in", "a", "to", "with", "disease", "disorders", "disorder",
        "syndrome", "acute", "chronic", "and", "other", "diseases", "for", "s"}


def parse_toc():
    doc = fitz.open(str(CONTENTS))
    full = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    lines = full.split("\n")
    chapters = []
    cur_part = 1
    buf = ""
    for ln in lines:
        pm = re.search(r"\bPART\s+(\d+)\b", ln)
        if pm:
            cur_part = int(pm.group(1))
        buf = (buf + " " + ln).strip()
        m = re.search(r"(?:^|\s)(\d{1,3})\s+([A-Z][A-Za-z0-9 ,:/\-’'()&]+?)\s*\.{2,}\s*(\d+)\s*$", buf)
        if m:
            no, title, page = int(m.group(1)), re.sub(r"\s+", " ", m.group(2)).strip(), int(m.group(3))
            title = re.sub(r"^(The Profession of Medicine\s+\d+\s+)", "", title)  # 첫 항목 노이즈
            if 1 <= no <= 520 and len(title) > 3:
                chapters.append({"chapter": no, "title": title, "page": page,
                                 "part": cur_part, "pdf": PART_PDF.get(cur_part)})
            buf = ""
        if len(buf) > 240:
            buf = ""
    # 챕터 번호 오름차순 유지, 중복 제거
    seen = set()
    uniq = []
    for c in chapters:
        if c["chapter"] in seen:
            continue
        seen.add(c["chapter"])
        uniq.append(c)
    return uniq


def toks(s):
    return [t for t in re.sub(r"[^a-z0-9 ]", " ", s.lower().replace("_", " ")).split()
            if t and t not in STOP and len(t) > 2]


def build_idf(chap_tokens):
    import math
    N = len(chap_tokens)
    df = {}
    for chtok in chap_tokens:
        for t in chtok:
            df[t] = df.get(t, 0) + 1
    return {t: math.log(N / c) for t, c in df.items()}, df


def match_concept(concept, chapters, chap_tokens, idf, df):
    ct = set(toks(concept))
    if not ct:
        return None
    best, best_score, best_maxidf, best_n = None, 0.0, 0.0, 0
    for c, chtok in zip(chapters, chap_tokens):
        inter = ct & chtok
        if not inter:
            continue
        w = sum(idf.get(t, 0) for t in inter)
        # 애매한 수식어(insufficiency/adult 등)는 '분별 단어'로 인정하지 않음
        AMBIG = {"insufficiency", "adult", "primary", "secondary", "acquired",
                 "juvenile", "congenital", "chronic", "failure", "injury"}
        distinct = inter - AMBIG
        maxidf = max((idf.get(t, 0) for t in distinct), default=0.0)
        score = w * (0.6 + 0.4 * len(inter) / max(1, len(ct)))
        # 게이트: (거의 유일 질환어 df<=2) 또는 (분별어 2개↑)
        ok = (maxidf >= 5.7) or (len(distinct) >= 2 and maxidf >= 4.6)
        if ok and score > best_score:
            best_score, best, best_maxidf, best_n = score, c, maxidf, len(inter)
    if best:
        conf = "high" if (best_maxidf >= 5.7 or best_n >= 2) else "medium"
        return best, round(best_score, 2), conf
    return None


# 큰 질환 단위 큐레이션: concept → 목차에서 찾을 제목 키워드
CURATED = {
    "copd": "Chronic Obstructive Pulmonary Disease",
    "heart_failure": "Heart Failure",
    "gastric_cancer": "Gastrointestinal Tract Cancer",
    "nephrotic_syndrome": "Glomerular Diseases",
    "hepatocellular_carcinoma": "Tumors of the Liver",
    "bipolar_disorder": "Psychiatric Disorders",
    "major_depressive_disorder": "Psychiatric Disorders",
    "schizophrenia": "Psychiatric Disorders",
    "generalized_anxiety_disorder": "Psychiatric Disorders",
    "panic_disorder": "Psychiatric Disorders",
    "thyroid_nodule": "Thyroid Gland Physiology",
    "hyperthyroidism": "Hyperthyroidism",
    "hypothyroidism": "Hypothyroidism",
    "hepatitis_b": "Chronic Hepatitis",
    "viral_hepatitis": "Acute Viral Hepatitis",
    "hepatitis_c": "Chronic Hepatitis",
    "congenital_heart_disease": "Congenital Heart Disease in the Adult",
    "hypokalemia": "Fluid and Electrolyte",
    "hyperkalemia": "Fluid and Electrolyte",
    "thrombocytopenia": "Bleeding and Thrombosis",
    "immune_thrombocytopenia": "Coagulation Disorders",
    "silicosis": "Occupational and Environmental Lung Disease",
    "preeclampsia": "Medical Disorders During Pregnancy",
    "severe_preeclampsia": "Medical Disorders During Pregnancy",
    "eclampsia": "Medical Disorders During Pregnancy",
    "choledocholithiasis": "Diseases of the Gallbladder and Bile Ducts",
    "acute_cholecystitis": "Diseases of the Gallbladder and Bile Ducts",
    "cholangitis": "Diseases of the Gallbladder and Bile Ducts",
    "insomnia": "Sleep Disorders",
    "obstructive_sleep_apnea": "Sleep Apnea",
    "acute_otitis_media": "Sore Throat, Earache",
    "allergic_rhinitis": "Allergies, Anaphylaxis",
    "asthma": "Asthma",
    "pneumonia": "Pneumonia",
    "pulmonary_embolism": "Pulmonary Thromboembolism",
    "deep_vein_thrombosis": "Pulmonary Thromboembolism",
    "acute_coronary_syndrome": "ST-Segment Elevation Myocardial Infarction",
    "diabetic_ketoacidosis": "Diabetes Mellitus",
    "type_1_diabetes": "Diabetes Mellitus",
    "type_2_diabetes": "Diabetes Mellitus",
    "achalasia": "Diseases of the Esophagus",
    "peptic_ulcer_disease": "Peptic Ulcer Disease",
    "ulcerative_colitis": "Inflammatory Bowel Disease",
    "crohn_disease": "Inflammatory Bowel Disease",
    "hepatic_encephalopathy": "Cirrhosis",
    "esophageal_variceal_bleeding": "Cirrhosis",
    "hematochezia": "Gastrointestinal Bleeding",
    "upper_gi_bleeding": "Gastrointestinal Bleeding",
    "meningitis": "Acute Meningitis",
    "bacterial_meningitis": "Acute Meningitis",
    "rheumatoid_arthritis": "Rheumatoid Arthritis",
    "gout": "Gout",
    "acromegaly": "Pituitary Tumor",
    "hyperprolactinemia": "Pituitary Tumor",
    "carbon_monoxide_poisoning": "Poisoning",
    "acute_pericarditis": "Pericardial Disease",
    "vibrio_vulnificus": "Vibrio",
    "leptospirosis": "Leptospirosis",
    "malaria": "Malaria",
    "epilepsy": "Seizures and Epilepsy",
    "parkinson_disease": "Parkinson",
}


def resolve_curated(keyword, chapters):
    kw = keyword.lower()
    hits = [c for c in chapters if kw in c["title"].lower()]
    if not hits:
        return None
    return min(hits, key=lambda c: len(c["title"]))


def accessmed_url(title):
    return f"{ACCESSMED}/SearchResults.aspx?q={urllib.parse.quote(title)}&searchType=1&book={BOOKID}"


def main():
    commit = "--commit" in sys.argv
    chapters = parse_toc()
    chap_tokens = [set(toks(c["title"])) for c in chapters]
    idf, df = build_idf(chap_tokens)
    print(f"[TOC] 파싱된 챕터: {len(chapters)}개")

    # 문항 concept 수집
    concepts = {}
    files = sorted(EXTRACTED.glob("COMPREHENSIVE_2026_1CHA_*.json"))
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        for q in d["questions"]:
            for t in (q.get("labels") or {}).get("concept_tags") or []:
                concepts.setdefault(t, 0)
                concepts[t] += 1

    concept_map = {}
    for concept in sorted(concepts):
        r = match_concept(concept, chapters, chap_tokens, idf, df)
        if r:
            c, score, conf = r
            concept_map[concept] = {
                "chapter": c["chapter"], "title": c["title"], "page": c["page"],
                "part": c["part"], "pdf": c["pdf"], "match_score": score,
                "confidence": conf, "status": "draft_auto", "needs_review": True,
                "accessmedicine": accessmed_url(c["title"]),
            }
    # 큐레이션 override(큰 질환 단위) — 자동보다 우선
    cur_n = 0
    for concept, kw in CURATED.items():
        if concept not in concepts:
            continue
        c = resolve_curated(kw, chapters)
        if c:
            concept_map[concept] = {
                "chapter": c["chapter"], "title": c["title"], "page": c["page"],
                "part": c["part"], "pdf": c["pdf"], "match_score": 99,
                "confidence": "curated", "status": "curated", "needs_review": True,
                "accessmedicine": accessmed_url(c["title"]),
            }
            cur_n += 1
    matched = len(concept_map)
    print(f"[match] concept {len(concepts)}개 중 {matched}개 매핑 (자동 + 큐레이션 {cur_n})")

    if commit:
        OUT_MAP.parent.mkdir(parents=True, exist_ok=True)
        OUT_MAP.write_text(json.dumps({"source": "Harrison 22e TOC", "edition": "22e", "bookid": BOOKID,
                                       "chapters_indexed": len(chapters),
                                       "concept_to_harrison": concept_map},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
        # 문항에 harrison_ref 부착(문항 concept 중 매칭되는 첫 챕터)
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            n = 0
            for q in d["questions"]:
                refs = []
                for t in (q.get("labels") or {}).get("concept_tags") or []:
                    if t in concept_map:
                        refs.append({"concept": t, **concept_map[t]})
                if refs:
                    # 최고 점수 1개를 대표로
                    q["harrison_ref"] = sorted(refs, key=lambda r: -r["match_score"])[0]
                    q["harrison_ref"]["alternates"] = [r["title"] for r in refs[1:3]]
                    n += 1
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  {f.stem}: harrison_ref {n}/80")
        print(f"[commit] 매핑 테이블 → {OUT_MAP}")
    else:
        # 샘플 미리보기
        for concept in list(concept_map)[:12]:
            m = concept_map[concept]
            print(f"  {concept:32s} → Ch.{m['chapter']} {m['title'][:42]} (p.{m['page']}, PART{m['part']})")


if __name__ == "__main__":
    raise SystemExit(main())
