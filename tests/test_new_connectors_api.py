"""API integration tests for S3 and WebDAV connectors."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.connectors
import api.libraries
import config
from api import app
from core.connectors.base import RemoteDocument
from core.library_store import LibraryStore

PASSWORD_ADMIN = "AdminStrongPass!123"


@pytest.fixture
def api_test_env(tmp_path: Path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()


    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir),
        DATABASE_URL="",
        ADMIN_USERNAME="admin_user",
        ADMIN_PASSWORD=PASSWORD_ADMIN,
        API_KEY="",
    )
    for m in (config, api.auth, api.libraries, api.connectors):
        monkeypatch.setattr(m, "cfg", test_cfg)

    store = LibraryStore(test_cfg.LIBRARY_DB_PATH)
    monkeypatch.setattr(api.libraries, "_store", store)

    api.auth.session_store.clear()
    api.auth.login_guard.clear()

    return test_cfg, store


def test_api_connectors_test_s3_and_webdav(api_test_env):
    cfg, store = api_test_env
    client = TestClient(app)
    login_res = client.post("/api/auth/login", json={"username": "admin_user", "password": PASSWORD_ADMIN})
    assert login_res.status_code == 200

    # Test S3 connector endpoint
    with patch("core.connectors.s3_bucket.S3BucketConnector.test_connection", return_value=(True, "Bucket OK")):
        res_s3 = client.post(
            "/api/connectors/test",
            json={"type": "s3_bucket", "config": {"bucket_name": "test-bucket"}},
        )
        assert res_s3.status_code == 200
        assert res_s3.json()["ok"] is True
        assert res_s3.json()["type"] == "s3_bucket"

    # Test WebDAV connector endpoint
    with patch("core.connectors.webdav.WebDAVConnector.test_connection", return_value=(True, "WebDAV OK")):
        res_dav = client.post(
            "/api/connectors/test",
            json={"type": "webdav", "config": {"base_url": "https://nextcloud.test/dav"}},
        )
        assert res_dav.status_code == 200
        assert res_dav.json()["ok"] is True
        assert res_dav.json()["type"] == "webdav"


def test_api_connectors_sync_s3_imports_documents(api_test_env):
    cfg, store = api_test_env
    lib = store.create_library("Cloud Docs", owner_id="admin_user")

    client = TestClient(app)
    login_res = client.post("/api/auth/login", json={"username": "admin_user", "password": PASSWORD_ADMIN})
    assert login_res.status_code == 200

    mock_doc = RemoteDocument(
        id="s3://test-bucket/guide.md",
        name="guide.md",
        content=b"# Cloud Guide\nWelcome to S3 sync.",
        media_type="text/markdown",
        source_url="s3://test-bucket/guide.md",
        last_modified="2026-01-01T00:00:00Z",
        metadata={"bucket": "test-bucket"},
    )

    with patch("core.connectors.s3_bucket.S3BucketConnector.fetch_documents", return_value=[mock_doc]):
        sync_res = client.post(
            "/api/connectors/sync",
            json={
                "type": "s3_bucket",
                "config": {"bucket_name": "test-bucket"},
                "target_library_id": lib["id"],
            },
        )
        assert sync_res.status_code == 200
        data = sync_res.json()
        assert data["imported_count"] == 1
        assert data["skipped_duplicates"] == 0


    # Verifica che il documento sia effettivamente presente nella biblioteca
    docs = store.list_documents(lib["id"])
    assert len(docs) == 1
    assert docs[0]["filename"] == "guide.md"
