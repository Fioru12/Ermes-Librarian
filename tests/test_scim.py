"""tests/test_scim.py
Test suite per la directory sync SCIM 2.0 (RFC 7643 / RFC 7644) di Ermes Knowledge.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import app
from config import cfg
from core.governance import create_or_update_user, list_users


@pytest.fixture
def scim_client(monkeypatch):
    test_token = "scim-test-secret-token-12345"
    monkeypatch.setattr(cfg, "SCIM_ENABLED", True)
    monkeypatch.setattr(cfg, "SCIM_TOKEN", test_token)
    return TestClient(app), test_token


def test_scim_unauthorized(scim_client):
    client, _ = scim_client
    res = client.get("/scim/v2/ServiceProviderConfig")
    assert res.status_code == 401

    res = client.get("/scim/v2/ServiceProviderConfig", headers={"Authorization": "Bearer bad-token"})
    assert res.status_code == 401


def test_scim_service_provider_config(scim_client):
    client, token = scim_client
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/scim/v2/ServiceProviderConfig", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig" in data.get("schemas", [])
    assert data.get("patch", {}).get("supported") is True


def test_scim_schemas(scim_client):
    client, token = scim_client
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/scim/v2/Schemas", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data.get("totalResults") >= 1
    assert any(r.get("id") == "urn:ietf:params:scim:schemas:core:2.0:User" for r in data.get("Resources", []))


def test_scim_crud_lifecycle(scim_client, tmp_path, monkeypatch):
    client, token = scim_client
    headers = {"Authorization": f"Bearer {token}"}

    users_file = str(tmp_path / "test_users.json")
    audit_file = str(tmp_path / "test_audit.jsonl")
    monkeypatch.setattr(cfg, "USERS_FILE", users_file)
    monkeypatch.setattr(cfg, "AUDIT_FILE", audit_file)

    # Inizializza file utenti
    create_or_update_user(users_file, "admin_seed", "admin", "pwd123", active=True)

    # 1. POST /scim/v2/Users
    payload = {
        "userName": "jdoe_scim@enterprise.com",
        "name": {"formatted": "John Doe"},
        "roles": [{"value": "editor"}],
        "active": True,
    }
    create_res = client.post("/scim/v2/Users", json=payload, headers=headers)
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["userName"] == "jdoe_scim"
    assert created_data["active"] is True
    assert created_data["roles"][0]["value"] == "editor"

    # 2. GET /scim/v2/Users with filter
    filter_res = client.get('/scim/v2/Users?filter=userName eq "jdoe_scim"', headers=headers)
    assert filter_res.status_code == 200
    f_data = filter_res.json()
    assert f_data["totalResults"] == 1
    assert f_data["Resources"][0]["userName"] == "jdoe_scim"

    # 3. GET /scim/v2/Users/{id}
    get_res = client.get("/scim/v2/Users/jdoe_scim", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == "jdoe_scim"

    # 4. PATCH /scim/v2/Users/{id} - Disattivazione (Deprovisioning)
    patch_payload = {
        "Operations": [
            {"op": "replace", "path": "active", "value": False},
            {"op": "replace", "path": "roles", "value": [{"value": "viewer"}]},
        ]
    }
    patch_res = client.patch("/scim/v2/Users/jdoe_scim", json=patch_payload, headers=headers)
    assert patch_res.status_code == 200
    patched_data = patch_res.json()
    assert patched_data["active"] is False
    assert patched_data["roles"][0]["value"] == "viewer"

    # Verifica nel DB utenti
    users_now = list_users(users_file)
    target = next((u for u in users_now if u["username"] == "jdoe_scim"), None)
    assert target is not None
    assert target["active"] is False

    # 5. DELETE /scim/v2/Users/{id}
    del_res = client.delete("/scim/v2/Users/jdoe_scim", headers=headers)
    assert del_res.status_code == 204

    # Verifica che sia rimosso
    get_after_del = client.get("/scim/v2/Users/jdoe_scim", headers=headers)
    assert get_after_del.status_code == 404
