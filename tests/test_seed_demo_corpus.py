"""tests/test_seed_demo_corpus.py
Test suite per lo script CLI di seeding del demo corpus.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scripts.seed_demo_corpus import (
    authenticate,
    find_or_create_library,
    require_ok,
    seed_library,
)


def test_require_ok_success():
    res = MagicMock()
    res.is_success = True
    res.json.return_value = {"status": "ok"}
    data = require_ok(res, "Error")
    assert data == {"status": "ok"}


def test_require_ok_failure():
    res = MagicMock()
    res.is_success = False
    res.status_code = 500
    res.text = "Internal Server Error"
    with pytest.raises(RuntimeError) as exc:
        require_ok(res, "Operation failed")
    assert "HTTP 500" in str(exc.value)


def test_authenticate_with_password():
    client = MagicMock()
    login_res = MagicMock()
    login_res.is_success = True
    login_res.json.return_value = {"role": "admin"}
    client.post.return_value = login_res

    authenticate(client, username="admin", password="password123", api_key="")
    client.post.assert_called_once_with(
        "/api/auth/login", json={"username": "admin", "password": "password123"}
    )


def test_authenticate_with_api_key():
    client = MagicMock()
    client.headers = {}

    authenticate(client, username="admin", password="", api_key="secret-key")
    assert client.headers["Authorization"] == "Bearer secret-key"


def test_find_or_create_library_existing():
    client = MagicMock()
    get_res = MagicMock()
    get_res.is_success = True
    get_res.json.return_value = {
        "items": [
            {"id": "lib-1", "name": "Existing Lib", "description": "Desc"}
        ]
    }
    client.get.return_value = get_res

    lib = find_or_create_library(client, "Existing Lib", "Desc")
    assert lib["id"] == "lib-1"
    client.post.assert_not_called()


def test_find_or_create_library_new():
    client = MagicMock()
    get_res = MagicMock()
    get_res.is_success = True
    get_res.json.return_value = {"items": []}
    client.get.return_value = get_res

    post_res = MagicMock()
    post_res.is_success = True
    post_res.json.return_value = {"id": "lib-new", "name": "New Lib"}
    client.post.return_value = post_res

    lib = find_or_create_library(client, "New Lib", "Desc")
    assert lib["id"] == "lib-new"
    client.post.assert_called_once_with(
        "/api/libraries",
        json={"name": "New Lib", "description": "Desc", "visibility": "private"},
    )


def test_seed_library(tmp_path: Path):
    doc1 = tmp_path / "doc1.md"
    doc1.write_text("# Doc 1\nContenuto", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("# Readme", encoding="utf-8")

    client = MagicMock()
    # Mock find_or_create_library
    get_libs = MagicMock()
    get_libs.is_success = True
    get_libs.json.return_value = {"items": [{"id": "lib-1", "name": "Test Lib"}]}

    # Mock list documents (empty initially)
    get_docs = MagicMock()
    get_docs.is_success = True
    get_docs.json.return_value = {"items": []}

    # Mock upload document
    post_doc = MagicMock()
    post_doc.is_success = True
    post_doc.json.return_value = {"id": "doc-1", "status": "queued"}

    # Mock ingestion jobs (ready)
    get_jobs = MagicMock()
    get_jobs.is_success = True
    get_jobs.json.return_value = {
        "items": [{"filename": "doc1.md", "status": "ready"}]
    }

    client.get.side_effect = [get_libs, get_docs, get_jobs]
    client.post.return_value = post_doc

    lib_id, count = seed_library(client, "Test Lib", "Desc", tmp_path)
    assert lib_id == "lib-1"
    assert count == 1  # only doc1.md, README.md ignored
    client.post.assert_called_once()
