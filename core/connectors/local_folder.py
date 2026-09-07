"""
core/connectors/local_folder.py
Local Shared Folder / NAS Network Drive Connector for Ermes Knowledge.
Scans local directories or mounted SMB/NFS network drives for supported documents.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

from core.connectors.base import BaseConnector, RemoteDocument

_logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".xlsx", ".pptx", ".csv", ".rtf"}


class LocalFolderConnector(BaseConnector):
    """
    Connettore per scansione ed estrazione da cartelle locali o mount NAS (SMB/NFS).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.folder_path = Path(config.get("folder_path", "")).expanduser().resolve()
        self.max_files = int(config.get("max_files", 200))
        self.recursive = bool(config.get("recursive", True))
        self.allowed_extensions = set(config.get("extensions", list(SUPPORTED_EXTENSIONS)))

    def test_connection(self) -> tuple[bool, str]:
        if not str(self.folder_path):
            return False, "Percorso cartella non specificato"

        if not self.folder_path.exists():
            return False, f"Il percorso non esiste: {self.folder_path}"

        if not self.folder_path.is_dir():
            return False, f"Il percorso non è una directory: {self.folder_path}"

        if not os.access(self.folder_path, os.R_OK):
            return False, f"Permesso di lettura negato per: {self.folder_path}"

        return True, f"Cartella raggiungibile e leggibile ({self.folder_path})"

    def fetch_documents(self) -> list[RemoteDocument]:
        ok, msg = self.test_connection()
        if not ok:
            _logger.warning("LocalFolderConnector test_connection fallito: %s", msg)
            return []

        documents: list[RemoteDocument] = []
        walker = self.folder_path.rglob("*") if self.recursive else self.folder_path.glob("*")

        for file_path in walker:
            if len(documents) >= self.max_files:
                _logger.info("Raggiunto il limite massimo di %d file", self.max_files)
                break

            if not file_path.is_file():
                continue

            ext = file_path.suffix.lower()
            if ext not in self.allowed_extensions:
                continue

            try:
                stat = file_path.stat()
                content = file_path.read_bytes()
                media_type, _ = mimetypes.guess_type(file_path.name)
                if not media_type:
                    media_type = "application/octet-stream"

                rel_path = str(file_path.relative_to(self.folder_path))
                doc_id = f"local_folder:{rel_path}"

                documents.append(
                    RemoteDocument(
                        id=doc_id,
                        name=file_path.name,
                        content=content,
                        media_type=media_type,
                        source_url=f"file://{file_path}",
                        last_modified=str(int(stat.st_mtime)),
                        metadata={
                            "relative_path": rel_path,
                            "absolute_path": str(file_path),
                            "file_size": stat.st_size,
                            "extension": ext,
                        },
                    )
                )
            except Exception as e:
                _logger.error("Errore durante la lettura del file %s: %s", file_path, e)
                continue

        return documents
