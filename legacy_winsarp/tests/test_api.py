"""
test_api.py
Test per l'API REST FastAPI.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from config import cfg

# Helpers e mock di supporto
def mock_check_ollama(model_id):
    return True, "OK"

class MockConfig:
    HOST = "127.0.0.1"
    PORT = 8502
    DOCS_DIR = "C:\\Temp\\test_docs"
    CHROMA_DIR = "C:\\Temp\\test_chroma"
    HASH_FILE = "C:\\Temp\\test_hashes.json"
    LOGS_DIR = "C:\\Temp\\test_logs"
    BASE_DIR = os.path.abspath(".")
    DEFAULT_MODEL_ID = "qwen2.5:7b"
    EMBED_MODEL_ID = "bge-m3"
    OLLAMA_HOST = "http://127.0.0.1:11434"
    SCORE_THRESHOLD_LOW = 0.35
    SCORE_THRESHOLD_MED = 0.55
    LOG_RETENTION_DAYS = 30
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "test_password"
    ADMIN_MAX_UPLOAD_MB = 50
    API_KEY = "test_api_key_1234567890"

# Moduli che verranno patchati (e poi ripristinati)
_MODULES_TO_PATCH = ["config", "core.rag_engine", "core.rate_limiter"]

@pytest.fixture(scope="module")
def api_app():
    saved_modules = {mod: sys.modules.get(mod) for mod in _MODULES_TO_PATCH}
    mock_config_module = MagicMock()
    mock_config_module.cfg = MockConfig()
    sys.modules["config"] = mock_config_module

    # --- Patch: core.rag_engine ---
    mock_rag = MagicMock()
    mock_rag.check_ollama_uncached = mock_check_ollama
    mock_rag.check_ollama = mock_check_ollama
    mock_rag.init_llama_settings = MagicMock()
    mock_rag.get_index = MagicMock()
    mock_rag.build_chat_engine = MagicMock()
    mock_rag.get_source_nodes = MagicMock()
    mock_rag.score_to_confidence = MagicMock()
    sys.modules["core.rag_engine"] = mock_rag

    # --- Patch: core.rate_limiter ---
    mock_rate = MagicMock()
    mock_limiter_instance = MagicMock()
    mock_limiter_instance.check_request_rate.return_value = (True, "")
    mock_rate.get_rate_limiter = MagicMock(return_value=mock_limiter_instance)
    sys.modules["core.rate_limiter"] = mock_rate

    sys.modules.pop("api", None)
    import api as api_module
    app = api_module.app
    yield app

    # --- Ripristino ---
    for mod, original in saved_modules.items():
        if original is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = original
    sys.modules.pop("api", None)

@pytest.fixture
def client(api_app):
    return TestClient(api_app)

def test_health_check_without_auth(client):
    response = client.get("/health")
    assert response.status_code == 200

def test_health_check_with_invalid_auth_is_still_public(client):
    response = client.get("/health", headers={"Authorization": "Bearer invalid_key"})
    assert response.status_code == 200

def test_modules_list_with_auth(client):
    with patch("api._list_available_modules", return_value=["HR", "WinSarp"]):
        response = client.get("/modules", headers={"Authorization": "Bearer test_api_key_1234567890"})
        assert response.status_code == 200
        assert response.json() == {"modules": ["HR", "WinSarp"]}

def test_query_endpoint_with_auth(client):
    mock_chat_engine = MagicMock()
    mock_chat_engine.chat.return_value = MagicMock(response="Risposta di test")

    with patch("api.check_ollama_uncached", return_value=(True, "OK")), \
         patch("api._list_available_modules", return_value=["WinSarp"]), \
         patch("api.get_index", return_value=MagicMock()), \
         patch("api.build_chat_engine", return_value=mock_chat_engine), \
         patch("api.get_source_nodes", return_value=[{"source": "doc.pdf", "score": 0.91, "text": "chunk"}]), \
         patch("api.score_to_confidence", return_value="alta"):
        response = client.post(
            "/query",
            headers={"Authorization": "Bearer test_api_key_1234567890"},
            json={"query": "test query", "module": "WinSarp"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["module"] == "WinSarp"
    assert data["confidence_score"] == 0.91
    assert len(data["sources"]) == 1

def test_query_endpoint_without_auth(client):
    response = client.post("/query", json={"query": "test query", "module": "WinSarp"})
    assert response.status_code == 401

def test_query_endpoint_invalid_auth(client):
    response = client.post("/query", headers={"Authorization": "Bearer invalid_key"}, json={"query": "test query", "module": "WinSarp"})
    assert response.status_code == 401

def test_api_disabled_when_no_key(api_app):
    original_key = sys.modules["config"].cfg.API_KEY
    sys.modules["config"].cfg.API_KEY = ""
    client_no_key = TestClient(api_app)
    response = client_no_key.get("/modules", headers={"Authorization": "Bearer test_api_key_1234567890"})
    assert response.status_code == 503
    sys.modules["config"].cfg.API_KEY = original_key

def test_rate_limiting(client):
    with patch("api.rate_limiter") as mock_limiter, patch("api.check_ollama_uncached", return_value=(True, "OK")):
        mock_limiter.check_request_rate.return_value = (False, "Rate limit exceeded")
        response = client.post("/query", headers={"Authorization": "Bearer test_api_key_1234567890"}, json={"query": "test query", "module": "WinSarp"})
        assert response.status_code == 429

def test_query_rejects_invalid_module_name(client):
    with patch("api.check_ollama_uncached", return_value=(True, "OK")):
        response = client.post("/query", headers={"Authorization": "Bearer test_api_key_1234567890"}, json={"query": "test query", "module": "../segreti"})
        assert response.status_code == 400
