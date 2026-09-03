"""
tests/test_hyde.py
Test suite per il motore HyDE (Hypothetical Document Embeddings) e integrazione RAG.
"""
from unittest.mock import patch, MagicMock
from core.hyde import generate_hypothetical_document


def test_generate_hypothetical_document_disabled():
    result = generate_hypothetical_document("Come richiedere i permessi ROL?", mode="disabled")
    assert result == "Come richiedere i permessi ROL?"


def test_generate_hypothetical_document_empty():
    assert generate_hypothetical_document("") == ""
    assert generate_hypothetical_document("   ") == "   "


def test_generate_hypothetical_document_mock_ollama():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "I permessi ROL si richiedono inserendo il giustificativo nel portale presenze aziendale."}
    }
    mock_response.raise_for_status.return_value = None

    with patch("httpx.post", return_value=mock_response):
        res = generate_hypothetical_document("Come richiedere i permessi ROL?", mode="local_ollama")
        assert "permessi ROL" in res or "giustificativo" in res


def test_generate_hypothetical_document_fallback_on_error():
    with patch("httpx.post", side_effect=RuntimeError("Connection failed")):
        res = generate_hypothetical_document("Query di prova", mode="local_ollama")
        assert res == "Query di prova"
