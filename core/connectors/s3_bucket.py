"""
core/connectors/s3_bucket.py
Amazon S3 / MinIO / Cloudflare R2 Bucket Connector for Ermes Knowledge.
Scans S3 buckets for supported documents and syncs them into libraries.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import PurePosixPath
from typing import Any

from core.connectors.base import BaseConnector, RemoteDocument

_logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".xlsx", ".pptx", ".csv", ".rtf"}

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".csv": "text/csv",
    ".rtf": "application/rtf",
}



class S3BucketConnector(BaseConnector):
    """Connettore per scansione ed estrazione da bucket compatibili S3 (AWS S3, MinIO, Cloudflare R2).

    Configurazione richiesta:
    - bucket_name: nome del bucket
    - endpoint_url: opzionale (es. 'http://localhost:9000' per MinIO)
    - access_key: AWS Access Key / MinIO user
    - secret_key: AWS Secret Key / MinIO password
    - prefix: prefisso/sottocartella remota (default: '')
    - region_name: regione (default: 'us-east-1')
    - max_files: numero massimo di file per scansione (default: 200)
    - extensions: lista estensioni ammesse
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.bucket_name = config.get("bucket_name", "").strip()
        self.endpoint_url = config.get("endpoint_url") or None
        self.access_key = config.get("access_key") or None
        self.secret_key = config.get("secret_key") or None
        self.prefix = config.get("prefix", "").strip().lstrip("/")
        self.region_name = config.get("region_name", "us-east-1")
        self.max_files = int(config.get("max_files", 200))
        self.allowed_extensions = set(config.get("extensions", list(SUPPORTED_EXTENSIONS)))
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
            except ImportError as exc:
                raise RuntimeError("boto3 non è installato nel runtime.") from exc
        return self._client

    def test_connection(self) -> tuple[bool, str]:
        if not self.bucket_name:
            return False, "Nome bucket S3 non specificato"
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.bucket_name)
            return True, f"Bucket S3 raggiungibile con successo ({self.bucket_name})"
        except Exception as exc:
            msg = str(exc)
            _logger.warning("Test connessione S3 fallito: %s", msg)
            return False, f"Impossibile raggiungere il bucket '{self.bucket_name}': {msg}"

    def fetch_documents(self) -> list[RemoteDocument]:
        ok, msg = self.test_connection()
        if not ok:
            _logger.warning("S3BucketConnector test_connection fallito: %s", msg)
            return []

        client = self._get_client()
        documents: list[RemoteDocument] = []
        paginator = client.get_paginator("list_objects_v2")
        paginate_kwargs: dict[str, Any] = {"Bucket": self.bucket_name}
        if self.prefix:
            paginate_kwargs["Prefix"] = self.prefix

        try:
            for page in paginator.paginate(**paginate_kwargs):
                contents = page.get("Contents", [])
                for item in contents:
                    if len(documents) >= self.max_files:
                        _logger.info("Raggiunto limite massimo di %d file da S3", self.max_files)
                        return documents

                    key = item.get("Key", "")
                    # Ignora chiavi directory / vuote
                    if not key or key.endswith("/"):
                        continue

                    path = PurePosixPath(key)
                    ext = path.suffix.lower()
                    if ext not in self.allowed_extensions:
                        continue

                    try:
                        resp = client.get_object(Bucket=self.bucket_name, Key=key)
                        content_bytes = bytes(resp["Body"].read())
                        media_type = MEDIA_TYPES.get(ext) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                        last_mod = item.get("LastModified")
                        last_mod_str = last_mod.isoformat() if hasattr(last_mod, "isoformat") else str(last_mod or "")

                        doc = RemoteDocument(
                            id=f"s3://{self.bucket_name}/{key}",
                            name=path.name,
                            content=content_bytes,
                            media_type=media_type,
                            source_url=f"s3://{self.bucket_name}/{key}",
                            last_modified=last_mod_str,
                            metadata={
                                "bucket": self.bucket_name,
                                "key": key,
                                "size": item.get("Size", len(content_bytes)),
                                "etag": item.get("ETag", "").strip('"'),
                            },
                        )

                        documents.append(doc)
                    except Exception as err:
                        _logger.warning("Errore scaricamento oggetto s3://%s/%s: %s", self.bucket_name, key, err)
                        continue

        except Exception as exc:
            _logger.error("Errore durante la scansione del bucket S3 %s: %s", self.bucket_name, exc)

        return documents
