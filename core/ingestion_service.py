"""Local persistent ingestion worker for the Ermes v0.1 library flow."""
from __future__ import annotations

from pathlib import Path

from config import cfg
from core.document_parser import chunk_source_units, DocumentParseError, extract_source_units
from core.library_embeddings import embed_texts
from core.library_store import LibraryStore


def process_ingestion_job(store: LibraryStore, job_id: str, storage_root: str | Path) -> None:
    """Parse one claimed job. It never exposes a partially built index."""
    job = store.claim_ingestion_job(job_id)
    if job is None:
        return
    document_id = job.get("document_id")
    try:
        if not document_id:
            raise DocumentParseError("Job senza documento associato")
        document = store.get_document(job["library_id"], document_id)
        path = Path(document["storage_path"])
        path.resolve().relative_to(Path(storage_root).resolve())
        if not path.is_file():
            raise DocumentParseError("Originale non disponibile")
        units = extract_source_units(document["filename"], path.read_bytes())
        if not units:
            raise DocumentParseError("Il documento non contiene testo estraibile")
        chunks = chunk_source_units(units)
        store.replace_document_index(
            job["library_id"], document_id,
            "\n\n".join(unit.text for unit in units), len(units), chunks,
        )
        embeddings = embed_texts([text for text, _ in chunks])
        if embeddings:
            store.store_chunk_embeddings(job["library_id"], document_id, embeddings, cfg.EMBED_MODEL_ID)
        store.finish_ingestion_job(job_id, "ready", document_id=document_id)
    except Exception as error:
        if document_id:
            store.mark_document_status(job["library_id"], document_id, "failed")
        message = str(error) if isinstance(error, DocumentParseError) else "Errore durante l'indicizzazione"
        store.finish_ingestion_job(job_id, "failed", document_id=document_id, error_message=message)
