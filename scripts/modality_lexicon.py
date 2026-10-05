#!/usr/bin/env python3
"""이미지 modality 표준 어휘·동의어 사전 (라벨 스키마 v3) — 단일 소스 오브 트루스.

배경(설문 T2, 4건): "초음파 사진이라 해놓고 CT/내시경" — 문두가 말하는 검사종류와
실제 이미지(라벨)가 다른 문항이 새고 있다. 원인은 라벨 modality가 자유서술
(labels_manual.json 실측 31종 비표준)이라 문두-라벨 대조가 어휘 수준에서 새는 것.

여기서 표준 enum + 동의어 사전을 한곳에 두고, 아래 세 소비자가 전부 이 모듈을 쓴다:
  - 라벨 도구(build_label_tool.py)의 modality 필수 드롭다운
  - 수집 게이트(collect_wf_items.py)의 문두-라벨 modality 하드 대조
  - 기존 v2 라벨(labels_manual.json)의 v3 마이그레이션(migrate_label_row)
프로토콜 문서: docs/Image_Labeling_Protocol_20260831.md

사용:
  python3 scripts/modality_lexicon.py    # 기존 라벨 파일의 enum 커버리지 자가점검
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

LABELS = Path("data_private/professor_items/pma_labels_v2/labels_manual.json")

# ── 표준 enum ────────────────────────────────────────────────────────────────
# labels_manual.json에서 실제 쓰인 31종을 기저 검사종류로 정규화한 것.
# 부위(가슴/복부/뇌…)는 body_region, 세부(심장초음파·위내시경…)는 modality_detail로 분리.
MODALITY_ENUM = (
    "단순X선", "CT", "MRI", "초음파", "심전도", "내시경", "투시조영", "혈관조영",
    "핵의학", "병리조직", "혈액도말", "현미경도말", "임상사진", "안과검사",
    "기능검사그래프", "검사결과표", "모식도", "기타",
)

# ── 레거시 라벨값 → (modality, modality_detail, body_region) ─────────────────
# v2 라벨 도구 드롭다운 전체 + labels_manual.json 실측값 전부를 포괄한다.
LEGACY_MODALITY_MAP = {
    # X선
    "가슴X선": ("단순X선", "", "가슴"),
    "복부X선": ("단순X선", "", "복부"),
    "척추/사지X선": ("단순X선", "", "척추·사지"),
    # CT / MRI
    "가슴CT": ("CT", "", "가슴"),
    "복부CT": ("CT", "", "복부"),
    "뇌CT": ("CT", "", "뇌"),
    "어깨CT": ("CT", "", "어깨"),
    "경부CT": ("CT", "", "경부"),
    "뇌MRI": ("MRI", "", "뇌"),
    "척수 MRI": ("MRI", "", "척수"),
    "뇌CT/MRI": ("CT", "뇌CT/MRI 병기", "뇌"),          # 모호 → needs_fix
    # 초음파
    "초음파": ("초음파", "", ""),
    "복부초음파": ("초음파", "", "복부"),
    "심장초음파": ("초음파", "심장초음파", "심장"),
    "산과초음파": ("초음파", "산과초음파", ""),
    "부인과초음파": ("초음파", "부인과초음파", "골반"),
    "유방촬영/초음파": ("기타", "유방촬영/초음파", "유방"),  # X선·초음파 혼재 → needs_fix
    # 심전도 계열
    "ECG": ("심전도", "", ""),
    "홀터": ("심전도", "홀터", ""),
    # 내시경
    "내시경": ("내시경", "", ""),
    "위내시경": ("내시경", "위내시경", ""),
    "대장내시경": ("내시경", "대장내시경", ""),
    "기관지내시경": ("내시경", "기관지내시경", ""),
    "방광경": ("내시경", "방광경", ""),
    # 조영·혈관·핵의학
    "자궁난관조영": ("투시조영", "자궁난관조영", "골반"),
    "식도조영": ("투시조영", "식도조영", "식도"),
    "MRCP/담도조영": ("투시조영", "MRCP/담도조영", "담도"),
    "IVP/요로조영": ("투시조영", "IVP/요로조영", "요로"),
    "혈관조영": ("혈관조영", "", ""),
    "골스캔/핵의학": ("핵의학", "골스캔", ""),
    "PET-CT": ("핵의학", "PET-CT", ""),
    # 병리·도말·현미경
    "병리조직": ("병리조직", "", ""),
    "골수도말/생검": ("병리조직", "골수도말/생검", "골수"),
    "말초혈액도말": ("혈액도말", "말초혈액도말", ""),
    "습식도말(wet smear)": ("현미경도말", "습식도말", ""),
    "그람염색/배양": ("현미경도말", "그람염색/배양", ""),
    "소변현미경": ("현미경도말", "소변현미경", ""),
    "객담검사": ("현미경도말", "객담검사", ""),
    # 사진·안과·기능검사
    "임상 사진": ("임상사진", "", ""),
    "피부병변 사진": ("임상사진", "피부병변", "피부"),
    "안저/눈": ("안과검사", "", "눈"),
    "안과 검사 자료": ("안과검사", "", "눈"),
    "NST(태아심박동)": ("기능검사그래프", "NST(태아심박동)", ""),
    "뇌파(EEG)": ("기능검사그래프", "뇌파(EEG)", "뇌"),
    "근전도(EMG/NCS)": ("기능검사그래프", "근전도(EMG/NCS)", ""),
    "청력검사": ("기능검사그래프", "청력검사", "귀"),
    "운동부하검사": ("기능검사그래프", "운동부하검사", "심장"),
    "폐기능검사": ("기능검사그래프", "폐기능검사", "폐"),
    # 표·모식도·기타
    "검사결과표": ("검사결과표", "", ""),
    "도표·그래프": ("기타", "도표·그래프", ""),
    "약물/처방 자료": ("기타", "약물/처방 자료", ""),
    "해부 모식도": ("모식도", "해부 모식도", ""),
    "임상 자료": ("기타", "임상 자료", ""),                 # 모호 → needs_fix
    "기타": ("기타", "", ""),
}

# 기저 검사종류를 특정할 수 없는 레거시값 → 마이그레이션 시 needs_fix=true
AMBIGUOUS_LEGACY = {"임상 자료", "뇌CT/MRI", "유방촬영/초음파"}

# ── 문두 동의어 사전 ─────────────────────────────────────────────────────────
# 원칙: **정밀도 우선** — 애매한 패턴(예: 그냥 "사진", "검사 결과", "병리"만)은 넣지
# 않는다. 게이트는 "문두 언급이 있는데 라벨이 그 집합에 없을 때만" 탈락시키므로,
# 못 잡는 것(재현율 손실)은 통과일 뿐이지만 오탐(정밀도 손실)은 과잉 탈락이 된다.
# 영문 약어는 한글 인접을 허용하되 영문자 인접은 차단: (?<![A-Za-z])…(?![A-Za-z])
# ("뇌CT"는 잡고 "Hct"는 안 잡는다. \b는 한글도 \w라 "뇌CT"를 놓친다.)
STEM_PATTERNS = {
    "단순X선": [
        r"X\s*-?\s*선", r"엑스선", r"(?<![A-Za-z])X-?ray", r"(?<![A-Za-z])CXR(?![A-Za-z])",
        r"(?<![A-Za-z])KUB(?![A-Za-z])", r"단순\s*촬영", r"단순\s*방사선", r"방사선\s*사진",
        r"(?i)radiograph",
    ],
    "CT": [
        r"(?<![A-Za-z])CT(?![A-Za-z])", r"(?<![A-Za-z])HRCT(?![A-Za-z])",
        r"전산화\s*단층", r"컴퓨터\s*단층", r"(?i)computed\s+tomograph",
    ],
    "MRI": [
        r"(?<![A-Za-z])MRI(?![A-Za-z])", r"자기\s*공명", r"(?i)magnetic\s+resonance",
        r"확산\s*강조", r"(?<![A-Za-z])DWI(?![A-Za-z])",
    ],
    "초음파": [
        r"초음파", r"(?i)ultraso", r"(?i)sonogra", r"(?<![A-Za-z])US(?![A-Za-z])",
        r"(?i)(?<![A-Za-z])sono(?![A-Za-z])",  # 임상 관용 축약 '복부 sono' — 단독 어절만
        r"도플러", r"(?i)doppler", r"(?<![A-Za-z])FAST(?![A-Za-z])",
    ],
    "심전도": [
        r"심전도", r"(?<![A-Za-z])(ECG|EKG)(?![A-Za-z])", r"(?i)electrocardio",
    ],
    "내시경": [
        r"내시경", r"방광경", r"(?<![A-Za-z])EGD(?![A-Za-z])",
        r"(?i)endoscop", r"(?i)gastroscop", r"(?i)colonoscop", r"(?i)bronchoscop",
        r"(?i)sigmoidoscop", r"(?i)cystoscop",
    ],
    "투시조영": [
        r"난관\s*조영", r"식도\s*조영", r"위장관\s*조영", r"대장\s*조영", r"바륨",
        r"요로\s*조영", r"담도\s*조영", r"신우\s*조영", r"배뇨방광요도\s*조영",
        r"(?<![A-Za-z])IVP(?![A-Za-z])", r"(?<![A-Za-z])HSG(?![A-Za-z])",
        r"(?<![A-Za-z])ERCP(?![A-Za-z])", r"(?i)hysterosalping",
    ],
    "혈관조영": [
        r"혈관\s*조영", r"관상동맥\s*조영", r"(?i)angiograph", r"(?<![A-Za-z])CAG(?![A-Za-z])",
    ],
    "핵의학": [
        r"골\s*스캔", r"(?i)bone\s+scan", r"신티그라", r"(?i)scintigra",
        r"(?<![A-Za-z])PET(?![A-Za-z])", r"핵의학",
    ],
    "병리조직": [
        r"병리\s*(조직|소견|사진|검사)", r"조직\s*병리", r"조직\s*검사", r"조직\s*소견",
        r"생검", r"(?i)biopsy", r"(?i)histolog", r"H&E", r"면역조직화학",
    ],
    "혈액도말": [
        r"혈액\s*도말", r"(?i)blood\s+smear", r"말초\s*혈액\s*펴바른",
        r"(?<![A-Za-z])PBS(?![A-Za-z])",
    ],
    "현미경도말": [
        r"습식\s*도말", r"(?i)wet\s+(smear|mount)", r"그람\s*염색", r"(?i)gram\s+stain",
        r"(?<![A-Za-z])KOH(?![A-Za-z])", r"소변\s*현미경", r"요\s*침사",
        r"질\s*분비물\s*(도말|검사)",
    ],
    "임상사진": [
        r"임상\s*사진", r"피부\s*병변", r"피부\s*사진", r"병변\s*사진", r"(?i)clinical\s+photo",
        # 국시 관용구 "…사진은 다음과 같다"(수식어 없는 사진 = 임상사진 관례).
        # "X선 사진은 다음과 같다"류는 X선 패턴도 같이 잡혀 집합 포함으로 통과된다.
        r"사진[은이]?\s*다음과\s*같", r"모습[은이]?\s*다음과\s*같",
    ],
    "안과검사": [
        r"안저", r"(?i)fundus", r"세극등", r"시야\s*검사",
    ],
    "기능검사그래프": [
        r"태아\s*심박동", r"비수축\s*검사", r"(?<![A-Za-z])NST(?![A-Za-z])",
        r"뇌파", r"(?<![A-Za-z])EEG(?![A-Za-z])", r"청력\s*검사", r"순음청력",
        r"(?i)audiogram", r"근전도", r"(?<![A-Za-z])EMG(?![A-Za-z])", r"신경전도",
        r"폐활량\s*곡선", r"유량[-·]?용적\s*곡선",
    ],
    "검사결과표": [
        # 주의: 일반 "검사 결과는 다음과 같다"는 lab_box 문항 대부분에 있어 오탐 →
        # 명시적으로 '표'를 말할 때만 잡는다.
        r"검사\s*결과표", r"결과표",
    ],
    "모식도": [r"모식도"],
    "기타": [],   # 게이트 제외 대상(대조 불가 범주)
}

_COMPILED = {m: [re.compile(p) for p in pats] for m, pats in STEM_PATTERNS.items()}


def match_modality(text: str):
    """문장에서 언급된 modality를 전부 추출 — 표준 enum 값의 목록(첫 등장 위치순, 중복 제거).

    과거력 언급("3년 전 CT에서…")까지 다 잡히므로, 게이트는 반드시
    "라벨 modality가 이 집합에 **없을 때만**" 탈락시켜야 한다(집합 포함 = 통과).
    언급이 하나도 없으면 빈 목록 → 게이트 통과(과잉 탈락 방지).
    """
    hits = []
    for mod, pats in _COMPILED.items():
        first = min((m.start() for p in pats for m in [p.search(text or "")] if m),
                    default=None)
        if first is not None:
            hits.append((first, mod))
    return [mod for _, mod in sorted(hits)]


def normalize_modality(value: str) -> str:
    """임의 표기(레거시 라벨값·자유서술) → 표준 enum. 실패 시 ''(게이트는 이때 건너뜀)."""
    v = re.sub(r"\s+", " ", str(value or "")).strip()
    if not v:
        return ""
    if v in MODALITY_ENUM:
        return v
    if v in LEGACY_MODALITY_MAP:
        return LEGACY_MODALITY_MAP[v][0]
    hit = match_modality(v)
    return hit[0] if hit else ""


def migrate_label_row(row: dict) -> dict:
    """v2 라벨 행 → v3 행. 원본 키를 보존하고 v3 필드를 채워 넣는다(멱등).

    하위호환: laterality·key_finding은 **신규 라벨에만** 필수 — 마이그레이션 행은
    공란을 허용하고 needs_fix를 세우지 않는다(기존 147건이 일괄 재검 대상이 되는
    소급 강제를 피한다). needs_fix는 modality가 모호/미상인 행에만 세운다.
    """
    out = dict(row)
    legacy = str(row.get("modality", "")).strip()
    mod, detail, region = LEGACY_MODALITY_MAP.get(
        legacy, (normalize_modality(legacy), "", ""))
    out["modality_legacy"] = out.get("modality_legacy", legacy)
    out["modality"] = mod or "기타"
    out.setdefault("modality_detail", detail)
    out.setdefault("body_region", region)
    out.setdefault("laterality", "")
    out.setdefault("key_finding", "")
    out.setdefault("quality_flag", "")
    out["needs_fix"] = bool(
        out.get("needs_fix")
        or legacy in AMBIGUOUS_LEGACY
        or not mod
        or not str(row.get("dx", "")).strip()
    )
    return out


def main() -> int:
    """자가점검: 기존 라벨 파일의 모든 modality 값이 enum으로 정규화되는지."""
    if not LABELS.exists():
        print(f"[스킵] 라벨 파일 없음: {LABELS}")
        return 0
    rows = json.loads(LABELS.read_text(encoding="utf-8"))
    canon, unknown = Counter(), Counter()
    for r in rows:
        m = normalize_modality(r.get("modality", ""))
        (canon if m else unknown)[m or r.get("modality", "(빈값)")] += 1
    print(f"라벨 {len(rows)}건 · 정규화 성공 {sum(canon.values())} · 실패 {sum(unknown.values())}")
    print("  표준 분포:", dict(canon.most_common()))
    if unknown:
        print("  [경고] 미정규화 값:", dict(unknown.most_common()))
    fixes = sum(1 for r in rows if migrate_label_row(r)["needs_fix"])
    print(f"  마이그레이션 시 needs_fix 예상: {fixes}건")
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
