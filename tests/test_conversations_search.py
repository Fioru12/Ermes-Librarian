"""tests/test_conversations_search.py
Unit and integration tests for multi-conversation history persistence and full-text search.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import _verify_api_key
from api.conversations import router
from config import cfg
from core.conversation_store import ConversationStore


def test_conversation_search_by_title_and_content(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "conv.db"))
    store = ConversationStore()

    # Create two conversations
    c1 = store.create_conversation("alice", "lib1", "Progetto Bilancio Q3")
    store.add_message(c1["id"], "user", "Quali sono i ricavi stimati per Q3?")
    store.add_message(c1["id"], "assistant", "I ricavi ammontano a 1.2 milioni di euro.")

    c2 = store.create_conversation("alice", "lib1", "Architettura Cloud S3")
    store.add_message(c2["id"], "user", "Come configuriamo MinIO?")
    store.add_message(c2["id"], "assistant", "Usa la variabile S3_ENDPOINT_URL.")

    c3 = store.create_conversation("bob", "lib1", "Bilancio di Bob")
    store.add_message(c3["id"], "user", "Ricavi segreti di Bob")

    # 1. Search by title
    results_title = store.search_conversations("alice", "Bilancio")
    assert len(results_title) == 1
    assert results_title[0]["id"] == c1["id"]

    # 2. Search by message content
    results_content = store.search_conversations("alice", "MinIO")
    assert len(results_content) == 1
    assert results_content[0]["id"] == c2["id"]

    # 3. Isolation: Alice should not see Bob's conversation
    results_bob_from_alice = store.search_conversations("alice", "segreti")
    assert len(results_bob_from_alice) == 0


def test_api_conversations_search_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "conv_api.db"))
    test_store = ConversationStore()
    c = test_store.create_conversation("mario", "lib_corp", "Report Audit 2026")
    test_store.add_message(c["id"], "user", "Trova le vulnerabilità critiche.")

    monkeypatch.setattr("api.conversations.conversation_store", test_store)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "mario", "role": "admin"}

    client = TestClient(app)

    # Search match
    res = client.get("/api/conversations?q=vulnerabilit")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 1
    assert data["items"][0]["title"] == "Report Audit 2026"

    # Search no match
    res_empty = client.get("/api/conversations?q=inesistente_xyz")
    assert res_empty.status_code == 200
    assert res_empty.json()["count"] == 0
