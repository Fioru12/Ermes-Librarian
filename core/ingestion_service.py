"""Local persistent ingestion worker for the Ermes v0.1 library flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config import cfg
from core.document_parser import DocumentParseError, chunk_source_units, extract_source_units
from core.library_embeddings import embed_texts
from core.library_store import LibraryStore, resolve_storage_path


@dataclass(frozen=True)
class IngestionOutcome:
    """Cosa e' successo al job, per chi decide se riprovare.

    `transient` e' True quando la causa non sta nel documento: un modello di
    embedding irraggiungibile, un errore di I/O, un'eccezione inattesa.
    Un documento illeggibile (DocumentParseError) non e' transitorio —
    riprovarlo produrrebbe lo stesso errore.
    """

    status: str  # "ready" | "failed" | "skipped"
    transient: bool = False
    error: str = ""


def process_ingestion_job(store: LibraryStore, job_id: str, storage_root: str | Path) -> IngestionOutcome:
    """Parse one claimed job. It never exposes a partially built index."""
    job = store.claim_ingestion_job(job_id)
    if job is None:
        return IngestionOutcome("skipped")
    document_id = job.get("document_id")
    try:
        if not document_id:
            raise DocumentParseError("Job senza documento associato")
        document = store.get_document(job["library_id"], document_id)
        storage_path = document["storage_path"]
        raw_bytes: bytes
        try:
            from core.storage_backend import get_storage_backend

            storage_backend = get_storage_backend()
            if storage_backend.exists(storage_path):
                raw_bytes = storage_backend.read_bytes(storage_path)
            else:
                path = resolve_storage_path(storage_path, storage_root)
                path.resolve().relative_to(Path(storage_root).resolve())
                if not path.is_file():
                    raise DocumentParseError("Originale non disponibile")
                raw_bytes = path.read_bytes()
        except DocumentParseError:
            raise
        except Exception as err:
            raise DocumentParseError(f"Originale non accessibile o percorso non valido: {err}") from err

        units = extract_source_units(document["filename"], raw_bytes)
        if not units:
            raise DocumentParseError("Il documento non contiene testo estraibile")
        chunks = chunk_source_units(units)
        store.replace_document_index(
            job["library_id"],
            document_id,
            "\n\n".join(unit.text for unit in units),
            len(units),
            chunks,
        )
        embeddings = embed_texts([text for text, _ in chunks])
        if embeddings:
            store.store_chunk_embeddings(job["library_id"], document_id, embeddings, cfg.EMBED_MODEL_ID)
        store.finish_ingestion_job(job_id, "ready", document_id=document_id)
        _record_job_metric("ready")
        return IngestionOutcome("ready")
    except Exception as error:
        if document_id:
            store.mark_document_status(job["library_id"], document_id, "failed")
        transient = not isinstance(error, DocumentParseError)
        message = str(error) if isinstance(error, DocumentParseError) else "Errore durante l'indicizzazione"
        store.finish_ingestion_job(job_id, "failed", document_id=document_id, error_message=message)
        _record_job_metric("failed")
        return IngestionOutcome("failed", transient=transient, error=message)


def _record_job_metric(status: str) -> None:
    """Metrica best-effort: un problema di observability non deve rompere l'ingestione."""
    try:
        from core.metrics import INGESTION_JOBS

        INGESTION_JOBS.labels(status=status).inc()
    except Exception:  # pragma: no cover - solo se prometheus_client manca
        pass
