"""Document endpoints: inventory, download, upload, ingestion jobs, ACL, reindex, restore, summary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key, rate_limited
from api.libraries.common import _require_library_member_manager, _unlink_storage_paths, get_library_store
from config import cfg
from core.document_parser import DocumentParseError, chunk_source_units, extract_source_units
from core.document_summary import summarize_document
from core.governance import append_audit
from core.ingestion_worker import run_ingestion_job
from core.input_validator import (
    validate_and_scan_document,
)
from core.library_embeddings import embed_texts
from core.library_store import (
    LibraryAccessError,
    LibraryNotFoundError,
    LibraryStore,
    resolve_storage_path,
    storage_relative_path,
)
from core.storage_provider import get_storage_provider

router = APIRouter(prefix="/api/libraries", tags=["Libraries"])


class DocumentAclRequest(BaseModel):
    """Allow-list dei nomi utente che possono vedere il documento.

    Lista vuota = nessuna restrizione oltre a quelle della libreria.
    """

    usernames: list[str] = Field(default_factory=list, max_length=100)


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


@router.get("/{library_id}/documents/{document_id}/download-url")
def get_document_download_url(
    library_id: str,
    document_id: str,
    expires_seconds: int = Query(default=3600, ge=60, le=86400),
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Restituisce un URL pre-firmato S3/MinIO per scaricare il documento direttamente dallo storage."""
    try:
        store.get_library(library_id, _auth)
        document = store.get_document(library_id, document_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error

    storage_provider = get_storage_provider()
    presigned_url = storage_provider.get_url(document["storage_path"], expires_seconds=expires_seconds)
    if not presigned_url:
        return {
            "mode": "proxied",
            "download_url": f"/api/libraries/{library_id}/documents/{document_id}/download",
            "expires_in": expires_seconds,
            "filename": document["filename"],
        }
    return {
        "mode": "presigned",
        "download_url": presigned_url,
        "expires_in": expires_seconds,
        "filename": document["filename"],
    }


@router.get("/{library_id}/documents/{document_id}/download")
def download_document(
    library_id: str,
    document_id: str,
    redirect: bool = Query(default=False),
    inline: bool = Query(default=False),
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Serve the current immutable original only after the library access check."""
    try:
        store.get_library(library_id, _auth)
        document = store.get_document(library_id, document_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error

    storage_provider = get_storage_provider()

    # Se richiesto il redirect e disponibile un presigned URL diretto
    if redirect:
        presigned_url = storage_provider.get_url(document["storage_path"], expires_seconds=3600)
        if presigned_url:
            return RedirectResponse(url=presigned_url, status_code=307)

    # Altrimenti leggiamo via storage provider (supporta S3, filesystem e decifratura trasparente)
    try:
        data = storage_provider.get(document["storage_path"])
    except FileNotFoundError as error:
        # Fallback locale per retrocompatibilità
        source_path = resolve_storage_path(document["storage_path"], cfg.LIBRARY_STORAGE_DIR)
        if source_path.is_file():
            data = source_path.read_bytes()
        else:
            raise HTTPException(status_code=404, detail="Originale non disponibile nello storage") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Errore lettura storage: {error}") from error

    append_audit(
        cfg.AUDIT_FILE,
        "document_downloaded",
        _auth["username"],
        {
            "library_id": library_id,
            "document_id": document_id,
            "filename": document["filename"],
            "version": document["version"],
            "inline": inline,
        },
    )
    media_type = document.get("media_type") or "application/octet-stream"
    encoded_filename = quote(document["filename"])
    # Il tipo del file lo dichiara chi lo carica: non ci si puo' fidare per mostrarlo nella
    # pagina. "Inline" (visualizzatore PDF) solo per un PDF vero, riconosciuto da estensione
    # e firma `%PDF`, con tipo fisso; qualunque altra cosa e' sempre un download. Altrimenti
    # un `.txt` caricato come `text/html` verrebbe aperto come pagina sotto il dominio dell'app.
    is_real_pdf = document["filename"].lower().endswith(".pdf") and data[:5] == b"%PDF-"
    show_inline = inline and is_real_pdf
    if show_inline:
        media_type = "application/pdf"
    disposition = "inline" if show_inline else "attachment"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_filename}"},
    )


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


@router.get("/{library_id}/ingestion-jobs/{job_id}/progress")
def get_ingestion_job_progress(
    library_id: str,
    job_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        store.get_library(library_id, _auth)
        progress = store.get_job_progress(job_id)
        if not progress or progress["library_id"] != library_id:
            raise HTTPException(status_code=404, detail="Job di indicizzazione non trovato")
        return progress
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.get("/{library_id}/dead-letter-jobs")
def list_dead_letter_jobs(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        store.get_library(library_id, _auth)
        return {"items": store.list_dead_letter_jobs(library_id)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.post("/{library_id}/dead-letter-jobs/{job_id}/reprocess")
def reprocess_dead_letter_job(
    library_id: str,
    job_id: str,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        store.get_library(library_id, _auth, write=True)
        reprocessed = store.reprocess_dead_letter_job(job_id)
        if not reprocessed:
            raise HTTPException(status_code=404, detail="Job non trovato nella Dead-Letter Queue")
        if background_tasks is None:
            background_tasks = BackgroundTasks()
        background_tasks.add_task(run_ingestion_job, store, job_id, cfg.LIBRARY_STORAGE_DIR)
        return {"status": "requeued", "job_id": job_id}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


# Rotte costose: parsing, embedding e generazione. Sono le uniche dove
# un abuso costa risorse reali, quindi le uniche a cui il limitatore
# e' applicato — non globalmente, per non trasformare uno scrape di
# /metrics o una sonda di health in un 429.
@router.post(
    "/{library_id}/documents",
    status_code=201,
    response_model=None,
    dependencies=[Depends(rate_limited)],
)
async def upload_document(
    library_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    content = await file.read((cfg.ADMIN_MAX_UPLOAD_MB * 1024 * 1024) + 1)
    if len(content) > cfg.ADMIN_MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File troppo grande")
    if not content:
        raise HTTPException(status_code=400, detail="File vuoto non supportato")

    is_valid, reason_or_name = validate_and_scan_document(file.filename or "", content)
    if not is_valid:
        raise HTTPException(status_code=400, detail=reason_or_name)
    safe_name = reason_or_name

    from core.antivirus import AntivirusScanError, scan_document

    try:
        scan_res = scan_document(content, filename=safe_name, actor=str(_auth.get("username", "")))
        if not scan_res.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"File malevolo bloccato dall'antivirus: {scan_res.virus_name or 'minaccia rilevata'}",
            )
    except AntivirusScanError as scan_err:
        raise HTTPException(status_code=503, detail=f"Servizio antivirus non disponibile: {scan_err}") from scan_err

    try:
        store.get_library(library_id, _auth, write=True)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error

    document_id = uuid.uuid4().hex
    rel_path = f"{library_id}/{document_id}_{safe_name}"
    storage_provider = get_storage_provider()
    try:
        storage_provider.save(rel_path, content)
    except Exception as error:
        raise HTTPException(status_code=500, detail="Impossibile salvare il file originale") from error
    try:
        document = store.add_document(
            library_id=library_id,
            filename=safe_name,
            media_type=file.content_type or "",
            content=content,
            storage_path=rel_path,
            status="queued",
            chunks=[],
        )
    except Exception as error:
        storage_provider.delete(rel_path)
        raise HTTPException(status_code=500, detail="Impossibile registrare il documento") from error
    job = store.start_ingestion_job(library_id, safe_name, document_id=document["id"])
    if background_tasks is None:  # chiamata diretta senza injection FastAPI
        background_tasks = BackgroundTasks()
    background_tasks.add_task(run_ingestion_job, store, job["id"], cfg.LIBRARY_STORAGE_DIR)
    return {**document, "ingestion_job_id": job["id"], "status": "queued"}


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
    append_audit(
        cfg.AUDIT_FILE,
        "library_document_deleted",
        _auth["username"],
        {"library_id": library_id, "document_id": document_id},
    )


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
        cfg.AUDIT_FILE,
        "document_summary",
        _auth["username"],
        {"library_id": library_id, "document_id": document_id, "status": result["status"], "mode": result["mode"]},
    )
    return {
        "document": {"id": document["id"], "filename": document["filename"], "version": document.get("version")},
        **result,
    }


class ReviewDueRequest(BaseModel):
    # Data ISO (AAAA-MM-GG); vuota per togliere la scadenza.
    review_due: str = Field(default="", max_length=10, pattern=r"^(\d{4}-\d{2}-\d{2})?$")


@router.put("/{library_id}/documents/{document_id}/review-due")
def set_document_review_due(
    library_id: str,
    document_id: str,
    request: ReviewDueRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Data entro cui il documento va rivisto (procedura, DVR, certificato)."""
    try:
        store.get_library(library_id, _auth, write=True)
        store.get_document(library_id, document_id, _auth)
        document = store.set_review_due(library_id, document_id, request.review_due)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Data non valida") from error
    append_audit(
        cfg.AUDIT_FILE,
        "document_review_due_changed",
        _auth["username"],
        {"library_id": library_id, "document_id": document_id, "review_due": request.review_due},
    )
    return {"id": document["id"], "review_due": document.get("review_due", "")}


@router.get("/{library_id}/reviews-due")
def list_documents_due_for_review(
    library_id: str,
    within_days: int = Query(default=30, ge=0, le=365),
    today: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Documenti con revisione scaduta o in scadenza, dal piu' urgente.

    `today` e' la data dell'ufficio mandata dall'interfaccia: il server puo'
    stare in un altro fuso orario. Rispetta i permessi per documento.
    """
    riferimento = today or datetime.now(UTC).date().isoformat()
    try:
        items = store.documents_due_for_review(library_id, _auth, riferimento, within_days)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    return {"items": items, "today": riferimento, "within_days": within_days}


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
            raise HTTPException(
                status_code=403,
                detail="Solo il proprietario o un amministratore possono vedere le restrizioni del documento",
            )
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
        cfg.AUDIT_FILE,
        "document_acl_changed",
        _auth["username"],
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

    storage_provider = get_storage_provider()
    try:
        content = storage_provider.get(document["storage_path"])
    except Exception:
        source_path = resolve_storage_path(document["storage_path"], cfg.LIBRARY_STORAGE_DIR)
        if not source_path.is_file():
            raise HTTPException(status_code=409, detail="Originale non disponibile: impossibile reindicizzare")
        content = source_path.read_bytes()

    try:
        source_units = extract_source_units(document["filename"], content)
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


def _version_content(source: dict) -> bytes:
    """L'originale di una versione, dallo storage o dal disco locale."""
    try:
        return bytes(get_storage_provider().get(source["storage_path"]))
    except Exception:
        source_path = resolve_storage_path(source["storage_path"], cfg.LIBRARY_STORAGE_DIR)
        if not source_path.is_file():
            raise HTTPException(status_code=409, detail="Originale della versione non disponibile") from None
        return source_path.read_bytes()


@router.get("/{library_id}/documents/{document_id}/versions/compare")
def compare_document_versions(
    library_id: str,
    document_id: str,
    from_version: int = Query(alias="from", ge=1),
    to_version: int = Query(alias="to", ge=1),
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Cosa e' cambiato fra due versioni, sezione per sezione (core/version_diff.py).

    Stessi controlli di accesso della lettura del documento, allow-list per
    documento compresa: chi non puo' aprire il documento non ne vede le
    differenze.
    """
    from core.version_diff import compare_units

    try:
        versions = store.list_document_versions(library_id, document_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Documento non trovato") from error
    by_number = {item["version"]: item for item in versions}
    if from_version not in by_number or to_version not in by_number:
        raise HTTPException(status_code=404, detail="Versione non trovata")
    try:
        before = extract_source_units(by_number[from_version]["filename"], _version_content(by_number[from_version]))
        after = extract_source_units(by_number[to_version]["filename"], _version_content(by_number[to_version]))
    except DocumentParseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    changes = compare_units(before, after)
    return {
        "document_id": document_id,
        "from": {"version": from_version, "created_at": by_number[from_version]["created_at"]},
        "to": {"version": to_version, "created_at": by_number[to_version]["created_at"]},
        "identical": not changes,
        "changes": [change.as_dict() for change in changes],
    }


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

    storage_provider = get_storage_provider()
    try:
        content = storage_provider.get(source["storage_path"])
    except Exception:
        source_path = resolve_storage_path(source["storage_path"], cfg.LIBRARY_STORAGE_DIR)
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
        # Relativo allo storage, come per ogni upload: fino al 18 settembre
        # 2026 qui finiva il percorso assoluto della macchina, e un restore su
        # un'altra cartella (backup, container) perdeva l'originale.
        #
        # Il nome file memorizzato (non `source["filename"]`, che e' quello
        # umano e puo' collidere con un altro documento) viene dall'ultimo
        # segmento di `source["storage_path"]`, disponibile in entrambi i
        # rami sopra: `source_path` esiste solo in quello di fallback
        # (storage_provider.get() fallito), e in quello normale non e' mai
        # stato assegnato.
        storage_path=storage_relative_path(library_id, Path(source["storage_path"]).name),
        extracted_text="\n\n".join(unit.text for unit in source_units),
        source_units=len(source_units),
        chunks=chunk_source_units(source_units),
    )
