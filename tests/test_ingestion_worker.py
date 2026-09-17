"""La politica attorno all'indicizzazione: concorrenza, retry, recupero.

`process_ingestion_job` sa indicizzare un documento. Cio' che mancava era
cosa fare quando cento arrivano insieme, quando fallisce per una causa
esterna, e quando un crash lascia un job a meta'. `recover_stale_ingestion_jobs`
esisteva con "Startup calls this" nella docstring, e nessuno la chiamava.
"""

import threading
import time
from pathlib import Path

import pytest

import config
from core import ingestion_service, ingestion_worker
from core.ingestion_worker import recover_on_startup, run_ingestion_job
from core.library_store import LibraryStore
from tests.test_ingestion_service import _seed_document


@pytest.fixture
def veloce(monkeypatch):
    """Retry immediato e config esplicita: il test non deve aspettare 5 s."""
    monkeypatch.setattr(
        "config.cfg",
        config.cfg.replace(INGESTION_WORKERS=2, INGESTION_MAX_ATTEMPTS=3, INGESTION_RETRY_SECONDS=0.05),
    )
    monkeypatch.setattr(ingestion_worker, "cfg", config.cfg)
    ingestion_worker._semaphore = None


def _attendi(store, job_id, stato, timeout=5.0):
    fine = time.time() + timeout
    while time.time() < fine:
        job = store.get_ingestion_job(job_id)
        if job and job["status"] == stato:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} non ha raggiunto '{stato}': {store.get_ingestion_job(job_id)}")


def test_a_transient_failure_is_retried_and_then_succeeds(tmp_path: Path, veloce, monkeypatch):
    store = LibraryStore(tmp_path / "jobs.sqlite3")
    library, document = _seed_document(store, tmp_path, "ok.md", b"# Titolo\nTesto sufficiente per un chunk.")
    chiamate = {"n": 0}
    originale = ingestion_service.embed_texts

    def embed_instabile(texts):
        chiamate["n"] += 1
        if chiamate["n"] == 1:
            raise ConnectionError("Ollama irraggiungibile")
        return originale(texts)

    monkeypatch.setattr(ingestion_service, "embed_texts", embed_instabile)

    primo = run_ingestion_job(store, document["job_id"], tmp_path)
    assert primo.status == "failed" and primo.transient

    job = _attendi(store, document["job_id"], "ready")
    assert job["attempts"] == 1
    assert store.get_document(library["id"], document["id"])["status"] == "ready"


def test_an_unreadable_document_is_not_retried(tmp_path: Path, veloce):
    store = LibraryStore(tmp_path / "jobs.sqlite3")
    _, document = _seed_document(store, tmp_path, "vuoto.md", b"")

    esito = run_ingestion_job(store, document["job_id"], tmp_path)

    assert esito.status == "failed" and not esito.transient
    time.sleep(0.2)
    job = store.get_ingestion_job(document["job_id"])
    assert job["status"] == "failed" and job["attempts"] == 0


def test_attempts_are_capped(tmp_path: Path, veloce, monkeypatch):
    store = LibraryStore(tmp_path / "jobs.sqlite3")
    _, document = _seed_document(store, tmp_path, "mai.md", b"# Titolo\nTesto sufficiente per un chunk.")
    monkeypatch.setattr(ingestion_service, "embed_texts", lambda texts: (_ for _ in ()).throw(OSError("disco")))

    run_ingestion_job(store, document["job_id"], tmp_path)
    fine = time.time() + 3
    while time.time() < fine:
        job = store.get_ingestion_job(document["job_id"])
        if job["status"] == "failed" and job["attempts"] == 2:
            break
        time.sleep(0.02)
    time.sleep(0.2)  # nessun ulteriore tentativo oltre il limite
    job = store.get_ingestion_job(document["job_id"])
    assert job["status"] == "failed" and job["attempts"] == 2  # 3 tentativi totali = 2 requeue


def test_concurrency_is_bounded(tmp_path: Path, veloce, monkeypatch):
    store = LibraryStore(tmp_path / "jobs.sqlite3")
    jobs = [_seed_document(store, tmp_path, f"d{i}.md", b"# T\nTesto sufficiente.")[1]["job_id"] for i in range(6)]
    attivi = {"ora": 0, "max": 0}
    lock = threading.Lock()

    def lento(texts):
        with lock:
            attivi["ora"] += 1
            attivi["max"] = max(attivi["max"], attivi["ora"])
        time.sleep(0.05)
        with lock:
            attivi["ora"] -= 1
        return []

    monkeypatch.setattr(ingestion_service, "embed_texts", lento)
    fili = [threading.Thread(target=run_ingestion_job, args=(store, j, tmp_path)) for j in jobs]
    for f in fili:
        f.start()
    for f in fili:
        f.join()

    assert attivi["max"] <= 2
    assert all(store.get_ingestion_job(j)["status"] == "ready" for j in jobs)


def test_startup_requeues_jobs_interrupted_mid_processing(tmp_path: Path, veloce):
    store = LibraryStore(tmp_path / "jobs.sqlite3")
    _, document = _seed_document(store, tmp_path, "crash.md", b"# T\nTesto sufficiente.")
    assert store.claim_ingestion_job(document["job_id"]) is not None  # "processing", poi crash

    da_eseguire = recover_on_startup(store, tmp_path)

    assert da_eseguire == [document["job_id"]]
    assert store.get_ingestion_job(document["job_id"])["status"] == "queued"
    assert store.ingestion_queue_stats()["queued"] == 1
