"""tests/test_storage_presigned_urls.py
Unit tests for Object Storage presigned URLs and download endpoints
(core/storage_provider.py and api/libraries.py).
"""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from api.auth import _require_role, _verify_api_key
from api.libraries import get_library_store, router
from config import cfg
from core.library_store import LibraryStore
from core.storage_provider import EncryptedStorageProvider, LocalStorageProvider, S3StorageProvider
from fastapi import FastAPI


# ==========================================
# 1. S3StorageProvider Presigned URL Tests
# ==========================================

def test_s3_storage_provider_get_url_success():
    provider = S3StorageProvider(
        bucket_name="test-bucket",
        endpoint_url="https://minio.example.com",
        access_key="admin",
        secret_key="secret",
    )
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = (
        "https://minio.example.com/test-bucket/doc123.pdf?X-Amz-Signature=abc123"
    )
    provider._client = mock_client

    url = provider.get_url("lib1/doc123.pdf", expires_seconds=1800)

    assert url == "https://minio.example.com/test-bucket/doc123.pdf?X-Amz-Signature=abc123"
    mock_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "lib1/doc123.pdf"},
        ExpiresIn=1800,
    )


def test_s3_storage_provider_get_url_exception_returns_none():
    provider = S3StorageProvider(bucket_name="test-bucket")
    mock_client = MagicMock()
    mock_client.generate_presigned_url.side_effect = Exception("AWS Error")
    provider._client = mock_client

    url = provider.get_url("doc.pdf")
    assert url is None


def test_encrypted_and_local_storage_provider_get_url_none(tmp_path):
    local = LocalStorageProvider(tmp_path)
    assert local.get_url("doc.pdf") is None

    encrypted = EncryptedStorageProvider(local, encryption_key="0" * 64)
    assert encrypted.get_url("doc.pdf") is None


# ==========================================
# 2. API Download & Download-URL Endpoint Tests
# ==========================================

def test_api_download_url_endpoint_local_returns_proxied(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "libraries.db"))
    monkeypatch.setattr(cfg, "LIBRARY_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(cfg, "STORAGE_BACKEND", "local")

    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("Test Lib", "Description", "private", "testuser")
    doc = store.add_document(
        library_id=lib["id"],
        filename="test.txt",
        media_type="text/plain",
        content=b"Hello World",
        storage_path=f"{lib['id']}/test.txt",
    )

    # Save to storage
    storage_dir = tmp_path / "storage" / lib["id"]
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "test.txt").write_bytes(b"Hello World")

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_library_store] = lambda: store
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "testuser", "role": "admin"}
    app.dependency_overrides[_require_role("editor")] = lambda: {"username": "testuser", "role": "admin"}

    client = TestClient(app)
    res = client.get(f"/api/libraries/{lib['id']}/documents/{doc['id']}/download-url")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "proxied"
    assert "download" in data["download_url"]
    assert data["filename"] == "test.txt"


def test_api_download_url_endpoint_s3_returns_presigned(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "libraries.db"))
    monkeypatch.setattr(cfg, "LIBRARY_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(cfg, "STORAGE_BACKEND", "s3")

    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("Cloud Lib", "Description", "private", "testuser")
    doc = store.add_document(
        library_id=lib["id"],
        filename="cloud_doc.pdf",
        media_type="application/pdf",
        content=b"%PDF-test",
        storage_path=f"{lib['id']}/cloud_doc.pdf",
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_library_store] = lambda: store
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "testuser", "role": "admin"}

    # Mock storage provider get_url
    from core.storage_provider import get_storage_provider
    provider = get_storage_provider()
    mock_url = "https://s3.amazonaws.com/ermes-bucket/cloud_doc.pdf?signed=1"
    monkeypatch.setattr(provider, "get_url", lambda path, expires_seconds=3600: mock_url)
    monkeypatch.setattr("api.libraries.get_storage_provider", lambda: provider)

    client = TestClient(app)
    res = client.get(f"/api/libraries/{lib['id']}/documents/{doc['id']}/download-url?expires_seconds=7200")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "presigned"
    assert data["download_url"] == mock_url
    assert data["expires_in"] == 7200


def test_api_download_redirect_to_presigned(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "libraries.db"))
    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("Cloud Lib 2", "Description", "private", "testuser")
    doc = store.add_document(
        library_id=lib["id"],
        filename="file.pdf",
        media_type="application/pdf",
        content=b"%PDF-test",
        storage_path=f"{lib['id']}/file.pdf",
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_library_store] = lambda: store
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "testuser", "role": "admin"}

    from core.storage_provider import get_storage_provider
    provider = get_storage_provider()
    mock_url = "https://minio.corp/bucket/file.pdf?token=xyz"
    monkeypatch.setattr(provider, "get_url", lambda path, expires_seconds=3600: mock_url)
    monkeypatch.setattr("api.libraries.get_storage_provider", lambda: provider)

    client = TestClient(app)
    res = client.get(f"/api/libraries/{lib['id']}/documents/{doc['id']}/download?redirect=true", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == mock_url
