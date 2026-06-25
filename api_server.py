from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.services.anki_export import build_anki_export
from src.services.cbt_hwp_export import build_cbt_hwp_export
from src.services.choice_explanations import build_choice_explanation_draft
from src.services.lecture_studio import (
    EXPORT_SET_DIR,
    IMAGE_DIR,
    MEDIA_ASSET_DIR,
    delete_media_asset,
    generate_studio_questions,
    get_model_catalog,
    load_question_set,
    list_media_assets,
    list_question_sets,
    save_media_asset,
    save_upload_bytes,
    split_metadata_values,
    update_question_review,
)
from src.services.medlegal_studio import (
    load_medlegal_case,
    load_medlegal_submission,
    list_medlegal_cases,
    submit_medlegal_note,
)
from src.services.notebooklm_import import import_notebooklm_question_set
from src.services.rag_library import (
    DEFAULT_COURSE_ID as DEFAULT_RAG_COURSE_ID,
    draft_anki_cards_from_evidence,
    get_rag_index_status,
    search_rag_evidence,
)
from scripts.extract_course_exam_hwp import (
    extract_file as extract_course_exam_hwp_file,
    render_markdown as render_course_exam_markdown,
    slugify as course_exam_slugify,
)
from scripts.extract_course_exam_pdf import extract_file as extract_course_exam_pdf_file
from scripts.render_course_exam_preview import render_record as render_course_exam_preview
from scripts.extract_answer_key_xlsx import (
    apply_answer_key_to_record,
    parse_answer_key_xlsx,
)


