"""tests/test_cloud_connectors.py
Test suite per i connettori Cloud Enterprise, la sincronizzazione incrementale (delta) e i webhook.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from api import app
from config import cfg
from core.connectors.confluence import ConfluenceConnector
from core.connectors.google_drive import GoogleDriveConnector
from core.connectors.microsoft_graph import MicrosoftGraphConnector
from core.library_store import LibraryStore


@pytest.fixture
def client():
    return TestClient(app)


def test_google_drive_connector_delta(monkeypatch):
    def mock_get(client_self, url, *args, **kwargs):
        req = httpx.Request("GET", str(url))
        url_str = str(url)
        if "changes/startPageToken" in url_str:
            return httpx.Response(200, json={"startPageToken": "token_100"}, request=req)
        elif "changes?pageToken=token_100" in url_str or "pageToken=token_100" in url_str:
            return httpx.Response(
                200,
                json={
                    "newStartPageToken": "token_101",
                    "nextPageToken": None,
                    "changes": [
                        {
                            "fileId": "file_doc_1",
                            "removed": False,
                            "file": {
                                "id": "file_doc_1",
                                "name": "Policy_Sicurezza.txt",
                                "mimeType": "text/plain",
                                "modifiedTime": "2026-09-21T10:00:00Z",
                                "trashed": False,
                            },
                        },
                        {
                            "fileId": "file_deleted_9",
                            "removed": True,
                        },
                    ],
                },
                request=req,
            )
        elif "files/file_doc_1?alt=media" in url_str:
            return httpx.Response(200, content=b"Contenuto policy aziendale aggiornato.", request=req)
        elif "about?fields=user" in url_str:
            return httpx.Response(200, json={"user": {"emailAddress": "admin@ermes.corp"}}, request=req)
        return httpx.Response(404, request=req)

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    connector = GoogleDriveConnector({"access_token": "ya29.test_token", "folder_id": "root"})
    ok, msg = connector.test_connection()
    assert ok is True
    assert "admin@ermes.corp" in msg

    # Delta scan with token_100
    delta_res = connector.fetch_delta("token_100")
    assert delta_res.next_delta_token == "token_101"
    assert len(delta_res.updated_documents) == 1
    assert delta_res.updated_documents[0].name == "Policy_Sicurezza.txt"
    assert delta_res.updated_documents[0].content == b"Contenuto policy aziendale aggiornato."
    assert "file_deleted_9" in delta_res.deleted_document_ids


def test_confluence_connector_delta(monkeypatch):
    def mock_get(client_self, url, *args, **kwargs):
        req = httpx.Request("GET", str(url))
        url_str = str(url)
        if "rest/api/space" in url_str:
            return httpx.Response(200, json={"key": "DEV"}, request=req)
        elif "content/search" in url_str:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "12345",
                            "title": "Manuale Operativo",
                            "body": {"storage": {"value": "<p>Istruzioni operative 2026</p>"}},
                            "version": {"when": "2026-09-21T12:00:00Z"},
                            "_links": {"webui": "/spaces/DEV/pages/12345"},
                        }
                    ],
                    "_links": {},
                },
                request=req,
            )
        return httpx.Response(404, request=req)

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    conn = ConfluenceConnector({
        "base_url": "https://company.atlassian.net",
        "username": "user@company.com",
        "api_token": "token123",
        "space_key": "DEV",
    })

    ok, msg = conn.test_connection()
    assert ok is True

    res = conn.fetch_delta("2026-09-20 00:00")
    assert len(res.updated_documents) == 1
    assert res.updated_documents[0].name == "Manuale Operativo.html"
    assert b"Istruzioni operative 2026" in res.updated_documents[0].content
    assert res.next_delta_token is not None


def test_microsoft_graph_delta(monkeypatch):
    def mock_post(client_self, url, *args, **kwargs):
        req = httpx.Request("POST", str(url))
        return httpx.Response(200, json={"access_token": "fake_graph_token"}, request=req)

    def mock_get(client_self, url, *args, **kwargs):
        req = httpx.Request("GET", str(url))
        url_str = str(url)
        if "delta" in url_str:
            return httpx.Response(
                200,
                json={
                    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/drives/root/delta?token=new_token_456",
                    "value": [
                        {
                            "id": "graph_item_1",
                            "name": "Report_Finanziario.docx",
                            "file": {"mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
                            "@microsoft.graph.downloadUrl": "https://download.graph.com/file1",
                            "webUrl": "https://sharepoint.com/file1",
                        },
                        {
                            "id": "graph_item_deleted",
                            "@removed": {"reason": "deleted"},
                        },
                    ],
                },
                request=req,
            )
        elif "download.graph.com/file1" in url_str:
            return httpx.Response(200, content=b"PK\x03\x04 fake docx content", request=req)
        return httpx.Response(404, request=req)

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    monkeypatch.setattr(httpx.Client, "get", mock_get)

    connector = MicrosoftGraphConnector({
        "tenant_id": "tenant-id",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "drive_id": "drive-1",
    })

    delta_res = connector.fetch_delta("token_123")
    assert delta_res.connector_type == "microsoft_graph"
    assert len(delta_res.updated_documents) == 1
    assert delta_res.updated_documents[0].name == "Report_Finanziario.docx"
    assert "graph_item_deleted" in delta_res.deleted_document_ids
    assert "new_token_456" in str(delta_res.next_delta_token)


def test_connectors_api_webhooks_and_delta(client, tmp_path, monkeypatch):
    from api.libraries import get_library_store

    # Setup test storage and database
    db_file = tmp_path / "test_connectors.db"
    store = LibraryStore(database_path=db_file)
    app.dependency_overrides[get_library_store] = lambda: store
    monkeypatch.setattr(cfg, "API_KEY", "admin-key")

    # Inizializza biblioteca di test
    lib = store.create_library("Cloud Library", owner_id="api-admin")
    lib_id = lib["id"]

    headers = {"Authorization": "Bearer admin-key"}

    # 1. Test Webhook Microsoft Graph Handshake (GET con validationToken)
    val_res = client.get("/api/connectors/webhooks/microsoft-graph?validationToken=secret_token_123")
    assert val_res.status_code == 200
    assert val_res.text == "secret_token_123"

    # 2. Test Webhook Microsoft Graph Notification (POST)
    post_res = client.post("/api/connectors/webhooks/microsoft-graph", json={"value": [{"resource": "drive/root"}]})
    assert post_res.status_code == 202

    # 3. Test Webhook Google Drive Push Notification
    g_res = client.post(
        "/api/connectors/webhooks/google-drive",
        headers={
            "X-Goog-Channel-ID": "chan-001",
            "X-Goog-Resource-State": "update",
            "X-Goog-Message-Number": "42",
        },
    )
    assert g_res.status_code == 200

    # 4. Test API Delta Sync con mock connector
    from core.connectors.base import BaseConnector, DeltaSyncResult, RemoteDocument

    class MockDeltaConnector(BaseConnector):
        def test_connection(self):
            return True, "Mock OK"

        def fetch_documents(self):
            return []

        def fetch_delta(self, delta_token=None):
            return DeltaSyncResult(
                connector_type="mock",
                updated_documents=[
                    RemoteDocument(
                        id="doc-1",
                        name="Test_Sync.txt",
                        content=b"Contenuto importato da delta sync",
                        media_type="text/plain",
                        source_url="https://cloud.com/test",
                        last_modified="2026-09-21T15:00:00Z",
                    )
                ],
                deleted_document_ids=[],
                next_delta_token="cursor_v2",
            )

    monkeypatch.setattr("api.connectors._build_connector", lambda c_type, config: MockDeltaConnector(config))

    try:
        sync_payload = {
            "type": "google_drive",
            "config": {"access_token": "token"},
            "target_library_id": lib_id,
            "delta_token": "cursor_v1",
        }
        sync_res = client.post("/api/connectors/sync-delta", json=sync_payload, headers=headers)
        assert sync_res.status_code == 200
        data = sync_res.json()
        assert data["ok"] is True
        assert data["imported_count"] == 1
        assert data["next_delta_token"] == "cursor_v2"

        # Verifica che il documento sia effettivamente presente nella biblioteca
        docs = store.list_documents(lib_id)
        assert len(docs) == 1
        assert docs[0]["filename"] == "Test_Sync.txt"
    finally:
        app.dependency_overrides.pop(get_library_store, None)
