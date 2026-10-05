#!/usr/bin/env python3
"""Prepare P:accine DB drafts from an authorized IPDISK local mirror.

The script does not log in to IPDISK or crawl protected folders. It scans files
that the user already has permission to access, then creates draft metadata
for faculty review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_RULES = {
    "lecture_keywords": ["강의", "강의록", "lecture", "ppt", "슬라이드"],
    "lesson_note_keywords": ["학습부원", "학습부", "정리본", "수업정리", "수업 정리", "노트"],
    "past_exam_keywords": ["기출", "문제", "PMA", "시험", "exam", "문항"],
    "explanation_keywords": ["해설", "풀이", "정답", "answer", "solution"],
    "media_keywords": ["CT", "MRI", "Xray", "X-ray", "초음파", "병리", "ECG", "EEG", "청음", "사진", "image"],
}

DOCUMENT_EXTS = {
    ".pdf": "pdf",
    ".ppt": "ppt",
    ".pptx": "pptx",
    ".hwp": "hwp",
    ".hwpx": "hwpx",
    ".doc": "doc",
    ".docx": "docx",
    ".txt": "txt",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".xlsx": "xlsx",
    ".xls": "xls",
}

IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
}

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
ARCHIVE_EXTS = {".zip", ".7z", ".rar", ".tar", ".gz"}
SUPPORTED_EXTS = set(DOCUMENT_EXTS) | IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS | ARCHIVE_EXTS


def _load_manifest(path: Path | None) -> dict[str, Any]:
    if not path:
        return {
            "batch_slug": f"ipdisk_scan_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "source_root_label": "authorized local mirror",
            "curriculum_context": {},
            "default_visibility": {
                "student_visible": False,
                "approved_for_ingest": False,
                "approved_for_question_use": False,
            },
            "classification_rules": DEFAULT_RULES,
            "path_include_keywords": [],
            "path_exclude_keywords": [],
            "path_required_keyword_groups": [],
        }
    with path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    merged = dict(manifest)
    merged["classification_rules"] = {
        **DEFAULT_RULES,
        **manifest.get("classification_rules", {}),
    }
    merged.setdefault("curriculum_context", {})
    merged.setdefault("path_include_keywords", [])
    merged.setdefault("path_exclude_keywords", [])
    merged.setdefault("path_required_keyword_groups", [])
    return merged


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _passes_path_filters(path_text: str, manifest: dict[str, Any]) -> bool:
    include_keywords = manifest.get("path_include_keywords") or []
    exclude_keywords = manifest.get("path_exclude_keywords") or []
    required_groups = manifest.get("path_required_keyword_groups") or []
    for group in required_groups:
        if isinstance(group, list) and group and not _contains_any(path_text, group):
            return False
    if include_keywords and not _contains_any(path_text, include_keywords):
        return False
    if exclude_keywords and _contains_any(path_text, exclude_keywords):
        return False
    return True


def _content_type(ext: str) -> str:
    if ext in DOCUMENT_EXTS:
        return DOCUMENT_EXTS[ext]
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in ARCHIVE_EXTS:
        return "archive"
    return "other"


def _material_type(path_text: str, ext: str, rules: dict[str, list[str]]) -> str:
    content_type = _content_type(ext)
    if content_type in {"image", "video", "audio"}:
        return "media"
    if _contains_any(path_text, rules.get("lesson_note_keywords", [])):
        return "lesson_note"
    if "정리족" in path_text:
        return "jokbo_summary"
    if "출족" in path_text:
        return "jokbo_recall"
    if _contains_any(path_text, rules.get("explanation_keywords", [])):
        return "explanation"
    if _contains_any(path_text, rules.get("past_exam_keywords", [])):
        return "past_exam"
    if _contains_any(path_text, rules.get("lecture_keywords", [])):
        return "lecture"
    if _contains_any(path_text, rules.get("media_keywords", [])):
        return "media"
    return "unknown"


def _guess_modality(path_text: str, content_type: str) -> str:
    lowered = path_text.lower()
    modality_rules = [
        ("x-ray", ["x-ray", "xray", "x ray", "엑스레이"]),
        ("CT", ["ct", "computed tomography"]),
        ("MRI", ["mri"]),
        ("ultrasound", ["ultrasound", "초음파", "us "]),
        ("pathology_slide", ["pathology", "병리", "slide", "histology"]),
        ("ECG", ["ecg", "ekg", "심전도"]),
        ("EEG", ["eeg", "뇌파"]),
        ("heart_sound", ["heart sound", "심음", "청음"]),
        ("lung_sound", ["lung sound", "폐음"]),
        ("endoscopy", ["endoscopy", "내시경", "egd", "colonoscopy"]),
    ]
    for modality, patterns in modality_rules:
        if any(pattern in lowered for pattern in patterns):
            return modality
    return content_type


def _guess_asset_type(path_text: str, content_type: str) -> str:
    modality = _guess_modality(path_text, content_type)
    if modality in {"x-ray", "CT", "MRI"}:
        return "radiology"
    if modality == "ultrasound":
        return "ultrasound"
    if modality == "pathology_slide":
        return "pathology"
    if modality in {"ECG", "EEG"}:
        return "ecg_eeg"
    if modality in {"heart_sound", "lung_sound"}:
        return "audio"
    if content_type == "video":
        return "video"
    if content_type == "image":
        return "clinical_photo"
    return "other"


def _extract_metadata(path_text: str) -> dict[str, Any]:
    year_match = re.search(r"(20\d{2})", path_text)
    compact_date_match = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", path_text)
    period_range_match = re.search(r"(\d+)\s*[-,~]\s*(\d+)\s*교시", path_text)
    period_match = re.search(r"(\d+)\s*교시", path_text)
    teacher_match = re.search(r"([가-힣]{2,5})\s*교수(?:님)?", path_text)
    turn_match = re.search(r"([ABCD])\s*턴", path_text, flags=re.IGNORECASE)
    grade_match = re.search(r"([1234])\s*학년", path_text)
    jokbo_type = ""
    if "정리족" in path_text:
        jokbo_type = "summary"
    elif "출족" in path_text:
        jokbo_type = "recall"
    elif _contains_any(path_text, DEFAULT_RULES["lesson_note_keywords"]):
        jokbo_type = "lesson_note"

    compact_date = ""
    compact_year = ""
    if compact_date_match:
        yy, mm, dd = compact_date_match.groups()
        compact_year = f"20{yy}"
        compact_date = f"20{yy}-{mm}-{dd}"

    exam_type = ""
    if re.search(r"PMA", path_text, flags=re.IGNORECASE):
        exam_type = "PMA"
    elif "기출" in path_text:
        exam_type = "past_exam"
    elif "과정시험" in path_text:
        exam_type = "course_exam"

    return {
        "year": year_match.group(1) if year_match else compact_year,
        "date": compact_date,
        "period": "-".join(period_range_match.groups()) if period_range_match else (period_match.group(1) if period_match else ""),
        "teacher": teacher_match.group(1) if teacher_match else "",
        "turn": turn_match.group(1).upper() if turn_match else "",
        "grade": grade_match.group(1) if grade_match else "",
        "exam_type": exam_type,
        "jokbo_type": jokbo_type,
    }


def _guess_course_unit(path_text: str) -> tuple[str, str]:
    normalized = path_text.replace("_", " ")
    course_rules = [
        ("신경 및 특수감각기학", ["신경 및 특수감각기", "신경특수", "신경약리", "망막", "외상성 신경질환"]),
        ("인간사회의료", ["인간사회의료", "인간.사회.의료", "인사의 ii", "인사의", "환경의학", "의료윤리", "장기이식"]),
        ("정신의학", ["정신의학", "정신건강", "정신과"]),
        ("성장발달노화", ["성장발달노화", "normal development", "분만손상", "가사"]),
        ("면역피부감염", ["면피", "베체트", "감염", "알레르기", "피부"]),
    ]
    for course, patterns in course_rules:
        if _contains_any(normalized, patterns):
            return course, ""
    return "", ""


def _extract_jokbo_fields(path: Path) -> dict[str, str]:
    stem = path.stem
    normalized = stem.replace("교수님", "교수")
    normalized = re.sub(r"^\[(정리족|출족)\]\s*", "", normalized)
    parts = [part.strip() for part in normalized.split("_") if part.strip()]
    result = {
        "jokbo_label": "정리족" if "정리족" in stem else ("출족" if "출족" in stem else ("학습부원" if _contains_any(stem, DEFAULT_RULES["lesson_note_keywords"]) else "")),
        "lecture_topic": "",
        "contributor": "",
    }
    if len(parts) >= 5 and "교수" in parts[2]:
        result["lecture_topic"] = parts[4]
        if len(parts) >= 6:
            result["contributor"] = parts[5]
    elif len(parts) >= 4 and "교수" in parts[1]:
        result["lecture_topic"] = parts[3]
        if len(parts) >= 5:
            result["contributor"] = parts[4]
    return result


def _material_id(relative_path: str) -> str:
    suffix = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:12]
    return f"ipdisk_mat_{suffix}"


def _asset_id(material_id: str) -> str:
    return f"media_{material_id.replace('ipdisk_mat_', 'ipdisk_')}"


def _probe_url(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "PaccineIPDISKProbe/0.1"})
    with urlopen(request, timeout=15) as response:
        body = response.read(2048).decode("utf-8", errors="replace")
        return {
            "url": url,
            "status": response.status,
            "content_type": response.headers.get("Content-Type", ""),
            "looks_like_login_required": "login.cgi" in body or "act=logout" in body,
            "body_preview": body[:300],
        }


def _scan_source(
    *,
    source_dir: Path,
    manifest: dict[str, Any],
    hash_files: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rules = manifest.get("classification_rules", DEFAULT_RULES)
    defaults = manifest.get("default_visibility", {})
    curriculum = manifest.get("curriculum_context", {})
    materials: list[dict[str, Any]] = []
    media_assets: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            continue

        relative_path = str(path.relative_to(source_dir))
        path_text = f"{relative_path} {path.stem}"
        if not _passes_path_filters(path_text, manifest):
            continue
        content_type = _content_type(ext)
        material_type = _material_type(path_text, ext, rules)
        metadata = _extract_metadata(path_text)
        jokbo_fields = _extract_jokbo_fields(path)
        guessed_course, guessed_unit = _guess_course_unit(path_text)
        material_id = _material_id(relative_path)
        file_hash = _sha256(path) if hash_files else ""

        material = {
            "material_id": material_id,
            "source_system": "ipdisk",
            "source_root_label": manifest.get("source_root_label", "authorized local mirror"),
            "source_root": str(source_dir),
            "institution": curriculum.get("institution", ""),
            "college": curriculum.get("college", ""),
            "curriculum_phase": curriculum.get("curriculum_phase", ""),
            "academic_year": curriculum.get("academic_year", ""),
            "semester": curriculum.get("semester", ""),
            "relative_path": relative_path,
            "original_name": path.name,
            "extension": ext,
            "material_type": material_type,
            "content_type": content_type,
            "course": guessed_course,
            "unit": guessed_unit or jokbo_fields["lecture_topic"],
            "teacher": metadata["teacher"],
            "year": metadata["year"],
            "date": metadata["date"],
            "period": metadata["period"],
            "exam_type": metadata["exam_type"],
            "jokbo_type": metadata["jokbo_type"],
            "jokbo_label": jokbo_fields["jokbo_label"],
            "lecture_topic": jokbo_fields["lecture_topic"],
            "contributor": jokbo_fields["contributor"],
            "turn": metadata["turn"],
            "grade": metadata["grade"] or curriculum.get("grade", ""),
            "file_size": path.stat().st_size,
            "file_hash": file_hash,
            "review_status": "needs_review",
            "approved_for_ingest": bool(defaults.get("approved_for_ingest", False)),
            "student_visible": bool(defaults.get("student_visible", False)),
            "created_at": now,
            "updated_at": now,
        }
        materials.append(material)

        if content_type in {"image", "video", "audio"}:
            modality = _guess_modality(path_text, content_type)
            media_assets.append({
                "asset_id": _asset_id(material_id),
                "source_system": "ipdisk",
                "source_material_id": material_id,
                "source_root_label": material["source_root_label"],
                "institution": material["institution"],
                "college": material["college"],
                "curriculum_phase": material["curriculum_phase"],
                "academic_year": material["academic_year"],
                "semester": material["semester"],
                "relative_path": relative_path,
                "asset_type": _guess_asset_type(path_text, content_type),
                "modality": modality,
                "subject": "",
                "unit": guessed_unit,
                "diagnosis": "",
                "caption": "",
                "key_findings": [],
                "deidentified": False,
                "approved_for_question_use": bool(defaults.get("approved_for_question_use", False)),
                "student_visible": bool(defaults.get("student_visible", False)),
                "original_name": path.name,
                "file_path": str(path),
                "file_hash": file_hash,
                "review_status": "needs_review",
                "created_at": now,
                "updated_at": now,
            })

    return materials, media_assets


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _copy_files(source_dir: Path, materials: list[dict[str, Any]], target_dir: Path) -> None:
    files_dir = target_dir / "files"
    for material in materials:
        src = source_dir / material["relative_path"]
        dst = files_dir / material["relative_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan an authorized IPDISK local mirror into P:accine draft metadata."
    )
    parser.add_argument("--probe-url", help="Check whether an IPDISK URL appears to require login.")
    parser.add_argument("--source-dir", type=Path, help="Authorized local folder to scan.")
    parser.add_argument("--manifest", type=Path, help="Optional ingest manifest JSON.")
    parser.add_argument("--output-dir", type=Path, default=Path("data_private/ipdisk/imports"))
    parser.add_argument("--batch-slug", help="Override output batch slug.")
    parser.add_argument("--hash-files", action="store_true", help="Compute SHA256 for each discovered file.")
    parser.add_argument("--copy-files", action="store_true", help="Copy scanned files into data_private output.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing draft JSON.")
    args = parser.parse_args()

    if args.probe_url:
        print(json.dumps(_probe_url(args.probe_url), ensure_ascii=False, indent=2))
        return 0

    if not args.source_dir:
        raise ValueError("--source-dir is required unless --probe-url is used")
    if not args.source_dir.exists() or not args.source_dir.is_dir():
        raise ValueError(f"source directory does not exist: {args.source_dir}")

    manifest = _load_manifest(args.manifest)
    batch_slug = args.batch_slug or manifest.get("batch_slug")
    if not batch_slug:
        batch_slug = f"ipdisk_scan_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    materials, media_assets = _scan_source(
        source_dir=args.source_dir,
        manifest=manifest,
        hash_files=args.hash_files,
    )

    status = {
        "source_dir": str(args.source_dir),
        "batch_slug": batch_slug,
        "materials_count": len(materials),
        "media_assets_count": len(media_assets),
        "material_type_counts": {},
        "content_type_counts": {},
        "written": not args.dry_run,
    }
    for material in materials:
        status["material_type_counts"][material["material_type"]] = (
            status["material_type_counts"].get(material["material_type"], 0) + 1
        )
        status["content_type_counts"][material["content_type"]] = (
            status["content_type_counts"].get(material["content_type"], 0) + 1
        )

    if not args.dry_run:
        target_dir = args.output_dir / str(batch_slug)
        _write_json(target_dir / "materials.draft.json", materials)
        _write_json(target_dir / "media_assets.draft.json", media_assets)
        _write_json(target_dir / "summary.json", status)
        if args.copy_files:
            _copy_files(args.source_dir, materials, target_dir)
        status["output_dir"] = str(target_dir)

    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ipdisk_ingest_harness error: {exc}", file=sys.stderr)
        raise SystemExit(1)
