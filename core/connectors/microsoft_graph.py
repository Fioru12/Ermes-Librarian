"""
core/connectors/microsoft_graph.py
Microsoft 365 SharePoint and OneDrive Enterprise Connector.
Interacts with Microsoft Graph API using OAuth2 Client Credentials flow.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from core.connectors.base import BaseConnector, RemoteDocument

_logger = logging.getLogger(__name__)


class MicrosoftGraphConnector(BaseConnector):
    """
    Connettore per Microsoft SharePoint & OneDrive tramite Microsoft Graph API.
    Configurazione richiesta:
    - tenant_id: Azure Tenant ID
    - client_id: Azure Application (Client) ID
    - client_secret: Azure Application Secret
    - drive_id: SharePoint/OneDrive Drive ID o Site ID
    - folder_path: percorso cartella remota (es. '/Documenti Condivisi')
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.tenant_id = config.get("tenant_id", "")
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.drive_id = config.get("drive_id", "")
        self.folder_path = config.get("folder_path", "/")
        self.recursive = bool(config.get("recursive", True))

    def _get_access_token(self) -> str:
        if not self.tenant_id or not self.client_id or not self.client_secret:
            raise ValueError("Credenziali Microsoft Graph incomplete (tenant_id, client_id, client_secret)")

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        with httpx.Client(timeout=15.0) as client:
            response = client.post(token_url, data=data)
            response.raise_for_status()
            token = response.json().get("access_token")
            if not token:
                raise ValueError("Risposta token Microsoft Graph non valida")
            return str(token)

    def test_connection(self) -> tuple[bool, str]:
        try:
            token = self._get_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            with httpx.Client(timeout=10.0) as client:
                res = client.get("https://graph.microsoft.com/v1.0/organization", headers=headers)
                if res.status_code == 200:
                    return True, "Connessione a Microsoft Graph stabilita con successo"
                return False, f"Errore Graph API: status {res.status_code}"
        except Exception as e:
            return False, f"Errore connessione Microsoft Graph: {e}"

    def _crawl_endpoint(
        self, client: httpx.Client, initial_url: str, headers: dict[str, str], documents: list[RemoteDocument]
    ) -> None:
        """Naviga un endpoint di SharePoint/OneDrive con paginazione e ricorsione su cartelle."""
        current_url: str | None = initial_url

        while current_url:
            res = client.get(current_url, headers=headers)
            if res.status_code != 200:
                _logger.error("Errore fetch Microsoft Graph (%s): %s", current_url, res.text)
                break

            data = res.json()
            items = data.get("value", [])
            for item in items:
                if "file" in item:
                    download_url = item.get("@microsoft.graph.downloadUrl")
                    content_bytes: bytes | None = None
                    if download_url:
                        file_res = client.get(download_url)
                        if file_res.status_code == 200:
                            content_bytes = file_res.content
                    elif item.get("id"):
                        # Fallback a direct stream endpoint
                        item_id = item["id"]
                        direct_url = (
                            f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/items/{item_id}/content"
                            if self.drive_id
                            else f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/content"
                        )
                        file_res = client.get(direct_url, headers=headers)
                        if file_res.status_code == 200:
                            content_bytes = file_res.content

                    if content_bytes is not None:
                        documents.append(
                            RemoteDocument(
                                id=str(item.get("id", "")),
                                name=str(item.get("name", "")),
                                content=content_bytes,
                                media_type=str(item.get("file", {}).get("mimeType", "application/octet-stream")),
                                source_url=str(item.get("webUrl", "")),
                                last_modified=str(item.get("lastModifiedDateTime", "")),
                                metadata={"size": item.get("size", 0), "etag": item.get("eTag", "")},
                            )
                        )
                elif "folder" in item and self.recursive:
                    subfolder_id = item.get("id")
                    if subfolder_id:
                        sub_url = (
                            f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/items/{subfolder_id}/children"
                            if self.drive_id
                            else f"https://graph.microsoft.com/v1.0/me/drive/items/{subfolder_id}/children"
                        )
                        self._crawl_endpoint(client, sub_url, headers, documents)

            current_url = data.get("@odata.nextLink")

    def fetch_documents(self) -> list[RemoteDocument]:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        documents: list[RemoteDocument] = []

        cleaned_path = self.folder_path.strip().strip("/")
        if cleaned_path:
            endpoint = (
                f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root:/{cleaned_path}:/children"
                if self.drive_id
                else f"https://graph.microsoft.com/v1.0/me/drive/root:/{cleaned_path}:/children"
            )
        else:
            endpoint = (
                f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root/children"
                if self.drive_id
                else "https://graph.microsoft.com/v1.0/me/drive/root/children"
            )

        with httpx.Client(timeout=30.0) as client:
            self._crawl_endpoint(client, endpoint, headers, documents)

        return documents

