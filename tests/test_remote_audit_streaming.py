"""
tests/test_remote_audit_streaming.py
Unit tests for SIEM / Remote Audit Log Streaming (HTTP Webhook & Syslog RFC 5424).
"""

from __future__ import annotations

from pathlib import Path

from config import cfg
from core.governance import (
    _send_http_audit,
    _send_syslog_audit,
    append_audit,
    flush_remote_audit,
    verify_audit_log_integrity,
)


def test_append_audit_local_only(tmp_path: Path, monkeypatch):
    """Verifica che append_audit funzioni localmente senza configurazione SIEM."""
    test_cfg = cfg.replace(
        AUDIT_REMOTE_URL="",
        AUDIT_SYSLOG_HOST="",
    )
    monkeypatch.setattr("config.cfg", test_cfg)

    audit_file = str(tmp_path / "audit.jsonl")
    append_audit(audit_file, "user.login", "admin", {"ip": "127.0.0.1"})
    flush_remote_audit()

    total, valid = verify_audit_log_integrity(audit_file)
    assert total == 1
    assert valid == 1


def test_remote_audit_http_webhook(monkeypatch):
    """Verifica la trasmissione di voci audit a un endpoint HTTP SIEM."""
    captured_requests = []

    class MockResponse:
        status_code = 200
        def raise_for_status(self):
            pass

    class MockHttpxClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None, headers=None):
            captured_requests.append({"url": url, "json": json, "headers": headers})
            return MockResponse()

    monkeypatch.setattr("httpx.Client", MockHttpxClient)

    entry = {
        "ts": "2026-09-19T12:00:00",
        "action": "document.delete",
        "actor": "sec_officer",
        "detail": {"doc_id": "doc-123"},
        "signature": "hmac123",
    }
    _send_http_audit(entry, "https://siem.enterprise.local/api/v1/events", "BearerTokenSecret")

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["url"] == "https://siem.enterprise.local/api/v1/events"
    assert req["headers"]["Authorization"] == "Bearer BearerTokenSecret"
    assert req["json"]["action"] == "document.delete"
    assert req["json"]["actor"] == "sec_officer"


def test_remote_audit_syslog_rfc5424(monkeypatch):
    """Verifica l'invio Syslog formato RFC 5424 via socket UDP."""
    received_packets = []

    # Mock del socket UDP
    class MockSocket:
        def __init__(self, family, type):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def settimeout(self, t):
            pass
        def sendto(self, data, address):
            received_packets.append({"data": data, "address": address})

    monkeypatch.setattr("socket.socket", MockSocket)

    entry = {
        "ts": "2026-09-19T12:00:00",
        "action": "auth.failed",
        "actor": "intruder",
        "detail": {"reason": "bad_password"},
        "signature": "sig999",
    }

    _send_syslog_audit(entry, "syslog.corp.net", 514, "local0")

    assert len(received_packets) == 1
    packet = received_packets[0]
    assert packet["address"] == ("syslog.corp.net", 514)
    msg_str = packet["data"].decode("utf-8")
    assert "<134>1 2026-09-19T12:00:00" in msg_str
    assert "ermes-knowledge" in msg_str
    assert "auth.failed" in msg_str
    assert "intruder" in msg_str
