"""Unit and integration tests for Cryptographic Audit Chain & SOC2/ISO27001 Compliance Verifier."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api import app
from api.audit import _rotate_audit_logs
from core.audit_chain import AuditChainManager, GENESIS_HASH, compute_entry_hash, compute_signature


@pytest.fixture
def audit_env(tmp_path, monkeypatch):
    audit_file = tmp_path / "test_audit.jsonl"
    monkeypatch.setattr("config.cfg.AUDIT_FILE", str(audit_file))
    monkeypatch.setattr("config.cfg.API_KEY", "test-audit-admin-key")
    monkeypatch.setattr("config.cfg.AUDIT_SECRET", "test-audit-hmac-secret-2026")

    return {
        "audit_file": str(audit_file),
        "headers": {"Authorization": "Bearer test-audit-admin-key"},
    }


def test_audit_chain_sequential_append_and_verification(audit_env):
    audit_file = audit_env["audit_file"]

    # 1. Append 3 records
    r1 = AuditChainManager.append_record(audit_file, "user_login", "alice", {"ip": "10.0.0.1"})
    assert r1["seq_id"] == 1
    assert r1["prev_hash"] == GENESIS_HASH
    assert r1["entry_hash"] is not None
    assert r1["signature"] is not None

    r2 = AuditChainManager.append_record(audit_file, "document_uploaded", "alice", {"doc": "manual.pdf"})
    assert r2["seq_id"] == 2
    assert r2["prev_hash"] == r1["entry_hash"]

    r3 = AuditChainManager.append_record(audit_file, "retention_policy_updated", "bob", {"days": 90})
    assert r3["seq_id"] == 3
    assert r3["prev_hash"] == r2["entry_hash"]

    # 2. Verify complete chain
    verification = AuditChainManager.verify_chain(audit_file)
    assert verification["valid"] is True
    assert verification["total_entries"] == 3
    assert verification["verified_entries"] == 3
    assert verification["corrupted_count"] == 0
    assert verification["head_hash"] == r3["entry_hash"]
    assert verification["integrity_status"] == "verified_authentic"


def test_audit_chain_detects_payload_tampering(audit_env):
    audit_file = audit_env["audit_file"]

    AuditChainManager.append_record(audit_file, "role_changed", "admin", {"user": "charlie", "role": "editor"})
    AuditChainManager.append_record(audit_file, "document_deleted", "admin", {"doc": "confidential.pdf"})

    # Tamper with the first entry's detail payload without updating hashes/signature
    with open(audit_file, encoding="utf-8") as f:
        lines = f.readlines()

    entry0 = json.loads(lines[0])
    entry0["detail"]["role"] = "admin"  # Malicious escalation
    lines[0] = json.dumps(entry0) + "\n"

    with open(audit_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Verification must flag the tampering
    verification = AuditChainManager.verify_chain(audit_file)
    assert verification["valid"] is False
    assert verification["corrupted_count"] >= 1
    assert verification["integrity_status"] == "compromised"
    assert any("payload_tampered" in t.get("reason", "") or "signature_invalid" in t.get("reason", "") for t in verification["tampered_entries"])


def test_audit_chain_detects_middle_entry_deletion(audit_env):
    audit_file = audit_env["audit_file"]

    AuditChainManager.append_record(audit_file, "event_1", "system", {"seq": 1})
    AuditChainManager.append_record(audit_file, "event_2_sensitive", "system", {"seq": 2})
    AuditChainManager.append_record(audit_file, "event_3", "system", {"seq": 3})

    # Delete the middle entry
    with open(audit_file, encoding="utf-8") as f:
        lines = f.readlines()

    del lines[1]  # Delete event_2_sensitive

    with open(audit_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Verification must detect the broken hash link
    verification = AuditChainManager.verify_chain(audit_file)
    assert verification["valid"] is False
    assert verification["corrupted_count"] >= 1
    assert any("chain_broken" in t.get("reason", "") for t in verification["tampered_entries"])


def test_compliance_report_generation(audit_env):
    audit_file = audit_env["audit_file"]

    AuditChainManager.append_record(audit_file, "scim_user_created", "okta-scim", {"user": "david"})
    AuditChainManager.append_record(audit_file, "legal_hold_modified", "compliance_officer", {"doc": "doc_999", "hold": True})
    AuditChainManager.append_record(audit_file, "document_retention_purged", "retention_engine", {"doc": "expired.pdf"})

    report = AuditChainManager.generate_compliance_report(
        audit_file=audit_file,
        organization="FinTech Corp Enterprise",
        auditor_id="soc2_lead_auditor",
    )

    assert report["report_id"].startswith("SOC2-REPORT-")
    assert report["organization"] == "FinTech Corp Enterprise"
    assert report["chain_verification"]["valid"] is True
    assert report["compliance_attestation"]["overall_status"] == "COMPLIANT"
    assert report["metrics"]["total_events_recorded"] == 3
    assert report["metrics"]["high_priority_governance_events_count"] == 3


def _append_with_ts(audit_file, action, actor, detail, ts, prev_hash, seq_id):
    """Costruisce a mano una voce con un timestamp arbitrario (per simulare voci vecchie
    senza dover falsificare l'orologio di sistema)."""
    entry_hash = compute_entry_hash(seq_id, prev_hash, ts, action, actor, detail)
    record = {
        "seq_id": seq_id,
        "ts": ts,
        "action": action,
        "actor": actor,
        "detail": detail,
        "prev_hash": prev_hash,
        "entry_hash": entry_hash,
        "signature": compute_signature(entry_hash),
    }
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def test_rotation_does_not_crash_on_utc_aware_timestamps(audit_env):
    """`ts` e' ora UTC-aware (`datetime.now(UTC)`); il cutoff di rotazione fino al 22
    settembre 2026 era naive, e confrontarli sollevava TypeError a ogni rotazione."""
    audit_file = audit_env["audit_file"]
    AuditChainManager.append_record(audit_file, "user_login", "alice", {})

    archived = _rotate_audit_logs(audit_file, retention_days=90)

    assert archived == 0


def test_rotation_preserves_chain_continuity_into_the_archive(audit_env):
    """Archiviare le voci vecchie non deve rompere la catena di quelle rimaste: fino al
    22 settembre 2026 la verifica ripartiva da GENESIS_HASH sul file live, e la prima
    voce rimasta puntava a un prev_hash ormai nell'archivio -> "compromised" per sempre
    dopo ogni rotazione di routine."""
    audit_file = audit_env["audit_file"]
    old_ts = (datetime.now(UTC) - timedelta(days=200)).isoformat()

    r1 = _append_with_ts(audit_file, "old_event_1", "sys", {"n": 1}, old_ts, GENESIS_HASH, 1)
    _append_with_ts(audit_file, "old_event_2", "sys", {"n": 2}, old_ts, r1["entry_hash"], 2)
    r3 = AuditChainManager.append_record(audit_file, "recent_event", "sys", {"n": 3})

    archived = _rotate_audit_logs(audit_file, retention_days=90)
    assert archived == 2

    verification = AuditChainManager.verify_chain(audit_file)
    assert verification["valid"] is True
    assert verification["total_entries"] == 3
    assert verification["head_hash"] == r3["entry_hash"]

    report = AuditChainManager.generate_compliance_report(audit_file)
    assert report["metrics"]["total_events_recorded"] == sum(report["metrics"]["action_breakdown"].values())
    assert report["compliance_attestation"]["overall_status"] == "COMPLIANT"


def test_rotation_still_catches_tampering_in_the_archived_segment(audit_env):
    audit_file = audit_env["audit_file"]
    old_ts = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    _append_with_ts(audit_file, "old_event", "sys", {"n": 1}, old_ts, GENESIS_HASH, 1)
    AuditChainManager.append_record(audit_file, "recent_event", "sys", {"n": 2})
    _rotate_audit_logs(audit_file, retention_days=90)

    archive_path = audit_file + ".archive"
    with open(archive_path, encoding="utf-8") as f:
        lines = f.readlines()
    tampered = json.loads(lines[0])
    tampered["detail"]["n"] = 999
    lines[0] = json.dumps(tampered) + "\n"
    with open(archive_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    verification = AuditChainManager.verify_chain(audit_file)
    assert verification["valid"] is False


def test_audit_rest_endpoints(audit_env):
    client = TestClient(app)
    audit_file = audit_env["audit_file"]
    headers = audit_env["headers"]

    AuditChainManager.append_record(audit_file, "user_login", "admin", {"ip": "127.0.0.1"})
    AuditChainManager.append_record(audit_file, "export_performed", "admin", {"format": "json"})

    # 1. GET /api/audit/verify
    verify_resp = client.get("/api/audit/verify", headers=headers)
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["valid"] is True
    assert v_data["total_entries"] == 2
    assert v_data["head_hash"] != GENESIS_HASH

    # 2. GET /api/audit/chain-head
    head_resp = client.get("/api/audit/chain-head", headers=headers)
    assert head_resp.status_code == 200
    h_data = head_resp.json()
    assert h_data["valid"] is True
    assert h_data["total_entries"] == 2
    assert h_data["head_hash"] == v_data["head_hash"]

    # 3. GET /api/audit/compliance-report
    comp_resp = client.get("/api/audit/compliance-report?organization=ACME%20Enterprise", headers=headers)
    assert comp_resp.status_code == 200
    c_data = comp_resp.json()
    assert c_data["organization"] == "ACME Enterprise"
    assert c_data["compliance_attestation"]["overall_status"] == "COMPLIANT"
