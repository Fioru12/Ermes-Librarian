"""Libraries and document inventory endpoints for Ermes Knowledge."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key
from config import cfg
from core.document_parser import DocumentParseError, chunk_source_units, extract_source_units
from core.evidence_assistant import answer_from_evidence
from core.governance import append_audit
from core.ingestion_service import process_ingestion_job
from core.input_validator import matches_expected_file_signature, sanitize_upload_name
from core.library_store import (
    LibraryAccessError,
    LibraryNotFoundError,
    LibraryStore,
    resolve_storage_path,
    storage_relative_path,
)

router = APIRouter(prefix="/api/libraries", tags=["Libraries"])
_store: LibraryStore | None = None


def get_library_store() -> LibraryStore:
    """Singleton legato al percorso configurato.

    Se cfg cambia (test con BASE_DIR temporanei, o un deployment che ripunta
    altrove), l'istanza vecchia punta a un file magari piu' esistente: la si
    ricrea invece di restituire un store morto.
    """
    global _store
    if _store is None or Path(_store.database_path) != Path(cfg.LIBRARY_DB_PATH):
        _store = LibraryStore(cfg.LIBRARY_DB_PATH)
    return _store


class CreateLibraryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    visibility: str = Field(default="private")


class AskLibraryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=10)


class AssistantPolicyRequest(BaseModel):
    mode: str = Field(pattern="^(evidence_only|local_ollama|approved_openrouter|approved_provider)$")
    provider_name: str = Field(default="", max_length=120, pattern=r"^[A-Za-z0-9 ._:-]*$")


class LibraryMemberRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    role: str = Field(pattern="^(viewer|editor)$")


class DocumentAclRequest(BaseModel):
    """Allow-list dei nomi utente che possono vedere il documento.

    Lista vuota = nessuna restrizione oltre a quelle della libreria.
    """

    usernames: list[str] = Field(default_factory=list, max_length=100)


def _require_library_member_manager(store: LibraryStore, library_id: str, actor: dict) -> None:
    try:
        if not store.can_manage_library_members(library_id, actor):
            raise HTTPException(status_code=403, detail="Solo il proprietario o un amministratore possono gestire i collaboratori")
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.get("")
def list_libraries(
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    return {"items": store.list_libraries(_auth)}


@router.post("", status_code=201)
def create_library(
    request: CreateLibraryRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        return store.create_library(request.name, request.description, request.visibility, owner_id=_auth["username"])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{library_id}/documents")
def list_documents(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        store.get_library(library_id, _auth)
        return {"items": store.list_documents(library_id, _auth)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.get("/{library_id}/documents/{document_id}/versions")
def list_document_versions(
    library_id: str,
    document_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        store.get_library(library_id, _auth)
        return {"items": store.list_document_versions(library_id, document_id, _auth)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error


@router.get("/{library_id}/documents/{document_id}/download")
def download_document(
    library_id: str,
    document_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Serve the current immutable original only after the library access check."""
    try:
        store.get_library(library_id, _auth)
        document = store.get_document(library_id, document_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error
    storage_root = Path(cfg.LIBRARY_STORAGE_DIR).resolve()
    source_path = resolve_storage_path(document["storage_path"], cfg.LIBRARY_STORAGE_DIR)
    try:
        source_path.resolve().relative_to(storage_root)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Percorso originale non valido") from error
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="Originale non disponibile")
    append_audit(
        cfg.AUDIT_FILE, "document_downloaded", _auth["username"],
        {"library_id": library_id, "document_id": document_id, "filename": document["filename"], "version": document["version"]},
    )
    return FileResponse(source_path, media_type=document["media_type"], filename=document["filename"])


