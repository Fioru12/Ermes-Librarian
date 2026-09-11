"""
tests/test_library_streaming.py
Tests for SSE streaming endpoint POST /api/libraries/{library_id}/ask/stream
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
def streaming_client(tmp_path: Path, monkeypatch):
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

    session_store.clear()
    monkeypatch.setattr(api.libraries, "_store", None)

    client = TestClient(app)
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassword!123"})
    assert login_res.status_code == 200

    yield client
    session_store.clear()


def test_streaming_endpoint_returns_sse_events(streaming_client: TestClient):
    # 1. Crea una biblioteca
    create_res = streaming_client.post(
        "/api/libraries",
        json={"name": "Biblioteca Streaming", "description": "Test SSE", "visibility": "private"},
    )
    assert create_res.status_code == 201
    lib_id = create_res.json()["id"]

    # 2. Chiama l'endpoint di streaming
    res = streaming_client.post(
        f"/api/libraries/{lib_id}/ask/stream",
        json={"question": "Quali sono le regole per il lavoro agile?", "top_k": 3},
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")

    # 3. Analizza gli eventi SSE
    body = res.text
    assert "event: status" in body
    assert "retrieving" in body
    assert "event: done" in body
    assert "abstained" in body or "answered" in body


def test_streaming_endpoint_respects_acl(streaming_client: TestClient, monkeypatch):
    # Biblioteca inesistente -> 404
    res_not_found = streaming_client.post(
        "/api/libraries/non_existent_id/ask/stream",
        json={"question": "Domanda di test?"},
    )
    assert res_not_found.status_code == 404

    # Utente anonimo -> 401
    anon_client = TestClient(app)
    res_anon = anon_client.post(
        "/api/libraries/qualunque/ask/stream",
        json={"question": "Domanda non autorizzata?"},
    )
    assert res_anon.status_code in {401, 403}


def test_streaming_endpoint_with_citations_and_answer(streaming_client: TestClient, monkeypatch):
    create_res = streaming_client.post(
        "/api/libraries",
        json={"name": "Biblioteca Con Dati", "visibility": "private"},
    )
    assert create_res.status_code == 201
    lib_id = create_res.json()["id"]

    mock_citations = [
        {
            "citation": {"filename": "manuale.md", "locator": "Sezione 1"},
            "excerpt": "Il lavoro agile e consentito per due giorni a settimana.",
            "relevance_score": 0.95,
        }
    ]

    store = api.libraries.get_library_store()
    monkeypatch.setattr(
        store,
        "search_with_profile",
        lambda *args, **kwargs: (mock_citations, {"mode": "keyword"}),
    )

    res = streaming_client.post(
        f"/api/libraries/{lib_id}/ask/stream",
        json={"question": "Quanti giorni di lavoro agile?", "top_k": 3},
    )
    assert res.status_code == 200
    body = res.text
    assert "event: status" in body
    assert "event: citations" in body
    assert "manuale.md" in body
    assert "event: answer" in body
    assert "event: done" in body
    assert "supported" in body

