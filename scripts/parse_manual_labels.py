#!/usr/bin/env python3
"""사람이 입력한 이미지 라벨(자유서술)을 [검사종류 + 짧은 진단/소견]으로 로컬 분리.

배경: 라벨링 도구의 검사종류 드롭다운을 쓰지 않고 진단명 칸에 전부 적었다.
      예) "진단명: 악성 중피종, 조직검사: papillary/glandular"
          "흉부 CT 에서는 양 측 폐기저부와 흉막하 부위에 reticular opacity, honeycombing 이 관찰됩니다."

정책(보안 프로토콜 §5.5): 자유서술 원문을 그대로 생성 프롬프트에 넣지 않는다.
  → 여기서 **개념 수준의 짧은 라벨**로 축약하고, 축약 실패분은 needs_review로 남긴다.
  → stdout은 통계와 축약된 짧은 라벨만 출력(장문 원문 미출력).

입력: pma_labels_v2/labels_manual_raw.json (localStorage 회수본), label_ledger.json
출력: pma_labels_v2/labels_manual.json
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

OUT = Path("data_private/professor_items/pma_labels_v2")

# 검사종류 판정(문두 라벨 → 본문 키워드 순). 앞쪽이 우선.
MOD_RULES = [
    ("NST(태아심박동)", r"NST|비수축검사|전자태아심박동|태아\s*심박동|자궁수축감시|nonstress"),
    ("산과초음파", r"산과\s*초음파|태아\s*초음파|제대\s*동맥|doppler|biophysical|양수지수|AFI"),
    ("부인과초음파", r"부인과\s*초음파|난소\s*(종양|낭종)?\s*초음파|자궁\s*초음파|질\s*초음파|경질"),
    ("자궁난관조영", r"자궁난관조영|HSG|hysterosalping"),
    ("유방촬영/초음파", r"유방\s*(촬영|초음파)|mammogra|breast\s*(us|ultra)"),
    ("ECG", r"심전도|\bECG\b|\bEKG\b|S1Q3T3|QRS|ST\s*분절|P\s*wave|QT|동율동|sinus\s*rhythm"),
    ("심장초음파", r"심장\s*초음파|심초음파|echocardiog|EF\s*\d|박출률|vegetation|판막\s*초음파"),
    ("운동부하검사", r"운동부하|treadmill|exercise\s*test"),
    ("홀터", r"홀터|holter|24시간\s*심전도"),
    ("가슴CT", r"(흉부|가슴|폐)\s*(전산화단층|CT)|chest\s*CT|HRCT|폐색전증\s*CT|honeycomb"),
    ("가슴X선", r"(흉부|가슴)\s*(단순)?\s*(X\s*-?\s*선|X\s*-?\s*ray|방사선|촬영)|\bCXR\b|chest\s*(PA|AP|x-?ray)"),
    ("복부CT", r"(복부|배|간|췌장|신장|콩팥)\s*(전산화단층|CT)|abdom\w*\s*CT|\bHCC\b\s*CT"),
    ("복부X선", r"복부\s*(단순)?\s*(X\s*-?\s*선|촬영)|abdomen\s*(x-?ray|AP)|\bKUB\b"),
    ("복부초음파", r"복부\s*초음파|간\s*초음파|담낭\s*초음파|abdom\w*\s*(us|ultra)"),
    ("뇌CT", r"(뇌|머리|두부)\s*(전산화단층|CT)|brain\s*CT"),
    ("뇌MRI", r"(뇌|머리|두부|척수)\s*(자기공명|MRI)|brain\s*MRI|확산강조|DWI"),
    ("척추/사지X선", r"(척추|경추|요추|무릎|어깨|골반|사지|손|발)\s*(X\s*-?\s*선|촬영|방사선)"),
    ("혈관조영", r"혈관조영|angiograph|관상동맥조영|coronary\s*angio"),
    ("골스캔/핵의학", r"골스캔|bone\s*scan|신티|scintigra|갑상선\s*스캔"),
    ("PET-CT", r"PET"),
    ("MRCP/담도조영", r"MRCP|ERCP|담도조영|cholangiog"),
    ("IVP/요로조영", r"\bIVP\b|요로조영|배설성\s*요로|urograph"),
    ("위내시경", r"위\s*내시경|상부\s*(위장관)?\s*내시경|\bEGD\b|gastroscop"),
    ("대장내시경", r"대장\s*내시경|결장\s*내시경|colonoscop|sigmoidoscop"),
    ("기관지내시경", r"기관지\s*내시경|bronchoscop"),
    ("방광경", r"방광경|cystoscop"),
    ("말초혈액도말", r"말초\s*혈액\s*도말|blood\s*smear|도말\s*검사|PBS\b"),
    ("골수도말/생검", r"골수\s*(도말|생검|검사)|bone\s*marrow"),
    ("병리조직", r"조직\s*(검사|소견)|병리|생검|biopsy|현미경|H&E|면역\w*염색|papillary|glandular"),
    ("그람염색/배양", r"그람\s*염색|gram\s*stain|배양\s*검사|culture"),
    ("소변현미경", r"소변\s*(현미경|침사)|요\s*침사|urinalysis|urine\s*sediment"),
    ("객담검사", r"객담|sputum|AFB"),
    ("폐기능검사", r"폐기능|spirometr|\bFEV1\b|\bFVC\b|폐활량"),
    ("뇌파(EEG)", r"뇌파|\bEEG\b"),
    ("근전도(EMG/NCS)", r"근전도|\bEMG\b|\bNCS\b|신경전도"),
    ("안저/눈", r"안저|fundus|세극등|각막|시야\s*검사"),
    ("청력검사", r"청력|audiogram|순음"),
    ("피부병변 사진", r"피부\s*(병변|소견)|발진|수포|홍반|병변\s*사진"),
    ("검사결과표", r"검사\s*결과|참고치|혈액\s*검사|\blab\b"),
    ("도표·그래프", r"그래프|도표|곡선|curve"),
]

# 사람이 "사용하지 말 것"으로 표시했거나 내용을 특정할 수 없는 이미지 → 제외
EXCLUDE_TEXT = re.compile(r"사용하지\s*말")
EXCLUDE_IMAGES = {
    "C1_73_f3174a7d4830.jpg",   # 라벨이 "표" 뿐이라 내용 특정 불가
}

# 자동 축약이 실패했거나 오탐인 항목의 확정 라벨 (image → (진단/소견, 검사종류))
OVERRIDES = {
    "C1_21_03cda7d51c0d.jpg": ("흉관 손상(암죽흉수)", "임상 자료"),
    "C1_44_daeb0f0f0405.bmp": ("얇은 자궁내막(자궁내막 위축)", "부인과초음파"),
    "C1_44_8c5a62ee9a6d.bmp": ("얇은 자궁내막(자궁내막 위축)", "부인과초음파"),
    "C1_48_8d5435c2db2a.jpg": ("트리코모나스 질염", "습식도말(wet smear)"),
    "C1_51_84af12e39624.bmp": ("신농양", "복부CT"),
    "C1_65_3ca7a7032cf6.bmp": ("양측 감각신경성 난청", "청력검사"),
    "C2_8_9035be2dd054.jpg": ("급성 횡단척수염", "척수 MRI"),
    "C2_10_b7d8d417c743.png": ("경막외혈종", "뇌CT"),
    "C2_18_1403fba96773.bmp": ("심실조기수축(PVC)", "ECG"),
    "C2_19_e07e2c51a3a8.bmp": ("폐렴(공기기관지음영 동반 경화)", "가슴CT"),
    "C2_28_5246d41e477b.bmp": ("얇은 자궁내막(자궁내막 위축)", "부인과초음파"),
    "C2_31_12ca272ec4b9.jpg": ("류마티스관절염", "임상 사진"),
    "C2_64_72a7ae8641f9.bmp": ("식도이완불능증(achalasia)", "식도조영"),
    "C2_80_705202c80172.bmp": ("재발성 어깨관절 전방탈구", "어깨CT"),
    "C3_21_daabe60b2965.jpg": ("에탐부톨 시신경병증", "안과 검사 자료"),
    "C3_76_2df771250ac2.jpg": ("니켈 접촉피부염", "피부병변 사진"),
    "C4_10_395e5d8e84f2.jpg": ("되돌이후두신경 손상", "해부 모식도"),
    "C4_18_1403fba96773.bmp": ("심실조기수축(PVC)", "ECG"),
    "C4_23_0f962697f48c.jpg": ("경부 열상", "임상 사진"),
    "C4_36_6617ca949876.jpg": ("유방울혈", "임상 사진"),
    "C4_76_7fed29315a10.jpg": ("콜린성 두드러기", "피부병변 사진"),
    # --- 파편 라벨(원문 확인 후 확정) ---
    "C1_25_b309b265c2ff.bmp": ("무반응성 태아심박동(non-reactive NST)", "NST(태아심박동)"),
    "C1_37_810fe4d7740e.jpg": ("폐고름집(공동 내 액체층)", "가슴X선"),
    "C1_43_51dcf5e8dd5f.bmp": ("전벽 ST분절상승 심근경색", "ECG"),
    "C1_45_be27e8687002.bmp": ("심방세동", "ECG"),
    "C2_4_a1a1ecb08f69.bmp": ("좌심실비대(strain pattern 동반)", "ECG"),
    "C2_17_900889c808c1.bmp": ("급성호흡곤란증후군(ARDS)", "가슴X선"),
    "C2_19_d0c2d79cef8c.bmp": ("기질화폐렴(Masson body)", "병리조직"),
    "C2_23_7457affeee47.bmp": ("급성호흡곤란증후군(ARDS)", "가슴X선"),
    "C2_61_1062b23c8d11.bmp": ("고칼륨혈증", "ECG"),
    "C2_74_c46dfedba1c2.bmp": ("악성 난소종양(다방성 낭성 종괴)", "부인과초음파"),
    "C2_75_6c8dc210b376.bmp": ("간세포암(동맥기 조영증강·washout)", "복부CT"),
    "C2_76_12a5c06f2657.bmp": ("De Winter 양상(근위부 LAD 폐색)", "ECG"),
    "C2_77_60a7fc22381d.bmp": ("감염성 심내막염", "임상 자료"),
    "C2_77_7500805dc10f.bmp": ("감염성 심내막염", "임상 자료"),
    "C2_78_e90e082a2d99.bmp": ("심방세동", "ECG"),
    "C3_8_142c3b0056a6.jpg": ("심부전", "가슴X선"),
    "C3_11_ebbf1a5df5e8.bmp": ("강직척추염(엉치엉덩관절염)", "척추/사지X선"),
    "C3_18_231d5c1a4628.bmp": ("정상 태아심박동(Category I)", "NST(태아심박동)"),
    "C3_20_7dbb0f8e885c.jpg": ("원발성 갑상샘 MALT 림프종", "병리조직"),
    "C3_23_8383d23910c5.jpg": ("폐결핵", "가슴CT"),
    "C3_39_26b8fbb1adbb.bmp": ("신농양", "복부CT"),
    "C3_53_31b7ee563473.bmp": ("하벽 ST분절상승 심근경색", "ECG"),
    "C3_74_88312d6d7918.bmp": ("승모판협착증(좌심방 확대)", "ECG"),
    "C3_78_0a0b07b91ad4.png": ("대동맥판협착증(좌심실비대)", "ECG"),
    "C4_17_900889c808c1.bmp": ("수혈관련 급성폐손상(TRALI)", "가슴X선"),
    "C4_22_2a08327f3979.jpg": ("만성폐쇄폐질환(COPD)", "가슴X선"),
    "C4_26_e87311fdc71e.bmp": ("만성콩팥병(흉부 X선 이상 없음)", "가슴X선"),
    "C4_28_d08b323c246c.jpg": ("열대열 말라리아", "말초혈액도말"),
    "C4_29_3de40f87a9f2.jpg": ("심부정맥혈전증(DVT)", "임상 사진"),
    "C4_38_9789037c75c5.png": ("결핵성 림프절염", "경부CT"),
    "C4_44_c3779c9042a6.bmp": ("저칼륨혈증(QT연장·U파)", "ECG"),
    "C4_53_4b7f6405a1eb.jpg": ("군날개(pterygium)", "안과 검사 자료"),
    "C4_64_44022dc009ea.png": ("횡격막 손상", "가슴X선"),
    "C4_72_eb5ec3d9a29b.jpg": ("제한형 전신경화증(간질폐질환 동반)", "임상 사진"),
    "C4_77_0a69017e035f.bmp": ("외상성 복강내출혈(FAST 양성)", "복부초음파"),
    "C3_8_94f2444f42e4.bmp": ("심부전", "ECG"),
    "C2_25_0fb377bb5bed.bmp": ("정상 흉부 X선(대조 영상)", "가슴X선"),
    "C4_27_8b4b2a2a95f1.bmp": ("정상 흉부 X선(대조 영상)", "가슴X선"),
    "C3_17_88b55cae15b2.jpg": ("호흡성 산증(호흡보조 필요)", "가슴X선"),
}

# 자유서술 안에서 '라벨: 값' 형태를 뽑는다.
SEG = re.compile(
    r"(진단명|진단|추정\s*진단|조직\s*검사|병리|소견|영상\s*소견|해석|"
    r"CXR|CT|MRI|X\s*-?\s*ray|X\s*선|초음파|심전도|ECG|EKG|NST|내시경|도말|검사)\s*[:：]\s*"
)
DX_LABEL = re.compile(r"^(진단명|진단|추정\s*진단)$")
# 서술형 종결·수식 표현 → 축약 실패 신호
NARRATIVE = re.compile(r"관찰됩니다|보입니다|시사합니다|보이지\s*않습니다|입니다\.|됩니다|하였다|있습니다")


def norm(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    s = re.sub(r"\s*([/()])\s*", r"\1", s)
    return s.strip(" .,·-")


def load_alias_index():
    """개념 레지스트리 별칭 → 개념 ID (긴 별칭 우선).

    한글 별칭은 붙여쓰기 정규화 후 부분일치, ASCII 별칭은 **단어경계 일치**만 허용한다.
    (ASCII 부분일치를 허용하면 'consolidations' 안의 'ida'가 IDA로 잡히는 오탐이 난다.)
    """
    idx = []
    for path, getter in (
        (Path("data_private/concept_registry.json"),
         lambda d: {cid: (c.get("aliases") or []) + [cid.replace("_", " ")]
                    for cid, c in d["concepts"].items()}),
        (Path("data_private/professor_items/seeds/alias_supplement.json"),
         lambda d: d),
    ):
        if not path.exists():
            continue
        try:
            for cid, aliases in getter(json.loads(path.read_text(encoding="utf-8"))).items():
                for a in aliases:
                    a = str(a)
                    hangul = any("가" <= ch <= "힣" for ch in a)
                    if hangul:
                        na = re.sub(r"[\s_\-.'’]+", "", a).lower()
                        if len(na) >= 3:
                            idx.append((na, a, cid, len(na), True))
                    else:
                        na = re.sub(r"\s+", " ", a).strip().lower()
                        if len(na) >= 5:   # 짧은 영문 약어는 오탐이 많아 제외
                            idx.append((na, a, cid, len(na), False))
        except Exception:
            pass
    idx.sort(key=lambda x: -x[3])
    return idx


def best_concept(text: str, idx):
    hay_k = re.sub(r"[\s_\-.'’]+", "", text).lower()
    hay_e = re.sub(r"\s+", " ", text).lower()
    for na, alias, cid, _, hangul in idx:
        if hangul:
            if na in hay_k:
                return alias, cid
        elif re.search(rf"(?<![a-z0-9]){re.escape(na)}(?![a-z0-9])", hay_e):
            return alias, cid
    return "", ""


def modality_of(text: str) -> str:
    for name, pat in MOD_RULES:
        if re.search(pat, text, re.I):
            return name
    return ""


def split_segments(text: str):
    """'라벨: 값' 구간을 (라벨, 값) 목록으로. 라벨이 없으면 [('', 전체)]."""
    parts, last, label = [], 0, ""
    for m in SEG.finditer(text):
        if m.start() > last:
            parts.append((label, text[last:m.start()]))
        label, last = re.sub(r"\s+", "", m.group(1)), m.end()
    parts.append((label, text[last:]))
    return [(lb, norm(v)) for lb, v in parts if norm(v)]


def condense(text: str, idx):
    """자유서술 → (짧은 라벨, 축약 방법). 실패 시 ('', 'fail')."""
    segs = split_segments(text)
    for lb, val in segs:
        if DX_LABEL.match(lb) and val:
            v = re.split(r"[,，]", val)[0]
            return norm(v)[:40], "labeled"
    alias, _ = best_concept(text, idx)
    if alias:
        return norm(alias)[:40], "registry"
    plain = norm(text)
    if len(plain) <= 28 and not NARRATIVE.search(plain):
        return plain, "short"
    # 영문 의학용어 구(honeycombing, reversed end-diastolic flow 등) 추출
    eng = re.findall(r"[A-Za-z][A-Za-z\-]{2,}(?:\s+[a-z\-]{2,}){0,3}", plain)
    eng = [e for e in eng if len(e) >= 5]
    if eng:
        return max(eng, key=len)[:40], "english"
    return "", "fail"


def main() -> int:
    raw = json.loads((OUT / "labels_manual_raw.json").read_text(encoding="utf-8"))
    led = {r["key"]: r for r in json.loads((OUT / "label_ledger.json").read_text(encoding="utf-8"))}
    idx = load_alias_index()

    rows, st = [], Counter()
    for rid, v in raw.items():
        if not isinstance(v, dict) or v.get("use") is False:
            st["skip_unused"] += 1
            continue
        text = norm(v.get("dx", ""))
        if not text:
            st["skip_empty"] += 1
            continue
        img = v.get("image") or ""
        if img in EXCLUDE_IMAGES or EXCLUDE_TEXT.search(text):
            st["skip_excluded"] += 1
            continue
        key = rid.split("__")[0]
        L = led.get(key, {})
        if img in OVERRIDES:
            dx, mod = OVERRIDES[img]
            how = "override"
        else:
            dx, how = condense(text, idx)
            mod = norm(v.get("modality", "")) or modality_of(text) or L.get("modality_guess", "")
        st[f"how:{how}"] += 1
        if mod:
            st["mod_ok"] += 1
        if dx:
            st["dx_ok"] += 1
        rows.append({
            "key": key,
            "image": img,
            "dx": dx,
            "modality": mod,
            "how": how,
            "raw_len": len(text),
            "subject_hint": L.get("subject_hint", ""),
            "turn": L.get("turn", ""), "period": L.get("period", ""), "qno": L.get("qno", 0),
            "needs_review": (not dx) or (not mod),
            "note": norm(v.get("note", ""))[:200],
        })

    rows.sort(key=lambda r: (r["turn"], r["period"], r["qno"], r["image"]))
    (OUT / "labels_manual.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"입력 {len(raw)} → 라벨 {len(rows)}  "
          f"(미사용 {st['skip_unused']} · 빈칸 {st['skip_empty']} · 사용제외 {st['skip_excluded']})")
    print(f"  진단/소견 확보 {st['dx_ok']}/{len(rows)} · 검사종류 확보 {st['mod_ok']}/{len(rows)}")
    print("  축약 경로:", {k[4:]: v for k, v in sorted(st.items()) if k.startswith("how:")})
    print("  검사종류 분포:", dict(Counter(r["modality"] or "(미상)" for r in rows).most_common()))
    nr = [r for r in rows if r["needs_review"]]
    print(f"  검토 필요 {len(nr)}건")
    for r in nr[:20]:
        print(f"    - {r['key']} {r['image']}: dx={r['dx'] or '(없음)'} mod={r['modality'] or '(없음)'}")
    print(f"[출력] {OUT/'labels_manual.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
