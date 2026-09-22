"""Cryptographic Immutable Audit Trail & Compliance Integrity Verifier.

Provides tamper-evident SHA-256 hash chaining (Merkle-link) and cryptographic
verification for SOC 2 Type II, ISO 27001, and GDPR Article 30/32 compliance.
Detects any modification, insertion, reordering, or deletion of audit logs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

_logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64


def _canonical_json(data: Any) -> str:
    """Serializes data into canonical sorted JSON string."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _get_audit_secret() -> bytes:
    """Returns the HMAC secret for audit signatures from governance."""
    from core.governance import _get_audit_secret as _gov_get_secret

    return _gov_get_secret()


def compute_entry_hash(seq_id: int, prev_hash: str, ts: str, action: str, actor: str, detail: dict) -> str:
    """Computes deterministic SHA-256 hash chaining over the audit record."""
    canonical_detail = _canonical_json(detail)
    payload = f"{seq_id}|{prev_hash}|{ts}|{action}|{actor}|{canonical_detail}".encode()
    return hashlib.sha256(payload).hexdigest()


def compute_signature(entry_hash: str) -> str:
    """Computes HMAC-SHA256 signature for non-repudiation."""
    secret = _get_audit_secret()
    return hmac.new(secret, entry_hash.encode("utf-8"), hashlib.sha256).hexdigest()


