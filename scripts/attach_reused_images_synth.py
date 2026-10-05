#!/usr/bin/env python3
"""검증된 기존 기출 이미지를 합성 세트 문항에 재사용 부착.

각 이미지는 사람(=본 세션)이 직접 열어 모달리티·소견을 육안 확인한 것만 포함.
파일은 복사하지 않고 기존 media/ 경로를 그대로 참조(비공개 유지).
"""

import json
from pathlib import Path

MEDIA_ROOT = "data_private/course_exams/media"

# (set, qnum) -> (folder, filename, modality, caption)
ATTACH = {
    ("SET1", 8):  ("COURSE_X_DATE_UNKNOWN_EXAM_2교시", "PAGE028_IMG044.jpeg", "ecg", "12유도 심전도 (고칼륨혈증 관련 소견 참고)"),
    ("SET1", 11): ("COURSE_X_DATE_UNKNOWN_EXAM_2교시", "PAGE026_IMG041.jpeg", "endoscopy", "상부위장관 내시경: 소화성궤양(노출 병변)"),
    ("SET1", 22): ("COURSE_X_DATE_UNKNOWN_EXAM_2교시", "PAGE014_IMG023.jpeg", "fluoroscopy", "식도조영: 하부식도 새부리(bird-beak) 협착"),
    ("SET1", 31): ("COURSE_X_DATE_UNKNOWN_EXAM_4교시", "PAGE010_IMG012.jpeg", "endoscopy", "상부위장관 내시경: 식도정맥류(적색징후)"),
    ("SET1", 42): ("COURSE_X_DATE_UNKNOWN_EXAM_2교시", "PAGE017_IMG030.jpeg", "xray", "기립 복부 X선: 다발성 공기-액체층(장폐색)"),
    ("SET1", 49): ("COURSE_X_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_3교시", "PAGE010_IMG016.jpeg", "xray", "가슴 X선 (폐결핵 관련 참고)"),
    ("SET1", 28): ("COURSE_2_20260306_HEMATOLOGY_ONCOLOGY_1차", "BIN0001.png", "blood_smear", "말초혈액도말: 다수의 모세포(급성백혈병)"),
    ("SET2", 29): ("PMA_202306_G3_B군_1교시", "PAGE001_IMG003.png", "blood_smear", "말초혈액도말: 혈소판 현저히 감소(면역혈소판감소증)"),
    ("SET2", 7):  ("PMA_202511_G3_B군_2교시", "PAGE026_IMG040.jpeg", "xray", "경부 X선 (크루프 관련 참고)"),
    ("SET2", 36): ("COURSE_X_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_3교시", "PAGE013_IMG024.jpeg", "photo", "하지의 만져지는 자반 (IgA혈관염/HSP)"),
    ("SET2", 39): ("COURSE_X_DATE_CLINICAL_COMPREHENSIVE_EXAM_EXAM_3교시", "PAGE004_IMG003.jpeg", "xray", "척추 X선 (강직척추염 관련 참고)"),
}

TARGETS = {
    "SET1": Path("data_private/course_exams/extracted/SYNTH_2026_MOCK_SET1.json"),
    "SET2": Path("data_private/course_exams/extracted/SYNTH_2026_MOCK_SET2.json"),
}
SRCSETS = {
    "SET1": Path("data_private/exam_sets/SYNTH_2026_SET1.json"),
    "SET2": Path("data_private/exam_sets/SYNTH_2026_SET2.json"),
}


def main():
    # 부착 대상 그룹핑
    by_set = {}
    for (s, n), v in ATTACH.items():
        by_set.setdefault(s, {})[n] = v

    for s, target in TARGETS.items():
        rec = json.loads(target.read_text(encoding="utf-8"))
        assets = rec.get("media_assets") or []
        existing_ids = {a.get("media_id") for a in assets}
        by_num = {q["question_number"]: q for q in rec["questions"]}
        added = 0
        for n, (folder, fname, modality, caption) in by_set.get(s, {}).items():
            path = Path(MEDIA_ROOT) / folder / fname
            if not path.exists():
                print(f"   [경고] 파일 없음: {path}")
                continue
            media_id = f"SYNTH_{s}_Q{n:03d}_REUSE_{fname.rsplit('.',1)[0]}"
            if media_id not in existing_ids:
                assets.append({
                    "media_id": media_id,
                    "file_path": str(path),
                    "relative_path": f"{folder}/{fname}",
                    "modality": modality,
                    "caption": caption,
                    "provenance": f"reused_from:{folder}",
                    "needs_review": True,
                })
                existing_ids.add(media_id)
            q = by_num[n]
            media = q.get("media") or {}
            refs = media.get("media_refs") or []
            if not any(r.get("media_id") == media_id for r in refs):
                refs.append({"media_id": media_id, "needs_review": True,
                             "caption": caption, "modality": modality,
                             "reused": True})
            media["media_refs"] = refs
            q["media"] = media
            added += 1
        rec["media_assets"] = assets
        target.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

        # 소스 세트에도 provenance 기록
        src = SRCSETS[s]
        sd = json.loads(src.read_text(encoding="utf-8"))
        sbn = {q["question_number"]: q for q in sd["questions"]}
        for n, (folder, fname, modality, caption) in by_set.get(s, {}).items():
            sbn[n]["reused_image"] = {"folder": folder, "file": fname,
                                       "modality": modality, "caption": caption,
                                       "verified_by": "visual_inspection"}
        src.write_text(json.dumps(sd, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{s}] 이미지 부착 {added}개 · media_assets {len(assets)}")

    print("완료. 육안 검증 후 부착한 문항: 세트1 Q8·11·22·31·42·49 / 세트2 Q7·36·39")


if __name__ == "__main__":
    raise SystemExit(main())
