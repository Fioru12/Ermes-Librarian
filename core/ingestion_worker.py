"""Coda di indicizzazione locale: concorrenza limitata, retry, recupero all'avvio.

Non c'e' un broker. I job sono gia' persistiti in `ingestion_jobs` e
reclamati atomicamente (`claim_ingestion_job`): quello che mancava era la
politica attorno a `process_ingestion_job`:

* un limite alla concorrenza — ogni upload partiva subito in un thread
  proprio, quindi cento upload erano cento parser insieme;
* un secondo tentativo quando la causa e' transitoria (modello di embedding
  irraggiungibile, I/O), e nessun tentativo quando non lo e' (documento
  illeggibile);
* il recupero dei job lasciati in `processing` da un crash:
  `recover_stale_ingestion_jobs` esisteva con la docstring "Startup calls
  this" e nessuno la chiamava.

Un worker separato (processo, container) puo' sostituire questo modulo
senza toccare lo store: il contratto — claim atomico, finish, requeue — e'
gia' quello.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from config import cfg
from core.ingestion_service import IngestionOutcome, process_ingestion_job
from core.library_store import LibraryStore

_logger = logging.getLogger("ermes.ingestion")

_semaphore_guard = threading.Lock()
_semaphore: threading.BoundedSemaphore | None = None
_semaphore_size = 0


def _slots() -> threading.BoundedSemaphore:
    """Semaforo condiviso, ricreato se la configurazione cambia (test)."""
    global _semaphore, _semaphore_size
    size = max(1, int(getattr(cfg, "INGESTION_WORKERS", 2)))
    with _semaphore_guard:
        if _semaphore is None or _semaphore_size != size:
            _semaphore = threading.BoundedSemaphore(size)
            _semaphore_size = size
        return _semaphore


def run_ingestion_job(store: LibraryStore, job_id: str, storage_root: str | Path) -> IngestionOutcome:
    """Esegue un job entro il limite di concorrenza; riprova se transitorio.

    Sostituisce `process_ingestion_job` come callable dato a BackgroundTasks /
    to_thread: la firma e' la stessa, in piu' c'e' la politica.
    """
    with _slots():
        outcome = process_ingestion_job(store, job_id, storage_root)
    if outcome.status == "failed" and outcome.transient:
        max_attempts = int(getattr(cfg, "INGESTION_MAX_ATTEMPTS", 3))
        if store.requeue_ingestion_job(job_id, max_attempts):
            delay = float(getattr(cfg, "INGESTION_RETRY_SECONDS", 5))
            job = store.get_ingestion_job(job_id) or {}
            _logger.warning(
                "Job %s fallito per causa transitoria (%s): nuovo tentativo %s/%s fra %.0fs",
                job_id,
                outcome.error,
                job.get("attempts", "?"),
                max_attempts,
                delay,
            )
            _record_retry_metric()
            timer = threading.Timer(delay, run_ingestion_job, args=(store, job_id, storage_root))
            timer.daemon = True
            timer.start()
        else:
            _logger.error("Job %s fallito e tentativi esauriti: %s", job_id, outcome.error)
    return outcome


def recover_on_startup(store: LibraryStore, storage_root: str | Path) -> list[str]:
    """Rimette in coda i job interrotti e restituisce gli id da eseguire."""
    stale = store.recover_stale_ingestion_jobs()
    if stale:
        _logger.warning("%d job di indicizzazione interrotti da un riavvio: rimessi in coda", stale)
    return [job["id"] for job in store.pending_ingestion_jobs()]


def _record_retry_metric() -> None:
    try:
        from core.metrics import INGESTION_JOBS

        INGESTION_JOBS.labels(status="retried").inc()
    except Exception:  # pragma: no cover
        pass
