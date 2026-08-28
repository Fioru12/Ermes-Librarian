"""Importazione documenti da cartelle registrate (core/folder_importer.py).

Regole verificate:
- la scansione importa i file supportati e crea i job di indicizzazione;
- i duplicati (stesso contenuto, anche con nome diverso) vengono saltati;
- le estensioni non supportate e le cartelle irraggiungibili non fanno crashare;
- solo editor/owner/admin possono registrare sorgenti e scansionare.
"""
from dataclasses import replace

from fastapi.testclient import TestClient

from api import app
from api.auth import _SESSIONS
from config import cfg


def api_client_factory(tmp_path, monkeypatch):
    test_cfg = replace(cfg, BASE_DIR=str(tmp_path), ADMIN_USERNAME="owner", ADMIN_PASSWORD="StrongPassword!123", API_KEY="")
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    _SESSIONS.clear()
    return TestClient(app), test_cfg


def _setup_library(tmp_path, monkeypatch):
    client, test_cfg = api_client_factory(tmp_path, monkeypatch)
    import api.libraries
    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Archivio", "", "private", owner_id="owner")
    assert client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    return client, store, library, test_cfg


def test_scan_imports_supported_files_and_deduplicates_by_content(tmp_path, monkeypatch):
    client, store, library, _ = _setup_library(tmp_path, monkeypatch)
    folder = tmp_path / "condivisa"
    folder.mkdir()
    (folder / "contratto.txt").write_text("Il contratto scade a dicembre.", encoding="utf-8")
    (folder / "stesso_contenuto.txt").write_text("Il contratto scade a dicembre.", encoding="utf-8")  # duplicato
    (folder / "foglio.xlsx").write_bytes(b"not supported")  # estensione non supportata

    added = client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(folder)})
    assert added.status_code == 201
    source_id = added.json()["id"]

    scan = client.post(f"/api/libraries/{library['id']}/sources/{source_id}/scan")
    assert scan.status_code == 200
    body = scan.json()
    assert [item["filename"] for item in body["imported"]] == ["contratto.txt"]
    assert body["skipped_duplicates"] == ["stesso_contenuto.txt"]
    assert body["skipped_unsupported"] == ["foglio.xlsx"]

    # Il documento importato è realmente nella biblioteca.
    documents = store.list_documents(library["id"])
    assert [d["filename"] for d in documents] == ["contratto.txt"]

    # Seconda scansione: nessun nuovo import; entrambi i file sono già noti.
    rescan = client.post(f"/api/libraries/{library['id']}/sources/{source_id}/scan").json()
    assert rescan["imported"] == []
    assert sorted(rescan["skipped_duplicates"]) == ["contratto.txt", "stesso_contenuto.txt"]


def test_source_registration_is_editor_only_and_validates_paths(tmp_path, monkeypatch):
    client, store, library, test_cfg = _setup_library(tmp_path, monkeypatch)
    from core.governance import create_or_update_user
    create_or_update_user(test_cfg.USERS_FILE, "bob", "viewer", "StrongViewer!123")

    # Viewer: la registrazione viene rifiutata con 401/403 (ruolo insufficiente).
    bob_client = TestClient(app)
    assert bob_client.post("/api/auth/login", json={"username": "bob", "password": "StrongViewer!123"}).status_code == 200
    denied = bob_client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(tmp_path / "x")})
    assert denied.status_code in {401, 403}

    # Percorso inesistente: la registrazione è consentita, ma la scansione lo segnala senza crashare.
    missing = client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(tmp_path / "inesistente")})
    assert missing.status_code == 201
    scan = client.post(f"/api/libraries/{library['id']}/sources/{missing.json()['id']}/scan")
    assert scan.status_code == 200
    assert "non raggiungibile" in scan.json()["failed"][0]["error"]

    # Duplicato della stessa sorgente -> 409.
    again = client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(tmp_path / "inesistente")})
    assert again.status_code == 409
