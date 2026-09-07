"""
tests/test_local_folder_connector.py
Tests for LocalFolderConnector (NAS / local folder scanner).
"""
from __future__ import annotations

from pathlib import Path

from core.connectors.local_folder import LocalFolderConnector


def test_local_folder_connector_test_connection_nonexistent(tmp_path: Path):
    non_existent = tmp_path / "does_not_exist_12345"
    connector = LocalFolderConnector({"folder_path": str(non_existent)})
    ok, msg = connector.test_connection()
    assert not ok
    assert "non esiste" in msg


def test_local_folder_connector_test_connection_valid(tmp_path: Path):
    folder = tmp_path / "valid_folder"
    folder.mkdir()
    connector = LocalFolderConnector({"folder_path": str(folder)})
    ok, msg = connector.test_connection()
    assert ok
    assert "raggiungibile" in msg.lower()


def test_local_folder_connector_fetch_documents(tmp_path: Path):
    folder = tmp_path / "docs"
    folder.mkdir()

    doc1 = folder / "policy.txt"
    doc1.write_text("Questa è la policy aziendale.", encoding="utf-8")

    subfolder = folder / "sub"
    subfolder.mkdir()
    doc2 = subfolder / "procedura.md"
    doc2.write_text("# Procedura IT\nSeguire i passi 1, 2, 3.", encoding="utf-8")

    ignored = folder / "script.py"
    ignored.write_text("print('hello')", encoding="utf-8")

    connector = LocalFolderConnector({
        "folder_path": str(folder),
        "recursive": True,
        "max_files": 100,
    })

    docs = connector.fetch_documents()
    assert len(docs) == 2
    names = {d.name for d in docs}
    assert "policy.txt" in names
    assert "procedura.md" in names
    assert "script.py" not in names
