import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api_server
from src.services import lecture_studio


@pytest.fixture()
def isolated_media_store(tmp_path: Path):
    media_dir = tmp_path / "media_bank"
    asset_dir = media_dir / "assets"
    index_path = media_dir / "media_assets.json"
    question_dir = tmp_path / "question_bank"
    review_dir = tmp_path / "review_sets"
    export_dir = tmp_path / "export_sets"
    upload_dir = tmp_path / "uploads"
    extracted_dir = tmp_path / "extracted"
    generated_dir = tmp_path / "generated"
    image_dir = tmp_path / "images"
    converted_dir = tmp_path / "converted"

    patches = [
        patch.object(lecture_studio, "DATA_ROOT", tmp_path),
        patch.object(lecture_studio, "MEDIA_DIR", media_dir),
        patch.object(lecture_studio, "MEDIA_ASSET_DIR", asset_dir),
        patch.object(lecture_studio, "MEDIA_INDEX_PATH", index_path),
        patch.object(lecture_studio, "QUESTION_BANK_DIR", question_dir),
        patch.object(lecture_studio, "REVIEW_SET_DIR", review_dir),
        patch.object(lecture_studio, "EXPORT_SET_DIR", export_dir),
        patch.object(lecture_studio, "UPLOAD_DIR", upload_dir),
        patch.object(lecture_studio, "EXTRACTED_DIR", extracted_dir),
        patch.object(lecture_studio, "GENERATED_DIR", generated_dir),
        patch.object(lecture_studio, "IMAGE_DIR", image_dir),
        patch.object(lecture_studio, "CONVERTED_DIR", converted_dir),
    ]
    for item in patches:
        item.start()
    lecture_studio.ensure_studio_dirs()
    try:
        yield {
            "index": index_path,
            "assets": asset_dir,
            "questions": question_dir,
        }
    finally:
        for item in reversed(patches):
            item.stop()


def _write_asset(store: dict[str, Path], asset_id: str, *, approved: bool = True, deidentified: bool = True):
    stored_name = f"{asset_id}.png"
    (store["assets"] / stored_name).write_bytes(b"png")
    asset = {
        "asset_id": asset_id,
        "stored_name": stored_name,
        "approved_for_question_use": approved,
        "deidentified": deidentified,
        "created_at": "2026-07-20T00:00:00+00:00",
    }
    store["index"].write_text(json.dumps([asset]), encoding="utf-8")
    return asset


def test_delete_media_asset_is_blocked_while_question_set_references_it(isolated_media_store):
    store = isolated_media_store
    asset = _write_asset(store, "media_used")
    packet = {
        "set_id": "set_1",
        "metadata": {"set_name": "안전 삭제 검사", "selected_media_ids": ["media_used"]},
        "questions": [
            {"question_id": "q1", "image_refs": [{"id": "media_used"}]},
        ],
    }
    (store["questions"] / "set_1.question_set.json").write_text(
        json.dumps(packet, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(lecture_studio.MediaAssetInUseError) as exc_info:
        lecture_studio.delete_media_asset("media_used")

    assert exc_info.value.references
    assert (store["assets"] / asset["stored_name"]).exists()
    assert lecture_studio.list_media_assets()[0]["asset_id"] == "media_used"


def test_delete_media_asset_succeeds_when_unreferenced(isolated_media_store):
    store = isolated_media_store
    asset = _write_asset(store, "media_free")

    deleted = lecture_studio.delete_media_asset("media_free")

    assert deleted["asset_id"] == "media_free"
    assert not (store["assets"] / asset["stored_name"]).exists()
    assert lecture_studio.list_media_assets() == []


def test_selected_media_must_be_approved_and_deidentified():
    safe = {
        "asset_id": "safe",
        "approved_for_question_use": True,
        "deidentified": True,
    }
    lecture_studio.validate_selected_media_assets(["safe"], [safe])

    unsafe = {
        "asset_id": "unsafe",
        "approved_for_question_use": True,
        "deidentified": False,
    }
    with pytest.raises(ValueError, match="승인·비식별"):
        lecture_studio.validate_selected_media_assets(["unsafe"], [unsafe])


def test_selected_media_must_exist():
    with pytest.raises(ValueError, match="존재하지 않는"):
        lecture_studio.validate_selected_media_assets(["missing"], [])


def test_media_delete_endpoint_returns_conflict_for_referenced_asset(monkeypatch):
    def blocked_delete(asset_id: str):
        raise lecture_studio.MediaAssetInUseError(
            asset_id,
            [{"set_id": "set_1", "question_id": "q1", "field": "image_refs"}],
        )

    monkeypatch.setattr(api_server, "delete_media_asset", blocked_delete)
    client = TestClient(api_server.app)
    client.cookies.set("paccine_role", "faculty")
    response = client.delete("/api/media/media_used")

    assert response.status_code == 409
    assert "연결되어 있어 삭제할 수 없습니다" in response.json()["detail"]
