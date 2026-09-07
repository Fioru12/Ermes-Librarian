"""
tests/test_folder_watcher_lifespan.py
Test per l'endpoint di monitoraggio e la sincronizzazione manuale del Folder Watcher.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api import app
import api.libraries
from api.auth import _SESSIONS
from config import cfg


@pytest.fixture
def watcher_client(tmp_path: Path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = cfg.replace(
        BASE_DIR=str(app_dir),
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="StrongPassword!123",
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    monkeypatch.setattr("api.connectors.cfg", test_cfg)

    _SESSIONS.clear()
    monkeypatch.setattr(api.libraries, "_store", None)

    client = TestClient(app)
    client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassword!123"})
    return client


def test_get_watcher_status(watcher_client: TestClient):
    resp = watcher_client.get("/api/connectors/watcher/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is True
    assert "monitored_sources_count" in data
    assert isinstance(data["sources"], list)


def test_sync_watcher_now(watcher_client: TestClient):
    resp = watcher_client.post("/api/connectors/watcher/sync")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "result" in data
    assert "scanned_sources" in data["result"]
