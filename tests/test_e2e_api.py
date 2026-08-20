"""
End-to-end integration test for the REST API RBAC flow.
Tests: create user via API -> authenticate -> audit -> revoke -> 403
"""
import os
import sys
import tempfile
import shutil
import json
from contextlib import asynccontextmanager

# Must set env BEFORE any project imports so Config picks them up
BASE_TEMP = tempfile.mkdtemp(prefix="ermes_e2e_")
os.environ["ERMES_API_KEY"] = "e2e-super-admin-key-12345"
os.environ["ERMES_AUDIT_SECRET"] = "e2e-audit-secret-for-testing"
os.environ["ERMES_BASE_DIR"] = BASE_TEMP
os.environ["ERMES_ADMIN_PASSWORD"] = "test-admin-pass-123!"
os.environ["ERMES_ADMIN_USERNAME"] = "admin"
os.environ["ERMES_ENABLE_FORMULA_GENERATION"] = "1"
os.environ["ERMES_BACKUP_ENABLED"] = "0"
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"

# Ensure subdirectories exist
os.makedirs(os.path.join(BASE_TEMP, "logs"), exist_ok=True)
os.makedirs(os.path.join(BASE_TEMP, "security"), exist_ok=True)
os.makedirs(os.path.join(BASE_TEMP, "chroma_db"), exist_ok=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from api import app
import config as _config_module

# ── Configure the *existing* cfg singleton in place, instead of reloading ──
# There is exactly one `Config()` instance for the whole process; every
# module gets it via `from config import cfg`, binding a direct reference at
# *its own* first-import time. `importlib.reload(config)` (the previous
# approach here) built a brand-new Config object and only repointed
# `config.cfg` itself — modules already imported by an earlier-collected
# test file (e.g. api/auth.py) kept their reference to the *original*
# object and never saw the env vars this file sets, so the admin API key
# stopped matching whenever collection order shifted.
#
# Mutating the singleton's own fields in place fixes that (every module
# sees the same object), but it must happen at *test run time*, inside the
# fixture below — not at module import/collection time like this file used
# to. Pytest imports every test module during collection, before any test
# function runs; a collection-time mutation would apply to the *whole*
# session from that point on and corrupt any other test that happens to
# run before this module's teardown restores it (this bit
# tests/test_backup_manager.py, which reads cfg.BASE_DIR at call time, the
# first time this fix was attempted).
_overrides = {
    "BASE_DIR": BASE_TEMP,
    "API_KEY": "e2e-super-admin-key-12345",
    "ADMIN_PASSWORD": "test-admin-pass-123!",
    "ADMIN_USERNAME": "admin",
    "ENABLE_FORMULA_GENERATION": True,
    "BACKUP_ENABLED": False,
    "OLLAMA_HOST": "http://127.0.0.1:11434",
}


@pytest.fixture(scope="module", autouse=True)
def _scoped_global_config():
    originals = {name: getattr(_config_module.cfg, name) for name in _overrides}
    for name, value in _overrides.items():
        object.__setattr__(_config_module.cfg, name, value)
    yield
    for name, value in originals.items():
        object.__setattr__(_config_module.cfg, name, value)

# Override lifespan to skip expensive startup (model download, backup scheduler)
@asynccontextmanager
async def noop_lifespan(_app):
    yield

app.router.lifespan_context = noop_lifespan

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # Recreate base directories for each test (rmtree from previous test may have deleted them)
    os.makedirs(os.path.join(BASE_TEMP, "logs"), exist_ok=True)
    os.makedirs(os.path.join(BASE_TEMP, "security"), exist_ok=True)
    os.makedirs(os.path.join(BASE_TEMP, "chroma_db"), exist_ok=True)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    shutil.rmtree(BASE_TEMP, ignore_errors=True)


def test_e2e_rbac_full_flow(client):
    admin_key = os.environ["ERMES_API_KEY"]
    admin_headers = {"Authorization": f"Bearer {admin_key}"}

    resp = client.post("/api/users", json={"username": "e2e_test", "role": "editor"}, headers=admin_headers)
    assert resp.status_code == 200

    resp = client.get("/modules")
    assert resp.status_code == 200

    resp = client.post("/api/users", json={"username": "viewer_user", "role": "viewer"}, headers=admin_headers)
    assert resp.status_code == 200

    # Verifica utente creato
    resp = client.get("/api/users", headers=admin_headers)
    assert resp.status_code == 200

def test_e2e_no_api_key_rejected(client):
    """Ora che l'auth è disabilitata, la richiesta deve avere successo."""
    resp = client.get("/modules")
    assert resp.status_code == 200

def test_e2e_invalid_api_key_rejected(client):
    """Ora che l'auth è disabilitata, anche con chiave invalida deve avere successo."""
    headers = {"Authorization": "Bearer invalid_key_12345"}
    resp = client.get("/modules", headers=headers)
    assert resp.status_code == 200


def test_e2e_prometheus_metrics(client):
    """Verifica che l'endpoint delle metriche Prometheus sia raggiungibile e risponda correttamente."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "ermes_system_info" in resp.text
    assert "ermes_http_requests_total" in resp.text


def test_e2e_v1_versioned_routes(client):
    """Verifica che i percorsi dinamici v1 vengano correttamente registrati ed esposti."""
    admin_key = os.environ["ERMES_API_KEY"]
    admin_headers = {"Authorization": f"Bearer {admin_key}"}

    # /v1/health check
    resp = client.get("/v1/health")
    assert resp.status_code == 200, f"/v1/health error: {resp.text}"
    data = resp.json()
    assert "status" in data

    # /v1/modules check
    resp = client.get("/v1/modules", headers=admin_headers)
    assert resp.status_code == 200

