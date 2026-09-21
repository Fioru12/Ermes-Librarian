"""Astrazione dello storage degli oggetti (file originali dei documenti).

Supporta sia il filesystem locale (default) sia lo storage compatibile S3 (MinIO / AWS S3 / Cloudflare R2).
Disaccoppia la memorizzazione dei file originali dal singolo nodo, permettendo la scalabilità orizzontale.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from config import cfg

_logger = logging.getLogger(__name__)


class StorageProvider(ABC):
    """Interfaccia astratta per il salvataggio e recupero dei file originali."""

    @abstractmethod
    def save(self, storage_path: str, content: bytes) -> str:
        """Salva il contenuto e restituisce il percorso o chiave normalizzata."""
        pass

    @abstractmethod
    def get(self, storage_path: str) -> bytes:
        """Legge e restituisce il contenuto binario del file."""
        pass

    @abstractmethod
    def delete(self, storage_path: str) -> bool:
        """Elimina il file dallo storage. Restituisce True se eliminato, False se inesistente."""
        pass

    @abstractmethod
    def exists(self, storage_path: str) -> bool:
        """Verifica se il file esiste nello storage."""
        pass

    def get_url(self, storage_path: str, expires_seconds: int = 3600) -> str | None:
        """Restituisce un URL pre-firmato o diretto per il download, o None se non applicabile."""
        return None


class LocalStorageProvider(StorageProvider):
    """Implementazione su filesystem locale con protezioni anti-traversal e scritture atomiche."""

    def __init__(self, root: str | Path | None = None) -> None:
        raw_root = str(root or getattr(cfg, "LIBRARY_STORAGE_DIR", "data/libraries"))
        self._root = Path(raw_root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, storage_path: str) -> Path:
        clean = storage_path.replace("\\", "/").lstrip("/")
        resolved = (self._root / clean).resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError:
            raise ValueError(f"Percorso illegale fuori dalla storage root: {storage_path}")
        return resolved

    def save(self, storage_path: str, content: bytes) -> str:
        dest = self._resolve(storage_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Scrittura atomica per evitare file corrotti o parziali
        with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        shutil.move(str(tmp_path), str(dest))
        return storage_path.replace("\\", "/").strip("/")

    def get(self, storage_path: str) -> bytes:
        path = self._resolve(storage_path)
        if not path.is_file():
            raise FileNotFoundError(f"File non trovato: {storage_path}")
        return path.read_bytes()

    def delete(self, storage_path: str) -> bool:
        try:
            path = self._resolve(storage_path)
            if path.is_file():
                path.unlink()
                return True
            return False
        except (ValueError, FileNotFoundError):
            return False

    def exists(self, storage_path: str) -> bool:
        try:
            return self._resolve(storage_path).is_file()
        except (ValueError, FileNotFoundError):
            return False


class S3StorageProvider(StorageProvider):
    """Implementazione per storage compatibile S3 (MinIO, AWS S3, Cloudflare R2, Ceph)."""

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region_name: str | None = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region_name = region_name or "us-east-1"
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import boto3  # type: ignore
                from botocore.config import Config  # type: ignore

                session = boto3.session.Session()
                self._client = session.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region_name,
                    config=Config(signature_version="s3v4"),
                )
            except ImportError as e:
                raise RuntimeError(
                    "boto3 non è installato: installalo per usare lo storage backend S3."
                ) from e
        return self._client

    def save(self, storage_path: str, content: bytes) -> str:
        key = storage_path.replace("\\", "/").strip("/")
        client = self._get_client()
        client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=content,
        )
        return key

    def get(self, storage_path: str) -> bytes:
        key = storage_path.replace("\\", "/").strip("/")
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self.bucket_name, Key=key)
            return bytes(response["Body"].read())
        except Exception as e:
            raise FileNotFoundError(f"Oggetto {key} non trovato in S3 bucket {self.bucket_name}: {e}") from e

    def delete(self, storage_path: str) -> bool:
        key = storage_path.replace("\\", "/").strip("/")
        client = self._get_client()
        try:
            client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception:
            return False

    def exists(self, storage_path: str) -> bool:
        key = storage_path.replace("\\", "/").strip("/")
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception:
            return False

    def get_url(self, storage_path: str, expires_seconds: int = 3600) -> str | None:
        key = storage_path.replace("\\", "/").strip("/")
        client = self._get_client()
        try:
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_seconds,
            )
            return str(url)
        except Exception as e:
            _logger.warning("Generazione presigned URL fallita per %s: %s", key, e)
            return None


def get_storage_provider() -> StorageProvider:
    """Restituisce il provider configurato per l'ambiente."""
    backend_type = getattr(cfg, "STORAGE_BACKEND", "local").lower()
    if backend_type == "s3":
        bucket = getattr(cfg, "S3_BUCKET_NAME", "ermes-documents")
        endpoint = getattr(cfg, "S3_ENDPOINT_URL", None)
        access_key = getattr(cfg, "S3_ACCESS_KEY_ID", None)
        secret_key = getattr(cfg, "S3_SECRET_ACCESS_KEY", None)
        region = getattr(cfg, "S3_REGION", "us-east-1")
        return S3StorageProvider(
            bucket_name=bucket,
            endpoint_url=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region_name=region,
        )
    return LocalStorageProvider(getattr(cfg, "LIBRARY_STORAGE_DIR", None))
