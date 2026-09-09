"""
tests/test_integrations_mcp_automation.py
Integration tests for MCP Server and Automation Webhook endpoints.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api import app
import api.libraries
from api.auth import session_store
from config import cfg


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = cfg.replace(
        BASE_DIR=str(app_dir),
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="StrongPassword!123",
        API_KEY="",
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    monkeypatch.setattr("api.mcp_server.cfg", test_cfg, raising=False)
    monkeypatch.setattr("api.webhook_gateway.cfg", test_cfg, raising=False)

    session_store.clear()
    monkeypatch.setattr(api.libraries, "_store", None)

    client = TestClient(app)
    # Login to initialize session cookie / auth
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassword!123"})
    assert login_res.status_code == 200

    yield client
    session_store.clear()


def test_mcp_info_and_tools(api_client: TestClient):
    res = api_client.get("/api/mcp/info")
    assert res.status_code == 200
    assert res.json()["name"] == "ermes-knowledge-mcp"

    res_tools = api_client.get("/api/mcp/tools")
    assert res_tools.status_code == 200
    tools = res_tools.json()["tools"]
    tool_names = [t["name"] for t in tools]
    assert "list_libraries" in tool_names
    assert "ask_library" in tool_names
    assert "search_documents" in tool_names


def test_mcp_jsonrpc_initialize_and_tools_list(api_client: TestClient):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    res = api_client.post("/api/mcp/rpc", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 1
    assert data["result"]["serverInfo"]["name"] == "ermes-knowledge-mcp"

    payload_list = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    res_list = api_client.post("/api/mcp/rpc", json=payload_list)
    assert res_list.status_code == 200
    assert "tools" in res_list.json()["result"]


def test_automation_webhook_flow(api_client: TestClient):
    # 1. Lista biblioteche
    res_libs = api_client.get("/api/integrations/automation/libraries")
    assert res_libs.status_code == 200
    assert res_libs.json()["ok"] is True

    # 2. Crea biblioteca tramite lo store
    store = api.libraries.get_library_store()
    lib = store.create_library("Automazione IT", "Descrizione", "private", owner_id="admin")
    lib_id = lib["id"]

    ingest_payload = {
        "library_id": lib_id,
        "filename": "procedura_vpn.txt",
        "content": "Per connettersi alla VPN aziendale usare il server vpn.azienda.local con porta 443.",
        "is_base64": False,
        "media_type": "text/plain",
    }

    res_ingest = api_client.post("/api/integrations/automation/ingest", json=ingest_payload)
    assert res_ingest.status_code == 200
    assert res_ingest.json()["ok"] is True
    assert res_ingest.json()["filename"] == "procedura_vpn.txt"

    # 3. Interroga la biblioteca tramite il webhook /ask
    ask_payload = {"library_id": lib_id, "question": "Qual è il server VPN aziendale?"}

    res_ask = api_client.post("/api/integrations/automation/ask", json=ask_payload)
    assert res_ask.status_code == 200
    ask_data = res_ask.json()
    assert ask_data["ok"] is True
    assert "vpn.azienda.local" in ask_data["answer"] or ask_data["evidence_found"] is True
