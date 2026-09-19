"""
tests/test_microsoft_graph_connector.py
Unit tests for Microsoft 365 SharePoint/OneDrive Connector.
"""

from __future__ import annotations

import pytest
from core.connectors.microsoft_graph import MicrosoftGraphConnector


class DummyResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, content: bytes = b""):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = content
        self.text = "Dummy response text"

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP error {self.status_code}")


def test_graph_credentials_validation():
    conn = MicrosoftGraphConnector({})
    with pytest.raises(ValueError, match="Credenziali Microsoft Graph incomplete"):
        conn.fetch_documents()


def test_graph_test_connection_success(monkeypatch):
    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, data=None):
            return DummyResponse(200, {"access_token": "fake-token"})
        def get(self, url, headers=None):
            if "organization" in url:
                return DummyResponse(200, {"value": [{"displayName": "Contoso"}]})
            return DummyResponse(404)

    monkeypatch.setattr("httpx.Client", MockClient)

    conn = MicrosoftGraphConnector({
        "tenant_id": "tenant-123",
        "client_id": "client-123",
        "client_secret": "secret-123",
    })
    ok, msg = conn.test_connection()
    assert ok is True
    assert "successo" in msg


def test_graph_fetch_documents_recursive_and_pagination(monkeypatch):
    """Verifica che il connettore Graph traversi ricorsivamente le sottocartelle e gestisca @odata.nextLink."""
    drive_id = "drv-456"

    # URL mappings
    # 1. Token URL -> access_token
    # 2. Initial folder URL -> file1 + page 2 nextLink
    # 3. Page 2 URL -> folder1 (subfolder)
    # 4. Subfolder URL -> file2 inside subfolder
    # 5. File downloads -> file content
    def mock_get(url, headers=None):
        if "root:/Progetti/RAG:/children" in url:
            return DummyResponse(200, {
                "value": [
                    {
                        "id": "file-1",
                        "name": "doc1.docx",
                        "file": {"mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
                        "@microsoft.graph.downloadUrl": "https://download.microsoft.com/file1",
                        "webUrl": "https://sharepoint.com/doc1.docx",
                        "lastModifiedDateTime": "2026-09-19T10:00:00Z",
                        "size": 1024,
                    }
                ],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/drives/drv-456/page2",
            })
        elif "page2" in url:
            return DummyResponse(200, {
                "value": [
                    {
                        "id": "subfolder-1",
                        "name": "Sottocartella",
                        "folder": {"childCount": 1},
                    }
                ]
            })
        elif "items/subfolder-1/children" in url:
            return DummyResponse(200, {
                "value": [
                    {
                        "id": "file-2",
                        "name": "doc2.txt",
                        "file": {"mimeType": "text/plain"},
                        "webUrl": "https://sharepoint.com/doc2.txt",
                        "lastModifiedDateTime": "2026-09-19T11:00:00Z",
                        "size": 512,
                        # Assenza di @microsoft.graph.downloadUrl per testare il fallback su /content
                    }
                ]
            })
        elif url == "https://download.microsoft.com/file1":
            return DummyResponse(200, content=b"DOCX_CONTENT")
        elif "items/file-2/content" in url:
            return DummyResponse(200, content=b"TEXT_CONTENT_FALLBACK")
        return DummyResponse(404)

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, data=None):
            return DummyResponse(200, {"access_token": "fake-token"})
        def get(self, url, headers=None):
            return mock_get(url, headers)

    monkeypatch.setattr("httpx.Client", MockClient)

    conn = MicrosoftGraphConnector({
        "tenant_id": "tenant-123",
        "client_id": "client-123",
        "client_secret": "secret-123",
        "drive_id": drive_id,
        "folder_path": "/Progetti/RAG/",
        "recursive": True,
    })

    docs = conn.fetch_documents()
    assert len(docs) == 2

    doc1 = next(d for d in docs if d.id == "file-1")
    assert doc1.name == "doc1.docx"
    assert doc1.content == b"DOCX_CONTENT"
    assert "wordprocessingml" in doc1.media_type

    doc2 = next(d for d in docs if d.id == "file-2")
    assert doc2.name == "doc2.txt"
    assert doc2.content == b"TEXT_CONTENT_FALLBACK"
    assert doc2.media_type == "text/plain"
