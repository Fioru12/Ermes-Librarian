"""tests/test_storage_encryption.py
Test suite for Enterprise Storage Encryption at Rest (AES-256-GCM authenticated encryption).
Validates StorageCipher, LocalStorageBackend, S3StorageBackend, tamper detection and config guards.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from config.validation import check_configuration
from core.storage_backend import (
    LocalStorageBackend,
    S3StorageBackend,
    StorageCipher,
    StorageError,
)


def test_storage_cipher_key_derivations():
    # Hex 64 chars (32 bytes)
    hex_key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    cipher_hex = StorageCipher(hex_key)
    ct = cipher_hex.encrypt(b"test-hex")
    assert cipher_hex.decrypt(ct) == b"test-hex"

    # Base64 32 bytes
    import base64
    b64_key = base64.b64encode(b"0" * 32).decode("ascii")
    cipher_b64 = StorageCipher(b64_key)
    ct_b64 = cipher_b64.encrypt(b"test-b64")
    assert cipher_b64.decrypt(ct_b64) == b"test-b64"

    # Passphrase (any length, derived via sha256)
    cipher_pass = StorageCipher("enterprise-master-passphrase-2026")
    ct_pass = cipher_pass.encrypt(b"test-passphrase")
    assert cipher_pass.decrypt(ct_pass) == b"test-passphrase"

    # Raw 32 bytes
    cipher_bytes = StorageCipher(b"K" * 32)
    ct_raw = cipher_bytes.encrypt(b"test-raw")
    assert cipher_bytes.decrypt(ct_raw) == b"test-raw"

    # Empty key raises
    with pytest.raises(StorageError):
        StorageCipher("")


def test_storage_cipher_tamper_and_corruption():
    cipher = StorageCipher("super-secret-key")
    data = b"Confidential Corporate Board Minutes 2026"
    encrypted = cipher.encrypt(data)

    assert encrypted.startswith(StorageCipher.MAGIC)
    assert len(encrypted) > len(data)

    # Incomplete envelope (< 35 bytes)
    with pytest.raises(StorageError, match="corrotto o incompleto"):
        cipher.decrypt(StorageCipher.MAGIC + b"short")

    # Tampered ciphertext byte
    tampered = bytearray(encrypted)
    tampered[-1] ^= 0x55  # flip bits in auth tag / ciphertext
    with pytest.raises(StorageError, match="Errore decifratura documento"):
        cipher.decrypt(bytes(tampered))

    # Tampered nonce
    tampered_nonce = bytearray(encrypted)
    tampered_nonce[len(StorageCipher.MAGIC) + 2] ^= 0xAA
    with pytest.raises(StorageError, match="Errore decifratura documento"):
        cipher.decrypt(bytes(tampered_nonce))


def test_storage_cipher_backward_compatibility_and_required_mode():
    plain_content = b"Legacy unencrypted document from 2024"

    # Default: require_encryption = False allows unencrypted legacy files
    cipher_permissive = StorageCipher("secret-key", require_encryption=False)
    assert cipher_permissive.decrypt(plain_content) == plain_content

    # Strict mode: require_encryption = True forbids unencrypted files
    cipher_strict = StorageCipher("secret-key", require_encryption=True)
    with pytest.raises(StorageError, match="il documento non è cifrato a riposo"):
        cipher_strict.decrypt(plain_content)


def test_local_storage_backend_with_encryption(tmp_path: Path):
    key = "local-storage-encryption-key-test"
    cipher = StorageCipher(key)
    backend = LocalStorageBackend(tmp_path, cipher=cipher)

    rel_path = "financials/q3_report.pdf"
    content = b"%PDF-1.4 Financial Statements and Balance Sheet"

    # Save
    saved_path = backend.save(rel_path, content)
    assert saved_path == rel_path

    # Verify physical file on disk is ENCRYPTED
    disk_file = tmp_path / "financials" / "q3_report.pdf"
    assert disk_file.is_file()
    raw_on_disk = disk_file.read_bytes()
    assert raw_on_disk.startswith(StorageCipher.MAGIC)
    assert content not in raw_on_disk  # Plaintext is NOT present on disk

    # Read back through backend (transparent decryption)
    decrypted = backend.read_bytes(rel_path)
    assert decrypted == content

    # Stream through backend
    stream_chunks = list(backend.get_stream(rel_path, chunk_size=16))
    assert b"".join(stream_chunks) == content

    # Backend without key attempting to read encrypted file
    unkeyed_backend = LocalStorageBackend(tmp_path, cipher=None)
    with pytest.raises(StorageError, match="ERMES_STORAGE_ENCRYPTION_KEY non è configurata"):
        unkeyed_backend.read_bytes(rel_path)

    with pytest.raises(StorageError, match="ERMES_STORAGE_ENCRYPTION_KEY non è configurata"):
        list(unkeyed_backend.get_stream(rel_path))

    # Backend with WRONG key
    wrong_key_backend = LocalStorageBackend(tmp_path, cipher=StorageCipher("wrong-key-value"))
    with pytest.raises(StorageError, match="Errore decifratura documento"):
        wrong_key_backend.read_bytes(rel_path)

    # Health check reflects encrypted mode
    ok, message = backend.check_health()
    assert ok is True
    assert "cifrato AES-256-GCM" in message


def test_s3_storage_backend_with_encryption():
    mock_client = MagicMock()
    cipher = StorageCipher("s3-encryption-passphrase")
    backend = S3StorageBackend(
        bucket_name="secure-corp-bucket",
        s3_client=mock_client,
        cipher=cipher,
    )

    rel_path = "contracts/agreement.docx"
    content = b"Non-Disclosure Agreement terms and signatures"

    # Save encrypts before calling put_object
    backend.save(rel_path, content)
    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "secure-corp-bucket"
    assert call_kwargs["Key"] == rel_path
    uploaded_body = call_kwargs["Body"]
    assert uploaded_body.startswith(StorageCipher.MAGIC)
    assert content not in uploaded_body

    # Read decrypts S3 response body
    mock_client.get_object.return_value = {"Body": io.BytesIO(uploaded_body)}
    decrypted = backend.read_bytes(rel_path)
    assert decrypted == content

    # Stream decrypts S3 response
    mock_client.get_object.return_value = {"Body": io.BytesIO(uploaded_body)}
    streamed = b"".join(backend.get_stream(rel_path))
    assert streamed == content

    # Health check reflects encrypted mode
    ok, message = backend.check_health()
    assert ok is True
    assert "cifrato AES-256-GCM" in message


def test_storage_encryption_config_validation():
    from config import cfg

    # 1. Required mode without key is FATAL
    cfg_invalid = cfg.replace(
        STORAGE_ENCRYPTION_REQUIRED=True,
        STORAGE_ENCRYPTION_KEY="",
        ADMIN_PASSWORD="super-strong-admin-password",
    )
    problems = check_configuration(cfg_invalid)
    fatal_problems = [p for p in problems if p.severity == "fatal" and p.setting == "ERMES_STORAGE_ENCRYPTION_REQUIRED"]
    assert len(fatal_problems) == 1

    # 2. Key set to a known repository placeholder is FATAL
    cfg_placeholder = cfg.replace(
        STORAGE_ENCRYPTION_KEY="change_me",
        ADMIN_PASSWORD="super-strong-admin-password",
    )
    problems_ph = check_configuration(cfg_placeholder)
    fatal_ph = [p for p in problems_ph if p.severity == "fatal" and p.setting == "ERMES_STORAGE_ENCRYPTION_KEY"]
    assert len(fatal_ph) == 1

