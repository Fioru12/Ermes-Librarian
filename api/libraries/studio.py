"""Studio outputs (briefing, FAQ, study guide) and personal notes of a library."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from api.auth import _verify_api_key, rate_limited
from api.libraries.common import get_library_store
from config import cfg
from core.governance import append_audit
from core.library_store import (
    LibraryAccessError,
    LibraryNotFoundError,
    LibraryStore,
)

router = APIRouter(prefix="/api/libraries", tags=["Libraries"])


@router.post("/{library_id}/studio/{kind}", dependencies=[Depends(rate_limited)])
def generate_library_studio(
    library_id: str,
    kind: Literal["briefing", "faq", "study_guide", "questions"],
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Briefing, FAQ, guida di studio o domande suggerite dalla biblioteca.

    Ogni punto cita i passaggi da cui viene; i punti senza citazione valida
    sono scartati (vedi core/library_studio.py). Usa il fornitore scelto per
    la biblioteca e nessun altro; in `evidence_only` risponde `unavailable`.
    """
    from core.library_studio import genera_studio

    try:
        library = store.get_library(library_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    result = genera_studio(store, library, kind, _auth)
    append_audit(
        cfg.AUDIT_FILE,
        "library_studio",
        _auth["username"],
        {
            "library_id": library_id,
            "kind": kind,
            "status": result["status"],
            "assistant_mode": library["assistant_mode"],
            "items": len(result["items"]),
            "discarded": result["discarded"],
        },
    )
    return {"library": {"id": library["id"], "name": library["name"]}, **result}


class NoteSource(BaseModel):
    document_id: str | None = Field(default=None, max_length=100)
    filename: str | None = Field(default=None, max_length=300)
    version: int | None = None
    locator: str | None = Field(default=None, max_length=300)
    excerpt: str | None = Field(default=None, max_length=2000)


class CreateNoteRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=20_000)
    sources: list[NoteSource] = Field(default_factory=list, max_length=20)


class UpdateNoteRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=20_000)


@router.get("/{library_id}/notes")
def list_library_notes(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Note personali di chi chiede in questa biblioteca: nessuno vede quelle altrui."""
    try:
        return {"items": store.list_notes(library_id, _auth)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.post("/{library_id}/notes", status_code=201)
def create_library_note(
    library_id: str,
    request: CreateNoteRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        return store.create_note(
            library_id, _auth, request.title, request.body, [s.model_dump(exclude_none=True) for s in request.sources]
        )
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.patch("/{library_id}/notes/{note_id}")
def update_library_note(
    library_id: str,
    note_id: str,
    request: UpdateNoteRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        return store.update_note(library_id, note_id, _auth, request.title, request.body)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Nota non trovata") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/{library_id}/notes/{note_id}", status_code=204)
def delete_library_note(
    library_id: str,
    note_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        store.delete_note(library_id, note_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Nota non trovata") from error
    return Response(status_code=204)
