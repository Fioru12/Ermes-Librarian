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
        "message": {
            "content": "I permessi ROL si richiedono inserendo il giustificativo nel portale presenze aziendale."
        }
    }
    mock_response.raise_for_status.return_value = None

    with patch("httpx.post", return_value=mock_response):
        res = generate_hypothetical_document("Come richiedere i permessi ROL?", mode="local_ollama")
        assert "permessi ROL" in res or "giustificativo" in res


def test_generate_hypothetical_document_fallback_on_error():
    with patch("httpx.post", side_effect=RuntimeError("Connection failed")):
        res = generate_hypothetical_document("Query di prova", mode="local_ollama")
        assert res == "Query di prova"


def test_generate_hypothetical_document_approved_openrouter(monkeypatch):
    import config

    test_cfg = config.cfg.replace(
        LIBRARY_CLOUD_CONSENT=True,
        OPENROUTER_API_KEY="sk-or-v1-test",
        OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
        DEFAULT_MODEL_ID="qwen3.5:9b",
        OPENROUTER_MODEL="mistralai/mistral-small",
    )
    monkeypatch.setattr("core.hyde.cfg", test_cfg)
    monkeypatch.setattr("core.evidence_assistant.cfg", test_cfg)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Questo è il documento ipotetico generato tramite OpenRouter."
                }
            }
        ]
    }
    mock_response.raise_for_status.return_value = None

    with patch("httpx.post", return_value=mock_response) as mock_post:
        res = generate_hypothetical_document("Procedura ferie e permessi", mode="approved_openrouter")
        assert "ipotetico generato tramite OpenRouter" in res
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["model"] == "mistralai/mistral-small"
        assert "Bearer sk-or-v1-test" in call_kwargs["headers"]["Authorization"]

