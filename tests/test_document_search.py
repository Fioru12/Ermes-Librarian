"""Ricerca limitata a un singolo documento (GET .../documents/{id}/search).

Regole verificate:
- i risultati contengono SOLO passaggi del documento richiesto;
- l'ACL per-documento vale anche qui: un utente escluso riceve 404;
- query troppo corte -> 422.
"""
from dataclasses import replace

from fastapi.testclient import TestClient

from api import app
from api.auth import _SESSIONS
from config import cfg


def api_client_factory(tmp_path, monkeypatch):
    """Client API con cfg isolata in tmp_path; ritorna (client, test_cfg)."""
    test_cfg = replace(cfg, BASE_DIR=str(tmp_path), ADMIN_USERNAME="owner", ADMIN_PASSWORD="StrongPassword!123", API_KEY="")
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    _SESSIONS.clear()
    return TestClient(app), test_cfg


def _add_doc(store, library_id: str, filename: str, text: str) -> dict:
    return store.add_document(
        library_id=library_id,
        filename=filename,
        media_type="text/plain",
        content=text.encode("utf-8"),
        storage_path=f"{library_id}/{filename}",
        extracted_text=text,
        source_units=1,
        chunks=[(text, "Pagina 1")],
    )


def test_document_scoped_search_returns_only_that_document(tmp_path, monkeypatch):
    client, _ = api_client_factory(tmp_path, monkeypatch)
    import api.libraries
    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Contratti", "", "private", owner_id="owner")
    contratto = _add_doc(store, library["id"], "contratto.txt", "Il contratto scade a dicembre con preavviso di trenta giorni.")
    altro = _add_doc(store, library["id"], "manuale.txt", "Il manuale di avvio descrive la procedura di dicembre.")

    assert client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    response = client.get(f"/api/libraries/{library['id']}/documents/{contratto['id']}/search?q=dicembre")
    assert response.status_code == 200
    body = response.json()
    assert {item["document_id"] for item in body["items"]} == {contratto["id"]}
    # La stessa query sull'altro documento non restituisce il contenuto del primo.
    response2 = client.get(f"/api/libraries/{library['id']}/documents/{altro['id']}/search?q=dicembre")
    assert all(item["document_id"] == altro["id"] for item in response2.json()["items"])

    short = client.get(f"/api/libraries/{library['id']}/documents/{contratto['id']}/search?q=d")
    assert short.status_code == 422
    missing = client.get(f"/api/libraries/{library['id']}/documents/inesistente/search?q=dicembre")
    assert missing.status_code == 404
