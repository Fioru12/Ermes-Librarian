"""
core/connectors/microsoft_graph.py
Microsoft 365 SharePoint and OneDrive Enterprise Connector.
Interacts with Microsoft Graph API using OAuth2 Client Credentials flow.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from core.connectors.base import BaseConnector, DeltaSyncResult, RemoteDocument

_logger = logging.getLogger(__name__)


def graph_permissions_to_principals(permissions: list[dict]) -> tuple[str, ...] | None:
    """Traduce i permessi Graph di un file in un elenco di identita'.

    Un link aperto a chiunque o a tutta l'organizzazione vuol dire che chi e'
    nella biblioteca lo vedrebbe comunque: None, nessun vincolo aggiuntivo.
    """
    principals: set[str] = set()
    for permission in permissions:
        if (permission.get("link") or {}).get("scope") in {"anonymous", "organization"}:
            return None
        granted = [permission.get("grantedToV2"), permission.get("grantedTo")]
        granted += list(permission.get("grantedToIdentitiesV2") or []) + list(
            permission.get("grantedToIdentities") or []
        )
        for identity in granted:
            for kind in ("user", "siteUser", "group", "siteGroup"):
                entity = (identity or {}).get(kind) or {}
                name = entity.get("email") or entity.get("userPrincipalName") or entity.get("loginName")
                if name:
                    principals.add(str(name))
    return tuple(sorted(principals))


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
        # Spento solo su richiesta esplicita: senza, un file riservato su
        # SharePoint diventa visibile a tutta la biblioteca.
        self.inherit_permissions = bool(config.get("inherit_permissions", True))

    def _drive_base(self) -> str:
        return (
            f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}"
            if self.drive_id
            else "https://graph.microsoft.com/v1.0/me/drive"
        )

    def _item_principals(self, client: httpx.Client, headers: dict[str, str], item_id: str) -> tuple[str, ...] | None:
        """Chi vede il file su SharePoint/OneDrive. Illeggibile = nessuno (chiude)."""
        if not self.inherit_permissions:
            return None
        try:
            res = client.get(f"{self._drive_base()}/items/{item_id}/permissions", headers=headers)
        except Exception as error:
            _logger.warning("Permessi del file %s non leggibili: %s", item_id, error)
            return ()
        if res.status_code != 200:
            _logger.warning("Permessi del file %s non leggibili (HTTP %s)", item_id, res.status_code)
            return ()
        return graph_permissions_to_principals(res.json().get("value", []))

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

    def fetch_documents(self) -> list[RemoteDocument]:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        documents: list[RemoteDocument] = []

        endpoint = (
            f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root/children"
            if self.drive_id
            else "https://graph.microsoft.com/v1.0/me/drive/root/children"
        )

        with httpx.Client(timeout=30.0) as client:
            res = client.get(endpoint, headers=headers)
            if res.status_code != 200:
                _logger.error("Errore fetch Microsoft Graph: %s", res.text)
                return []

            items = res.json().get("value", [])
            for item in items:
                if "file" in item:
                    download_url = item.get("@microsoft.graph.downloadUrl")
                    if download_url:
                        file_res = client.get(download_url)
                        if file_res.status_code == 200:
                            documents.append(
                                RemoteDocument(
                                    id=str(item.get("id", "")),
                                    name=str(item.get("name", "")),
                                    content=file_res.content,
                                    media_type=str(item.get("file", {}).get("mimeType", "application/octet-stream")),
                                    source_url=str(item.get("webUrl", "")),
                                    last_modified=str(item.get("lastModifiedDateTime", "")),
                                    metadata={"size": item.get("size", 0), "etag": item.get("eTag", "")},
                                    allowed_principals=self._item_principals(client, headers, str(item.get("id", ""))),
                                )
                            )
        return documents

    def fetch_delta(self, delta_token: str | None = None) -> DeltaSyncResult:
        """Sincronizzazione incrementale basata sulle API delta di Microsoft Graph.

        Estrae solo file creati/modificati o eliminati dall'ultima sincronizzazione.
        """
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        updated_docs: list[RemoteDocument] = []
        deleted_ids: list[str] = []
        errors: list[str] = []

        if delta_token and delta_token.startswith("http"):
            url = delta_token
        elif delta_token:
            base = (
                f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root/delta"
                if self.drive_id
                else "https://graph.microsoft.com/v1.0/me/drive/root/delta"
            )
            url = f"{base}?token={delta_token}"
        else:
            url = (
                f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root/delta"
                if self.drive_id
                else "https://graph.microsoft.com/v1.0/me/drive/root/delta"
            )

        next_delta_link: str | None = None

        with httpx.Client(timeout=30.0) as client:
            while url:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    errors.append(f"Errore Graph Delta API ({res.status_code}): {res.text[:200]}")
                    break

                body = res.json()
                items = body.get("value", [])

                for item in items:
                    item_id = str(item.get("id", ""))
                    if "@removed" in item or item.get("deleted"):
                        deleted_ids.append(item_id)
                    elif "file" in item:
                        download_url = item.get("@microsoft.graph.downloadUrl")
                        if download_url:
                            try:
                                file_res = client.get(download_url)
                                if file_res.status_code == 200:
                                    updated_docs.append(
                                        RemoteDocument(
                                            id=item_id,
                                            name=str(item.get("name", "")),
                                            content=file_res.content,
                                            media_type=str(
                                                item.get("file", {}).get("mimeType", "application/octet-stream")
                                            ),
                                            source_url=str(item.get("webUrl", "")),
                                            last_modified=str(item.get("lastModifiedDateTime", "")),
                                            metadata={"size": item.get("size", 0), "etag": item.get("eTag", "")},
                                            allowed_principals=self._item_principals(client, headers, item_id),
                                        )
                                    )
                            except Exception as dl_err:
                                errors.append(f"Errore download {item.get('name')}: {dl_err}")

                # Gestione paginazione delta (@odata.nextLink vs @odata.deltaLink)
                if "@odata.nextLink" in body:
                    url = body["@odata.nextLink"]
                else:
                    next_delta_link = body.get("@odata.deltaLink")
                    url = ""

        return DeltaSyncResult(
            connector_type="microsoft_graph",
            updated_documents=updated_docs,
            deleted_document_ids=deleted_ids,
            next_delta_token=next_delta_link or delta_token,
            errors=errors,
        )
