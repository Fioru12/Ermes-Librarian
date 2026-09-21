"""Standalone distributed ingestion worker daemon for Ermes library jobs.

Designed to run in decoupled environments (separate background processes,
Docker containers, Kubernetes worker pods) to scale document indexing
without impacting the FastAPI request/response loop.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import signal
import socket
import threading
import uuid
from pathlib import Path

from config import cfg
from core.ingestion_service import IngestionOutcome, process_claimed_job
from core.library_store import LibraryStore

logger = logging.getLogger("ermes.distributed_worker")


class DistributedIngestionWorker:
    """Decoupled ingestion worker that atomically claims and processes jobs from the database queue."""

    def __init__(
        self,
        store: LibraryStore,
        storage_root: str | Path,
        worker_id: str | None = None,
        concurrency: int | None = None,
        poll_interval: float = 1.0,
        max_attempts: int | None = None,
        retry_delay: float | None = None,
    ) -> None:
        self.store = store
        self.storage_root = Path(storage_root)
        self.worker_id = worker_id or f"worker-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.concurrency = max(1, concurrency or int(getattr(cfg, "INGESTION_WORKERS", 2)))
        self.poll_interval = max(0.1, poll_interval)
        self.max_attempts = max_attempts or int(getattr(cfg, "INGESTION_MAX_ATTEMPTS", 3))
        self.retry_delay = retry_delay if retry_delay is not None else float(getattr(cfg, "INGESTION_RETRY_SECONDS", 5))

        self._stop_event = threading.Event()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.concurrency,
            thread_name_prefix=f"{self.worker_id}-task",
        )
        self._lock = threading.Lock()
        self._active_jobs: set[str] = set()
        self._processed_count = 0
        self._error_count = 0

    def stats(self) -> dict:
        """Restituisce le statistiche runtime del worker."""
        with self._lock:
            return {
                "worker_id": self.worker_id,
                "concurrency": self.concurrency,
                "active_jobs_count": len(self._active_jobs),
                "active_job_ids": list(self._active_jobs),
                "processed_count": self._processed_count,
                "error_count": self._error_count,
                "is_running": not self._stop_event.is_set(),
            }

    def run_once(self) -> int:
        """Elabora tutti i job attualmente in coda fino ad esaurimento, restituendo il numero di job eseguiti."""
        executed = 0
        while not self._stop_event.is_set():
            job = self.store.claim_next_ingestion_job(self.worker_id)
            if not job:
                break
            self._handle_job(job)
            executed += 1
        return executed

    def run_forever(self) -> None:
        """Avvia il loop del worker e attende i segnali di arresto del sistema (SIGINT, SIGTERM)."""
        logger.info(
            "Avvio DistributedIngestionWorker %s (concorrenza=%d, polling=%.1fs, root=%s)",
            self.worker_id,
            self.concurrency,
            self.poll_interval,
            self.storage_root,
        )

        def _signal_handler(signum, frame):  # noqa: ANN001
            logger.info("Ricevuto segnale %s, avvio graceful shutdown...", signum)
            self.stop()

        try:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        except (ValueError, AttributeError):
            # In thread secondari o su ambienti particolari
            pass

        # Recupera job interrotti da crash precedenti
        recovered = self.store.recover_stale_ingestion_jobs()
        if recovered:
            logger.warning("Recuperati %d job in sospeso da esecuzioni precedenti", recovered)

        futures: list[concurrent.futures.Future] = []

        while not self._stop_event.is_set():
            # Rimuove future completati
            futures = [f for f in futures if not f.done()]

            # Se abbiamo slot liberi, tenta di reclamare un nuovo job
            while len(futures) < self.concurrency and not self._stop_event.is_set():
                job = self.store.claim_next_ingestion_job(self.worker_id)
                if not job:
                    break
                job_id = job["id"]
                with self._lock:
                    self._active_jobs.add(job_id)
                future = self._executor.submit(self._handle_job_wrapper, job)
                futures.append(future)

            # Polling backoff se non ci sono job o la capacità è satura
            self._stop_event.wait(self.poll_interval)

        logger.info("Attesa completamento job in corso (%d rimasti)...", len(futures))
        concurrent.futures.wait(futures, timeout=30.0)
        self._executor.shutdown(wait=True)
        logger.info("Worker %s terminato con successo.", self.worker_id)

    def stop(self) -> None:
        """Richiede l'arresto del worker."""
        self._stop_event.set()

    def _handle_job_wrapper(self, job: dict) -> IngestionOutcome:
        job_id = job["id"]
        try:
            return self._handle_job(job)
        finally:
            with self._lock:
                self._active_jobs.discard(job_id)

    def _handle_job(self, job: dict) -> IngestionOutcome:
        job_id = job["id"]
        logger.info("Elaborazione job %s (doc=%s, file=%s)", job_id, job.get("document_id"), job.get("filename"))
        outcome = process_claimed_job(self.store, job, self.storage_root)

        with self._lock:
            if outcome.status == "ready":
                self._processed_count += 1
            else:
                self._error_count += 1

        if outcome.status == "failed":
            if outcome.transient:
                if self.store.requeue_ingestion_job(job_id, self.max_attempts):
                    updated_job = self.store.get_ingestion_job(job_id) or {}
                    attempts = updated_job.get("attempts", "?")
                    logger.warning(
                        "Job %s fallito per causa transitoria (%s). Re-accodato: tentativo %s/%d fra %.1fs",
                        job_id,
                        outcome.error,
                        attempts,
                        self.max_attempts,
                        self.retry_delay,
                    )
                else:
                    logger.error("Job %s fallito e tentativi esauriti: inviato in DLQ (%s)", job_id, outcome.error)
                    self.store.move_to_dead_letter(
                        job_id, f"Tentativi esauriti ({self.max_attempts}): {outcome.error}"
                    )
            else:
                logger.error("Job %s fallito per errore permanente: inviato in DLQ (%s)", job_id, outcome.error)
                self.store.move_to_dead_letter(job_id, f"Errore permanente: {outcome.error}")

        return outcome
