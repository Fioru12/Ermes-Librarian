"""Unit and integration tests for document encryption at rest (AES-256-GCM)."""

from pathlib import Path

import pytest

from core.encryption import (
    MAGIC_HEADER,
    DecryptionError,
    decrypt_document,
    encrypt_document,
    is_encrypted_document,
)
from core.storage_provider import EncryptedStorageProvider, LocalStorageProvider


def test_encryption_roundtrip_success():
    secret_key = "super-secret-enterprise-master-key"
    plaintext = b"Sensitive document content with confidential HR payroll info."

    ciphertext = encrypt_document(plaintext, key=secret_key)
    assert ciphertext != plaintext
    assert ciphertext.startswith(MAGIC_HEADER)
    assert is_encrypted_document(ciphertext) is True

    decrypted = decrypt_document(ciphertext, key=secret_key)
    assert decrypted == plaintext


def test_tampering_detection_raises_decryption_error():
    secret_key = "encryption-key-123"
    plaintext = b"Unmodified contract clauses."

    ciphertext = bytearray(encrypt_document(plaintext, key=secret_key))
    # Modifica un byte nel payload cifrato per simulare manomissione
    ciphertext[-1] ^= 0x01

    with pytest.raises(DecryptionError, match="Tag di autenticazione non valido"):
        decrypt_document(bytes(ciphertext), key=secret_key)


def test_wrong_key_raises_decryption_error():
    plaintext = b"Private patient records."
    ciphertext = encrypt_document(plaintext, key="correct-key")

    with pytest.raises(DecryptionError):
        decrypt_document(ciphertext, key="wrong-key")


def test_legacy_plaintext_pass_through():
    plaintext = b"Legacy unencrypted markdown file content."
    assert is_encrypted_document(plaintext) is False

    # Deve restituire il testo in chiaro senza errori
    assert decrypt_document(plaintext, key="any-key") == plaintext


def test_encrypted_storage_provider_local_disk(tmp_path: Path):
    storage_root = tmp_path / "encrypted_storage"
    base_provider = LocalStorageProvider(root=storage_root)
    encrypted_provider = EncryptedStorageProvider(underlying=base_provider, encryption_key="storage-aes-key")

    test_content = b"Encrypted financial report 2026."
    rel_path = "lib-1/report.pdf"

    saved_path = encrypted_provider.save(rel_path, test_content)
    assert saved_path == rel_path
    assert encrypted_provider.exists(rel_path) is True

    # Verifica che su disco il file sia fisicamente cifrato
    disk_file = storage_root / "lib-1" / "report.pdf"
    assert disk_file.is_file()
    raw_disk_bytes = disk_file.read_bytes()
    assert raw_disk_bytes.startswith(MAGIC_HEADER)
    assert test_content not in raw_disk_bytes  # Nessun frammento in chiaro

    # Lettura tramite provider restituisce il contenuto originale
    recovered = encrypted_provider.get(rel_path)
    assert recovered == test_content

    # Eliminazione
    assert encrypted_provider.delete(rel_path) is True
    assert encrypted_provider.exists(rel_path) is False
