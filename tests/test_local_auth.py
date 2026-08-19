from dataclasses import replace

from fastapi.testclient import TestClient

from api import app
from api.auth import _SESSIONS
from config import cfg
from core.governance import create_or_update_user


def test_local_password_login_protects_libraries(tmp_path, monkeypatch):
    test_cfg = replace(
        cfg,
        BASE_DIR=str(tmp_path),
        ADMIN_USERNAME="owner",
        ADMIN_PASSWORD="StrongPassword!123",
        API_KEY="",
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    _SESSIONS.clear()
    client = TestClient(app)

    assert client.get("/api/libraries").status_code == 401
    assert client.post("/api/auth/login", json={"username": "owner", "password": "wrong"}).status_code == 401

    response = client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"})
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert client.get("/api/libraries").status_code == 200

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/libraries").status_code == 401


def test_disabled_local_account_loses_an_existing_browser_session(tmp_path, monkeypatch):
    test_cfg = replace(
        cfg,
        BASE_DIR=str(tmp_path),
        ADMIN_USERNAME="owner",
        ADMIN_PASSWORD="StrongPassword!123",
        API_KEY="",
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    _SESSIONS.clear()
    client = TestClient(app)

    assert client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    create_or_update_user(test_cfg.USERS_FILE, "owner", "admin", "", active=False)
    assert client.get("/api/libraries").status_code == 401


def test_sensitive_operations_are_admin_only_and_shutdown_is_disabled_without_key(tmp_path, monkeypatch):
    test_cfg = replace(
        cfg,
        BASE_DIR=str(tmp_path),
        ADMIN_USERNAME="owner",
        ADMIN_PASSWORD="StrongPassword!123",
        API_KEY="",
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    _SESSIONS.clear()
    admin = TestClient(app)
    assert admin.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    create_or_update_user(test_cfg.USERS_FILE, "maria", "editor", "StrongEditor!123")

    editor = TestClient(app)
    assert editor.post("/api/auth/login", json={"username": "maria", "password": "StrongEditor!123"}).status_code == 200
    for path in ("/api/providers", "/api/audit/logs", "/backup/list", "/shutdown"):
        assert editor.get(path).status_code == 403 if path != "/shutdown" else editor.post(path).status_code == 403

    assert admin.post("/shutdown").status_code == 503
