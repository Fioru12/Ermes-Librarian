"""
core/connectors/webdav.py
Nextcloud / ownCloud / WebDAV Enterprise Connector for Ermes Knowledge.
Interacts with WebDAV servers using standard HTTP PROPFIND and GET requests.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urljoin

import httpx
from defusedxml import ElementTree

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


PROPFIND_XML_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname/>
    <d:getcontentlength/>
    <d:getlastmodified/>
    <d:resourcetype/>
  </d:prop>
</d:propfind>"""


class WebDAVConnector(BaseConnector):
    """Connettore per istanze Nextcloud, ownCloud o server WebDAV generici.

    Configurazione richiesta:
    - base_url: URL base WebDAV (es. https://nextcloud.domain.com/remote.php/dav/files/username/)
    - username: nome utente
    - password: password o App Token
    - folder_path: sottocartella opzionale (default: '/')
    - verify_ssl: verifica certificati TLS (default: True)
    - max_files: limite massimo di file (default: 200)
    - extensions: estensioni consentite
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        raw_url = config.get("base_url", "").strip()
        if raw_url and not raw_url.endswith("/"):
            raw_url += "/"
        self.base_url = raw_url
        self.username = config.get("username", "").strip()
        self.password = config.get("password", "").strip()
        folder = config.get("folder_path", "/").strip().lstrip("/")
        if folder and not folder.endswith("/"):
            folder += "/"
        self.folder_path = folder
        self.verify_ssl = bool(config.get("verify_ssl", True))
        self.max_files = int(config.get("max_files", 200))
        self.allowed_extensions = set(config.get("extensions", list(SUPPORTED_EXTENSIONS)))

    def _get_target_url(self) -> str:
        if self.folder_path:
            return str(urljoin(self.base_url, self.folder_path))
        return str(self.base_url)


    def _get_client(self) -> httpx.Client:
        auth = httpx.BasicAuth(self.username, self.password) if (self.username and self.password) else None
        return httpx.Client(
            auth=auth,
            verify=self.verify_ssl,
            timeout=25.0,
            headers={"User-Agent": "Ermes-Knowledge/1.0 WebDAVConnector"},
        )

    def test_connection(self) -> tuple[bool, str]:
        if not self.base_url:
            return False, "URL WebDAV (base_url) non specificato"

        target_url = self._get_target_url()
        try:
            with self._get_client() as client:
                resp = client.request(
                    "PROPFIND",
                    target_url,
                    content=PROPFIND_XML_BODY,
                    headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
                )
                if resp.status_code in (200, 207):
                    return True, f"Server WebDAV raggiungibile con successo ({target_url})"
                if resp.status_code in (401, 403):
                    return False, f"Autenticazione WebDAV fallita (status {resp.status_code})"
                return False, f"Risposta WebDAV inattesa (status {resp.status_code}): {resp.text[:200]}"
        except Exception as exc:
            _logger.warning("Test connessione WebDAV fallito per %s: %s", target_url, exc)
            return False, f"Errore di rete verso WebDAV ({target_url}): {exc}"

    def fetch_documents(self) -> list[RemoteDocument]:
        ok, msg = self.test_connection()
        if not ok:
            _logger.warning("WebDAVConnector test_connection fallito: %s", msg)
            return []

        target_url = self._get_target_url()
        documents: list[RemoteDocument] = []

        try:
            with self._get_client() as client:
                resp = client.request(
                    "PROPFIND",
                    target_url,
                    content=PROPFIND_XML_BODY,
                    headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
                )
                if resp.status_code not in (200, 207):
                    _logger.error("WebDAV PROPFIND fallito con status %s", resp.status_code)
                    return []

                root = ElementTree.fromstring(resp.content)
                # I namespace WebDAV standard usano 'DAV:'

                ns = {"d": "DAV:"}

                for response_node in root.findall("d:response", ns):
                    if len(documents) >= self.max_files:
                        _logger.info("Raggiunto limite massimo di %d file da WebDAV", self.max_files)
                        break

                    href_node = response_node.find("d:href", ns)
                    if href_node is None or not href_node.text:
                        continue

                    href = unquote(href_node.text.strip())
                    # Ignora se è una directory (ha d:resourcetype/d:collection o termina per /)
                    is_dir = False
                    resourcetype = response_node.find(".//d:resourcetype", ns)
                    if resourcetype is not None and resourcetype.find("d:collection", ns) is not None:
                        is_dir = True
                    if href.endswith("/") or is_dir:
                        continue

                    path = PurePosixPath(href)
                    ext = path.suffix.lower()
                    if ext not in self.allowed_extensions:
                        continue

                    # Estrai metadata se presenti
                    last_mod_node = response_node.find(".//d:getlastmodified", ns)
                    last_mod_str = last_mod_node.text.strip() if last_mod_node is not None and last_mod_node.text else ""

                    size_node = response_node.find(".//d:getcontentlength", ns)
                    file_size = int(size_node.text.strip()) if size_node is not None and size_node.text and size_node.text.isdigit() else 0

                    file_url = urljoin(self.base_url, href)

                    # Scarica il file
                    try:
                        file_resp = client.get(file_url)
                        file_resp.raise_for_status()
                        file_bytes = file_resp.content

                        media_type = MEDIA_TYPES.get(ext) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                        doc = RemoteDocument(
                            id=file_url,
                            name=path.name,
                            content=file_bytes,
                            media_type=media_type,
                            source_url=file_url,
                            last_modified=last_mod_str,
                            metadata={"href": href, "size": file_size or len(file_bytes)},
                        )

                        documents.append(doc)
                    except Exception as err:
                        _logger.warning("Errore scaricamento file WebDAV %s: %s", file_url, err)
                        continue

        except Exception as exc:
            _logger.error("Errore durante fetch_documents da WebDAV %s: %s", target_url, exc)

        return documents
