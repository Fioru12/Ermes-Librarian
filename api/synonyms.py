"""
api/synonyms.py
Gestione dei sinonimi aziendali e acronimi personalizzati (Glossario Aziendale).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key
from config import cfg
from core.governance import append_audit
from core.query_expander import (
    add_custom_synonym,
    delete_custom_synonym,
    get_all_synonyms,
    load_custom_synonyms,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/synonyms", tags=["Glossary"])


class SynonymPayload(BaseModel):
    term: str = Field(..., min_length=1, max_length=100, description="Termine o acronimo principale")
    synonyms: list[str] = Field(..., min_length=1, description="Lista di sinonimi o espansioni equivalenti")


@router.get("", summary="Consulta il glossario aziendale e i sinonimi personalizzati")
async def get_synonyms(_auth: dict = Depends(_verify_api_key)):
    """Restituisce sia l'elenco dei sinonimi custom definiti dall'organizzazione,

    sia il dizionario completo attivo (built-in + custom).
    """
    custom = load_custom_synonyms()
    all_active = get_all_synonyms()
    return {
        "custom": custom,
        "all": all_active,
        "count_custom": len(custom),
        "count_total": len(all_active),
    }


@router.post("", summary="Aggiunge o aggiorna un termine con i relativi sinonimi")
async def set_synonym(
    payload: SynonymPayload,
    user: dict = Depends(_require_role("editor")),
):
    """Crea o aggiorna un termine con i relativi sinonimi nel glossario aziendale.

    Richiede ruolo editor o admin.
    """
    clean_term = payload.term.strip().lower()
    if not clean_term:
        raise HTTPException(status_code=400, detail="Il termine non puo' essere vuoto")

    clean_synonyms = [s.strip().lower() for s in payload.synonyms if s.strip().lower() and s.strip().lower() != clean_term]
    if not clean_synonyms:
        raise HTTPException(
            status_code=400,
            detail="Specificare almeno un sinonimo valido diverso dal termine stesso",
        )

    try:
        updated_dict = add_custom_synonym(clean_term, clean_synonyms)
    except Exception as e:
        _logger.error("Errore nel salvataggio del sinonimo '%s': %s", clean_term, e)
        raise HTTPException(status_code=500, detail=f"Errore durante il salvataggio: {e}") from e

    append_audit(
        cfg.AUDIT_FILE,
        "synonym_upsert",
        user.get("username", "unknown"),
        {"term": clean_term, "synonyms": clean_synonyms},
    )

    return {
        "success": True,
        "term": clean_term,
        "synonyms": updated_dict.get(clean_term, clean_synonyms),
    }


@router.delete("/{term}", summary="Rimuove un termine dai sinonimi personalizzati")
async def remove_synonym(
    term: str,
    user: dict = Depends(_require_role("editor")),
):
    """Elimina un termine dal glossario aziendale personalizzato.

    Richiede ruolo editor o admin.
    """
    clean_term = term.strip().lower()
    if not clean_term:
        raise HTTPException(status_code=400, detail="Termine non specificato")

    deleted = delete_custom_synonym(clean_term)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Termine '{clean_term}' non trovato tra i sinonimi personalizzati",
        )

    append_audit(
        cfg.AUDIT_FILE,
        "synonym_deleted",
        user.get("username", "unknown"),
        {"term": clean_term},
    )

    return {
        "success": True,
        "term": clean_term,
    }
