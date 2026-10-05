import json
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_server import app


def test_source_hub_list_exposes_preview_review_and_answer_key_state():
    record = {
        "exam": {
            "source_exam": "heme_midterm_2026",
            "source_file": "혈액종양_2026_중간.hwp",
            "course_name": "혈액및종양학",
            "round_label": "중간고사",
        },
        "answer_key": {"source_file": "혈액종양_정답.xlsx"},
        "questions": [
            {"question_id": "q1", "answer": 2, "needs_review": False},
            {"question_id": "q2", "answer": None, "needs_review": True},
        ],
        "media_assets": [],
    }
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        extracted = root / "extracted"
        previews = root / "previews"
        extracted.mkdir()
        previews.mkdir()
        (extracted / "heme_midterm_2026.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        (previews / "heme_midterm_2026.html").write_text("<h1>preview</h1>", encoding="utf-8")

        with (
            patch("api_server.ensure_course_exam_dirs"),
            patch("api_server.COURSE_EXAM_EXTRACTED_DIR", extracted),
            patch("api_server.COURSE_EXAM_PREVIEW_DIR", previews),
        ):
            response = TestClient(app).get("/api/course-exams")

    assert response.status_code == 200
    source = response.json()["exams"][0]
    assert source["exam_id"] == "heme_midterm_2026"
    assert source["preview_url"] == "/api/course-exams/previews/heme_midterm_2026.html"
    assert source["review_set_id"] == "course_exam_heme_midterm_2026"
    assert source["review_set_exists"] is False
    assert source["answer_key_source"] == "혈액종양_정답.xlsx"
    assert source["question_count"] == 2
    assert source["needs_review_count"] == 1


def test_source_hub_import_preserves_original_name_and_faculty_metadata():
    extracted_record = {
        "exam": {"source_exam": "source_hub_import", "source_file": "temporary.pdf"},
        "questions": [{"question_id": "q1", "answer": 1, "needs_review": False}],
        "media_assets": [],
    }
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        directories = {
            "COURSE_EXAM_UPLOAD_DIR": root / "uploads",
            "COURSE_EXAM_EXTRACTED_DIR": root / "extracted",
            "COURSE_EXAM_MARKDOWN_DIR": root / "markdown",
            "COURSE_EXAM_MEDIA_DIR": root / "media",
            "COURSE_EXAM_PREVIEW_DIR": root / "previews",
            "LEARNING_ANALYTICS_DIR": root / "analytics",
        }
        with ExitStack() as stack:
            for name, path in directories.items():
                stack.enter_context(patch(f"api_server.{name}", path))
            stack.enter_context(patch("api_server.extract_course_exam_pdf_file", return_value=extracted_record))
            stack.enter_context(patch("api_server.render_course_exam_markdown", return_value="# preview"))
            stack.enter_context(patch("api_server.render_course_exam_preview", return_value="<h1>preview</h1>"))
            stack.enter_context(patch(
                "api_server.archive_course_exam_review_set",
                return_value={"set_id": "course_exam_source_hub_import", "summary": {}},
            ))
            client = TestClient(app)
            client.cookies.set("paccine_role", "faculty")
            response = client.post(
                "/api/course-exams/import",
                data={"subject": "혈액및종양학", "unit": "중간고사"},
                files={"exam_file": ("혈액종양_2026_중간.pdf", b"pdf", "application/pdf")},
            )
            review_response = client.post("/api/course-exams/source_hub_import/review-set")
            saved = json.loads(
                (directories["COURSE_EXAM_EXTRACTED_DIR"] / "source_hub_import.json").read_text(encoding="utf-8")
            )

    assert response.status_code == 200
    assert review_response.status_code == 200
    assert review_response.json()["set_id"] == "course_exam_source_hub_import"
    assert response.json()["exam_id"] == "source_hub_import"
    assert response.json()["summary"]["exam_id"] == "source_hub_import"
    assert saved["exam"]["source_file"] == "혈액종양_2026_중간.pdf"
    assert saved["exam"]["course_name"] == "혈액및종양학"
    assert saved["exam"]["round_label"] == "중간고사"
