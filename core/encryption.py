"""Crittografia a riposo per i documenti (AES-256-GCM).

Fornisce cifratura autenticata a livello militare (AEAD) con integrità garantita
da un tag di autenticazione a 128 bit. I documenti cifrati iniziano con l'header
magico `b"ERM1"`, seguito da un nonce casuale di 96 bit (12 byte) e dal payload cifrato.
"""

from __future__ import annotations

import logging
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config import cfg

_logger = logging.getLogger("ermes.encryption")

MAGIC_HEADER = b"ERM1"
NONCE_LENGTH = 12  # 96-bit nonce standard per AES-GCM
KEY_LENGTH = 32  # 256-bit key per AES-256


class DecryptionError(Exception):
    """Sollevata quando la decifratura fallisce (chiave errata o file manomesso)."""


def derive_key(secret: str | bytes, salt: bytes | None = None) -> bytes:
    """Deriva una chiave simmetrica a 256 bit tramite HKDF-SHA256."""
    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    if len(secret_bytes) == KEY_LENGTH:
        return secret_bytes

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=salt or b"ermes-document-storage-salt-v1",
        info=b"ermes-aes-256-gcm-key",
    )
    return hkdf.derive(secret_bytes)


def _get_active_key(key: str | bytes | None = None) -> bytes:
    if key is not None:
        return derive_key(key)
    raw_key: str | bytes = (
        getattr(cfg, "STORAGE_ENCRYPTION_KEY", None)
        or getattr(cfg, "SECRET_KEY", None)
        or "ermes-default-storage-key"
    )
    return derive_key(raw_key)



def is_encrypted_document(data: bytes) -> bool:
    """Verifica se i byte del documento corrispondono al formato cifrato Ermes."""
    return data.startswith(MAGIC_HEADER) and len(data) >= (len(MAGIC_HEADER) + NONCE_LENGTH + 16)


def encrypt_document(data: bytes, key: str | bytes | None = None) -> bytes:
    """Cifra i dati in chiaro con AES-256-GCM.

    Format: [b"ERM1" (4B)] + [Nonce (12B)] + [Ciphertext + Tag (16B)].
    """
    key_bytes = _get_active_key(key)
    nonce = os.urandom(NONCE_LENGTH)
    aesgcm = AESGCM(key_bytes)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return MAGIC_HEADER + nonce + ciphertext


def decrypt_document(data: bytes, key: str | bytes | None = None) -> bytes:
    """Decifra il documento con AES-256-GCM.

    Se il documento non è cifrato (non inizia con `b"ERM1"`), lo restituisce intatto
    per garantire la totale retrocompatibilità con i file già presenti a riposo.
    """
    if not is_encrypted_document(data):
        return data

    key_bytes = _get_active_key(key)
    nonce = data[len(MAGIC_HEADER) : len(MAGIC_HEADER) + NONCE_LENGTH]
    ciphertext = data[len(MAGIC_HEADER) + NONCE_LENGTH :]
    aesgcm = AESGCM(key_bytes)

    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise DecryptionError("Tag di autenticazione non valido: chiave errata o file manomesso") from exc
    except Exception as exc:
        raise DecryptionError(f"Errore durante la decifratura: {exc}") from exc
