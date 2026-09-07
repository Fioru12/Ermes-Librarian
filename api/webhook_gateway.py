"""
api/webhook_gateway.py
Automation Webhook Gateway for n8n, Zapier, Make, and Custom Microservices.
Provides clean REST webhook endpoints for asking questions and ingesting documents
into Ermes Knowledge libraries via API Key authentication.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _verify_api_key
from api.libraries import _answer_question, get_library_store
from core.library_store import LibraryStore

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/automation", tags=["Automation Webhooks (n8n/Zapier)"])


class AskAutomationRequest(BaseModel):
    library_id: str = Field(min_length=1, description="ID della biblioteca target")
    question: str = Field(min_length=1, description="Domanda in linguaggio naturale")


class IngestAutomationRequest(BaseModel):
    library_id: str = Field(min_length=1, description="ID della biblioteca target")
    filename: str = Field(min_length=1, description="Nome del file da caricare")
    content: str = Field(min_length=1, description="Contenuto testuale o stringa Base64")
    is_base64: bool = Field(default=False, description="True se il contenuto è in Base64")
    media_type: str | None = Field(default="text/plain", description="Tipo MIME del documento")


@router.get("/libraries", summary="Lista biblioteche per tendine n8n/Zapier")
def list_libraries_for_automation(
    user: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    libs = store.list_libraries(user)
    return {
        "ok": True,
        "count": len(libs),
        "libraries": [
            {
                "id": lib.get("id"),
                "name": lib.get("name"),
                "description": lib.get("description"),
            }
            for lib in libs
        ],
    }


@router.post("/ask", summary="Esegue una query RAG da n8n/Zapier e restituisce testo + citazioni")
def automation_ask(
    request: AskAutomationRequest,
    user: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    lib = store.get_library(request.library_id, user)
    if not lib:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata o permessi insufficienti")

    res = _answer_question(store, request.library_id, request.question, 5, user)
    citations = res.get("citations", [])

    sources_summary = [
        f"{c.get('filename')} (v{c.get('version', 1)})" for c in citations if isinstance(c, dict) and c.get("filename")
    ]

    return {
        "ok": True,
        "library_id": request.library_id,
        "question": request.question,
        "answer": res.get("answer"),
        "evidence_found": len(citations) > 0,
        "evidence_only_mode": res.get("evidence_only", False),
        "citations": citations,
        "sources_summary": list(set(sources_summary)),
    }


@router.post("/ingest", summary="Ingestione diretta documenti da webhooks esterni")
def automation_ingest(
    request: IngestAutomationRequest,
    user: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    lib = store.get_library(request.library_id, user)
    if not lib:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata o permessi insufficienti")

    try:
        if request.is_base64:
            raw_bytes = base64.b64decode(request.content)
        else:
            raw_bytes = request.content.encode("utf-8")

        from core.document_parser import chunk_source_units, extract_source_units

        units = extract_source_units(request.filename, raw_bytes)
        chunks = chunk_source_units(units)
        if not chunks:
            text_decoded = raw_bytes.decode("utf-8", errors="ignore")
            chunks = [(text_decoded, "Testo")]

        stored_rel_path = f"{request.library_id}/{request.filename}"
        doc_record = store.add_document(
            library_id=request.library_id,
            filename=request.filename,
            media_type=request.media_type or "text/plain",
            content=raw_bytes,
            storage_path=stored_rel_path,
            status="ready",
            chunks=chunks,
        )

        return {
            "ok": True,
            "library_id": request.library_id,
            "filename": request.filename,
            "document_id": doc_record.get("id"),
            "size_bytes": len(raw_bytes),
            "message": f"Documento {request.filename} importato con successo.",
        }
    except Exception as e:
        _logger.error("Errore durante l'ingestione automation: %s", e)
        raise HTTPException(status_code=500, detail=f"Errore durante l'ingestione: {str(e)}")
