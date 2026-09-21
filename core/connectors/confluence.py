"""core/connectors/confluence.py
Atlassian Confluence Enterprise Cloud Connector with incremental Delta Sync.
Supports Confluence Cloud REST API (v2 / v1).
"""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from core.connectors.base import BaseConnector, DeltaSyncResult, RemoteDocument

_logger = logging.getLogger(__name__)


class ConfluenceConnector(BaseConnector):
    """Connettore per Atlassian Confluence Cloud con sincronizzazione incrementale basata su CQL."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "").rstrip("/")
        self.username = config.get("username", "").strip()
        self.api_token = config.get("api_token", "").strip()
        self.space_key = config.get("space_key", "").strip()

    def _get_headers(self) -> dict[str, str]:
        if not self.base_url or not self.username or not self.api_token:
            raise ValueError("Configurazione Confluence incompleta (base_url, username, api_token)")
        raw_auth = f"{self.username}:{self.api_token}".encode()
        encoded = base64.b64encode(raw_auth).decode("ascii")
        return {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
        }

    def test_connection(self) -> tuple[bool, str]:
        try:
            headers = self._get_headers()
            url = f"{self.base_url}/wiki/rest/api/space/{self.space_key}" if self.space_key else f"{self.base_url}/wiki/rest/api/space"
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    return True, "Connessione a Confluence riuscita"
                return False, f"Errore Confluence API ({res.status_code}): {res.text[:200]}"
        except Exception as e:
            return False, f"Errore connessione Confluence: {e}"

    def fetch_documents(self) -> list[RemoteDocument]:
        headers = self._get_headers()
        docs: list[RemoteDocument] = []
        cql = f"space = '{self.space_key}' and type = page" if self.space_key else "type = page"
        url = f"{self.base_url}/wiki/rest/api/content/search?cql={cql}&expand=body.storage,version,history&limit=50"

        with httpx.Client(timeout=30.0) as client:
            while url:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    _logger.error("Errore fetch Confluence: %s", res.text[:200])
                    break

                body = res.json()
                for item in body.get("results", []):
                    page_id = str(item.get("id", ""))
                    title = str(item.get("title", f"Confluence Page {page_id}"))
                    storage_body = item.get("body", {}).get("storage", {}).get("value", "")
                    content_bytes = storage_body.encode("utf-8")
                    version_info = item.get("version", {})
                    modified_when = str(version_info.get("when", ""))
                    links = item.get("_links", {})
                    web_url = f"{self.base_url}/wiki{links.get('webui', '')}"

                    docs.append(
                        RemoteDocument(
                            id=page_id,
                            name=f"{title}.html",
                            content=content_bytes,
                            media_type="text/html",
                            source_url=web_url,
                            last_modified=modified_when,
                            metadata={"page_id": page_id, "space": self.space_key},
                        )
                    )

                next_link = body.get("_links", {}).get("next")
                if next_link:
                    url = f"{self.base_url}{next_link}" if next_link.startswith("/") else next_link
                else:
                    url = ""

        return docs

    def fetch_delta(self, delta_token: str | None = None) -> DeltaSyncResult:
        """Sincronizzazione incrementale Confluence basata su timestamp CQL (`lastModified > '...'`)."""
        headers = self._get_headers()
        docs: list[RemoteDocument] = []
        errors: list[str] = []
        now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

        if not delta_token:
            # Full initial scan
            docs = self.fetch_documents()
            return DeltaSyncResult(
                connector_type="confluence",
                updated_documents=docs,
                deleted_document_ids=[],
                next_delta_token=now_iso,
            )

        # Incrementale con filtro CQL lastModified
        space_filter = f"space = '{self.space_key}' and " if self.space_key else ""
        cql = f"{space_filter}type = page and lastModified > '{delta_token}'"
        url = f"{self.base_url}/wiki/rest/api/content/search?cql={cql}&expand=body.storage,version,history&limit=50"

        with httpx.Client(timeout=30.0) as client:
            while url:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    errors.append(f"Errore Confluence Delta API ({res.status_code}): {res.text[:200]}")
                    break

                body = res.json()
                for item in body.get("results", []):
                    page_id = str(item.get("id", ""))
                    title = str(item.get("title", f"Confluence Page {page_id}"))
                    storage_body = item.get("body", {}).get("storage", {}).get("value", "")
                    content_bytes = storage_body.encode("utf-8")
                    version_info = item.get("version", {})
                    modified_when = str(version_info.get("when", ""))
                    links = item.get("_links", {})
                    web_url = f"{self.base_url}/wiki{links.get('webui', '')}"

                    docs.append(
                        RemoteDocument(
                            id=page_id,
                            name=f"{title}.html",
                            content=content_bytes,
                            media_type="text/html",
                            source_url=web_url,
                            last_modified=modified_when,
                            metadata={"page_id": page_id, "space": self.space_key},
                        )
                    )

                next_link = body.get("_links", {}).get("next")
                if next_link:
                    url = f"{self.base_url}{next_link}" if next_link.startswith("/") else next_link
                else:
                    url = ""

        return DeltaSyncResult(
            connector_type="confluence",
            updated_documents=docs,
            deleted_document_ids=[],
            next_delta_token=now_iso,
            errors=errors,
        )
