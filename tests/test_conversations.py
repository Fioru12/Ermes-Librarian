"""Test per il modulo conversazioni (core/conversation_store.py e api/conversations.py)."""

import pytest
from fastapi.testclient import TestClient

import api.auth
import config
from api import app
from core.conversation_store import conversation_store

PASSWORD = "StrongPassword!123"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir),
        DATABASE_URL="",
        ADMIN_USERNAME="capo",
        ADMIN_PASSWORD=PASSWORD,
        API_KEY="",
    )
    monkeypatch.setattr(config, "cfg", test_cfg)
    monkeypatch.setattr(api.auth, "cfg", test_cfg)

    # Inizializza admin
    from core.governance import ensure_default_admin

    ensure_default_admin(test_cfg.USERS_FILE, "capo", PASSWORD)
    conversation_store.clear()
    yield app_dir
    conversation_store.clear()


def test_conversation_store_crud(istanza):
    # Creazione
    conv = conversation_store.create_conversation("user1", "lib1", "Titolo Test")
    cid = conv["id"]
    assert cid
    assert conv["title"] == "Titolo Test"

    # Aggiunta messaggi
    msg1 = conversation_store.add_message(cid, "user", "Ciao!")
    assert msg1["role"] == "user"
    assert msg1["content"] == "Ciao!"

    citations = [{"document_id": "doc1", "filename": "test.txt", "excerpt": "estratto"}]
    msg2 = conversation_store.add_message(cid, "assistant", "Risposta", citations=citations)
    assert msg2["role"] == "assistant"
    assert len(msg2["citations"]) == 1

    # Get conversazione
    fetched = conversation_store.get_conversation(cid, username="user1")
    assert fetched is not None
    assert len(fetched["messages"]) == 2
    assert fetched["messages"][1]["citations"][0]["filename"] == "test.txt"

    # Isolamento utente
    assert conversation_store.get_conversation(cid, username="user2") is None

    # Aggiorna titolo
    assert conversation_store.update_title(cid, "Nuovo Titolo", username="user1") is True
    assert conversation_store.get_conversation(cid)["title"] == "Nuovo Titolo"

    # Cancellazione
    assert conversation_store.delete_conversation(cid, username="user1") is True
    assert conversation_store.get_conversation(cid) is None


def test_api_conversations_flow(istanza):
    client = TestClient(app)

    # Login come admin
    res = client.post("/api/auth/login", json={"username": "capo", "password": PASSWORD})
    assert res.status_code == 200

    # Lista iniziale vuota
    res = client.get("/api/conversations?library_id=lib_hr")
    assert res.status_code == 200
    assert res.json()["count"] == 0

    # Crea conversazione
    res = client.post("/api/conversations", json={"library_id": "lib_hr", "title": "Domanda Ferie"})
    assert res.status_code == 200
    data = res.json()
    cid = data["id"]
    assert data["title"] == "Domanda Ferie"

    # Aggiungi messaggio
    res = client.post(
        f"/api/conversations/{cid}/messages",
        json={"role": "user", "content": "Come chiedo le ferie?", "citations": []},
    )
    assert res.status_code == 200

    # Recupera conversazione con messaggi
    res = client.get(f"/api/conversations/{cid}")
    assert res.status_code == 200
    conv_data = res.json()
    assert len(conv_data["messages"]) == 1
    assert conv_data["messages"][0]["content"] == "Come chiedo le ferie?"

    # Aggiorna titolo
    res = client.patch(f"/api/conversations/{cid}", json={"title": "Ferie 2026"})
    assert res.status_code == 200

    # Elimina conversazione
    res = client.delete(f"/api/conversations/{cid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Verifica rimozione
    res = client.get(f"/api/conversations/{cid}")
    assert res.status_code == 404


def test_ask_endpoint_persists_conversation(istanza):
    client = TestClient(app)
    # Login
    res = client.post("/api/auth/login", json={"username": "capo", "password": PASSWORD})
    assert res.status_code == 200

    # Crea biblioteca
    res = client.post("/api/libraries", json={"name": "HR Test", "description": "desc"})
    assert res.status_code == 201
    lib_id = res.json()["id"]

    # Ask con conversation_id
    cid = "conv-auto-123"
    res = client.post(
        f"/api/libraries/{lib_id}/ask",
        json={"question": "Qual e' la procedura di onboarding?", "conversation_id": cid},
    )
    assert res.status_code == 200

    # Verifica che la conversazione esista e contenga 2 messaggi (user + assistant)
    res = client.get(f"/api/conversations/{cid}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == cid
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Qual e' la procedura di onboarding?"
    assert data["messages"][1]["role"] == "assistant"


def test_message_feedback(istanza):
    client = TestClient(app)
    res = client.post("/api/auth/login", json={"username": "capo", "password": PASSWORD})
    assert res.status_code == 200

    # Crea conversazione
    res = client.post("/api/conversations", json={"library_id": "lib_hr", "title": "Test Feedback"})
    cid = res.json()["id"]

    # Aggiungi messaggio assistant
    msg = client.post(
        f"/api/conversations/{cid}/messages",
        json={"role": "assistant", "content": "Risposta generata", "citations": []},
    ).json()
    mid = msg["id"]

    # Invia feedback positivo
    fb_res = client.post(
        f"/api/conversations/{cid}/messages/{mid}/feedback",
        json={"rating": "positive", "comment": "Molto chiaro!"},
    )
    assert fb_res.status_code == 200
    assert fb_res.json()["ok"] is True

    # Verifica persistenza feedback nel messaggio
    conv = client.get(f"/api/conversations/{cid}").json()
    assert conv["messages"][0]["feedback"]["rating"] == "positive"
    assert conv["messages"][0]["feedback"]["comment"] == "Molto chiaro!"


