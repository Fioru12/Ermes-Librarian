import os
import pytest
from unittest.mock import patch, PropertyMock
from fastapi.testclient import TestClient
import tempfile
from pathlib import Path


@pytest.fixture
def test_catalog_and_client():
    temp_dir = Path(tempfile.mkdtemp())
    test_catalog_path = temp_dir / "WinSarp_Formule_test.txt"

    with open(test_catalog_path, "w", encoding="utf-8") as f:
        f.write("## [130] | Straordinario Notturno | Subroutine | Standard\n\n**Tipo:** Subroutine\n**Scopo:** Calcola notturno\n\n```\n130=1\n```")

    with patch.object(type(__import__("config").cfg), "CATALOGO_PATH",
                      new_callable=PropertyMock, return_value=str(test_catalog_path)):
        import importlib
        import api
        importlib.reload(api)
        client = TestClient(api.app)
        yield client, test_catalog_path


def test_generate_formula_integration(test_catalog_and_client):
    client, _ = test_catalog_and_client
    payload = {
        "query": "Mostrami la formula per lo straordinario notturno",
        "module": "WinSarp",
        "model": "gpt-4o",
        "request_id": "test-123"
    }

    response = client.post("/api/formula/generate", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert "formula" in data, "La risposta deve contenere la formula"
    assert "source" in data, "La risposta deve contenere la sorgente (catalogo o LLM)"
    assert len(data["formula"]) > 0, "La formula non può essere vuota"


def test_generate_formula_invalid_query(test_catalog_and_client):
    client, _ = test_catalog_and_client
    payload = {
        "query": "",
        "module": "WinSarp",
        "model": "gpt-4o"
    }
    response = client.post("/api/formula/generate", json=payload)
    assert response.status_code in [200, 422]
