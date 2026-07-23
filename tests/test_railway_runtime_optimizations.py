from __future__ import annotations

import hashlib
import json

from fastapi.testclient import TestClient

import api_server
from src.services import qbank_enrichment


def test_qbank_catalog_supports_conditional_revalidation(monkeypatch):
    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", "")
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", "")
    client = TestClient(api_server.app)

    first = client.get("/api/student/qbank")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "private, max-age=0, must-revalidate"
    etag = first.headers["etag"]

    second = client.get("/api/student/qbank", headers={"if-none-match": etag})
    assert second.status_code == 304
    assert second.headers["etag"] == etag

    weak = client.get("/api/student/qbank", headers={"if-none-match": f"W/{etag}"})
    assert weak.status_code == 304
    assert weak.headers["etag"] == etag
    assert not weak.content


def test_versioned_static_assets_are_immutable(monkeypatch):
    monkeypatch.setattr(api_server, "_ALLOWED_EMAIL", "")
    monkeypatch.setattr(api_server, "_AUTH_PASSWORD", "")
    client = TestClient(api_server.app)

    response = client.get("/student-v3/app.js?v=runtime-test")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_release_snapshot_cache_invalidates_when_file_changes(tmp_path, monkeypatch):
    qbank = tmp_path / "qbank.json"
    releases = tmp_path / "releases.json"
    qbank.write_text(json.dumps({"questions": []}), encoding="utf-8")
    checksum = hashlib.sha256(qbank.read_bytes()).hexdigest()

    def write_release(explanation: str) -> None:
        releases.write_text(
            json.dumps(
                {
                    "built_against_sha256": checksum,
                    "releases": {
                        "Q1": {
                            "approved": True,
                            "medical_approval": True,
                            "demo_release": False,
                            "needs_real_faculty_review": False,
                            "reviewer_id": "faculty:test",
                            "reviewed_at": "2026-07-24T00:00:00Z",
                            "explanation": explanation,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(qbank_enrichment, "QBANK_PATH", qbank)
    monkeypatch.setattr(qbank_enrichment, "RELEASES_PATH", releases)
    qbank_enrichment._load_snapshot.cache_clear()
    qbank_enrichment._sha256_snapshot.cache_clear()

    write_release("first")
    assert qbank_enrichment.load_releases()["Q1"]["explanation"] == "first"
    assert qbank_enrichment.load_releases()["Q1"]["explanation"] == "first"
    assert qbank_enrichment._load_snapshot.cache_info().hits >= 1
    assert qbank_enrichment._sha256_snapshot.cache_info().hits >= 1

    write_release("second-version")
    assert qbank_enrichment.load_releases()["Q1"]["explanation"] == "second-version"
