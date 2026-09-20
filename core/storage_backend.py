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

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def check_health(self) -> tuple[bool, str]:
        import os

        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            if not self.root_dir.is_dir():
                return False, f"La cartella di storage non esiste: {self.root_dir}"
            if not os.access(self.root_dir, os.W_OK):
                return False, f"La cartella di storage non è scrivibile: {self.root_dir}"
            return True, f"Storage locale pronto: {self.root_dir}"
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
            target.write_bytes(content)
        else:
            with open(target, "wb") as f:
                while chunk := content.read(64 * 1024):
                    f.write(chunk)
        return norm

    def read_bytes(self, relative_path: str) -> bytes:
        target = self._resolve(relative_path)
        if not target.is_file():
            raise StorageFileNotFoundError(f"File not found in local storage: {relative_path}")
        return target.read_bytes()

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
    ) -> None:
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region_name = region_name
        self._client = s3_client

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
            return bytes(data) if data is not None else b""
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
            response = client.get_object(Bucket=self.bucket_name, Key=norm)
            body = response["Body"]
            while chunk := body.read(chunk_size):
                yield chunk
        except Exception as err:
            msg = str(err).lower()
            if "nosuchkey" in msg or "404" in msg or "not found" in msg:
                raise StorageFileNotFoundError(f"Object {norm} not found in bucket {self.bucket_name}") from err
            raise StorageError(f"Failed to stream object {norm} from S3: {err}") from err

    def check_health(self) -> tuple[bool, str]:
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.bucket_name)
            return True, f"Bucket S3 raggiungibile: {self.bucket_name}"
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

    current_key = (backend_type, storage_root, s3_endpoint, s3_bucket, s3_access_key, s3_region)

    if _storage_backend_singleton is None or _storage_backend_config_key != current_key or force_refresh:
        if backend_type == "s3":
            _storage_backend_singleton = S3StorageBackend(
                bucket_name=s3_bucket,
                endpoint_url=s3_endpoint or None,
                access_key_id=s3_access_key or None,
                secret_access_key=s3_secret_key or None,
                region_name=s3_region,
            )
        else:
            _storage_backend_singleton = LocalStorageBackend(storage_root)
        _storage_backend_config_key = current_key

    return _storage_backend_singleton
