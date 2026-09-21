"""core/connectors/google_drive.py
Google Drive Enterprise Cloud Connector with incremental Delta Sync.
Interacts with Google Drive API v3.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from core.connectors.base import BaseConnector, DeltaSyncResult, RemoteDocument

_logger = logging.getLogger(__name__)


class GoogleDriveConnector(BaseConnector):
    """Connettore enterprise per Google Drive con supporto a token incrementale."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.access_token = config.get("access_token", "").strip()
        self.folder_id = config.get("folder_id", "root").strip()

    def _get_headers(self) -> dict[str, str]:
        if not self.access_token:
            raise ValueError("Token di accesso Google Drive mancante (access_token)")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def test_connection(self) -> tuple[bool, str]:
        try:
            headers = self._get_headers()
            with httpx.Client(timeout=10.0) as client:
                res = client.get("https://www.googleapis.com/drive/v3/about?fields=user", headers=headers)
                if res.status_code == 200:
                    user_data = res.json().get("user", {})
                    email = user_data.get("emailAddress", "utente sconosciuto")
                    return True, f"Connessione Google Drive riuscita (Account: {email})"
                return False, f"Errore Google Drive API ({res.status_code}): {res.text[:200]}"
        except Exception as e:
            return False, f"Errore connessione Google Drive: {e}"

    def fetch_documents(self) -> list[RemoteDocument]:
        headers = self._get_headers()
        docs: list[RemoteDocument] = []
        q = f"'{self.folder_id}' in parents and trashed = false" if self.folder_id != "root" else "trashed = false"
        url = (
            f"https://www.googleapis.com/drive/v3/files?q={q}"
            "&fields=nextPageToken,files(id,name,mimeType,modifiedTime,size,webViewLink)"
            "&pageSize=100"
        )

        with httpx.Client(timeout=30.0) as client:
            while url:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    _logger.error("Errore list Google Drive: %s", res.text[:200])
                    break

                body = res.json()
                for f in body.get("files", []):
                    # Salta cartelle e file nativi Google Docs non esportabili come raw media
                    mime = f.get("mimeType", "")
                    if mime == "application/vnd.google-apps.folder":
                        continue

                    file_id = f.get("id")
                    name = f.get("name", file_id)
                    media_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

                    try:
                        dl_res = client.get(media_url, headers=headers)
                        if dl_res.status_code == 200:
                            docs.append(
                                RemoteDocument(
                                    id=str(file_id),
                                    name=str(name),
                                    content=dl_res.content,
                                    media_type=mime or "application/octet-stream",
                                    source_url=str(f.get("webViewLink", "")),
                                    last_modified=str(f.get("modifiedTime", "")),
                                    metadata={"size": f.get("size", 0)},
                                )
                            )
                    except Exception as err:
                        _logger.warning("Impossibile scaricare file %s (%s): %s", name, file_id, err)

                next_page = body.get("nextPageToken")
                if next_page:
                    url = (
                        f"https://www.googleapis.com/drive/v3/files?q={q}"
                        f"&fields=nextPageToken,files(id,name,mimeType,modifiedTime,size,webViewLink)"
                        f"&pageSize=100&pageToken={next_page}"
                    )
                else:
                    url = ""

        return docs

    def fetch_delta(self, delta_token: str | None = None) -> DeltaSyncResult:
        """Sincronizzazione incrementale basata sulla Changes API di Google Drive."""
        headers = self._get_headers()
        updated_docs: list[RemoteDocument] = []
        deleted_ids: list[str] = []
        errors: list[str] = []

        with httpx.Client(timeout=30.0) as client:
            # Se non abbiamo un token di partenza, richiediamo startPageToken
            if not delta_token:
                start_res = client.get(
                    "https://www.googleapis.com/drive/v3/changes/startPageToken",
                    headers=headers,
                )
                if start_res.status_code == 200:
                    start_token = start_res.json().get("startPageToken")
                    # Effettua la scansione iniziale
                    initial_docs = self.fetch_documents()
                    return DeltaSyncResult(
                        connector_type="google_drive",
                        updated_documents=initial_docs,
                        deleted_document_ids=[],
                        next_delta_token=start_token,
                    )
                errors.append(f"Impossibile ottenere startPageToken: {start_res.text[:200]}")
                return DeltaSyncResult(
                    connector_type="google_drive",
                    updated_documents=[],
                    deleted_document_ids=[],
                    next_delta_token=None,
                    errors=errors,
                )

            # Abbiamo un token: eseguiamo polling dei soli cambiamenti
            page_token = delta_token
            new_start_token: str | None = None

            while page_token:
                changes_url = (
                    f"https://www.googleapis.com/drive/v3/changes?pageToken={page_token}"
                    "&includeRemoved=true&fields=nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,size,trashed,webViewLink))"
                )
                res = client.get(changes_url, headers=headers)
                if res.status_code != 200:
                    errors.append(f"Errore Google Drive Changes API ({res.status_code}): {res.text[:200]}")
                    break

                body = res.json()
                for ch in body.get("changes", []):
                    file_id = str(ch.get("fileId", ""))
                    is_removed = ch.get("removed", False)
                    f_info = ch.get("file") or {}
                    is_trashed = f_info.get("trashed", False)

                    if is_removed or is_trashed:
                        deleted_ids.append(file_id)
                        continue

                    mime = f_info.get("mimeType", "")
                    if mime == "application/vnd.google-apps.folder":
                        continue

                    media_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
                    try:
                        dl_res = client.get(media_url, headers=headers)
                        if dl_res.status_code == 200:
                            updated_docs.append(
                                RemoteDocument(
                                    id=file_id,
                                    name=str(f_info.get("name", file_id)),
                                    content=dl_res.content,
                                    media_type=mime or "application/octet-stream",
                                    source_url=str(f_info.get("webViewLink", "")),
                                    last_modified=str(f_info.get("modifiedTime", "")),
                                    metadata={"size": f_info.get("size", 0)},
                                )
                            )
                    except Exception as err:
                        errors.append(f"Errore download {file_id}: {err}")

                new_start_token = body.get("newStartPageToken")
                page_token = body.get("nextPageToken")

        return DeltaSyncResult(
            connector_type="google_drive",
            updated_documents=updated_docs,
            deleted_document_ids=deleted_ids,
            next_delta_token=new_start_token or delta_token,
            errors=errors,
        )
