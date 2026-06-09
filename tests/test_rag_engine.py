"""
test_rag_engine.py
Test per il modulo core/rag_engine.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from unittest.mock import MagicMock, patch

from core.rag_engine import fetch_ollama_models
from config import cfg


class TestFetchOllamaModels:
    """Test per il recupero modelli Ollama."""

    def test_returns_sorted_list(self):
        """Ritorna lista ordinata di modelli non-embedding."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "models": [
                {"name": "qwen2.5:7b"},
                {"name": "qwen2.5-coder:7b"},
                {"name": cfg.EMBED_MODEL_ID},
            ]
        }).encode()
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            models = fetch_ollama_models()

        assert "qwen2.5:7b" in models
        assert "qwen2.5-coder:7b" in models
        assert cfg.EMBED_MODEL_ID not in models
        assert models == sorted(models)

    def test_empty_when_not_available(self):
        """Ritorna lista vuota se Ollama non raggiungibile."""
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            models = fetch_ollama_models()
        assert models == []

    def test_empty_when_no_models(self):
        """Ritorna lista vuota se nessun modello."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"models": []}).encode()
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            models = fetch_ollama_models()
        assert models == []
