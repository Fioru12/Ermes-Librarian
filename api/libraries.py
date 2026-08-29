"""Libraries and document inventory endpoints for Ermes Knowledge."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key
from config import cfg
from core.document_parser import DocumentParseError, chunk_source_units, extract_source_units
from core.document_summary import summarize_document
from core.evidence_assistant import answer_from_evidence
from core.folder_importer import scan_import_source
from core.governance import append_audit
from core.ingestion_service import process_ingestion_job
from core.input_validator import matches_expected_file_signature, sanitize_upload_name
from core.library_embeddings import embed_texts
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


class ImportSourceRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class ChatIntegrationRequest(BaseModel):
    platform: Literal["slack", "teams"]
    external_channel_id: str = Field(min_length=1, max_length=500)


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

@router.get("/index-consistency")
def library_index_consistency(
    _auth: dict = Depends(_require_role("admin")),
    store: LibraryStore = Depends(get_library_store),
):
    """Diagnostica di allineamento tra DB, originali e vettori (solo admin)."""
    report = store.verify_index_consistency(cfg.LIBRARY_STORAGE_DIR, cfg.EMBED_MODEL_ID)
    return report


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


@router.get("/{library_id}/documents/{document_id}")
def get_document_detail(
    library_id: str,
    document_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Dettaglio di un documento: usato per il polling dello stato di indicizzazione."""
    try:
        return store.get_document(library_id, document_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error


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


def _answer_question(store: LibraryStore, library_id: str, question: str, top_k: int, actor: dict) -> dict:
    """Evidence-first assistant baseline, intentionally abstaining without sources.

    Shared by the HTTP `/ask` endpoint and the chat webhooks (Slack/Teams):
    both must go through the same access checks and the same evidence-only
    guarantee, so this is the only place that logic is allowed to live.
    """
    try:
        library = store.get_library(library_id, actor)
        citations, retrieval_profile = store.search_with_profile(library_id, question, limit=top_k, actor=actor)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if not citations:
        return {
            "answer_id": str(uuid.uuid4()),
            "library": {"id": library["id"], "name": library["name"]},
            "question": question,
            "answer": "Non ho trovato evidenza sufficiente nella biblioteca selezionata. Prova con parole più specifiche oppure carica il documento pertinente.",
            "status": "abstained",
            "evidence": {"coverage": "insufficient_evidence", "reason": "Nessun passaggio corrispondente recuperato."},
            "citations": [],
            "meta": {"assistant_mode": library["assistant_mode"], "assistant_provider": library.get("assistant_provider", ""), "retrieval_profile": retrieval_profile, "created_at": datetime.now(UTC).isoformat()},
        }
    answer, coverage, reason = answer_from_evidence(
        question, citations, mode=library["assistant_mode"], provider_name=library.get("assistant_provider", ""),
    )
    append_audit(
        cfg.AUDIT_FILE, "library_answer", actor["username"],
        {"library_id": library_id, "assistant_mode": library["assistant_mode"], "assistant_provider": library.get("assistant_provider", ""), "retrieval_profile": retrieval_profile["mode"], "citation_count": len(citations), "coverage": coverage},
    )
    return {
        "answer_id": str(uuid.uuid4()),
        "library": {"id": library["id"], "name": library["name"]},
        "question": question,
        "answer": answer,
        "status": "answered" if coverage == "supported" else "abstained",
        "evidence": {"coverage": coverage, "reason": reason},
        "citations": [item["citation"] | {"excerpt": item["excerpt"], "marker": index, "relevance_score": item["relevance_score"]} for index, item in enumerate(citations, start=1)],
        "meta": {"assistant_mode": library["assistant_mode"], "assistant_provider": library.get("assistant_provider", ""), "retrieval_profile": retrieval_profile, "created_at": datetime.now(UTC).isoformat()},
    }


@router.post("/{library_id}/ask")
def ask_library(
    library_id: str,
    request: AskLibraryRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    return _answer_question(store, library_id, request.question, request.top_k, _auth)


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


def _unlink_storage_paths(paths: list[str], root: str | Path | None = None) -> None:
    """Unlink storage files returned by the store, never outside the root.

    The storage root is owned by the API layer (same boundary as reindex);
    path safety mirrors resolve_storage_path + relative_to there. `root`
    defaults to the configured storage dir; tests may pass a narrower root.
    """
    root = Path(root or cfg.LIBRARY_STORAGE_DIR).resolve()
    for rel in paths:
        try:
            target = resolve_storage_path(rel, cfg.LIBRARY_STORAGE_DIR)
            target.resolve().relative_to(root)
        except (ValueError, OSError):
            continue
        try:
            target.unlink(missing_ok=True)
        except OSError:
            continue
        parent = target.parent
        for _ in range(3):
            if parent == root or root not in parent.parents:
                break
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


@router.delete("/{library_id}/documents/{document_id}", status_code=204)
def delete_library_document(
    library_id: str,
    document_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Rimuove un documento con chunk, versioni, ACL e file originali."""
    try:
        store.get_library(library_id, _auth, write=True)
        paths = store.delete_document(library_id, document_id)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error
    _unlink_storage_paths(paths)
    append_audit(cfg.AUDIT_FILE, "library_document_deleted", _auth["username"], {"library_id": library_id, "document_id": document_id})


@router.delete("/{library_id}", status_code=204)
def delete_library(
    library_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Elimina l'intera biblioteca. Solo il proprietario o un admin globale."""
    try:
        library = store.get_library(library_id, _auth, write=True)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if library["access_role"] != "owner" and _auth.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo il proprietario puo' eliminare la biblioteca")
    paths = store.delete_library(library_id)
    _unlink_storage_paths(paths)
    append_audit(cfg.AUDIT_FILE, "library_deleted", _auth["username"], {"library_id": library_id, "name": library["name"]})


@router.get("/{library_id}/sources")
def list_library_sources(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        return {"items": store.list_import_sources(library_id)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


def _reject_source_path_inside_app(path: str) -> None:
    """Refuse a registered import source that resolves inside the app's own tree.

    Found by review, not in the wild: with no restriction here, any editor of
    ANY library could register another library's storage directory
    (storage/libraries/<other-id>/) as a "folder source" for their own
    library and scan it in — the confidential document would be imported
    verbatim, fully readable via the importing library's own citations. That
    is a complete bypass of the product's central guarantee ("retrieval never
    crosses a library boundary"), reachable without ever touching the normal
    read path the isolation tests actually cover.

    This check is independent of the role gate below: it holds even for a
    library's own owner, because there is no legitimate reason a folder
    source should ever point inside data the application itself manages
    (storage/, data/, security/, docs/, the source tree). A folder source
    exists to pull in an *external* network drop folder.
    """
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Percorso non valido") from error
    app_root = Path(cfg.BASE_DIR).resolve()
    if resolved == app_root or app_root in resolved.parents:
        raise HTTPException(
            status_code=422,
            detail="Il percorso non puo' trovarsi dentro la directory dell'applicazione",
        )


def _require_library_owner_or_admin(store: LibraryStore, library_id: str, actor: dict) -> dict:
    """Import sources grant the server filesystem read access on the actor's say-so.

    That is a materially larger blast radius than uploading through the
    browser, so registering or removing one requires the same trust level as
    deleting the library outright (owner or global admin) — not just
    "editor", which any collaborator added to a shared library can be.
    """
    library = store.get_library(library_id, actor, write=True)
    if library["access_role"] != "owner" and actor.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo il proprietario o un amministratore possono gestire le sorgenti cartella")
    return library


@router.post("/{library_id}/sources", status_code=201)
def add_library_source(
    library_id: str,
    request: ImportSourceRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Registra una cartella da cui importare documenti (solo percorso, mai credenziali)."""
    path = request.path.strip()
    if not path:
        raise HTTPException(status_code=422, detail="Indica il percorso della cartella")
    _reject_source_path_inside_app(path)
    try:
        _require_library_owner_or_admin(store, library_id, _auth)
        source = store.add_import_source(library_id, path, created_by=_auth["username"])
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    append_audit(cfg.AUDIT_FILE, "import_source_added", _auth["username"], {"library_id": library_id, "path": source["path"]})
    return source


@router.delete("/{library_id}/sources/{source_id}")
def remove_library_source(
    library_id: str,
    source_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        _require_library_owner_or_admin(store, library_id, _auth)
        removed = store.remove_import_source(library_id, source_id)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if not removed:
        raise HTTPException(status_code=404, detail="Sorgente non trovata")
    append_audit(cfg.AUDIT_FILE, "import_source_removed", _auth["username"], {"library_id": library_id, "source_id": source_id})
    return {"removed": True}


@router.post("/{library_id}/sources/{source_id}/scan")
def scan_library_source(
    library_id: str,
    source_id: str,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Scansiona la cartella e importa i nuovi documenti (dedup per contenuto)."""
    try:
        store.get_library(library_id, _auth, write=True)
        source = store.get_import_source_by_id(library_id, source_id)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Sorgente non trovata") from error
    result = scan_import_source(store, library_id, source, cfg.LIBRARY_STORAGE_DIR)
    for imported in result["imported"]:
        background_tasks.add_task(process_ingestion_job, store, imported["job_id"], cfg.LIBRARY_STORAGE_DIR)
    append_audit(
        cfg.AUDIT_FILE, "import_source_scanned", _auth["username"],
        {"library_id": library_id, "source_id": source_id, "imported": len(result["imported"]),
         "skipped_duplicates": len(result["skipped_duplicates"]), "failed": len(result["failed"])},
    )
    return result


@router.get("/{library_id}/integrations")
def list_library_chat_integrations(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        return {"items": store.list_chat_integrations(library_id)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.post("/{library_id}/integrations", status_code=201)
def add_library_chat_integration(
    library_id: str,
    request: ChatIntegrationRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Collega un canale Slack/Teams a questa biblioteca (nessuna credenziale
    di piattaforma qui: solo l'id del canale che potrà interrogarla)."""
    try:
        _require_library_owner_or_admin(store, library_id, _auth)
        integration = store.add_chat_integration(
            library_id, request.platform, request.external_channel_id, created_by=_auth["username"],
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    append_audit(
        cfg.AUDIT_FILE, "chat_integration_added", _auth["username"],
        {"library_id": library_id, "platform": integration["platform"], "external_channel_id": integration["external_channel_id"]},
    )
    return integration


@router.delete("/{library_id}/integrations/{integration_id}")
def remove_library_chat_integration(
    library_id: str,
    integration_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        _require_library_owner_or_admin(store, library_id, _auth)
        removed = store.remove_chat_integration(library_id, integration_id)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if not removed:
        raise HTTPException(status_code=404, detail="Collegamento non trovato")
    append_audit(cfg.AUDIT_FILE, "chat_integration_removed", _auth["username"], {"library_id": library_id, "integration_id": integration_id})
    return {"removed": True}


@router.get("/{library_id}/documents/{document_id}/search")
def search_single_document(
    library_id: str,
    document_id: str,
    q: str = "",
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Ricerca limitata a un documento, con lo stesso ACL della lettura."""
    if len(q.strip()) < 2:
        raise HTTPException(status_code=422, detail="Inserisci almeno 2 caratteri per cercare")
    try:
        store.get_document(library_id, document_id, actor=_auth)
        items, retrieval_profile = store.search_with_profile(library_id, q, limit=50, actor=_auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error
    filtered = [item for item in items if item["document_id"] == document_id]
    return {"items": filtered, "retrieval_profile": retrieval_profile}


@router.get("/{library_id}/documents/{document_id}/summary")
def summarize_library_document(
    library_id: str,
    document_id: str,
    use_llm: bool = True,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Riassunto evidence-bound di un documento, rispettando l'ACL per-documento.

    `use_llm` e' un'opzione del chiamante per rinunciare al generativo anche
    quando la biblioteca lo permetterebbe (preferire il riassunto estrattivo
    deterministico), mai per attivarlo. In modalita' evidence_only nessun
    modello deve vedere il contenuto del documento — e' il primo principio
    dichiarato del prodotto — quindi qui viene ignorato lato server, non
    fidandosi del client: la UI chiamava questo endpoint senza mai passare
    il parametro, e ogni riassunto passava per Ollama a prescindere dalla
    policy scelta dal proprietario della biblioteca.
    """
    try:
        library = store.get_library(library_id, _auth)
        document = store.get_document(library_id, document_id, actor=_auth)
        chunks = store.get_document_chunks(library_id, document_id, actor=_auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error
    use_local_llm = use_llm and library["assistant_mode"] != "evidence_only"
    result = summarize_document(document["filename"], chunks, use_local_llm=use_local_llm)
    append_audit(
        cfg.AUDIT_FILE, "document_summary", _auth["username"],
        {"library_id": library_id, "document_id": document_id, "status": result["status"], "mode": result["mode"]},
    )
    return {
        "document": {"id": document["id"], "filename": document["filename"], "version": document.get("version")},
        **result,
    }


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

    try:
        chunks = chunk_source_units(source_units)
        result = store.replace_document_index(
            library_id=library_id,
            document_id=document_id,
            extracted_text="\n\n".join(unit.text for unit in source_units),
            source_units=len(source_units),
            chunks=chunks,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail="Impossibile ricostruire l'indice del documento") from error

    # Allineato a core/ingestion_service.py: replace_document_index ricrea i
    # chunk da zero (embedding_json persi), quindi il profilo semantico va
    # ricalcolato qui, altrimenti un reindex degraderebbe silenziosamente la
    # biblioteca da "hybrid_local" a "keyword".
    embeddings = embed_texts([text for text, _ in chunks])
    if embeddings:
        store.store_chunk_embeddings(library_id, document_id, embeddings, cfg.EMBED_MODEL_ID)

    return result


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
