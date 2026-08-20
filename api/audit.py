"""
api/audit.py
Audit log endpoints.
"""
import json
import logging
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from api.auth import _require_role

from config import cfg

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Audit"])


# ── Log Rotation ──
def _rotate_audit_logs(audit_file: str, retention_days: int = 90) -> int:
    """Archivia gli entry più vecchi di retention_days in un file .archive."""
    if not os.path.exists(audit_file):
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    kept = []
    archived = []
    with open(audit_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts_str = entry.get("ts", "")
                entry_ts = datetime.fromisoformat(ts_str) if ts_str else None
                if entry_ts and entry_ts < cutoff:
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
    sliced = entries[offset:offset + limit]
    return {"entries": sliced, "total": total, "offset": offset, "limit": limit, "returned": len(sliced)}


@router.get("/api/audit/verify", summary="Verifica l'integrità del log di audit")
async def audit_verify(_auth: dict = Depends(_require_role("admin"))):
    from core.governance import verify_audit_log_integrity
    total, valid = verify_audit_log_integrity(cfg.AUDIT_FILE)
    return {"total": total, "valid": valid, "tampered": total - valid, "integrity_ok": total == valid}


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

    cutoff = datetime.now() - timedelta(days=days)
    entries = []
    with open(audit_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts_str = entry.get("ts", "")
                try:
                    entry_ts = datetime.fromisoformat(ts_str)
                    if entry_ts < cutoff:
                        continue
                except (ValueError, TypeError):
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
