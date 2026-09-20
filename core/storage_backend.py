"""core/storage_backend.py
Unified Document Storage Abstraction Layer for Ermes Knowledge.

Provides an enterprise-ready, pluggable storage interface supporting:
- Local filesystem (default, zero-config, portable)
- S3 / MinIO compatible Object Storage (multi-replica, cloud-native)

Guarantees:
- Strict path sanitisation preventing directory traversal attacks.
- Uniform CRUD API: save, read_bytes, get_stream, exists, delete, delete_many.
- Graceful degradation and zero performance penalty on local storage.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

_logger = logging.getLogger("ermes.storage")


class StorageError(Exception):
    """Base exception for document storage errors."""


class StoragePathTraversalError(StorageError):
    """Raised when an operation targets a path escaping the designated storage boundary."""


class StorageFileNotFoundError(StorageError, FileNotFoundError):
    """Raised when a requested document does not exist in the storage backend."""


def normalize_relative_path(relative_path: str) -> str:
    """Sanitises and normalises a relative storage path.

    Rejects absolute paths, drive letters, and parent traversal segments ('..').
    Returns a clean POSIX-style relative path string.
    """
    clean = relative_path.replace("\\", "/").strip().lstrip("/")
    if re.match(r"^[A-Za-z]:", clean):
        raise StoragePathTraversalError(f"Drive letters are not permitted in storage paths: {relative_path!r}")

    segments = [s for s in clean.split("/") if s not in ("", ".")]
    if any(s == ".." for s in segments):
        raise StoragePathTraversalError(f"Directory traversal ('..') detected in storage path: {relative_path!r}")
    if not segments:
        raise StoragePathTraversalError("Empty storage path")

    return "/".join(segments)


class StorageCipher:
    """Enterprise-grade AES-256-GCM authenticated encryption for document storage."""

    MAGIC: bytes = b"ERM256\x01"

    def __init__(self, key: str | bytes, require_encryption: bool = False) -> None:
        self.require_encryption = bool(require_encryption)
        self._aesgcm = self._derive_aesgcm(key)

    @classmethod
    def _derive_aesgcm(cls, key: str | bytes) -> object:
        import base64
        import hashlib

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as err:
            raise StorageError(
                "La crittografia dei documenti a riposo richiede la libreria 'cryptography'."
            ) from err

        if not key:
            raise StorageError("La chiave di crittografia storage non può essere vuota.")

        if isinstance(key, str):
            clean = key.strip()
            # Chiave raw a 256 bit in formato esadecimale (64 caratteri)
            if len(clean) == 64 and all(c in "0123456789abcdefABCDEF" for c in clean):
                key_bytes = bytes.fromhex(clean)
            # Chiave raw a 256 bit in base64 (43/44 caratteri)
            elif len(clean) in (43, 44):
                try:
                    decoded = base64.b64decode(clean)
                    if len(decoded) == 32:
                        key_bytes = decoded
                    else:
                        key_bytes = hashlib.sha256(clean.encode("utf-8")).digest()
                except Exception:
                    key_bytes = hashlib.sha256(clean.encode("utf-8")).digest()
            else:
                key_bytes = hashlib.sha256(clean.encode("utf-8")).digest()
        elif isinstance(key, (bytes, bytearray)):
            if len(key) == 32:
                key_bytes = bytes(key)
            else:
                key_bytes = hashlib.sha256(key).digest()
        else:
            raise StorageError(f"Tipo di chiave crittografica non supportato: {type(key)}")

        return AESGCM(key_bytes)

    def encrypt(self, data: bytes) -> bytes:
        import os

        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, data, None)
        return self.MAGIC + nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        if data.startswith(self.MAGIC):
            min_len = len(self.MAGIC) + 12 + 16
            if len(data) < min_len:
                raise StorageError("Documento cifrato corrotto o incompleto.")
            nonce = data[len(self.MAGIC) : len(self.MAGIC) + 12]
            ciphertext = data[len(self.MAGIC) + 12 :]
            try:
                return self._aesgcm.decrypt(nonce, ciphertext, None)
            except Exception as err:
                raise StorageError("Errore decifratura documento: chiave errata o dati manomessi.") from err

        if self.require_encryption:
            raise StorageError("Accesso negato: il documento non è cifrato a riposo e la cifratura è obbligatoria.")
        return data


class StorageBackend(ABC):
    """Abstract interface for storing and retrieving document originals."""

    @abstractmethod
    def save(self, relative_path: str, content: bytes | BinaryIO) -> str:
        """Saves file content to the target relative path. Returns the normalized path."""

    @abstractmethod
    def read_bytes(self, relative_path: str) -> bytes:
        """Reads and returns the complete binary content of the file."""

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        """Checks whether the file exists in storage."""

    @abstractmethod
    def delete(self, relative_path: str) -> bool:
        """Deletes the file. Returns True if deleted, False if not found."""

    def delete_many(self, relative_paths: list[str]) -> None:
        """Deletes multiple files. Default implementation calls delete() iteratively."""
        for p in relative_paths:
            try:
                self.delete(p)
            except Exception as e:
                _logger.warning("Failed to delete storage path %s: %s", p, e)

    @abstractmethod
    def get_stream(self, relative_path: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        """Yields chunks of binary content for streaming downloads."""

    @abstractmethod
    def check_health(self) -> tuple[bool, str]:
        """Checks storage availability and write/read readiness."""

    def get_local_path(self, relative_path: str) -> Path | None:
        """Returns a local Path if stored locally on disk, otherwise None."""
        return None


class LocalStorageBackend(StorageBackend):
    """Filesystem-backed storage backend (default for Ermes)."""

    def __init__(self, root_dir: str | Path, cipher: StorageCipher | None = None) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.cipher = cipher

    def check_health(self) -> tuple[bool, str]:
        import os

        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            if not self.root_dir.is_dir():
                return False, f"La cartella di storage non esiste: {self.root_dir}"
            if not os.access(self.root_dir, os.W_OK):
                return False, f"La cartella di storage non è scrivibile: {self.root_dir}"
            mode = "cifrato AES-256-GCM" if self.cipher else "chiaro"
            return True, f"Storage locale pronto ({mode}): {self.root_dir}"
        except Exception as e:
            return False, f"Errore storage locale: {e}"

    def _resolve(self, relative_path: str) -> Path:
        norm = normalize_relative_path(relative_path)
        resolved = (self.root_dir / norm).resolve()
        try:
            resolved.relative_to(self.root_dir)
        except ValueError as err:
            raise StoragePathTraversalError(f"Path escapes storage root: {relative_path!r}") from err
        return resolved

    def save(self, relative_path: str, content: bytes | BinaryIO) -> str:
        norm = normalize_relative_path(relative_path)
        target = self._resolve(norm)
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (bytes, bytearray)):
            raw = bytes(content)
        else:
            raw = content.read()
        if self.cipher is not None:
            raw = self.cipher.encrypt(raw)
        target.write_bytes(raw)
        return norm

    def read_bytes(self, relative_path: str) -> bytes:
        target = self._resolve(relative_path)
        if not target.is_file():
            raise StorageFileNotFoundError(f"File not found in local storage: {relative_path}")
        raw = target.read_bytes()
        if self.cipher is not None:
            return self.cipher.decrypt(raw)
        if raw.startswith(StorageCipher.MAGIC):
            raise StorageError(
                "Il documento è cifrato a riposo ma ERMES_STORAGE_ENCRYPTION_KEY non è configurata."
            )
        return raw

    def exists(self, relative_path: str) -> bool:
        try:
            target = self._resolve(relative_path)
            return target.is_file()
        except StoragePathTraversalError:
            return False

    def delete(self, relative_path: str) -> bool:
        try:
            target = self._resolve(relative_path)
        except StoragePathTraversalError:
            return False
        if not target.is_file():
            return False
        try:
            target.unlink(missing_ok=True)
            # Cleanup empty parent directories up to storage root
            parent = target.parent
            for _ in range(3):
                if parent == self.root_dir or self.root_dir not in parent.parents:
                    break
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
            return True
        except OSError as e:
            _logger.warning("Error deleting file %s: %s", target, e)
            return False

    def get_stream(self, relative_path: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        target = self._resolve(relative_path)
        if not target.is_file():
            raise StorageFileNotFoundError(f"File not found in local storage: {relative_path}")
        with open(target, "rb") as f:
            header = f.read(len(StorageCipher.MAGIC))
        if self.cipher is not None or header == StorageCipher.MAGIC:
            decrypted = self.read_bytes(relative_path)
            for i in range(0, len(decrypted), chunk_size):
                yield decrypted[i : i + chunk_size]
        else:
            with open(target, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk


    def get_local_path(self, relative_path: str) -> Path | None:
        try:
            target = self._resolve(relative_path)
            return target if target.is_file() else None
        except StoragePathTraversalError:
            return None


class S3StorageBackend(StorageBackend):
    """S3 and MinIO compatible Object Storage backend."""

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region_name: str = "us-east-1",
        s3_client: object | None = None,
        cipher: StorageCipher | None = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region_name = region_name
        self._client = s3_client
        self.cipher = cipher

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as err:
            raise StorageError(
                "Il supporto S3/MinIO richiede la libreria 'boto3'. "
                "Installala con: pip install boto3"
            ) from err

        session = boto3.session.Session()
        client = session.client(
            "s3",
            endpoint_url=self.endpoint_url or None,
            aws_access_key_id=self.access_key_id or None,
            aws_secret_access_key=self.secret_access_key or None,
            region_name=self.region_name or "us-east-1",
        )
        self._client = client
        return client

    def save(self, relative_path: str, content: bytes | BinaryIO) -> str:
        norm = normalize_relative_path(relative_path)
        client = self._get_client()
        body = content if isinstance(content, (bytes, bytearray)) else content.read()
        if self.cipher is not None:
            body = self.cipher.encrypt(body)
        try:
            client.put_object(
                Bucket=self.bucket_name,
                Key=norm,
                Body=body,
            )
            return norm
        except Exception as err:
            raise StorageError(f"Failed to put object {norm} to S3: {err}") from err

    def read_bytes(self, relative_path: str) -> bytes:
        norm = normalize_relative_path(relative_path)
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self.bucket_name, Key=norm)
            body = response["Body"]
            data = body.read()
            raw = bytes(data) if data is not None else b""
            if self.cipher is not None:
                return self.cipher.decrypt(raw)
            if raw.startswith(StorageCipher.MAGIC):
                raise StorageError(
                    "Il documento è cifrato a riposo su S3 ma ERMES_STORAGE_ENCRYPTION_KEY non è configurata."
                )
            return raw
        except StorageError:
            raise
        except Exception as err:
            msg = str(err).lower()
            if "nosuchkey" in msg or "404" in msg or "not found" in msg:
                raise StorageFileNotFoundError(f"Object {norm} not found in bucket {self.bucket_name}") from err
            raise StorageError(f"Failed to get object {norm} from S3: {err}") from err

    def exists(self, relative_path: str) -> bool:
        norm = normalize_relative_path(relative_path)
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket_name, Key=norm)
            return True
        except Exception:
            return False

    def delete(self, relative_path: str) -> bool:
        norm = normalize_relative_path(relative_path)
        client = self._get_client()
        try:
            if not self.exists(norm):
                return False
            client.delete_object(Bucket=self.bucket_name, Key=norm)
            return True
        except Exception as err:
            _logger.warning("Failed to delete S3 object %s: %s", norm, err)
            return False

    def delete_many(self, relative_paths: list[str]) -> None:
        if not relative_paths:
            return
        client = self._get_client()
        clean_keys = []
        for p in relative_paths:
            try:
                clean_keys.append(normalize_relative_path(p))
            except StoragePathTraversalError:
                continue
        if not clean_keys:
            return
        try:
            client.delete_objects(
                Bucket=self.bucket_name,
                Delete={"Objects": [{"Key": k} for k in clean_keys], "Quiet": True},
            )
        except Exception as err:
            _logger.warning("Batch S3 deletion failed: %s, falling back to sequential", err)
            super().delete_many(relative_paths)

    def get_stream(self, relative_path: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        norm = normalize_relative_path(relative_path)
        client = self._get_client()
        try:
            if self.cipher is not None:
                decrypted = self.read_bytes(norm)
                for i in range(0, len(decrypted), chunk_size):
                    yield decrypted[i : i + chunk_size]
            else:
                response = client.get_object(Bucket=self.bucket_name, Key=norm)
                body = response["Body"]
                first = body.read(len(StorageCipher.MAGIC))
                if first == StorageCipher.MAGIC:
                    raise StorageError(
                        "Il documento è cifrato a riposo su S3 ma ERMES_STORAGE_ENCRYPTION_KEY non è configurata."
                    )
                if first:
                    yield first
                while chunk := body.read(chunk_size):
                    yield chunk
        except StorageError:
            raise
        except Exception as err:
            msg = str(err).lower()
            if "nosuchkey" in msg or "404" in msg or "not found" in msg:
                raise StorageFileNotFoundError(f"Object {norm} not found in bucket {self.bucket_name}") from err
            raise StorageError(f"Failed to stream object {norm} from S3: {err}") from err

    def check_health(self) -> tuple[bool, str]:
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.bucket_name)
            mode = "cifrato AES-256-GCM" if self.cipher else "chiaro"
            return True, f"Bucket S3 raggiungibile ({mode}): {self.bucket_name}"
        except Exception as e:
            return False, f"Bucket S3 non raggiungibile ({self.bucket_name}): {e}"



_storage_backend_singleton: StorageBackend | None = None
_storage_backend_config_key: tuple | None = None


def get_storage_backend(force_refresh: bool = False) -> StorageBackend:
    """Factory returns the active StorageBackend singleton based on configuration."""
    global _storage_backend_singleton, _storage_backend_config_key
    from config import cfg

    backend_type = getattr(cfg, "STORAGE_BACKEND", "local").lower().strip()
    storage_root = str(getattr(cfg, "LIBRARY_STORAGE_DIR", ""))

    s3_endpoint = str(getattr(cfg, "S3_ENDPOINT_URL", ""))
    s3_bucket = str(getattr(cfg, "S3_BUCKET_NAME", "ermes-documents"))
    s3_access_key = str(getattr(cfg, "S3_ACCESS_KEY_ID", ""))
    s3_secret_key = str(getattr(cfg, "S3_SECRET_ACCESS_KEY", ""))
    s3_region = str(getattr(cfg, "S3_REGION_NAME", "us-east-1"))

    enc_key = str(getattr(cfg, "STORAGE_ENCRYPTION_KEY", "")).strip()
    enc_req = bool(getattr(cfg, "STORAGE_ENCRYPTION_REQUIRED", False))

    current_key = (
        backend_type,
        storage_root,
        s3_endpoint,
        s3_bucket,
        s3_access_key,
        s3_region,
        enc_key,
        enc_req,
    )

    if _storage_backend_singleton is None or _storage_backend_config_key != current_key or force_refresh:
        cipher = StorageCipher(enc_key, require_encryption=enc_req) if enc_key else None
        if backend_type == "s3":
            _storage_backend_singleton = S3StorageBackend(
                bucket_name=s3_bucket,
                endpoint_url=s3_endpoint or None,
                access_key_id=s3_access_key or None,
                secret_access_key=s3_secret_key or None,
                region_name=s3_region,
                cipher=cipher,
            )
        else:
            _storage_backend_singleton = LocalStorageBackend(storage_root, cipher=cipher)
        _storage_backend_config_key = current_key

    return _storage_backend_singleton
