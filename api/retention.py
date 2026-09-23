"""REST API Endpoints for Enterprise Document Retention & Legal Hold Policies."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key
from api.libraries import get_library_store
from core.library_store import LibraryAccessError, LibraryNotFoundError, LibraryStore
from core.retention_engine import RetentionAction, get_retention_engine

router = APIRouter(prefix="/api/retention", tags=["Retention"])


def _require_library_access(store: LibraryStore, library_id: str, actor: dict[str, Any], write: bool) -> None:
    """Retention/legal-hold policy and status are per-library data: `_require_role`
    only checks the account's global role, not membership in this specific
    library. Without this, any account with the global "editor" role could set a
    legal hold on a library it has no membership in, and any authenticated
    account could read another library's retention status and legal-hold reason
    (e.g. "under investigation for embezzlement") — neither the endpoints nor
    RetentionEngine itself ever checked library-level access; `actor` there is
    only a string used for audit attribution.
    """
    try:
        store.get_library(library_id, actor=actor, write=write)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


class SetRetentionPolicyRequest(BaseModel):
    retention_days: int = Field(ge=0, le=3650, description="Giorni di conservazione prima dell'azione (0 = indefinito)")
    action: RetentionAction = Field(default="archive", description="Azione: archive, soft_delete o purge")


class SetLegalHoldRequest(BaseModel):
    library_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    legal_hold: bool = Field(description="True per bloccare la cancellazione per verifiche legali")
    reason: str = Field(default="", max_length=500, description="Motivazione del blocco legale o di conformità")


class EnforceRetentionRequest(BaseModel):
    library_id: str | None = Field(default=None, description="Opzionale: id libreria specifica da elaborare")
    dry_run: bool = Field(default=True, description="Se True simula senza applicare modifiche")


@router.get("/policies/{library_id}")
def get_policy(
    library_id: str,
    actor: dict[str, Any] = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    """Recupera la policy di retention attiva per una biblioteca."""
    _require_library_access(store, library_id, actor, write=False)
    engine = get_retention_engine()
    policy = engine.get_library_policy(library_id)
    if not policy:
        return {
            "library_id": library_id,
            "retention_days": 0,
            "action": "archive",
            "active": False,
        }
    return {
        "library_id": policy.library_id,
        "retention_days": policy.retention_days,
        "action": policy.action,
        "active": policy.retention_days > 0,
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


@router.put("/policies/{library_id}")
def set_policy(
    library_id: str,
    request: SetRetentionPolicyRequest,
    actor: dict[str, Any] = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    """Imposta o aggiorna la retention policy per una biblioteca (richiede ruolo editor o superiore, e accesso in scrittura alla biblioteca)."""
    _require_library_access(store, library_id, actor, write=True)
    engine = get_retention_engine()
    try:
        policy = engine.set_library_policy(
            library_id=library_id,
            retention_days=request.retention_days,
            action=request.action,
            actor=actor.get("username", "system"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "library_id": policy.library_id,
        "retention_days": policy.retention_days,
        "action": policy.action,
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


@router.post("/legal-hold")
def set_legal_hold(
    request: SetLegalHoldRequest,
    actor: dict[str, Any] = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    """Applica o rimuove un Legal Hold su un documento per impedire la cancellazione."""
    _require_library_access(store, request.library_id, actor, write=True)
    engine = get_retention_engine()
    res = engine.set_document_legal_hold(
        library_id=request.library_id,
        document_id=request.document_id,
        legal_hold=request.legal_hold,
        reason=request.reason,
        actor=actor.get("username", "system"),
    )
    return res


@router.get("/documents/{library_id}/{document_id}")
def get_document_status(
    library_id: str,
    document_id: str,
    actor: dict[str, Any] = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    """Recupera lo stato di retention e eventuale legal hold del documento."""
    _require_library_access(store, library_id, actor, write=False)
    engine = get_retention_engine()
    return engine.get_document_retention_status(library_id, document_id)


@router.post("/enforce")
def enforce_retention(
    request: EnforceRetentionRequest,
    actor: dict[str, Any] = Depends(_require_role("admin")),
) -> dict[str, Any]:
    """Esegue la valutazione e applicazione delle policy di retention per documenti scaduti."""
    engine = get_retention_engine()
    report = engine.evaluate_retention(
        library_id=request.library_id,
        dry_run=request.dry_run,
        actor=actor.get("username", "system"),
    )
    return report
