"""
api/backup.py
Backup management endpoints.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import _require_role

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Backup"])


class BackupResponse(BaseModel):
    success: bool
    message: str
    data: dict | None = None


@router.post("/backup/create", response_model=BackupResponse,
             summary="Crea un backup del sistema")
async def create_backup(_auth: dict = Depends(_require_role("admin"))):
    from core.backup_manager import create_backup
    try:
        result = create_backup(label="api")
        return BackupResponse(success=True, message="Backup creato", data=result)
    except Exception as e:
        _logger.error("Backup fallito: %s", e)
        raise HTTPException(status_code=500, detail=f"Backup fallito: {e}")


@router.get("/backup/list", tags=["Backup"],
            summary="Elenca backup disponibili")
async def list_backups(_auth: dict = Depends(_require_role("admin"))):
    from core.backup_manager import list_backups
    return {"backups": list_backups()}


@router.post("/backup/restore/{backup_name}", response_model=BackupResponse,
             summary="Ripristina un backup")
async def restore_backup(backup_name: str, dry_run: bool = False, _auth: dict = Depends(_require_role("admin"))):
    from core.backup_manager import restore_backup
    try:
        result = restore_backup(backup_name, dry_run=dry_run)
        return BackupResponse(
            success=True,
            message=f"{'Preview' if dry_run else 'Ripristino'} completato",
            data=result,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _logger.error("Restore fallito: %s", e)
        raise HTTPException(status_code=500, detail=f"Restore fallito: {e}")


@router.get("/backup/status", tags=["Backup"],
            summary="Stato sistema backup")
async def backup_status(_auth: dict = Depends(_require_role("admin"))):
    from core.backup_manager import get_backup_status
    return get_backup_status()