@router.get("/{library_id}/ingestion-jobs")
def list_ingestion_jobs(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        store.get_library(library_id, _auth)
        return {"items": store.list_ingestion_jobs(library_id)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.post("/{library_id}/documents", status_code=201, response_model=None)
async def upload_document(
    library_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    safe_name = sanitize_upload_name(file.filename or "")
    if safe_name is None:
        raise HTTPException(status_code=400, detail="Nome file o estensione non supportati")

    content = await file.read((cfg.ADMIN_MAX_UPLOAD_MB * 1024 * 1024) + 1)
    if len(content) > cfg.ADMIN_MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File troppo grande")
    if not content or not matches_expected_file_signature(BytesIO(content), safe_name):
        raise HTTPException(status_code=400, detail="Il contenuto non corrisponde al tipo di file dichiarato")

    try:
        store.get_library(library_id, _auth, write=True)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error

    document_id = uuid.uuid4().hex
    library_dir = Path(cfg.LIBRARY_STORAGE_DIR) / library_id
    library_dir.mkdir(parents=True, exist_ok=True)
    destination = library_dir / f"{document_id}_{safe_name}"
    try:
        destination.write_bytes(content)
    except OSError as error:
        raise HTTPException(status_code=500, detail="Impossibile salvare il file originale") from error
    try:
        document = store.add_document(
            library_id=library_id, filename=safe_name, media_type=file.content_type or "", content=content,
            storage_path=storage_relative_path(library_id, destination.name), status="queued", chunks=[],
        )
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Impossibile registrare il documento") from error
    job = store.start_ingestion_job(library_id, safe_name, document_id=document["id"])
    if background_tasks is None:  # chiamata diretta senza injection FastAPI
        background_tasks = BackgroundTasks()
    background_tasks.add_task(process_ingestion_job, store, job["id"], cfg.LIBRARY_STORAGE_DIR)
    return {**document, "ingestion_job_id": job["id"], "status": "queued"}


@router.get("/{library_id}/search")
def search_library(
    library_id: str,
    q: str = "",
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    if len(q.strip()) < 2:
        raise HTTPException(status_code=422, detail="Inserisci almeno 2 caratteri per cercare")
    try:
        store.get_library(library_id, _auth)
        items, retrieval_profile = store.search_with_profile(library_id, q, actor=_auth)
        return {"items": items, "retrieval_profile": retrieval_profile}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.post("/{library_id}/ask")
def ask_library(
    library_id: str,
    request: AskLibraryRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Evidence-first assistant baseline, intentionally abstaining without sources."""
    try:
        library = store.get_library(library_id, _auth)
        citations, retrieval_profile = store.search_with_profile(library_id, request.question, limit=request.top_k, actor=_auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if not citations:
        return {
            "answer_id": str(uuid.uuid4()),
            "library": {"id": library["id"], "name": library["name"]},
            "question": request.question,
            "answer": "Non ho trovato evidenza sufficiente nella biblioteca selezionata. Prova con parole più specifiche oppure carica il documento pertinente.",
            "status": "abstained",
            "evidence": {"coverage": "insufficient_evidence", "reason": "Nessun passaggio corrispondente recuperato."},
            "citations": [],
            "meta": {"assistant_mode": library["assistant_mode"], "assistant_provider": library.get("assistant_provider", ""), "retrieval_profile": retrieval_profile, "created_at": datetime.now(UTC).isoformat()},
        }
    answer, coverage, reason = answer_from_evidence(
        request.question, citations, mode=library["assistant_mode"], provider_name=library.get("assistant_provider", ""),
    )
    append_audit(
        cfg.AUDIT_FILE, "library_answer", _auth["username"],
        {"library_id": library_id, "assistant_mode": library["assistant_mode"], "assistant_provider": library.get("assistant_provider", ""), "retrieval_profile": retrieval_profile["mode"], "citation_count": len(citations), "coverage": coverage},
    )
    return {
        "answer_id": str(uuid.uuid4()),
        "library": {"id": library["id"], "name": library["name"]},
        "question": request.question,
        "answer": answer,
        "status": "answered" if coverage == "supported" else "abstained",
        "evidence": {"coverage": coverage, "reason": reason},
        "citations": [item["citation"] | {"excerpt": item["excerpt"], "marker": index, "relevance_score": item["relevance_score"]} for index, item in enumerate(citations, start=1)],
        "meta": {"assistant_mode": library["assistant_mode"], "assistant_provider": library.get("assistant_provider", ""), "retrieval_profile": retrieval_profile, "created_at": datetime.now(UTC).isoformat()},
    }


@router.put("/{library_id}/assistant-policy")
def set_library_assistant_policy(
    library_id: str,
    request: AssistantPolicyRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Set the explicit generation/data-egress policy for one library."""
    try:
        library = store.get_library(library_id, _auth, write=True)
        if request.mode in {"approved_openrouter", "approved_provider"} and not store.can_manage_library_members(library_id, _auth):
            raise HTTPException(status_code=403, detail="Solo il proprietario o un amministratore possono autorizzare un provider cloud")
        if request.mode == "approved_openrouter" and (not cfg.LIBRARY_CLOUD_CONSENT or not cfg.OPENROUTER_API_KEY):
            raise HTTPException(status_code=409, detail="OpenRouter non e autorizzato o configurato per questa istanza")
        if request.mode == "approved_provider" and _get_approved_cloud_provider(request.provider_name) is None:
            raise HTTPException(status_code=409, detail="Provider cloud non autorizzato o non configurato per questa istanza")
        updated = store.set_assistant_policy(library_id, request.mode, request.provider_name)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    append_audit(
        cfg.AUDIT_FILE, "library_assistant_policy_changed", _auth["username"],
        {"library_id": library["id"], "mode": request.mode, "provider_name": updated.get("assistant_provider", "")},
    )
    return {"id": updated["id"], "assistant_mode": updated["assistant_mode"], "assistant_provider": updated.get("assistant_provider", "")}


def _get_approved_cloud_provider(name: str):
    """Return one enabled, credentialed, non-local provider without secrets."""
    if not cfg.LIBRARY_CLOUD_CONSENT or not name:
        return None
    from core.ai.providers.registry import get_registry
    provider = get_registry().get_provider(name)
    if provider is None or not provider.config.enabled or provider.config.type == "ollama":
        return None
    if not provider.config.api_key or not provider.config.default_model:
        return None
    return provider


@router.get("/{library_id}/assistant-options")
def library_assistant_options(
    library_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Safe provider labels for a library policy picker; no credentials leak."""
    try:
        store.get_library(library_id, _auth, write=True)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if not cfg.LIBRARY_CLOUD_CONSENT:
        return {"items": [], "cloud_enabled": False}
    from core.ai.providers.registry import get_registry
    items = []
    for item in get_registry().list_providers():
        provider = _get_approved_cloud_provider(str(item.get("name", "")))
        if provider:
            items.append({"name": provider.config.name, "type": provider.config.type, "default_model": provider.config.default_model})
    return {"items": items, "cloud_enabled": True}


@router.get("/{library_id}/members")
def list_library_members(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    _require_library_member_manager(store, library_id, _auth)
    return {"items": store.list_library_members(library_id)}


@router.put("/{library_id}/members")
def set_library_member(
    library_id: str,
    request: LibraryMemberRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    _require_library_member_manager(store, library_id, _auth)
    try:
        member = store.set_library_member(library_id, request.username, request.role)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    append_audit(cfg.AUDIT_FILE, "library_member_changed", _auth["username"], {"library_id": library_id, **member})
    return member


@router.delete("/{library_id}/members/{username}", status_code=204)
def remove_library_member(
    library_id: str,
    username: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    _require_library_member_manager(store, library_id, _auth)
    if not store.remove_library_member(library_id, username):
        raise HTTPException(status_code=404, detail="Collaboratore non trovato")
    append_audit(cfg.AUDIT_FILE, "library_member_removed", _auth["username"], {"library_id": library_id, "username": username})


@router.get("/{library_id}/documents/{document_id}/acl")
def get_document_acl(
    library_id: str,
    document_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Allow-list di un documento. Solo proprietario o amministratore."""
    try:
        if not store.can_manage_library_members(library_id, _auth):
            raise HTTPException(status_code=403, detail="Solo il proprietario o un amministratore possono vedere le restrizioni del documento")
        return {"items": store.list_document_acl(library_id, document_id)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error


@router.put("/{library_id}/documents/{document_id}/acl")
def set_document_acl(
    library_id: str,
    document_id: str,
    request: DocumentAclRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Replace the document allow-list. Owner or administrator only."""
    _require_library_member_manager(store, library_id, _auth)
    requested = sorted({username.strip() for username in request.usernames if username and username.strip()})
    from core.governance import list_users
    known = {item["username"] for item in list_users(cfg.USERS_FILE)}
    unknown = [username for username in requested if username not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Utenti sconosciuti: {', '.join(unknown)}")
    try:
        result = store.set_document_acl(library_id, document_id, requested)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error
    append_audit(
        cfg.AUDIT_FILE, "document_acl_changed", _auth["username"],
        {"library_id": library_id, "document_id": document_id, "usernames": requested},
    )
    return result


@router.post("/{library_id}/documents/{document_id}/reindex")
def reindex_library_document(
    library_id: str,
    document_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Rebuild derived text and citations from the immutable original file."""
    try:
        store.get_library(library_id, _auth, write=True)
        document = store.get_document(library_id, document_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error

    source_path = resolve_storage_path(document["storage_path"], cfg.LIBRARY_STORAGE_DIR)
    storage_root = Path(cfg.LIBRARY_STORAGE_DIR).resolve()
    try:
        source_path.resolve().relative_to(storage_root)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Percorso originale non valido") from error
    if not source_path.is_file():
        raise HTTPException(status_code=409, detail="Originale non disponibile: impossibile reindicizzare")
    try:
        source_units = extract_source_units(document["filename"], source_path.read_bytes())
    except DocumentParseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not source_units:
        raise HTTPException(status_code=422, detail="Il documento non contiene testo estraibile")

    return store.replace_document_index(
        library_id=library_id,
        document_id=document_id,
        extracted_text="\n\n".join(unit.text for unit in source_units),
        source_units=len(source_units),
        chunks=chunk_source_units(source_units),
    )


@router.post("/{library_id}/documents/{document_id}/versions/{version}/restore")
def restore_document_version(
    library_id: str,
    document_id: str,
    version: int,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Make an older immutable original the current document as a new version."""
    try:
        store.get_library(library_id, _auth, write=True)
        versions = store.list_document_versions(library_id, document_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error
    source = next((item for item in versions if item["version"] == version), None)
    if source is None:
        raise HTTPException(status_code=404, detail="Versione non trovata")

    storage_root = Path(cfg.LIBRARY_STORAGE_DIR).resolve()
    source_path = resolve_storage_path(source["storage_path"], cfg.LIBRARY_STORAGE_DIR)
    try:
        source_path.resolve().relative_to(storage_root)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Percorso originale non valido") from error
    if not source_path.is_file():
        raise HTTPException(status_code=409, detail="Originale della versione non disponibile")

    content = source_path.read_bytes()
    try:
        source_units = extract_source_units(source["filename"], content)
    except DocumentParseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not source_units:
        raise HTTPException(status_code=422, detail="La versione non contiene testo estraibile")
    return store.add_document(
        library_id=library_id,
        filename=source["filename"],
        media_type=source["media_type"],
        content=content,
        storage_path=str(source_path),
        extracted_text="\n\n".join(unit.text for unit in source_units),
        source_units=len(source_units),
        chunks=chunk_source_units(source_units),
    )
