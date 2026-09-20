"""
tests/test_antivirus.py
Test suite per il modulo Antivirus / ClamAV Scanner e integrazione API.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api import app
from api.auth import session_store
import api.libraries
import config
from core.antivirus import (
    AntivirusScanError,
    scan_bytes_clamav,
    scan_document,
)
from core.governance import verify_audit_log_integrity


def test_antivirus_disabled_by_default(monkeypatch):
    test_cfg = config.cfg.replace(CLAMAV_ENABLED=False)
    monkeypatch.setattr("core.antivirus.cfg", test_cfg)

    res = scan_document(b"EICAR test payload", filename="malware.exe")
    assert res.is_clean is True
    assert "disattivato" in res.details.lower()


def test_antivirus_clean_file_mocked(monkeypatch):
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = [b"stream: OK\x00", b""]
    mock_sock.__enter__.return_value = mock_sock

    with patch("socket.create_connection", return_value=mock_sock):
        res = scan_bytes_clamav(b"Hello clean world")
        assert res.is_clean is True
        assert res.details == "Clean"


def test_antivirus_infected_file_mocked(monkeypatch):
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = [b"stream: Win.Test.EICAR_HDB-1 FOUND\x00", b""]
    mock_sock.__enter__.return_value = mock_sock

    with patch("socket.create_connection", return_value=mock_sock):
        res = scan_bytes_clamav(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*")
        assert res.is_clean is False
        assert res.virus_name == "Win.Test.EICAR_HDB-1"


def test_antivirus_unreachable_fail_open(monkeypatch):
    test_cfg = config.cfg.replace(CLAMAV_ENABLED=True, CLAMAV_FAIL_CLOSED=False)
    monkeypatch.setattr("core.antivirus.cfg", test_cfg)

    with patch("socket.create_connection", side_effect=ConnectionRefusedError("clamd offline")):
        res = scan_document(b"Sample payload", filename="doc.pdf")
        assert res.is_clean is True
        assert "fail-open" in res.details.lower()


def test_antivirus_unreachable_fail_closed(monkeypatch):
    test_cfg = config.cfg.replace(CLAMAV_ENABLED=True, CLAMAV_FAIL_CLOSED=True)
    monkeypatch.setattr("core.antivirus.cfg", test_cfg)

    with patch("socket.create_connection", side_effect=ConnectionRefusedError("clamd offline")):
        with pytest.raises(AntivirusScanError) as exc_info:
            scan_document(b"Sample payload", filename="doc.pdf")
        assert "fail-closed" in str(exc_info.value).lower()


def test_api_upload_blocked_by_antivirus(tmp_path: Path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir),
        ADMIN_USERNAME="owner",
        ADMIN_PASSWORD="StrongPassword!123",
        API_KEY="",
        CLAMAV_ENABLED=True,
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    monkeypatch.setattr("core.antivirus.cfg", test_cfg)

    session_store.clear()
    monkeypatch.setattr(api.libraries, "_store", None)
    client = TestClient(app)

    # Login
    assert client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    store = api.libraries.get_library_store()
    lib = store.create_library("Security Lab", "Antivirus test", "private", owner_id="owner")

    mock_sock = MagicMock()
    mock_sock.recv.side_effect = [b"stream: Eicar-Signature FOUND\x00", b""]
    mock_sock.__enter__.return_value = mock_sock

    with patch("socket.create_connection", return_value=mock_sock):
        resp = client.post(
            f"/api/libraries/{lib['id']}/documents",
            files={"file": ("virus_note.txt", b"Infected content line", "text/plain")},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "antivirus" in detail.lower()
        assert "Eicar-Signature" in detail

    # Verifica registrazione audit log
    audit_file = test_cfg.AUDIT_FILE
    total, valid = verify_audit_log_integrity(audit_file)
    assert total >= 1
    assert valid == total
    audit_text = Path(audit_file).read_text(encoding="utf-8")
    assert "security_malware_blocked" in audit_text
    assert "Eicar-Signature" in audit_text


def test_folder_importer_blocked_by_antivirus(tmp_path: Path, monkeypatch):
    from core.folder_importer import scan_import_source
    from core.library_store import LibraryStore

    db_path = tmp_path / "test.db"
    storage_dir = tmp_path / "storage"
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "clean.txt").write_text("Clean text", encoding="utf-8")
    (source_dir / "infected.txt").write_text("Infected payload", encoding="utf-8")

    store = LibraryStore(database_path=db_path)
    lib = store.create_library("Lib", "Desc", "private", owner_id="admin")
    source = store.add_import_source(lib["id"], str(source_dir))

    test_cfg = config.cfg.replace(CLAMAV_ENABLED=True)
    monkeypatch.setattr("core.antivirus.cfg", test_cfg)

    def _mock_scan(content: bytes, filename: str = "", actor: str = ""):
        from core.antivirus import ScanResult

        if "infected" in filename:
            return ScanResult(is_clean=False, virus_name="EICAR.Test", details="Blocked")
        return ScanResult(is_clean=True, details="Clean")

    monkeypatch.setattr("core.antivirus.scan_document", _mock_scan)

    res = scan_import_source(store, lib["id"], source, str(storage_dir))
    imported_names = [item["filename"] for item in res["imported"]]
    failed_names = [item["file"] for item in res["failed"]]

    assert "clean.txt" in imported_names
    assert "infected.txt" in failed_names
    assert any("malevolo" in item["error"].lower() or "eicar" in item["error"].lower() for item in res["failed"])


def test_connector_sync_blocked_by_antivirus(tmp_path: Path, monkeypatch):
    from api.libraries import get_library_store
    from core.connectors.base import RemoteDocument
    from core.library_store import LibraryStore

    db_path = tmp_path / "test.db"
    store = LibraryStore(database_path=db_path)
    lib = store.create_library("Lib", "Desc", "private", owner_id="admin")

    test_cfg = config.cfg.replace(
        BASE_DIR=str(tmp_path),
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="StrongPassword!123",
        API_KEY="",
        CLAMAV_ENABLED=True,
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.connectors.cfg", test_cfg)
    monkeypatch.setattr("core.antivirus.cfg", test_cfg)

    app.dependency_overrides[get_library_store] = lambda: store
    try:
        session_store.clear()
        client = TestClient(app)
        assert (
            client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassword!123"}).status_code == 200
        )

        docs = [
            RemoteDocument(
                id="1",
                name="infected.txt",
                content=b"malware bytes",
                media_type="text/plain",
                source_url="http://mock/infected.txt",
                last_modified="2026-09-19T00:00:00Z",
            )
        ]
        with patch("core.connectors.local_folder.LocalFolderConnector.fetch_documents", return_value=docs):

            def _mock_scan(content: bytes, filename: str = "", actor: str = ""):
                from core.antivirus import ScanResult

                return ScanResult(is_clean=False, virus_name="Trojan.Generic", details="Blocked")

            monkeypatch.setattr("core.antivirus.scan_document", _mock_scan)

            resp = client.post(
                "/api/connectors/sync",
                json={"type": "local_folder", "config": {"folder_path": str(tmp_path)}, "target_library_id": lib["id"]},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["imported_count"] == 0
            assert len(data["errors"]) == 1
            assert "malevolo" in data["errors"][0].lower()
    finally:
        app.dependency_overrides.pop(get_library_store, None)