ROOT = Path(__file__).parent
FRONTEND_DIR = ROOT / "frontend"
COURSE_EXAM_ROOT = ROOT / "data_private" / "course_exams"
COURSE_EXAM_UPLOAD_DIR = COURSE_EXAM_ROOT / "uploads"
COURSE_EXAM_EXTRACTED_DIR = COURSE_EXAM_ROOT / "extracted"
COURSE_EXAM_MARKDOWN_DIR = COURSE_EXAM_ROOT / "markdown"
COURSE_EXAM_MEDIA_DIR = COURSE_EXAM_ROOT / "media"
COURSE_EXAM_PREVIEW_DIR = COURSE_EXAM_ROOT / "previews"
VIEWABLE_COURSE_MEDIA_EXTS = {".bmp", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

app = FastAPI(
    title="Axioma Studio API",
    description="HTML/CSS 교수용 Studio UI를 위한 로컬 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def save_upload_file(upload: UploadFile, *, kind: str):
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"{upload.filename or kind} 파일이 비어 있습니다.")
    return save_upload_bytes(content, upload.filename or f"{kind}.txt", kind=kind)


def form_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def ensure_course_exam_dirs() -> None:
    for directory in (
        COURSE_EXAM_UPLOAD_DIR,
        COURSE_EXAM_EXTRACTED_DIR,
        COURSE_EXAM_MARKDOWN_DIR,
        COURSE_EXAM_MEDIA_DIR,
        COURSE_EXAM_PREVIEW_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def course_exam_summary(record: dict) -> dict:
    questions = record.get("questions", [])
    exam = record.get("exam", {})
    labeling = exam.get("labeling", {})
    def has_question_labels(question: dict) -> bool:
        labels = question.get("labels") or {}
        if labels.get("labeling_status") == "labeled":
            return True
        return any(
            labels.get(key)
            for key in (
                "course_name_labeled",
                "course_name",
                "major_category",
                "topic",
                "subtopic",
                "assessment_domain",
                "question_type_labeled",
                "question_type",
                "concept_tags",
            )
        )

    return {
        "source_exam": exam.get("source_exam"),
        "source_file": exam.get("source_file"),
        "course_id": exam.get("course_id"),
        "course_name": exam.get("course_name"),
        "grade": exam.get("grade"),
        "exam_date": exam.get("exam_date"),
        "round_label": exam.get("round_label"),
        "period_label": exam.get("period_label"),
        "parser_version": exam.get("parser_version"),
        "question_count": len(questions),
        "expected_objective_count": record.get("exam", {}).get("objective_count_from_filename"),
        "with_answer_count": sum(1 for q in questions if q.get("answer") is not None),
        "with_stimulus_count": sum(1 for q in questions if q.get("stimulus")),
        "with_explanation_count": sum(1 for q in questions if q.get("explanation")),
        "needs_review_count": sum(1 for q in questions if q.get("needs_review")),
        "media_asset_count": len(record.get("media_assets", [])),
        "media_linked_question_count": sum(
            1 for q in questions if q.get("media", {}).get("media_refs")
        ),
        "extraction_warnings": record.get("exam", {}).get("extraction_warnings", []),
        "labeling": labeling,
        "labeled_question_count": sum(
            1 for q in questions if has_question_labels(q)
        ),
    }


def load_course_exam_record(exam_id: str) -> tuple[Path, dict]:
    safe_name = Path(exam_id).name
    if not safe_name.endswith(".json"):
        safe_name = f"{safe_name}.json"
    record_path = (COURSE_EXAM_EXTRACTED_DIR / safe_name).resolve()
    extracted_root = COURSE_EXAM_EXTRACTED_DIR.resolve()
    if extracted_root not in record_path.parents or not record_path.exists():
        raise FileNotFoundError(exam_id)
    return record_path, json.loads(record_path.read_text(encoding="utf-8"))


def course_exam_media_url(asset: dict) -> str | None:
    file_path_value = asset.get("file_path")
    if not file_path_value:
        return None
    file_path = Path(file_path_value)
    if not file_path.is_absolute():
        file_path = (ROOT / file_path).resolve()
    if file_path.suffix.lower() not in VIEWABLE_COURSE_MEDIA_EXTS or not file_path.exists():
        return None

    relative_path = asset.get("relative_path")
    if relative_path:
        relative = Path(relative_path)
    else:
        try:
            relative = file_path.relative_to(COURSE_EXAM_MEDIA_DIR.resolve())
        except ValueError:
            return None
    source_dir = Path(relative).parent.name
    filename = Path(relative).name
    return f"/api/course-exams/media/{quote(source_dir)}/{quote(filename)}"


def course_exam_answer_values(question: dict) -> list[str]:
    source = question.get("generated_answer")
    if not source:
        source = question.get("answer")
    values = source if isinstance(source, list) else [source]
    return [str(value).strip() for value in values if str(value or "").strip()]


def course_exam_choice_count(question: dict) -> int:
    choices = question.get("choices") or {}
    if isinstance(choices, dict):
        return sum(1 for value in choices.values() if str(value or "").strip())
    if isinstance(choices, list):
        return sum(1 for value in choices if str(value or "").strip())
    return 0


def course_exam_is_practice_ready(question: dict) -> bool:
    if not str(question.get("stem") or "").strip():
        return False
    if not course_exam_answer_values(question):
        return False
    if course_exam_choice_count(question) < 2:
        return False
    choice_text = " ".join(
        str(value)
        for value in (question.get("choices") or {}).values()
        if str(value or "").strip()
    )
    malformed_markers = ("<문제해설>", "<-케이스->", "@")
    return not any(marker in choice_text for marker in malformed_markers)


def course_exam_practice_question(question: dict, media_by_id: dict[str, dict]) -> dict:
    media_refs = []
    for ref in question.get("media", {}).get("media_refs") or []:
        asset = media_by_id.get(ref.get("media_id"), {})
        media_refs.append(
            {
                **ref,
                "url": course_exam_media_url(asset),
                "filename": Path(asset.get("file_path") or "").name,
                "caption": asset.get("caption"),
                "modality": asset.get("modality"),
                "needs_review": ref.get("needs_review", asset.get("needs_review", True)),
            }
        )
    return {
        "question_id": question.get("question_id"),
        "question_number": question.get("question_number"),
        "stem": question.get("stem"),
        "stimulus": question.get("stimulus"),
        "choices": question.get("choices") or {},
        "answer": question.get("answer"),
        "generated_answer": question.get("generated_answer"),
        "explanation": question.get("explanation"),
        "key_info": question.get("key_info"),
        "answer_rationale": question.get("answer_rationale"),
        "choice_explanations": question.get("choice_explanations") or question.get("explanations_by_choice"),
        "key_learning_points": question.get("key_learning_points") or [],
        "anki_cards": question.get("anki_cards") or question.get("anki_card_candidates") or [],
        "question_format": question.get("question_format"),
        "sub_format": question.get("sub_format"),
        "labels": question.get("labels") or {},
        "needs_review": question.get("needs_review", True),
        "review_reasons": question.get("review_reasons") or [],
        "media_refs": media_refs,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": "axioma-studio"}


@app.get("/api/models")
def models() -> dict:
    return get_model_catalog()


@app.get("/api/rag/status")
def rag_status(course_id: str = DEFAULT_RAG_COURSE_ID) -> dict:
    return get_rag_index_status(course_id)


@app.get("/api/rag/search")
def rag_search(q: str, course_id: str = DEFAULT_RAG_COURSE_ID, limit: int = 8) -> dict:
    try:
        return search_rag_evidence(q, course_id=course_id, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/rag/anki-draft")
def rag_anki_draft(payload: Annotated[dict, Body()]) -> dict:
    query = str(payload.get("query") or payload.get("q") or "").strip()
    course_id = str(payload.get("course_id") or DEFAULT_RAG_COURSE_ID).strip()
    limit = int(payload.get("limit") or 5)
    try:
        return draft_anki_cards_from_evidence(query, course_id=course_id, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/questions/choice-explanations/draft")
def choice_explanation_draft(payload: Annotated[dict, Body()]) -> dict:
    question = payload.get("question") if isinstance(payload.get("question"), dict) else payload
    if not isinstance(question, dict):
        raise HTTPException(status_code=400, detail="question 객체가 필요합니다.")
    course_id = payload.get("course_id") if isinstance(payload, dict) else None
    use_rag = form_bool(payload.get("use_rag", True)) if isinstance(payload, dict) else True
    return build_choice_explanation_draft(question, course_id=course_id, use_rag=use_rag)


@app.get("/api/studio/images/{filename}")
def studio_image(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    image_path = (IMAGE_DIR / safe_name).resolve()
    image_root = IMAGE_DIR.resolve()
    if image_root not in image_path.parents or not image_path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    return FileResponse(image_path)


@app.get("/api/media")
def media_assets() -> dict:
    return {"assets": list_media_assets()}


@app.get("/api/media/assets/{filename}")
def media_asset_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    asset_path = (MEDIA_ASSET_DIR / safe_name).resolve()
    asset_root = MEDIA_ASSET_DIR.resolve()
    if asset_root not in asset_path.parents or not asset_path.exists():
        raise HTTPException(status_code=404, detail="미디어 파일을 찾을 수 없습니다.")
    return FileResponse(asset_path)


@app.delete("/api/media/{asset_id}")
def remove_media_asset(asset_id: str) -> dict:
    try:
        return {"deleted": delete_media_asset(asset_id)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="제시자료를 찾을 수 없습니다.") from None


@app.get("/api/course-exams")
def course_exam_list(limit: int = 50) -> dict:
    ensure_course_exam_dirs()
    exams = []
    for record_path in sorted(
        COURSE_EXAM_EXTRACTED_DIR.glob("*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:limit]:
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        summary = course_exam_summary(record)
        questions = record.get("questions", [])
        summary.update(
            {
                "exam_id": record_path.stem,
                "updated_at": datetime.fromtimestamp(record_path.stat().st_mtime).isoformat(timespec="seconds"),
                "practice_ready_count": sum(
                    1
                    for question in questions
                    if course_exam_is_practice_ready(question)
                ),
            }
        )
        exams.append(summary)
    return {"exams": exams}


@app.get("/api/course-exams/extracted/{exam_id}")
def course_exam_detail(exam_id: str, limit: int | None = None) -> dict:
    try:
        record_path, record = load_course_exam_record(exam_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="구조화된 시험지를 찾을 수 없습니다.") from None

    media_by_id = {
        asset.get("media_id"): asset
        for asset in record.get("media_assets", [])
        if asset.get("media_id")
    }
    questions = [
        course_exam_practice_question(question, media_by_id)
        for question in record.get("questions", [])
        if course_exam_is_practice_ready(question)
    ]
    if limit and limit > 0:
        questions = questions[:limit]
    return {
        "exam_id": record_path.stem,
        "exam": record.get("exam", {}),
        "summary": course_exam_summary(record),
        "questions": questions,
        "question_index": record.get("question_index") or [],
        "subjective_questions": record.get("subjective_questions") or [],
        "final_review_summary": record.get("final_review_summary") or {},
    }


@app.get("/api/course-exams/previews/{filename}")
def course_exam_preview_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    preview_path = (COURSE_EXAM_PREVIEW_DIR / safe_name).resolve()
    preview_root = COURSE_EXAM_PREVIEW_DIR.resolve()
    if preview_root not in preview_path.parents or not preview_path.exists():
        raise HTTPException(status_code=404, detail="검수 미리보기를 찾을 수 없습니다.")
    return FileResponse(preview_path, media_type="text/html")


@app.get("/api/course-exams/media/{source_exam}/{filename}")
def course_exam_media_file(source_exam: str, filename: str) -> FileResponse:
    safe_source = Path(source_exam).name
    safe_name = Path(filename).name
    media_path = (COURSE_EXAM_MEDIA_DIR / safe_source / safe_name).resolve()
    media_root = COURSE_EXAM_MEDIA_DIR.resolve()
    if media_root not in media_path.parents or not media_path.exists():
        raise HTTPException(status_code=404, detail="시험지 제시자료를 찾을 수 없습니다.")
    return FileResponse(media_path)


@app.post("/api/course-exams/import")
async def import_course_exam(
    exam_file: Annotated[UploadFile, File(description="기출/과정시험 HWP 또는 PDF")],
    answer_key_file: Annotated[UploadFile | None, File(description="정답지 XLSX")] = None,
) -> dict:
    ensure_course_exam_dirs()
    content = await exam_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="시험지 파일이 비어 있습니다.")

    original_name = exam_file.filename or "course_exam"
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".hwp", ".pdf"}:
        raise HTTPException(status_code=400, detail="현재 HWP/PDF 시험지만 구조화할 수 있습니다.")

    safe_stem = course_exam_slugify(Path(original_name).stem)
    saved_path = COURSE_EXAM_UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}_{safe_stem}{suffix}"
    saved_path.write_bytes(content)

    try:
        if suffix == ".pdf":
            record = extract_course_exam_pdf_file(saved_path, media_root=COURSE_EXAM_MEDIA_DIR)
        else:
            record = extract_course_exam_hwp_file(saved_path, media_root=COURSE_EXAM_MEDIA_DIR)
        if answer_key_file and answer_key_file.filename:
            key_content = await answer_key_file.read()
            if key_content:
                key_suffix = Path(answer_key_file.filename).suffix.lower()
                if key_suffix not in {".xlsx", ".xlsm"}:
                    raise HTTPException(status_code=400, detail="정답지는 XLSX 파일만 지원합니다.")
                key_stem = course_exam_slugify(Path(answer_key_file.filename).stem)
                key_path = COURSE_EXAM_UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}_answer_key_{key_stem}{key_suffix}"
                key_path.write_bytes(key_content)
                record = apply_answer_key_to_record(record, parse_answer_key_xlsx(key_path))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"시험지 구조화 실패: {exc}") from exc

    output_name = f"{course_exam_slugify(record['exam']['source_exam'])}.json"
    markdown_name = f"{course_exam_slugify(record['exam']['source_exam'])}.md"
    preview_name = f"{course_exam_slugify(record['exam']['source_exam'])}.html"
    output_path = COURSE_EXAM_EXTRACTED_DIR / output_name
    markdown_path = COURSE_EXAM_MARKDOWN_DIR / markdown_name
    preview_path = COURSE_EXAM_PREVIEW_DIR / preview_name

    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_course_exam_markdown(record), encoding="utf-8")
    preview_path.write_text(render_course_exam_preview(record, preview_path), encoding="utf-8")

    return {
        "status": "imported",
        "summary": course_exam_summary(record),
        "paths": {
            "json": str(output_path),
            "markdown": str(markdown_path),
            "preview": str(preview_path),
        },
        "answer_key": record.get("answer_key"),
        "preview_url": f"/api/course-exams/previews/{preview_name}",
    }


@app.post("/api/media")
async def upload_media_asset(
    media_file: Annotated[UploadFile, File(description="환자 사진/영상/병리/검사 이미지")],
    asset_type: Annotated[str, Form()] = "clinical_photo",
    modality: Annotated[str, Form()] = "",
    subject: Annotated[str, Form()] = "",
    unit: Annotated[str, Form()] = "",
    diagnosis: Annotated[str, Form()] = "",
    caption: Annotated[str, Form()] = "",
    key_findings: Annotated[str, Form()] = "",
    deidentified: Annotated[str, Form()] = "false",
    approved_for_question_use: Annotated[str, Form()] = "false",
    faculty_note: Annotated[str, Form()] = "",
) -> dict:
    content = await media_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="미디어 파일이 비어 있습니다.")
    asset = save_media_asset(
        content,
        media_file.filename or "media.png",
        asset_type=asset_type,
        modality=modality.strip(),
        subject=subject.strip(),
        unit=unit.strip(),
        diagnosis=diagnosis.strip(),
        caption=caption.strip(),
        key_findings=key_findings,
        deidentified=form_bool(deidentified),
        approved_for_question_use=form_bool(approved_for_question_use),
        faculty_note=faculty_note.strip(),
    )
    return {"asset": asset}


@app.get("/api/question-sets")
def question_sets(limit: int = 20) -> dict:
    return {"sets": list_question_sets(limit=limit)}


@app.get("/api/question-sets/{set_id}")
def question_set_detail(set_id: str) -> dict:
    try:
        return load_question_set(set_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/notebooklm/import")
def import_notebooklm(payload: Annotated[dict, Body()]) -> dict:
    try:
        return import_notebooklm_question_set(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/medlegal/cases")
def medlegal_cases(track: str | None = None) -> dict:
    return {"cases": list_medlegal_cases(track=track)}


@app.get("/api/medlegal/cases/{case_id}")
def medlegal_case_detail(case_id: str) -> dict:
    try:
        return load_medlegal_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="의료법/EMR 교육 케이스를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/medlegal/cases/{case_id}/submit")
def submit_medlegal_case_note(
    case_id: str,
    payload: Annotated[dict, Body()],
) -> dict:
    try:
        return submit_medlegal_note(
            case_id,
            str(payload.get("note_text") or ""),
            learner_role=str(payload.get("learner_role") or "student"),
            note_type=str(payload.get("note_type") or ""),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="의료법/EMR 교육 케이스를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/medlegal/submissions/{submission_id}")
def medlegal_submission_detail(submission_id: str) -> dict:
    try:
        return load_medlegal_submission(submission_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="제출 기록을 찾을 수 없습니다.") from None


@app.post("/api/question-sets/{set_id}/export/anki")
def export_question_set_anki(
    set_id: str,
    payload: Annotated[dict | None, Body()] = None,
) -> dict:
    payload = payload or {}
    try:
        return build_anki_export(
            set_id,
            deck_name=str(payload.get("deck_name") or "").strip() or None,
            include_unapproved=form_bool(payload.get("include_unapproved")),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Anki export 생성 실패: {exc}") from exc


@app.post("/api/question-sets/{set_id}/export/cbt-hwp")
def export_question_set_cbt_hwp(
    set_id: str,
    payload: Annotated[dict | None, Body()] = None,
) -> dict:
    payload = payload or {}
    try:
        return build_cbt_hwp_export(
            set_id,
            include_unapproved=form_bool(payload.get("include_unapproved")),
            include_answers=payload.get("include_answers", True) is not False,
            include_explanations=payload.get("include_explanations", True) is not False,
            include_references=payload.get("include_references", True) is not False,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CBT HWP 양식 생성 실패: {exc}") from exc


@app.get("/api/exports/{filename}")
def export_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    export_path = (EXPORT_SET_DIR / safe_name).resolve()
    export_root = EXPORT_SET_DIR.resolve()
    if export_root not in export_path.parents or not export_path.exists():
        raise HTTPException(status_code=404, detail="내보내기 파일을 찾을 수 없습니다.")
    return FileResponse(export_path, filename=safe_name)


@app.patch("/api/question-sets/{set_id}/questions/{question_id}")
def update_question_detail(
    set_id: str,
    question_id: str,
    payload: Annotated[dict, Body()],
) -> dict:
    try:
        updates = payload.get("updates", payload)
        comment = str(payload.get("comment") or "")
        actor_id = str(payload.get("actor_id") or "local_faculty")
        return update_question_review(
            set_id,
            question_id,
            updates,
            action="edited",
            actor_id=actor_id,
            comment=comment,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/question-sets/{set_id}/questions/{question_id}/approve")
def approve_question(
    set_id: str,
    question_id: str,
    payload: Annotated[dict | None, Body()] = None,
) -> dict:
    payload = payload or {}
    try:
        return update_question_review(
            set_id,
            question_id,
            payload.get("updates", {}),
            action="approved",
            actor_id=str(payload.get("actor_id") or "local_faculty"),
            comment=str(payload.get("comment") or "교수 검수 승인"),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.") from None


@app.post("/api/question-sets/{set_id}/questions/{question_id}/reject")
def reject_question(
    set_id: str,
    question_id: str,
    payload: Annotated[dict | None, Body()] = None,
) -> dict:
    payload = payload or {}
    try:
        return update_question_review(
            set_id,
            question_id,
            payload.get("updates", {}),
            action="rejected",
            actor_id=str(payload.get("actor_id") or "local_faculty"),
            comment=str(payload.get("comment") or "교수 검수 반려"),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.") from None


@app.post("/api/generate")
async def generate_questions(
    lecture_file: Annotated[UploadFile, File(description="강의자료 PDF/DOCX/PPTX/HWP/TXT/MD")],
    style_files: Annotated[list[UploadFile] | None, File(description="기출문항 유형 참고 자료")] = None,
    evidence_files: Annotated[list[UploadFile] | None, File(description="승인 근거자료")] = None,
    image_files: Annotated[list[UploadFile] | None, File(description="사진/영상/검사 이미지 자료")] = None,
    subject: Annotated[str, Form()] = "General",
    unit: Annotated[str, Form()] = "미분류",
    num_questions: Annotated[int, Form(ge=1, le=30)] = 5,
    difficulty: Annotated[str, Form()] = "보통",
    question_type: Annotated[str, Form()] = "clinical_case",
    reference_policy: Annotated[str, Form()] = "local_open",
    image_policy: Annotated[str, Form()] = "none",
    selected_media_ids: Annotated[str, Form()] = "",
    image_description: Annotated[str, Form()] = "",
    include_tables: Annotated[str, Form()] = "false",
    provider: Annotated[str, Form()] = "auto",
    model: Annotated[str, Form()] = "auto",
) -> dict:
    try:
        started_at = datetime.now().isoformat(timespec="seconds")
        print(
            "[studio.generate.start]",
            started_at,
            {
                "lecture": lecture_file.filename,
                "style_count": len([f for f in (style_files or []) if f and f.filename]),
                "evidence_count": len([f for f in (evidence_files or []) if f and f.filename]),
                "image_count": len([f for f in (image_files or []) if f and f.filename]),
                "provider": provider,
                "model": model,
                "question_type": question_type,
                "reference_policy": reference_policy,
                "image_policy": image_policy,
                "selected_media_ids": split_metadata_values(selected_media_ids),
                "has_image_description": bool(image_description.strip()),
                "include_tables": form_bool(include_tables),
            },
            flush=True,
        )
        lecture = await save_upload_file(lecture_file, kind="lecture")
        style_uploads = [
            await save_upload_file(upload, kind="style")
            for upload in (style_files or [])
            if upload and upload.filename
        ]
        evidence_uploads = [
            await save_upload_file(upload, kind="evidence")
            for upload in (evidence_files or [])
            if upload and upload.filename
        ]
        image_uploads = [
            await save_upload_file(upload, kind="image")
            for upload in (image_files or [])
            if upload and upload.filename
        ]

        result = generate_studio_questions(
            lecture,
            subject=subject.strip() or "General",
            unit=unit.strip() or "미분류",
            num_questions=num_questions,
            difficulty=difficulty.strip() or "보통",
            question_type=question_type,
            reference_policy=reference_policy,
            image_policy=image_policy,
            selected_media_ids=split_metadata_values(selected_media_ids),
            image_description=image_description.strip(),
            include_tables=form_bool(include_tables),
            provider=provider,
            model=model,
            style_uploads=style_uploads,
            evidence_uploads=evidence_uploads,
            image_uploads=image_uploads,
        )
        print(
            "[studio.generate.done]",
            datetime.now().isoformat(timespec="seconds"),
            {
                "status": result.get("status"),
                "question_count": result.get("question_count"),
                "output": result.get("paths", {}).get("output"),
            },
            flush=True,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        print("[studio.generate.error]", datetime.now().isoformat(timespec="seconds"), repr(exc), flush=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")
