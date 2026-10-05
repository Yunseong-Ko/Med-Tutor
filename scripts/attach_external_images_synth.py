#!/usr/bin/env python3
"""외부 저작권-안전(CC BY/CC BY-SA/CC0) 이미지를 합성 문항에 부착. 출처·라이선스 표기 포함.

모두 육안 검증 완료. B2B(상업) 사용 가능한 라이선스만 사용(NC/ND 제외).
파일: data_private/course_exams/media/SYNTH_GENERATED/
"""

import json
from pathlib import Path

FOLDER = "SYNTH_GENERATED"
MEDIA_ROOT = Path("data_private/course_exams/media") / FOLDER

# (set, qnum) -> dict(file, modality, caption, license, attribution, source)
ATTACH = {
    ("SET1", 15): dict(
        file="ptbxl_AFIB_351.png", modality="ecg",
        caption="12유도 심전도: 심방세동(불규칙·P파 소실)",
        license="CC BY 4.0", attribution="PTB-XL, Wagner et al. 2020 (PhysioNet)",
        source="https://physionet.org/content/ptb-xl/1.0.3/"),
    ("SET1", 54): dict(
        file="wiki_3AVB.png", modality="ecg",
        caption="심전도: 완전(3도)방실차단 — P파-QRS 해리",
        license="CC BY 3.0", attribution="Gregory Marcus, MD (Wikimedia Commons)",
        source="https://commons.wikimedia.org/wiki/File:3rd_degree_heart_block.PNG"),
    ("SET2", 34): dict(
        file="wiki_VF.png", modality="ecg",
        caption="심전도: 심실세동(무질서한 세동파)",
        license="CC BY-SA 3.0", attribution="Jer5150 (Wikimedia Commons)",
        source="https://commons.wikimedia.org/wiki/File:Ventricular_fibrillation.png"),
    ("SET2", 64): dict(
        file="wiki_pericarditis.png", modality="ecg",
        caption="심전도: 급성 심막염 — 미만성 ST상승·PR변화",
        license="CC BY-SA 4.0", attribution="Dr Ihab Suliman (Wikimedia Commons)",
        source="https://commons.wikimedia.org/wiki/File:PERICADITIS_ECG_Changes.png"),
    ("SET2", 30): dict(
        file="wiki_CRAO_fundus.jpg", modality="fundus",
        caption="안저: 황반 체리홍반점(망막중심동맥폐쇄)",
        license="CC BY 2.0", attribution="Fiess et al. (Wikimedia Commons)",
        source="https://commons.wikimedia.org/wiki/File:Cherry_Red_Spot_Fiess.jpg"),
}

TARGETS = {
    "SET1": (Path("data_private/course_exams/extracted/SYNTH_2026_MOCK_SET1.json"),
             Path("data_private/exam_sets/SYNTH_2026_SET1.json")),
    "SET2": (Path("data_private/course_exams/extracted/SYNTH_2026_MOCK_SET2.json"),
             Path("data_private/exam_sets/SYNTH_2026_SET2.json")),
}


def main():
    by_set = {}
    for (s, n), v in ATTACH.items():
        by_set.setdefault(s, {})[n] = v

    for s, (mock, src) in TARGETS.items():
        rec = json.loads(mock.read_text(encoding="utf-8"))
        assets = rec.get("media_assets") or []
        ids = {a.get("media_id") for a in assets}
        bn = {q["question_number"]: q for q in rec["questions"]}
        added = 0
        for n, v in by_set.get(s, {}).items():
            path = MEDIA_ROOT / v["file"]
            if not path.exists():
                print(f"   [경고] 없음 {path}")
                continue
            mid = f"SYNTH_{s}_Q{n:03d}_EXT_{v['file'].rsplit('.',1)[0]}"
            if mid not in ids:
                assets.append({
                    "media_id": mid, "file_path": str(path),
                    "relative_path": f"{FOLDER}/{v['file']}",
                    "modality": v["modality"], "caption": v["caption"],
                    "license": v["license"], "attribution": v["attribution"],
                    "source": v["source"], "provenance": "external_open_license",
                    "needs_review": True})
                ids.add(mid)
            q = bn[n]
            media = q.get("media") or {}
            refs = media.get("media_refs") or []
            if not any(r.get("media_id") == mid for r in refs):
                refs.append({"media_id": mid, "needs_review": True,
                             "caption": v["caption"], "modality": v["modality"],
                             "license": v["license"], "attribution": v["attribution"]})
            media["media_refs"] = refs
            q["media"] = media
            added += 1
        rec["media_assets"] = assets
        mock.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

        sd = json.loads(src.read_text(encoding="utf-8"))
        sbn = {q["question_number"]: q for q in sd["questions"]}
        for n, v in by_set.get(s, {}).items():
            sbn[n]["external_image"] = {"folder": FOLDER, "file": v["file"],
                                         "caption": v["caption"], "license": v["license"],
                                         "attribution": v["attribution"], "source": v["source"],
                                         "verified_by": "visual_inspection"}
        src.write_text(json.dumps(sd, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{s}] 외부 이미지 부착 {added}개")

    print("완료: 세트1 Q15(AF)·Q54(완전방실차단) / 세트2 Q34(VF)·Q64(심막염)")


if __name__ == "__main__":
    raise SystemExit(main())
