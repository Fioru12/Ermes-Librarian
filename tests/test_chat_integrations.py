"""Collegamento canale Slack/Teams -> biblioteca (core/library_store.py,
api/libraries.py: add/list/remove_library_chat_integration).

Un webhook non ha una sessione utente Ermes: la sicurezza dell'intera
integrazione chatops dipende dal fatto che SOLO il proprietario di una
biblioteca (o un admin globale) possa decidere quale canale la interroga —
esattamente lo stesso confine gia' verificato per le sorgenti cartella in
tests/test_folder_import.py, qui replicato per lo stesso motivo.
"""
from dataclasses import replace

from fastapi.testclient import TestClient

from api import app
from api.auth import _SESSIONS
from config import cfg


def api_client_factory(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = replace(cfg, BASE_DIR=str(app_dir), ADMIN_USERNAME="owner", ADMIN_PASSWORD="StrongPassword!123", API_KEY="")
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    _SESSIONS.clear()
    return TestClient(app), test_cfg


def _setup_library(tmp_path, monkeypatch, *, visibility="shared"):
    client, test_cfg = api_client_factory(tmp_path, monkeypatch)
    import api.libraries
    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Archivio", "", visibility, owner_id="owner")
    assert client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    return client, store, library, test_cfg


def _login_as(test_cfg, username, role, password):
    from core.governance import create_or_update_user
    create_or_update_user(test_cfg.USERS_FILE, username, role, password)
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return client


def test_owner_can_add_list_and_remove_an_integration(tmp_path, monkeypatch):
    client, store, library, _ = _setup_library(tmp_path, monkeypatch)

    added = client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "slack", "external_channel_id": "C123"})
    assert added.status_code == 201
    integration_id = added.json()["id"]

    listed = client.get(f"/api/libraries/{library['id']}/integrations")
    assert listed.status_code == 200
    assert [item["external_channel_id"] for item in listed.json()["items"]] == ["C123"]

    removed = client.delete(f"/api/libraries/{library['id']}/integrations/{integration_id}")
    assert removed.status_code == 200
    assert client.get(f"/api/libraries/{library['id']}/integrations").json()["items"] == []


def test_integration_registration_requires_ownership_not_just_a_role(tmp_path, monkeypatch):
    client, store, library, test_cfg = _setup_library(tmp_path, monkeypatch, visibility="shared")

    viewer_client = _login_as(test_cfg, "carol", "viewer", "StrongViewer!123")
    client.put(f"/api/libraries/{library['id']}/members", json={"username": "carol", "role": "viewer"})
    denied = viewer_client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "slack", "external_channel_id": "C1"})
    assert denied.status_code == 403

    editor_client = _login_as(test_cfg, "bob", "editor", "StrongEditor!123")
    client.put(f"/api/libraries/{library['id']}/members", json={"username": "bob", "role": "editor"})
    denied_editor = editor_client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "slack", "external_channel_id": "C1"})
    assert denied_editor.status_code == 403

    added = client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "slack", "external_channel_id": "C1"})
    integration_id = added.json()["id"]
    denied_remove = editor_client.delete(f"/api/libraries/{library['id']}/integrations/{integration_id}")
    assert denied_remove.status_code == 403


def test_a_channel_can_only_be_bound_to_one_library(tmp_path, monkeypatch):
    client, store, library, test_cfg = _setup_library(tmp_path, monkeypatch)
    other = client.post("/api/libraries", json={"name": "Altra", "visibility": "private"}).json()

    first = client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "slack", "external_channel_id": "C1"})
    assert first.status_code == 201

    conflict = client.post(f"/api/libraries/{other['id']}/integrations", json={"platform": "slack", "external_channel_id": "C1"})
    assert conflict.status_code == 409


def test_deleting_a_library_removes_its_chat_integrations(tmp_path, monkeypatch):
    client, store, library, _ = _setup_library(tmp_path, monkeypatch, visibility="private")
    added = client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "teams", "external_channel_id": "T1"})
    assert added.status_code == 201

    assert client.delete(f"/api/libraries/{library['id']}").status_code == 204
    assert store.get_chat_integration_by_channel("teams", "T1") is None
