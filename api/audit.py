"""
api/audit.py
Audit log endpoints.
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends

from api.auth import _require_role
from config import cfg

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Audit"])


def _is_older_than(ts_str: str, cutoff_naive: datetime, cutoff_aware: datetime) -> bool:
    """True se `ts_str` precede il cutoff, qualunque sia il formato del timestamp.

    Voci scritte prima della migrazione alla catena crittografica (core/audit_chain.py)
    hanno `ts` naive (`datetime.now().isoformat()`); quelle scritte dopo sono UTC-aware
    (`datetime.now(UTC).isoformat()`). Confrontare un cutoff aware con un timestamp
    naive solleva TypeError: bisogna scegliere il cutoff dello stesso tipo dell'entry.
    """
    if not ts_str:
        return False
    entry_ts = datetime.fromisoformat(ts_str)
    cutoff = cutoff_aware if entry_ts.tzinfo is not None else cutoff_naive
    return entry_ts < cutoff


# ── Log Rotation ──
def _rotate_audit_logs(audit_file: str, retention_days: int = 90) -> int:
    """Archivia gli entry più vecchi di retention_days in un file .archive."""
    if not os.path.exists(audit_file):
        return 0
    cutoff_naive = datetime.now() - timedelta(days=retention_days)
    cutoff_aware = datetime.now(UTC) - timedelta(days=retention_days)
    kept = []
    archived = []
    with open(audit_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if _is_older_than(entry.get("ts", ""), cutoff_naive, cutoff_aware):
                    archived.append(line)
                else:
                    kept.append(line)
            except (json.JSONDecodeError, ValueError, TypeError):
                kept.append(line)
    if archived:
        archive_file = audit_file + ".archive"
        with open(archive_file, "a", encoding="utf-8") as af:
            af.write("\n".join(archived) + "\n")
        with open(audit_file, "w", encoding="utf-8") as kf:
            kf.write("\n".join(kept) + ("\n" if kept else ""))
        _logger.info("Audit rotation: archiviati %d entry vecchi (>%d giorni)", len(archived), retention_days)
    return len(archived)


@router.get("/api/audit/logs", summary="Interroga il log di audit")
async def audit_logs(
    limit: int = 100,
    action: str | None = None,
    actor: str | None = None,
    offset: int = 0,
    _auth: dict = Depends(_require_role("admin")),
):
    audit_file = cfg.AUDIT_FILE
    if not os.path.exists(audit_file):
        return {"entries": [], "total": 0}

    entries = []
    with open(audit_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if action and entry.get("action") != action:
                    continue
                if actor and entry.get("actor") != actor:
                    continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue

    total = len(entries)
    entries.reverse()
    sliced = entries[offset : offset + limit]
    return {"entries": sliced, "total": total, "offset": offset, "limit": limit, "returned": len(sliced)}


@router.get("/api/audit/verify", summary="Verifica l'integrità crittografica dell'intera catena di audit log")
async def audit_verify(_auth: dict = Depends(_require_role("admin"))):
    from core.audit_chain import AuditChainManager

    report = AuditChainManager.verify_chain(cfg.AUDIT_FILE)
    return report


@router.get("/api/audit/compliance-report", summary="Genera un report di conformità SOC 2 / ISO 27001 / GDPR")
async def audit_compliance_report(
    organization: str = "Ermes Enterprise",
    _auth: dict = Depends(_require_role("admin")),
):
    from core.audit_chain import AuditChainManager

    report = AuditChainManager.generate_compliance_report(
        audit_file=cfg.AUDIT_FILE,
        organization=organization,
        auditor_id=_auth.get("username", "security_admin"),
    )
    return report


@router.get("/api/audit/chain-head", summary="Recupera l'ultimo hash e altezza del registro di audit")
async def audit_chain_head(_auth: dict = Depends(_require_role("admin"))):
    from core.audit_chain import AuditChainManager

    verification = AuditChainManager.verify_chain(cfg.AUDIT_FILE)
    return {
        "head_hash": verification["head_hash"],
        "total_entries": verification["total_entries"],
        "latest_event_at": verification["latest_event_at"],
        "valid": verification["valid"],
    }


@router.get("/api/audit/stats", summary="Statistiche del log di audit")
async def audit_stats(days: int = 30, _auth: dict = Depends(_require_role("admin"))):
    from core.monitoring import analyze_audit

    return analyze_audit(cfg.AUDIT_FILE, days=days)


@router.post("/api/audit/export", summary="Esporta il log di audit")
async def audit_export(
    action: str | None = None,
    actor: str | None = None,
    days: int = 30,
    _auth: dict = Depends(_require_role("admin")),
):
    audit_file = cfg.AUDIT_FILE
    if not os.path.exists(audit_file):
        return {"entries": [], "total": 0}

    cutoff_naive = datetime.now() - timedelta(days=days)
    cutoff_aware = datetime.now(UTC) - timedelta(days=days)
    entries = []
    with open(audit_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                try:
                    if _is_older_than(entry.get("ts", ""), cutoff_naive, cutoff_aware):
                        continue
                except ValueError:
                    pass
                if action and entry.get("action") != action:
                    continue
                if actor and entry.get("actor") != actor:
                    continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue

    return {"entries": entries, "total": len(entries), "days": days}


@router.post("/api/audit/rotate", summary="Ruota (archivia) i log di audit più vecchi")
async def audit_rotate(days: int = 90, _auth: dict = Depends(_require_role("admin"))):
    archived = _rotate_audit_logs(cfg.AUDIT_FILE, retention_days=days)
    return {"archived": archived, "retention_days": days}
