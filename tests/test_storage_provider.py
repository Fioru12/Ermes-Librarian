"""Test per il modulo core/storage_provider.py (LocalStorageProvider e S3StorageProvider)."""

from unittest.mock import MagicMock

import pytest

from core.storage_provider import LocalStorageProvider, S3StorageProvider


def test_local_storage_provider_crud(tmp_path):
    storage = LocalStorageProvider(tmp_path)

    # Save
    key = storage.save("lib1/test.txt", b"Contenuto di prova")
    assert key == "lib1/test.txt"
    assert storage.exists(key)

    # Get
    data = storage.get(key)
    assert data == b"Contenuto di prova"

    # Anti-traversal guard
    with pytest.raises(ValueError):
        storage.save("../escape.txt", b"hacked")

    # Delete
    assert storage.delete(key) is True
    assert not storage.exists(key)

    with pytest.raises(FileNotFoundError):
        storage.get(key)


def test_s3_storage_provider_mock():
    provider = S3StorageProvider(bucket_name="test-bucket")
    mock_client = MagicMock()
    provider._client = mock_client

    # Save
    provider.save("lib1/doc.pdf", b"%PDF-1.4...")
    mock_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="lib1/doc.pdf",
        Body=b"%PDF-1.4...",
    )

    # Get
    mock_client.get_object.return_value = {"Body": MagicMock(read=lambda: b"%PDF-1.4...")}
    content = provider.get("lib1/doc.pdf")
    assert content == b"%PDF-1.4..."

    # Delete
    assert provider.delete("lib1/doc.pdf") is True
    mock_client.delete_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="lib1/doc.pdf",
    )


def test_storage_provider_check_health(tmp_path):
    # Local Storage Health
    local_storage = LocalStorageProvider(tmp_path / "test_store")
    ok, msg = local_storage.check_health()
    assert ok is True
    assert "pronto" in msg.lower()

    # S3 Storage Health (success)
    s3_storage = S3StorageProvider(bucket_name="test-bucket")
    mock_client = MagicMock()
    mock_client.head_bucket.return_value = {}
    s3_storage._client = mock_client
    ok_s3, msg_s3 = s3_storage.check_health()
    assert ok_s3 is True
    assert "raggiungibile" in msg_s3.lower()

    # S3 Storage Health (failure)
    mock_client.head_bucket.side_effect = Exception("Access Denied")
    ok_s3_fail, msg_s3_fail = s3_storage.check_health()
    assert ok_s3_fail is False
    assert "non raggiungibile" in msg_s3_fail.lower()
