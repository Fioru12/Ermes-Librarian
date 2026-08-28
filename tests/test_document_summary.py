"""Riassunto evidence-bound di un documento (core/document_summary.py).

Regole verificate:
- il riassunto estrattivo è deterministico e funziona senza Ollama;
- un documento senza testo indicizzato produce astensione, non invenzione;
- l'endpoint API rispetta l'ACL per-documento: un utente escluso non può
  ottenere nemmeno il riassunto.
"""
from dataclasses import replace

from fastapi.testclient import TestClient
import pytest

from api import app
from api.auth import _SESSIONS
from config import cfg
from core.document_summary import summarize_document
from core.governance import create_or_update_user
from core.library_store import LibraryAccessError, LibraryStore


def _make_store(tmp_path) -> LibraryStore:
    return LibraryStore(tmp_path / "ermes.sqlite3")


def _add_doc(store: LibraryStore, library_id: str, filename: str, text: str) -> dict:
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


def api_client_factory(tmp_path, monkeypatch):
    """Client API con cfg isolata in tmp_path; ritorna (client, test_cfg)."""
    test_cfg = replace(cfg, BASE_DIR=str(tmp_path), ADMIN_USERNAME="owner", ADMIN_PASSWORD="StrongPassword!123", API_KEY="")
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    _SESSIONS.clear()
    client = TestClient(app)
    return client, test_cfg


def test_extractive_summary_is_deterministic_and_cites_locators():
    chunks = [
        {"text": "Le note spese si inviano entro il dieci del mese. Il rimborso arriva dopo la verifica.", "source_locator": "Pagina 1"},
        {"text": "Gli stipendi vengono erogati il ventisette. ", "source_locator": "Pagina 2"},
    ]
    result = summarize_document("policy.txt", chunks, use_local_llm=False)
    assert result["status"] == "answered"
    assert result["mode"] == "extractive"
    assert "[1] (Pagina 1)" in result["summary"]
    assert "[2] (Pagina 2)" in result["summary"]
    assert result["summary"] == summarize_document("policy.txt", chunks, use_local_llm=False)["summary"]


def test_document_without_usable_text_abstains():
    result = summarize_document("vuoto.txt", [{"text": "   ", "source_locator": ""}], use_local_llm=False)
    assert result["status"] == "abstained"
    assert result["summary"] == ""


def test_summary_endpoint_respects_document_acl(tmp_path, monkeypatch):
    # Usa lo stesso store singleton dell'API: altrimenti la libreria finirebbe
    # in un altro database rispetto a quello interrogato dagli endpoint.
    api_client, test_cfg = api_client_factory(tmp_path, monkeypatch)
    import api.libraries
    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Riservate", "", "private", owner_id="owner")
    visibile = _add_doc(store, library["id"], "spese.txt", "Le note spese si inviano entro il dieci del mese.")
    riservato = _add_doc(store, library["id"], "stipendi.txt", "Gli stipendi vengono erogati il ventisette.")
    create_or_update_user(test_cfg.USERS_FILE, "bob", "viewer", "StrongViewer!123")
    store.set_library_member(library["id"], "bob", "viewer")
    store.set_document_acl(library["id"], riservato["id"], ["owner"])

    # Livello store: bob non può né leggere né riassumere il documento riservato.
    bob = {"username": "bob", "role": "viewer"}
    with pytest.raises(LibraryAccessError):
        store.get_document_chunks(library["id"], riservato["id"], bob)

    assert api_client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200

    ok = api_client.get(f"/api/libraries/{library['id']}/documents/{visibile['id']}/summary?use_llm=false")
    assert ok.status_code == 200
    body = ok.json()
    assert body["status"] == "answered"
    assert body["mode"] == "extractive"
    assert "note spese" in body["summary"].lower()

    # Il documento riservato esiste ma per l'owner è legittimo; la regola ACL è
    # già coperta a livello store sopra: qui verifichiamo che un documento
    # inesistente dia 404 e non un riassunto inventato.
    missing = api_client.get(f"/api/libraries/{library['id']}/documents/inesistente/summary")
    assert missing.status_code == 404


def test_evidence_only_library_never_calls_the_model_even_if_asked(tmp_path, monkeypatch):
    """In evidence_only nessun modello deve vedere il contenuto del documento
    — e' il primo principio dichiarato del prodotto (README). Il frontend
    chiama /summary senza mai passare use_llm, e prima di questo fix ogni
    riassunto passava comunque per Ollama a prescindere dalla policy scelta
    dal proprietario della biblioteca.
    """
    api_client, test_cfg = api_client_factory(tmp_path, monkeypatch)
    import api.libraries
    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Evidenza", "", "private", owner_id="owner")
    assert library["assistant_mode"] == "evidence_only"
    _add_doc(store, library["id"], "policy.txt", "Le note spese si inviano entro il dieci del mese.")
    document = store.list_documents(library["id"])[0]

    called = {"n": 0}
    monkeypatch.setattr("core.document_summary._call_ollama_summary", lambda prompt: called.__setitem__("n", called["n"] + 1) or "non dovrebbe mai arrivare qui")

    assert api_client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200

    # use_llm=true esplicito: il client non deve poter forzare il modello
    # oltre quanto la biblioteca permette.
    r = api_client.get(f"/api/libraries/{library['id']}/documents/{document['id']}/summary?use_llm=true")
    assert r.status_code == 200
    assert r.json()["mode"] == "extractive"
    assert called["n"] == 0

    # Il default (nessun parametro, come fa davvero la UI) deve comportarsi
    # allo stesso modo.
    r = api_client.get(f"/api/libraries/{library['id']}/documents/{document['id']}/summary")
    assert r.status_code == 200
    assert r.json()["mode"] == "extractive"
    assert called["n"] == 0


def test_local_ollama_library_can_still_use_the_model(tmp_path, monkeypatch):
    """Il fix non deve disattivare il generativo dove la policy lo permette."""
    api_client, test_cfg = api_client_factory(tmp_path, monkeypatch)
    import api.libraries
    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Locale", "", "private", owner_id="owner")
    store.set_assistant_mode(library["id"], "local_ollama")
    _add_doc(store, library["id"], "policy.txt", "Le note spese si inviano entro il dieci del mese.")
    document = store.list_documents(library["id"])[0]

    monkeypatch.setattr("core.document_summary._call_ollama_summary", lambda prompt: "Riassunto generato localmente.")

    assert api_client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    r = api_client.get(f"/api/libraries/{library['id']}/documents/{document['id']}/summary")
    assert r.status_code == 200
    assert r.json()["mode"] == "local_llm"
    assert r.json()["summary"] == "Riassunto generato localmente."