class AuditChainManager:
    """Manages appending and verifying cryptographic audit log records."""

    @staticmethod
    def append_record(
        audit_file: str,
        action: str,
        actor: str,
        detail: dict | None = None,
    ) -> dict[str, Any]:
        """Appends an immutable tamper-evident record to the audit chain."""
        canonical_path = os.path.abspath(audit_file)
        os.makedirs(os.path.dirname(canonical_path), exist_ok=True)
        lock_path = canonical_path + ".lock"

        detail_payload = detail or {}
        now_ts = datetime.now(UTC).isoformat()

        from core.governance import _get_file_lock

        with _get_file_lock(lock_path):
            prev_hash = GENESIS_HASH
            seq_id = 1

            if os.path.exists(canonical_path) and os.path.getsize(canonical_path) > 0:
                with open(canonical_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            prev_hash = item.get("entry_hash") or item.get("signature") or prev_hash
                            seq_id = int(item.get("seq_id", seq_id)) + 1
                        except (json.JSONDecodeError, ValueError):
                            continue

            entry_hash = compute_entry_hash(seq_id, prev_hash, now_ts, action, actor, detail_payload)
            signature = compute_signature(entry_hash)

            record = {
                "seq_id": seq_id,
                "ts": now_ts,
                "action": action,
                "actor": actor,
                "detail": detail_payload,
                "prev_hash": prev_hash,
                "entry_hash": entry_hash,
                "signature": signature,
            }

            with open(canonical_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return record

    @staticmethod
    def verify_chain(audit_file: str) -> dict[str, Any]:
        """Cryptographically verifies the audit log chain from genesis to head.

        `_rotate_audit_logs` (api/audit.py) moves old records out of `audit_file`
        into `audit_file + ".archive"` without touching their stored hashes —
        rewriting them would itself be tampering. So the chain that started in
        the archive continues, unbroken, into the live file: verification reads
        the archive segment first (if any) and carries its running hash forward,
        instead of treating the live file as a chain of its own that starts at
        genesis. Without this, every rotation would flag its own output as
        "compromised" — a tamper-evidence system unable to survive its own
        maintenance operation is not one anyone would trust.
        """
        archive_file = audit_file + ".archive"
        segments = [p for p in (archive_file, audit_file) if os.path.exists(p) and os.path.getsize(p) > 0]

        if not segments:
            return {
                "valid": True,
                "total_entries": 0,
                "verified_entries": 0,
                "corrupted_count": 0,
                "tampered_entries": [],
                "head_hash": GENESIS_HASH,
                "first_event_at": None,
                "latest_event_at": None,
                "integrity_status": "empty_log",
            }

        total = 0
        verified = 0
        expected_prev_hash = GENESIS_HASH
        tampered: list[dict[str, Any]] = []
        first_ts = None
        latest_ts = None
        last_valid_hash = GENESIS_HASH

        for segment in segments:
            with open(segment, encoding="utf-8") as f:
                for line_idx, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    total += 1

                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        tampered.append({
                            "file": segment,
                            "line": line_idx,
                            "seq_id": total,
                            "reason": "json_parse_error",
                        })
                        continue

                    seq_id = entry.get("seq_id", total)
                    ts = entry.get("ts", "")
                    action = entry.get("action", "")
                    actor = entry.get("actor", "")
                    detail = entry.get("detail", {})
                    prev_hash = entry.get("prev_hash")
                    entry_hash = entry.get("entry_hash")
                    signature = entry.get("signature")

                    if first_ts is None:
                        first_ts = ts
                    latest_ts = ts

                    # Legacy entries compatibility (without prev_hash/entry_hash)
                    if not entry_hash or not prev_hash:
                        # Verify legacy HMAC signature
                        from core.governance import _verify_audit_signature

                        if _verify_audit_signature(entry.copy()):
                            verified += 1
                            expected_prev_hash = signature or expected_prev_hash
                        else:
                            tampered.append({
                                "file": segment,
                                "line": line_idx,
                                "seq_id": seq_id,
                                "reason": "legacy_signature_invalid",
                            })
                        continue

                    # 1. Verify previous hash chaining
                    if prev_hash != expected_prev_hash:
                        tampered.append({
                            "file": segment,
                            "line": line_idx,
                            "seq_id": seq_id,
                            "reason": f"chain_broken: expected prev_hash {expected_prev_hash[:12]}..., got {prev_hash[:12]}...",
                        })
                        continue

                    # 2. Verify deterministic entry hash
                    recomputed_hash = compute_entry_hash(seq_id, prev_hash, ts, action, actor, detail)
                    if recomputed_hash != entry_hash:
                        tampered.append({
                            "file": segment,
                            "line": line_idx,
                            "seq_id": seq_id,
                            "reason": "payload_tampered: entry_hash mismatch",
                        })
                        continue

                    # 3. Verify HMAC signature
                    recomputed_sig = compute_signature(entry_hash)
                    if recomputed_sig != signature:
                        tampered.append({
                            "file": segment,
                            "line": line_idx,
                            "seq_id": seq_id,
                            "reason": "signature_invalid: HMAC mismatch",
                        })
                        continue

                    verified += 1
                    expected_prev_hash = entry_hash
                    last_valid_hash = entry_hash

        is_valid = len(tampered) == 0 and total == verified
        return {
            "valid": is_valid,
            "total_entries": total,
            "verified_entries": verified,
            "corrupted_count": len(tampered),
            "tampered_entries": tampered,
            "head_hash": last_valid_hash,
            "first_event_at": first_ts,
            "latest_event_at": latest_ts,
            "integrity_status": "verified_authentic" if is_valid else "compromised",
        }

    @staticmethod
    def generate_compliance_report(
        audit_file: str,
        organization: str = "Ermes Enterprise",
        auditor_id: str = "security_auditor",
    ) -> dict[str, Any]:
        """Generates a SOC 2 Type II / ISO 27001 / GDPR compliance certification report."""
        verification = AuditChainManager.verify_chain(audit_file)
        now_iso = datetime.now(UTC).isoformat()

        action_counts: dict[str, int] = {}
        actor_counts: dict[str, int] = {}
        security_events: list[dict[str, Any]] = []

        # Same segments verify_chain just walked (archive then live), so the
        # breakdown below sums to total_events_recorded even after a rotation.
        for segment in (audit_file + ".archive", audit_file):
            if not os.path.exists(segment):
                continue
            with open(segment, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        act = entry.get("action", "unknown")
                        usr = entry.get("actor", "anonymous")
                        action_counts[act] = action_counts.get(act, 0) + 1
                        actor_counts[usr] = actor_counts.get(usr, 0) + 1

                        if act in {
                            "user_created",
                            "user_deleted",
                            "role_changed",
                            "retention_policy_updated",
                            "legal_hold_modified",
                            "document_retention_purged",
                            "scim_user_created",
                            "scim_user_deleted",
                            "scim_group_updated",
                        }:
                            security_events.append({
                                "ts": entry.get("ts"),
                                "action": act,
                                "actor": usr,
                                "seq_id": entry.get("seq_id"),
                            })
                    except json.JSONDecodeError:
                        continue

        report_id = f"SOC2-REPORT-{hashlib.sha256(now_iso.encode()).hexdigest()[:12].upper()}"

        return {
            "report_id": report_id,
            "generated_at": now_iso,
            "auditor": auditor_id,
            "organization": organization,
            "standards_evaluated": [
                "SOC 2 Type II (Trust Services Criteria CC6.1, CC6.6, CC7.2)",
                "ISO/IEC 27001:2022 (Annex A.8.15 - Logging & Monitoring)",
                "GDPR Article 30 & 32 (Security of Processing & Accountability)",
            ],
            "chain_verification": verification,
            "metrics": {
                "total_events_recorded": verification["total_entries"],
                "unique_actors": len(actor_counts),
                "action_breakdown": action_counts,
                "actor_activity": actor_counts,
                "high_priority_governance_events_count": len(security_events),
            },
            "recent_governance_events": security_events[-20:],
            "compliance_attestation": {
                "immutable_logging": verification["valid"],
                "tamper_evidence": "SHA-256 Chained + HMAC Authenticated",
                "audit_non_repudiation": "PASSED" if verification["valid"] else "FAILED",
                "overall_status": "COMPLIANT" if verification["valid"] else "NON_COMPLIANT",
            },
        }
