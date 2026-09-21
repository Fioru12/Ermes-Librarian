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
