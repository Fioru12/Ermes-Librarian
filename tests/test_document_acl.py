"""Isolamento a livello documento (ACL per-documento).

Regola: un documento senza allow-list segue le regole della libreria; un
documento CON allow-list e' visibile solo ad admin, proprietario e utenti
elencati. Il filtro agisce dentro `search_with_profile`, prima che qualsiasi
citazione venga costruita: il leak attraverso i risultati di ricerca deve essere
impossibile, non solo raro.
"""
from dataclasses import replace

from fastapi.testclient import TestClient
import pytest

from api import app
from api.auth import _SESSIONS
from config import cfg
from core.governance import create_or_update_user
from core.library_store import LibraryAccessError, LibraryStore


def _make_store(tmp_path) -> LibraryStore:
    return LibraryStore(tmp_path / "ermes.sqlite3")


def _add_doc(store: LibraryStore, library_id: str, filename: str, marker: str) -> dict:
    return store.add_document(
        library_id=library_id,
        filename=filename,
        media_type="text/plain",
        content=marker.encode("utf-8"),
        storage_path=f"{library_id}/{filename}",
        extracted_text=marker,
        source_units=1,
        chunks=[(marker, "Pagina 1")],
    )


def test_document_acl_hides_list_search_and_details_from_non_listed_users(tmp_path):
    store = _make_store(tmp_path)
    library = store.create_library("Riservate", "", "private", owner_id="alice")
    library_id = library["id"]
    _add_doc(store, library_id, "spese.txt", "Le note spese si inviano entro il dieci del mese.")
    riservato = _add_doc(store, library_id, "stipendi.txt", "Gli stipendi vengono erogati il ventisette.")

    # bob e carol sono collaboratori della libreria: senza ACL vedrebbero tutto.
    store.set_library_member(library_id, "bob", "viewer")
    store.set_library_member(library_id, "carol", "viewer")
    store.set_document_acl(library_id, riservato["id"], ["carol"])

    bob = {"username": "bob", "role": "viewer"}
    carol = {"username": "carol", "role": "viewer"}
    alice = {"username": "alice", "role": "viewer"}  # proprietario, ruolo minimo
    root = {"username": "root", "role": "admin"}

    def names_for(actor):
        return sorted(d["filename"] for d in store.list_documents(library_id, actor))

    assert names_for(bob) == ["spese.txt"]
    assert names_for(carol) == ["spese.txt", "stipendi.txt"]
    assert names_for(alice) == ["spese.txt", "stipendi.txt"]
    assert names_for(root) == ["spese.txt", "stipendi.txt"]

    with pytest.raises(LibraryAccessError):
        store.get_document(library_id, riservato["id"], bob)

    hits_bob = store.search_with_profile(library_id, "stipendi", actor=bob)[0]
    assert [item["document_id"] for item in hits_bob] == []
    hits_carol = store.search_with_profile(library_id, "stipendi", actor=carol)[0]
    assert {item["document_id"] for item in hits_carol} == {riservato["id"]}

    # Nemmeno le versioni trapelano.
    with pytest.raises(LibraryAccessError):
        store.list_document_versions(library_id, riservato["id"], bob)


def test_empty_acl_removes_the_restriction(tmp_path):
    store = _make_store(tmp_path)
    library = store.create_library("Aperta", "", "shared", owner_id="alice")
    document = _add_doc(store, library["id"], "manuale.txt", "Il manuale descrive la procedura di avvio.")
    store.set_document_acl(library["id"], document["id"], ["carol"])
    bob = {"username": "bob", "role": "viewer"}

    assert store.list_documents(library["id"], bob) == []
    store.set_document_acl(library["id"], document["id"], [])
    assert [d["filename"] for d in store.list_documents(library["id"], bob)] == ["manuale.txt"]


def test_acl_api_is_owner_admin_only_and_validates_usernames(tmp_path, monkeypatch):
    test_cfg = replace(cfg, BASE_DIR=str(tmp_path), ADMIN_USERNAME="owner", ADMIN_PASSWORD="StrongPassword!123", API_KEY="")
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    _SESSIONS.clear()
    client = TestClient(app)

    assert client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    create_or_update_user(test_cfg.USERS_FILE, "maria", "editor", "StrongEditor!123")

    # Usa lo stesso store singleton dell'API: altrimenti la libreria finirebbe
    # in un altro database rispetto a quello interrogato dagli endpoint.
    import api.libraries
    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Demo", "", "private", owner_id="owner")
    document = _add_doc(store, library["id"], "contratto.txt", "Il contratto scade a dicembre.")
    store.set_library_member(library["id"], "maria", "viewer")
    headers: dict[str, str] = {}  # autenticazione via cookie di sessione

    # Un collaboratore che non e' proprietario vede la libreria ma non puo'
    # né leggere né modificare le restrizioni dei documenti.
    maria = TestClient(app)
    assert maria.post("/api/auth/login", json={"username": "maria", "password": "StrongEditor!123"}).status_code == 200
    base = f"/api/libraries/{library['id']}/documents/{document['id']}/acl"
    assert maria.get(base, headers=headers).status_code == 403
    assert maria.put(base, json={"usernames": []}, headers=headers).status_code == 403

    # Utenti inesistenti rifiutati con 422...
    response = client.put(base, json={"usernames": ["fantasma"]}, headers=headers)
    assert response.status_code == 422
    assert "fantasma" in response.json()["detail"]

    # ...quelli validi vengono registrati e auditati. Finche' non esiste una
    # allow-list il documento e' visibile ai membri...
    listed = maria.get(f"/api/libraries/{library['id']}/documents", headers=headers).json()["items"]
    assert [item["filename"] for item in listed] == ["contratto.txt"]

    # ...ma basta restringerlo a un altro utente per renderlo invisibile a Maria.
    create_or_update_user(test_cfg.USERS_FILE, "anna", "viewer", "StrongViewer!123")
    assert client.put(base, json={"usernames": ["anna"]}, headers=headers).status_code == 200
    assert maria.get(f"/api/libraries/{library['id']}/documents", headers=headers).json()["items"] == []
    audit_text = (tmp_path / "logs" / "audit_admin.jsonl").read_text(encoding="utf-8")
    assert '"document_acl_changed"' in audit_text

    # Aggiungere Maria all'allow-list le ridà visibilità: il filtro regge via API.
    assert client.put(base, json={"usernames": ["maria"]}, headers=headers).status_code == 200
    items = client.get(base, headers=headers).json()["items"]
    assert [item["username"] for item in items] == ["maria"]
    listed = maria.get(f"/api/libraries/{library['id']}/documents", headers=headers).json()["items"]
    assert [item["filename"] for item in listed] == ["contratto.txt"]
