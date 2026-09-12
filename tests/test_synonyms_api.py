"""
tests/test_synonyms_api.py
Unit and integration tests for api/synonyms.py (Glossario Aziendale Dinamico REST API).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

from api import app
from api.synonyms import (
    SynonymPayload,
    get_synonyms,
    remove_synonym,
    set_synonym,
)
from config import cfg
from core.query_expander import load_custom_synonyms


def test_synonyms_api_direct_functions(tmp_path: Path, monkeypatch):
    syn_file = tmp_path / "config" / "synonyms.json"
    syn_file.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)

    test_cfg = cfg.replace(BASE_DIR=str(tmp_path))
    monkeypatch.setattr("api.synonyms.cfg", test_cfg)
    monkeypatch.setenv("ERMES_SYNONYMS_FILE", str(syn_file))

    viewer_actor = {"username": "viewer1", "role": "viewer"}
    editor_actor = {"username": "editor1", "role": "editor"}

    # 1. Inizialmente custom è vuoto, all contiene i default
    res = asyncio.run(get_synonyms(_auth=viewer_actor))
    assert res["custom"] == {}
    assert "tfr" in res["all"]
    assert res["count_custom"] == 0

    # 2. Crea un nuovo termine (editor)
    payload = SynonymPayload(term="ddt", synonyms=["documento di trasporto", "bolla"])
    res_set = asyncio.run(set_synonym(payload=payload, user=editor_actor))
    assert res_set["success"] is True
    assert res_set["term"] == "ddt"
    assert "documento di trasporto" in res_set["synonyms"]

    # 3. Verifica persistenza su file
    on_disk = load_custom_synonyms(syn_file)
    assert "ddt" in on_disk

    # 4. Rileggi tramite get_synonyms
    res2 = asyncio.run(get_synonyms(_auth=viewer_actor))
    assert "ddt" in res2["custom"]
    assert "ddt" in res2["all"]
    assert res2["count_custom"] == 1

    # 5. Rimuovi termine
    res_del = asyncio.run(remove_synonym(term="ddt", user=editor_actor))
    assert res_del["success"] is True
    assert res_del["term"] == "ddt"

    # 6. Rimuovi termine inesistente -> 404
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(remove_synonym(term="ddt", user=editor_actor))
    assert exc_info.value.status_code == 404

    # 7. Validazione: termine con soli sinonimi identici al termine -> 400
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            set_synonym(
                payload=SynonymPayload(term="test", synonyms=["test", "  "]),
                user=editor_actor,
            )
        )
    assert exc_info.value.status_code == 400


def test_synonyms_api_via_testclient(tmp_path: Path, monkeypatch):
    syn_file = tmp_path / "config" / "synonyms.json"
    syn_file.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)

    test_cfg = cfg.replace(BASE_DIR=str(tmp_path), API_KEY="test-admin-key-123")
    monkeypatch.setattr("api.synonyms.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setenv("ERMES_SYNONYMS_FILE", str(syn_file))

    client = TestClient(app)

    # Senza auth -> 401
    resp = client.get("/api/synonyms")
    assert resp.status_code == 401

    headers = {"Authorization": "Bearer test-admin-key-123"}

    # Con auth admin -> 200
    resp = client.get("/api/synonyms", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "custom" in data
    assert "all" in data

    # POST crea sinonimo
    resp_post = client.post(
        "/api/synonyms",
        headers=headers,
        json={"term": "cig", "synonyms": ["codice identificativo gara", "codice appalto"]},
    )
    assert resp_post.status_code == 200
    assert resp_post.json()["term"] == "cig"

    # GET lo trova
    resp_get = client.get("/api/synonyms", headers=headers)
    assert resp_get.status_code == 200
    assert "cig" in resp_get.json()["custom"]

    # DELETE lo rimuove
    resp_del = client.delete("/api/synonyms/cig", headers=headers)
    assert resp_del.status_code == 200
    assert resp_del.json()["success"] is True

    # DELETE secondo tentativo -> 404
    resp_del404 = client.delete("/api/synonyms/cig", headers=headers)
    assert resp_del404.status_code == 404
