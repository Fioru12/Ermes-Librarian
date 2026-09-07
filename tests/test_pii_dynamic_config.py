"""
tests/test_pii_dynamic_config.py
Test suite per la configurazione dinamica PII/DLP, regole custom regex ed endpoint API REST.
"""
from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api import app
import api.libraries
from api.auth import _SESSIONS
from config import cfg
from core.pii_filter import filter_pii, update_pii_config


@pytest.fixture
def pii_client(tmp_path: Path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = cfg.replace(
        BASE_DIR=str(app_dir),
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="StrongPassword!123",
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    monkeypatch.setattr("api.pii.cfg", test_cfg)

    _SESSIONS.clear()
    monkeypatch.setattr(api.libraries, "_store", None)

    client = TestClient(app)
    client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassword!123"})
    return client


def test_pii_filter_custom_regex_and_toggles(tmp_path: Path, monkeypatch):
    test_cfg = cfg.replace(BASE_DIR=str(tmp_path))
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("core.pii_filter._cached_config", None)

    # Configura disattivazione email e aggiunta custom regex per badge "EMP-XXXXXX"
    config_data = {
        "enabled_patterns": {
            "email": False,
            "codice_fiscale": True,
        },
        "custom_rules": [
            {
                "id": "rule_badge",
                "name": "Badge Dipendente",
                "pattern": r"\bEMP-\d{6}\b",
                "replacement": "[BADGE]",
                "enabled": True,
            }
        ]
    }
    update_pii_config(config_data)

    input_text = "Il dipendente EMP-123456 con CF RSSMRA80A01H501U e mail mario@test.com"
    masked = filter_pii(input_text, enabled=True)

    assert "[BADGE]" in masked
    assert "[CODICE_FISCALE]" in masked
    assert "mario@test.com" in masked  # Email non mascherata perche' disabilitata


def test_pii_api_endpoints(pii_client: TestClient):
    # GET config
    resp = pii_client.get("/api/pii/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled_patterns" in data
    assert "standard_patterns_meta" in data

    # POST config
    update_res = pii_client.post("/api/pii/config", json={
        "enabled_patterns": {"email": True, "iban": True},
        "custom_rules": [
            {
                "name": "ID Ordine",
                "pattern": r"\bORD-\d{4}\b",
                "replacement": "[ID_ORDINE]",
                "enabled": True
            }
        ]
    })
    assert update_res.status_code == 200
    assert update_res.json()["ok"] is True

    # POST test
    test_res = pii_client.post("/api/pii/test", json={
        "text": "Ordine ORD-9999 effettuato da mario@test.it"
    })
    assert test_res.status_code == 200
    res_data = test_res.json()
    assert "[ID_ORDINE]" in res_data["masked"]
    assert "[EMAIL]" in res_data["masked"]
    assert res_data["detected_count"] >= 2
