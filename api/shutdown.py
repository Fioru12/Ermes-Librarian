"""
api/shutdown.py
Shutdown endpoint.
"""
import logging
import os
import signal

from fastapi import APIRouter, Depends, HTTPException
from api.auth import _require_role

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["System"])

_shutdown_key: str = os.environ.get("ERMES_SHUTDOWN_KEY", "")


@router.post("/shutdown", include_in_schema=False)
async def shutdown_endpoint(key: str = "", _: dict = Depends(_require_role("admin"))):
    if not _shutdown_key:
        raise HTTPException(503, "shutdown non configurato")
    if key != _shutdown_key:
        raise HTTPException(403, "invalid shutdown key")
    os.kill(os.getpid(), signal.SIGTERM)
    return {"ok": True}
