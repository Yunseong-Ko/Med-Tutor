#!/usr/bin/env python3
"""이미지 라벨 128종 → 플랫폼 generation_grounding 팩(압축판) 일괄 생성.

플랫폼 파이프라인 그대로: concept_registry 매칭 → 정제된 온톨로지 필드만 추출.
원본 시험 텍스트는 어떤 경로로도 읽지 않는다 (registry + Harrison 포인터만).

압축 규칙: 풀팩 ~40KB → 프롬프트용 ~4KB.
  - cognitive_model 전체 유지 (C.C/단서/제시자료 — 플랫폼의 핵심 자산)
  - clinical_axes: 축별 summary + 목록 상위 6개
  - distractor_pool: 상위 8개 label (+provenance)
  - evidence: Harrison chapter/page 포인터만 (파일경로·sha 제거)
출력: pma_labels_v2/grounding_packs.json + 매칭 통계
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generation_grounding import build_generation_grounding  # noqa: E402

OUT = Path("data_private/professor_items/pma_labels_v2")

# 라벨 표기 → 레지스트리가 알아듣는 검색어 보정
TOPIC_FIX = {
    "정상 흉부 X선(대조 영상)": None,       # 질환 아님 → fallback
    "정상 HSG": None,
    "정상 태아심박동(Category I)": None,
    "무반응성 태아심박동(non-reactive NST)": "태아곤란",
    "variable deceleration": "태아곤란",
    "reversed end-diastolic flow": "태아발육지연",
    "reticular pattern": "특발성 폐섬유증",
    "reticular opacity": "특발성 폐섬유증",
    "폐고름집(공동 내 액체층)": "폐농양",
    "전벽 ST분절상승 심근경색": "심근경색",
    "하벽 ST분절상승 심근경색": "심근경색",
    "De Winter 양상(근위부 LAD 폐색)": "심근경색",
    "좌심실 비대": "고혈압",
    "좌심실비대(strain pattern 동반)": "고혈압",
    "얇은 자궁내막(자궁내막 위축)": "아셔만증후군",
    "위 출혈": "상부위장관출혈",
    "위암으로 인한 위 날문 폐쇄": "위암",
    "beak appearance": "식도이완불능증",
    "식도이완불능증(achalasia)": "식도이완불능증",
    "폐렴(공기기관지음영 동반 경화)": "지역사회획득 폐렴",
    "기질화폐렴(Masson body)": "기질화 폐렴",
    "규폐증(Silicosis)": "규폐증",
    "결핵 CXR": "폐결핵",
    "폐결핵 CXR": "폐결핵",
    "폐결핵 CT": "폐결핵",
    "결핵성 흉막염": "결핵성 흉막염",
    "심실조기수축(PVC)": "심실조기수축",
    "심실조기박동": "심실조기수축",
    "3도 방실차단 상태": "방실차단",
    "Aortic Stenosis": "대동맥판협착증",
    "대동맥판협착증(좌심실비대)": "대동맥판협착증",
    "Mitral Stenosis": "승모판협착증",
    "승모판협착증(좌심방 확대)": "승모판협착증",
    "Mitral Stenosis, 심도자술 소견": "승모판협착증",
    "Mitral Stenosis, CXR 소견": "승모판협착증",
    "Irregularly irregular rhythm": "심방세동",
    "심방세동": "심방세동",
    "heart failure": "심부전",
    "Cardiomegaly": "심부전",
    "hypertrophy": "대동맥판협착증",
    "간세포암(동맥기 조영증강·washout)": "간세포암",
    "HCC": "간세포암",
    "악성 난소종양(다방성 낭성 종괴)": "난소암",
    "좌측 난소 종괴": "난소암",
    "우측 난소 부위에 종괴": "성숙 낭성 기형종",
    "트리코모나스 질염": "질염",
    "니켈 접촉피부염": "접촉피부염",
    "콜린성 두드러기": "두드러기",
    "재발성 어깨관절 전방탈구": "어깨 탈구",
    "경막외혈종": "경막외출혈",
    "급성 횡단척수염": "횡단성 척수염",
    "에탐부톨 시신경병증": "시신경염",
    "군날개(pterygium)": None,
    "되돌이후두신경 손상": "갑상선암",
    "경부 열상": None,
    "유방울혈": "유방염",
    "유방 파제트병": "유방 파제트병",
    "심부정맥혈전증(DVT)": "심부정맥혈전증",
    "심부정맥혈전증(DVT)다리 사진": "심부정맥혈전증",
    "외상성 복강내출혈(FAST 양성)": "복부 외상",
    "횡격막 손상": "복부 외상",
    "Diaphragm injury": "복부 외상",
    "흉관 손상(암죽흉수)": "흉수",
    "양측 감각신경성 난청": "소음성 난청",
    "신농양": "신우신염",
    "수혈관련 급성폐손상(TRALI)": "수혈 부작용",
    "만성콩팥병(흉부 X선 이상 없음)": "만성콩팥병",
    "제한형 전신경화증(간질폐질환 동반)": "전신경화증",
    "저칼륨혈증(QT연장·U파)": "저칼륨혈증",
    "고칼륨혈증": "고칼륨혈증",
    "열대열 말라리아": "말라리아",
    "결핵성 림프절염": "결핵성 림프절염",
    "1분기 산전검사 이상(다운증후군)": "다운증후군",
    "분만 진통 시작": "조기진통",
    "샘창자폐쇄 초음파": "샘창자폐쇄",
    "Air-fluid level": "폐농양",
    "COPD": "만성폐쇄폐질환",
    "만성폐쇄폐질환(COPD)": "만성폐쇄폐질환",
    "정상 CXR": None,
    "정상 CXR, 진단명 AF": "심방세동",
    "bird-beak": "식도이완불능증",

    "장폐색": "장폐색",
    "소장폐색": "장폐색",
}


def trim(x, n):
    return x[:n] if isinstance(x, list) else x


def condense(pack: dict) -> dict:
    axes = {}
    for ax, v in (pack.get("clinical_axes") or {}).items():
        if isinstance(v, dict):
            axes[ax] = {k: trim(w, 6) for k, w in v.items()
                        if k in ("summary", "key_steps", "factors", "staging_or_grading",
                                 "first_line", "options", "indications", "tests")}
        elif isinstance(v, list):
            axes[ax] = v[:6]
    ev = (pack.get("evidence") or {}).get("harrison_route") or {}
    dp = [{"label": d.get("label"), "why": d.get("provenance")}
          for d in (pack.get("distractor_pool") or [])[:8]]
    return {
        "disease_concept_id": pack.get("disease_concept_id"),
        "label": pack.get("label"),
        "assessment_domains": pack.get("assessment_domains"),
        "cognitive_model": pack.get("cognitive_model"),
        "clinical_axes": axes,
        "distractor_pool": dp,
        "evidence": {"harrison_chapter": ev.get("chapter"), "harrison_page": ev.get("page"),
                     "edition": ev.get("edition")},
        "needs_review": bool(pack.get("needs_review")),
    }


def main() -> int:
    rows = json.loads((OUT / "labels_manual.json").read_text(encoding="utf-8"))
    uniq = {}
    for r in rows:
        uniq.setdefault((r["dx"], r["modality"]), r)

    packs, st = {}, Counter()
    for (dx, modality), r in uniq.items():
        # topic 후보 순서: ① 라벨 직접(꼬리 제거) ② TOPIC_FIX 보정 — 직접 매칭이
        # 이기게 한다(별칭 보강 후에는 직접 매칭이 더 정확; FIX가 오히려 가리는 사고 방지).
        direct = re.split(r"[,:：(]", dx)[0].strip() or dx
        fix = TOPIC_FIX.get(dx, "__absent__")
        if fix is None and direct == dx:
            candidates = []            # 질환 아님으로 명시된 라벨
        elif fix in ("__absent__", None):
            candidates = [direct]
        else:
            candidates = [direct, fix]
        entry = {"dx": dx, "modality": modality, "key": r["key"], "image": r["image"],
                 "subject": r["subject_hint"], "topic": candidates[0] if candidates else None}
        if not candidates:
            st["no_concept"] += 1
            entry["grounding"] = None
            entry["grounding_status"] = "non_disease_label"
        else:
            entry["grounding"] = None
            entry["grounding_status"] = "no_match"
            try:
                for topic in candidates:
                    g = build_generation_grounding(topic)
                    status = (g.get("match") or {}).get("status")
                    if status == "matched" and g.get("pack"):
                        entry["grounding"] = condense(g["pack"])
                        entry["grounding_status"] = "matched"
                        entry["topic"] = topic
                        st["matched"] += 1
                        break
                    entry["grounding_status"] = status or "no_match"
                else:
                    st["fallback"] += 1
            except Exception as e:
                entry["grounding_status"] = f"error:{type(e).__name__}"
                st["error"] += 1
        packs[f"{dx}|{modality}"] = entry

    (OUT / "grounding_packs.json").write_text(
        json.dumps(packs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"고유 라벨 {len(packs)} · 온톨로지 매칭 {st['matched']} · fallback {st['fallback']} "
          f"· 질환아님 {st['no_concept']} · 오류 {st['error']}")
    misses = [e["dx"] for e in packs.values() if e["grounding_status"] not in ("matched", "non_disease_label")]
    if misses:
        print("미매칭:", " · ".join(misses[:20]))
    sizes = [len(json.dumps(e["grounding"], ensure_ascii=False)) for e in packs.values() if e["grounding"]]
    if sizes:
        print(f"압축팩 크기: 중앙값 {sorted(sizes)[len(sizes)//2]:,}B · 최대 {max(sizes):,}B")
    print(f"[출력] {OUT/'grounding_packs.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
