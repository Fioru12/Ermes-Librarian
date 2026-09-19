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
