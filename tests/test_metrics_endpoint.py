"""Copertura dell'endpoint /metrics: exposition Prometheus nativa e sicurezza.

Default-secure: senza ERMES_METRICS_TOKEN solo loopback/testclient; con token,
Bearer obbligatorio. Le metriche di business RAG sono incrementate dal flusso /ask.
"""
import pytest
from fastapi.testclient import TestClient

from api import app
from api.auth import _SESSIONS
from config import cfg


@pytest.fixture
def env(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = cfg.replace(BASE_DIR=str(app_dir), ADMIN_USERNAME="owner", ADMIN_PASSWORD="StrongPassword!123", API_KEY="")
    for target in ("config", "api", "api.auth", "api.libraries"):
        monkeypatch.setattr(f"{target}.cfg", test_cfg)
    _SESSIONS.clear()
    # Forza il re-set di system_info: in suite completa un altro test può aver
    # già inizializzato il gauge prometheus su un'istanza distinta (reload moduli);
    # senza questo il sample manca anche se HELP/TYPE sono presenti.
    from core import metrics
    metrics.init_system_info(
        version=getattr(test_cfg, "APP_VERSION", "test"),
        python_version="3.12",
        environment="test",
    )
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"})
        yield client, test_cfg


def test_metrics_exposes_prometheus_format(env):
    client, _ = env
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "ermes_http_requests_total" in body
    assert "# HELP" in body and "# TYPE" in body
    # istogramma con bucket, assente nella vecchia exposition in-memory
    assert "ermes_http_request_duration_seconds_bucket" in body
    assert "ermes_system_info{" in body  # inizializzata nel lifespan, non solo dichiarata


def test_metrics_requires_bearer_token_when_configured(env, monkeypatch):
    client, test_cfg = env
    secured = test_cfg.replace(METRICS_TOKEN="s3cret")
    for target in ("config", "api", "api.auth", "api.libraries"):
        monkeypatch.setattr(f"{target}.cfg", secured)

    denied = client.get("/metrics")
    assert denied.status_code == 401
    wrong = client.get("/metrics", headers={"Authorization": "Bearer sbagliato"})
    assert wrong.status_code == 401
    ok = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert "ermes_http_requests_total" in ok.text


def test_metrics_denied_from_remote_without_token():
    """Senza token, l'accesso è consentito solo al loopback: verifica diretta
    dell'endpoint con una Request che simula un client remoto."""
    from fastapi import HTTPException
    from api import prometheus_metrics
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/metrics", "headers": [],
             "client": ("10.1.2.3", 50000), "query_string": b""}
    request = Request(scope)
    with pytest.raises(HTTPException) as excinfo:
        prometheus_metrics(request)
    assert excinfo.value.status_code == 401


def test_rag_business_metrics_recorded_by_ask(env, monkeypatch):
    client, test_cfg = env
    monkeypatch.setattr("api.libraries._store", None)

    store = __import__("api.libraries", fromlist=["get_library_store"]).get_library_store()
    library = store.create_library("Metrics", "", "private", owner_id="owner")

    answer = client.post(f"/api/libraries/{library['id']}/ask", json={"question": "termine inesistente xyzzy"})
    assert answer.status_code == 200
    assert answer.json()["status"] == "abstained"

    after = client.get("/metrics").text
    assert "ermes_rag_questions_total" in after
    assert 'outcome="abstained"' in after
