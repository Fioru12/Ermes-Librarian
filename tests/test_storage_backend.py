"""tests/test_storage_backend.py
Unit and Integration test suite for the unified Document Storage Abstraction Layer.
Covers LocalStorageBackend, S3StorageBackend, security/traversal guards, and API integration.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from api import app
from api.auth import session_store
import api.libraries
from config import cfg
from core.storage_backend import (
    LocalStorageBackend,
    S3StorageBackend,
    StorageFileNotFoundError,
    StoragePathTraversalError,
    get_storage_backend,
    normalize_relative_path,
)


def test_normalize_relative_path_valid():
    assert normalize_relative_path("lib1/doc.pdf") == "lib1/doc.pdf"
    assert normalize_relative_path("/lib1/sub/doc.pdf") == "lib1/sub/doc.pdf"
    assert normalize_relative_path("lib1\\sub\\doc.pdf") == "lib1/sub/doc.pdf"


def test_normalize_relative_path_traversal_rejection():
    with pytest.raises(StoragePathTraversalError):
        normalize_relative_path("../secret.txt")
    with pytest.raises(StoragePathTraversalError):
        normalize_relative_path("lib1/../../secret.txt")
    with pytest.raises(StoragePathTraversalError):
        normalize_relative_path("C:/Windows/System32/calc.exe")
    with pytest.raises(StoragePathTraversalError):
        normalize_relative_path("   ")


def test_local_storage_backend_crud(tmp_path: Path):
    backend = LocalStorageBackend(tmp_path)
    rel_path = "procedures/manual.txt"
    content = b"Ermes Enterprise Manual v1.0"

    # Save
    saved_path = backend.save(rel_path, content)
    assert saved_path == rel_path
    assert backend.exists(rel_path)

    # Read
    read_data = backend.read_bytes(rel_path)
    assert read_data == content

    # Local Path
    local_p = backend.get_local_path(rel_path)
    assert local_p is not None
    assert local_p.is_file()

    # Stream
    chunks = list(backend.get_stream(rel_path, chunk_size=8))
    assert b"".join(chunks) == content

    # Non-existent
    assert not backend.exists("non_existent/file.txt")
    with pytest.raises(StorageFileNotFoundError):
        backend.read_bytes("non_existent/file.txt")

    # Delete
    deleted = backend.delete(rel_path)
    assert deleted is True
    assert not backend.exists(rel_path)
    assert backend.delete(rel_path) is False


def test_local_storage_backend_traversal_defense(tmp_path: Path):
    backend = LocalStorageBackend(tmp_path)
    with pytest.raises(StoragePathTraversalError):
        backend.save("../outside.txt", b"malicious")
    with pytest.raises(StoragePathTraversalError):
        backend.read_bytes("../outside.txt")


def test_s3_storage_backend_mocked():
    mock_s3 = MagicMock()
    backend = S3StorageBackend(
        bucket_name="test-bucket",
        s3_client=mock_s3,
    )

    rel_path = "hr/policy.pdf"
    content = b"%PDF-1.4 Mock Content"

    # Save
    saved = backend.save(rel_path, content)
    assert saved == rel_path
    mock_s3.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key=rel_path,
        Body=content,
    )

    # Exists
    mock_s3.head_object.return_value = {"ContentLength": len(content)}
    assert backend.exists(rel_path) is True
    mock_s3.head_object.assert_called_with(Bucket="test-bucket", Key=rel_path)

    # Read bytes
    mock_body = MagicMock()
    mock_body.read.return_value = content
    mock_s3.get_object.return_value = {"Body": mock_body}
    assert backend.read_bytes(rel_path) == content

    # Stream
    mock_stream_body = MagicMock()
    mock_stream_body.read.side_effect = [b"chunk1", b"chunk2", b""]
    mock_s3.get_object.return_value = {"Body": mock_stream_body}
    chunks = list(backend.get_stream(rel_path, chunk_size=6))
    assert chunks == [b"chunk1", b"chunk2"]

    # Delete
    backend.delete(rel_path)
    mock_s3.delete_object.assert_called_with(Bucket="test-bucket", Key=rel_path)

    # Delete many
    backend.delete_many(["doc1.pdf", "doc2.pdf"])
    mock_s3.delete_objects.assert_called_once_with(
        Bucket="test-bucket",
        Delete={"Objects": [{"Key": "doc1.pdf"}, {"Key": "doc2.pdf"}], "Quiet": True},
    )


def test_factory_get_storage_backend(tmp_path: Path, monkeypatch):
    test_cfg = cfg.replace(
        STORAGE_BACKEND="local",
        BASE_DIR=str(tmp_path),
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    b_local = get_storage_backend(force_refresh=True)
    assert isinstance(b_local, LocalStorageBackend)

    test_cfg_s3 = cfg.replace(
        STORAGE_BACKEND="s3",
        S3_BUCKET_NAME="my-enterprise-bucket",
    )
    monkeypatch.setattr("config.cfg", test_cfg_s3)
    b_s3 = get_storage_backend(force_refresh=True)
    assert isinstance(b_s3, S3StorageBackend)
    assert b_s3.bucket_name == "my-enterprise-bucket"


def test_api_upload_and_download_with_storage_backend(tmp_path: Path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = cfg.replace(
        BASE_DIR=str(app_dir),
        STORAGE_BACKEND="local",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="TestPassword!123",
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    session_store.clear()
    monkeypatch.setattr(api.libraries, "_store", None)

    client = TestClient(app)
    # Login
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "TestPassword!123"})
    assert login_res.status_code == 200

    # Create library
    create_res = client.post("/api/libraries", json={"name": "Cloud Storage Test", "visibility": "shared"})
    assert create_res.status_code == 201
    library_id = create_res.json()["id"]

    # Upload document
    doc_content = b"# Documento Enterprise Cloud\nQuesto file e' gestito tramite storage backend astratto."
    upload_res = client.post(
        f"/api/libraries/{library_id}/documents",
        files={"file": ("procedura.md", io.BytesIO(doc_content), "text/markdown")},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]
    storage_path = upload_res.json()["storage_path"]

    # Verify storage backend has file
    backend = get_storage_backend(force_refresh=True)
    assert backend.exists(storage_path)
    assert backend.read_bytes(storage_path) == doc_content

    # Download document
    dl_res = client.get(f"/api/libraries/{library_id}/documents/{doc_id}/download")
    assert dl_res.status_code == 200
    assert dl_res.content == doc_content

    # Delete document
    del_res = client.delete(f"/api/libraries/{library_id}/documents/{doc_id}")
    assert del_res.status_code == 204
    assert not backend.exists(storage_path)
