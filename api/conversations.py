"""
api/conversations.py
Gestione delle sessioni di conversazione multi-chat persistenti per utente.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import _verify_api_key, rate_limited
from config import cfg
from core.conversation_store import conversation_store
from core.governance import append_audit

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


class CreateConversationRequest(BaseModel):
    library_id: str = Field(min_length=1, max_length=100)
    title: str = Field(default="Nuova conversazione", min_length=1, max_length=100)


class UpdateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class AddMessageRequest(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(min_length=1, max_length=10000)
    citations: list[dict[str, Any]] = Field(default_factory=list)


@router.get("", summary="Elenco delle conversazioni dell'utente con ricerca")
def list_conversations(
    library_id: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Filtra per testo nel titolo o nei messaggi"),
    limit: int = Query(default=50, ge=1, le=100),
    auth: dict = Depends(_verify_api_key),
):
    username = auth.get("username", "")
    if q and q.strip():
        items = conversation_store.search_conversations(
            username=username, query=q.strip(), library_id=library_id, limit=limit
        )
    else:
        items = conversation_store.list_conversations(username=username, library_id=library_id, limit=limit)
    return {"items": items, "count": len(items)}


@router.post("", summary="Crea una nuova conversazione", dependencies=[Depends(rate_limited)])
def create_conversation(
    req: CreateConversationRequest,
    auth: dict = Depends(_verify_api_key),
):
    username = auth.get("username", "")
    conv = conversation_store.create_conversation(
        username=username,
        library_id=req.library_id,
        title=req.title,
    )
    append_audit(
        cfg.AUDIT_FILE,
        "conversation_created",
        username,
        {"conversation_id": conv["id"], "library_id": req.library_id},
    )
    return conv


@router.get("/{conversation_id}", summary="Recupera la conversazione con i relativi messaggi")
def get_conversation(
    conversation_id: str,
    auth: dict = Depends(_verify_api_key),
):
    username = auth.get("username", "")
    is_admin = auth.get("role") == "admin"
    conv = conversation_store.get_conversation(
        conversation_id=conversation_id,
        username=None if is_admin else username,
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversazione non trovata")
    return conv


@router.patch("/{conversation_id}", summary="Aggiorna il titolo della conversazione")
def update_conversation(
    conversation_id: str,
    req: UpdateConversationRequest,
    auth: dict = Depends(_verify_api_key),
):
    username = auth.get("username", "")
    is_admin = auth.get("role") == "admin"
    updated = conversation_store.update_title(
        conversation_id=conversation_id,
        title=req.title,
        username=None if is_admin else username,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Conversazione non trovata o non autorizzato")
    return {"ok": True, "id": conversation_id, "title": req.title}


@router.delete("/{conversation_id}", summary="Elimina una conversazione")
def delete_conversation(
    conversation_id: str,
    auth: dict = Depends(_verify_api_key),
):
    username = auth.get("username", "")
    is_admin = auth.get("role") == "admin"
    deleted = conversation_store.delete_conversation(
        conversation_id=conversation_id,
        username=None if is_admin else username,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversazione non trovata o non autorizzato")
    append_audit(
        cfg.AUDIT_FILE,
        "conversation_deleted",
        username,
        {"conversation_id": conversation_id},
    )
    return {"ok": True, "deleted_id": conversation_id}


@router.post("/{conversation_id}/messages", summary="Aggiunge un messaggio alla conversazione")
def add_message(
    conversation_id: str,
    req: AddMessageRequest,
    auth: dict = Depends(_verify_api_key),
):
    username = auth.get("username", "")
    is_admin = auth.get("role") == "admin"
    conv = conversation_store.get_conversation(
        conversation_id=conversation_id,
        username=None if is_admin else username,
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversazione non trovata o non autorizzato")

    msg = conversation_store.add_message(
        conversation_id=conversation_id,
        role=req.role,
        content=req.content,
        citations=req.citations,
    )
    return msg
