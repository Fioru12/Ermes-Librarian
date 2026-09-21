"""Unit and integration tests for core/distributed_worker.py."""

from pathlib import Path

from core.distributed_worker import DistributedIngestionWorker
from core.library_store import LibraryStore
from tests.test_ingestion_service import _seed_document


def test_claim_next_ingestion_job_fifo_and_atomicity(tmp_path: Path):
    store = LibraryStore(tmp_path / "test_worker.sqlite3")
    lib, doc1 = _seed_document(store, tmp_path, "doc1.md", b"# Doc 1\nContenuto del primo documento.")
    _, doc2 = _seed_document(store, tmp_path, "doc2.md", b"# Doc 2\nContenuto del secondo documento.")

    # Inizialmente entrambi sono in stato 'queued'
    pending = store.pending_ingestion_jobs()
    assert len(pending) == 2

    # Primo claim: deve prendere doc1 (FIFO)
    claimed1 = store.claim_next_ingestion_job("worker-a")
    assert claimed1 is not None
    assert claimed1["id"] == doc1["job_id"]
    assert claimed1["status"] == "processing"

    # Secondo claim: deve prendere doc2
    claimed2 = store.claim_next_ingestion_job("worker-b")
    assert claimed2 is not None
    assert claimed2["id"] == doc2["job_id"]
    assert claimed2["status"] == "processing"

    # Terzo claim: coda vuota, deve restituire None
    claimed3 = store.claim_next_ingestion_job("worker-a")
    assert claimed3 is None


def test_distributed_worker_run_once(tmp_path: Path):
    store = LibraryStore(tmp_path / "test_worker_run.sqlite3")
    lib, doc1 = _seed_document(store, tmp_path, "file1.md", b"# File 1\nTesto per l'indicizzazione.")
    _, doc2 = _seed_document(store, tmp_path, "file2.md", b"# File 2\nAltro testo per l'indicizzazione.")

    worker = DistributedIngestionWorker(
        store=store,
        storage_root=tmp_path,
        worker_id="test-worker-1",
        concurrency=2,
    )

    initial_stats = worker.stats()
    assert initial_stats["worker_id"] == "test-worker-1"
    assert initial_stats["processed_count"] == 0
    assert initial_stats["error_count"] == 0

    processed_count = worker.run_once()
    assert processed_count == 2

    # Verifica che entrambi i job siano completati con successo
    job1 = store.get_ingestion_job(doc1["job_id"])
    job2 = store.get_ingestion_job(doc2["job_id"])
    assert job1["status"] == "ready"
    assert job2["status"] == "ready"

    # Verifica stats aggiornate
    final_stats = worker.stats()
    assert final_stats["processed_count"] == 2
    assert final_stats["error_count"] == 0
    assert final_stats["active_jobs_count"] == 0


def test_distributed_worker_graceful_stop(tmp_path: Path):
    store = LibraryStore(tmp_path / "test_worker_stop.sqlite3")
    worker = DistributedIngestionWorker(
        store=store,
        storage_root=tmp_path,
        concurrency=1,
    )
    assert worker.stats()["is_running"] is True
    worker.stop()
    assert worker.stats()["is_running"] is False
