"""
api/pii.py
Enterprise PII & Data Loss Prevention (DLP) Configuration and Real-Time Testing API endpoints.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key
from config import cfg
from core.governance import append_audit
from core.pii_filter import (
    STANDARD_PATTERNS,
    detect_pii,
    filter_pii,
    get_pii_config,
    update_pii_config,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pii", tags=["DLP & PII Security"])


class CustomRuleModel(BaseModel):
    id: str = Field(default="", max_length=80)
    name: str = Field(min_length=1, max_length=120)
    pattern: str = Field(min_length=1, max_length=500)
    replacement: str = Field(min_length=1, max_length=120)
    enabled: bool = Field(default=True)


class UpdatePiiConfigRequest(BaseModel):
    enabled_patterns: dict[str, bool] = Field(default_factory=dict)
    custom_rules: list[CustomRuleModel] = Field(default_factory=list)


class TestPiiRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


@router.get("/config", summary="Ottieni configurazione regole PII/DLP attive")
def get_pii_configuration(
    _auth: dict = Depends(_verify_api_key),
) -> dict[str, Any]:
    config = get_pii_config()
    meta = [
        {
            "id": pid,
            "label": data["label"],
            "replacement": data["replacement"],
            "enabled": config.get("enabled_patterns", {}).get(pid, data["default_enabled"]),
        }
        for pid, data in STANDARD_PATTERNS.items()
    ]
    return {
        "enabled_patterns": config.get("enabled_patterns", {}),
        "custom_rules": config.get("custom_rules", []),
        "standard_patterns_meta": meta,
        "pii_filter_globally_enabled": cfg.PII_FILTER_ENABLED,
    }


@router.post("/config", summary="Aggiorna configurazione regole PII/DLP e regole custom")
def update_pii_configuration(
    request: UpdatePiiConfigRequest,
    _auth: dict = Depends(_require_role("admin")),
) -> dict[str, Any]:
    try:
        updated = update_pii_config(request.model_dump())
        append_audit(
            cfg.AUDIT_FILE,
            "update_pii_config",
            _auth["username"],
            {
                "enabled_patterns_count": sum(1 for v in updated.get("enabled_patterns", {}).values() if v),
                "custom_rules_count": len(updated.get("custom_rules", [])),
            },
        )
        return {"ok": True, "config": updated}
    except Exception as e:
        _logger.error("Errore durante l'aggiornamento della configurazione PII: %s", e)
        raise HTTPException(status_code=400, detail=f"Impossibile salvare le regole PII: {e}") from e


@router.post("/test", summary="Testa il mascheramento PII in tempo reale su un testo di prova")
def test_pii_masking(
    request: TestPiiRequest,
    _auth: dict = Depends(_verify_api_key),
) -> dict[str, Any]:
    masked = filter_pii(request.text, enabled=True)
    detected = detect_pii(request.text)
    return {
        "original": request.text,
        "masked": masked,
        "detected": detected,
        "detected_count": len(detected),
    }
