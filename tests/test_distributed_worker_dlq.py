"""tests/test_distributed_worker_dlq.py
Unit and integration tests for per-chunk progress reporting and Dead-Letter Queue (DLQ)
handling in Ermes Knowledge ingestion pipeline.
"""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from api.auth import _require_role, _verify_api_key
from api.libraries import get_library_store, router
from config import cfg
from core.ingestion_service import IngestionOutcome
from core.ingestion_worker import run_ingestion_job
from core.library_store import LibraryStore


# ==========================================
# 1. LibraryStore Progress & DLQ Unit Tests
# ==========================================

def test_job_progress_calculation(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "libraries.db"))
    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("Progress Lib", "Test", "private", "admin")

    job = store.start_ingestion_job(lib["id"], "large_document.pdf")
    job_id = job["id"]

    # Initial state
    progress = store.get_job_progress(job_id)
    assert progress is not None
    assert progress["processed_chunks"] == 0
    assert progress["total_chunks"] == 0
    assert progress["progress_percent"] == 0.0

    # Halfway update
    store.update_job_progress(job_id, processed_chunks=25, total_chunks=50)
    progress = store.get_job_progress(job_id)
    assert progress["processed_chunks"] == 25
    assert progress["total_chunks"] == 50
    assert progress["progress_percent"] == 50.0

    # Completed update
    store.update_job_progress(job_id, processed_chunks=50, total_chunks=50)
    progress = store.get_job_progress(job_id)
    assert progress["processed_chunks"] == 50
    assert progress["progress_percent"] == 100.0


def test_dead_letter_queue_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "libraries.db"))
    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("DLQ Lib", "Test", "private", "admin")

    job = store.start_ingestion_job(lib["id"], "corrupt_data.bin")
    job_id = job["id"]

    # Move to DLQ
    store.move_to_dead_letter(job_id, reason="Corrupt binary format")
    dlq_jobs = store.list_dead_letter_jobs(lib["id"])
    assert len(dlq_jobs) == 1
    assert dlq_jobs[0]["id"] == job_id
    assert dlq_jobs[0]["status"] == "dead_letter"
    assert dlq_jobs[0]["dead_letter_reason"] == "Corrupt binary format"

    stats = store.ingestion_queue_stats()
    assert stats["dead_letter"] == 1

    # Reprocess from DLQ
    reprocessed = store.reprocess_dead_letter_job(job_id)
    assert reprocessed is True

    updated_job = store.get_ingestion_job(job_id)
    assert updated_job["status"] == "queued"
    assert updated_job["attempts"] == 0
    assert updated_job["dead_letter_reason"] == ""

    dlq_after = store.list_dead_letter_jobs(lib["id"])
    assert len(dlq_after) == 0


# ==========================================
# 2. Worker Automatic DLQ Routing Tests
# ==========================================

def test_worker_routes_permanent_failure_to_dlq(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "libraries.db"))
    monkeypatch.setattr(cfg, "LIBRARY_STORAGE_DIR", str(tmp_path / "storage"))
    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("Permanent Fail Lib", "Test", "private", "admin")
    job = store.start_ingestion_job(lib["id"], "unreadable.pdf")
    job_id = job["id"]

    # Mock process_ingestion_job returning permanent failure
    mock_process = MagicMock(return_value=IngestionOutcome(status="failed", transient=False, error="File damaged"))
    monkeypatch.setattr("core.ingestion_worker.process_ingestion_job", mock_process)

    run_ingestion_job(store, job_id, tmp_path / "storage")

    job_record = store.get_ingestion_job(job_id)
    assert job_record["status"] == "dead_letter"
    assert "File damaged" in job_record["dead_letter_reason"]


def test_worker_routes_exhausted_retries_to_dlq(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "libraries.db"))
    monkeypatch.setattr(cfg, "LIBRARY_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(cfg, "INGESTION_MAX_ATTEMPTS", 1)  # Only 1 attempt allowed
    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("Transient Fail Lib", "Test", "private", "admin")
    job = store.start_ingestion_job(lib["id"], "network_error.pdf")
    job_id = job["id"]

    # Mock transient failure
    mock_process = MagicMock(return_value=IngestionOutcome(status="failed", transient=True, error="Embedding timeout"))
    monkeypatch.setattr("core.ingestion_worker.process_ingestion_job", mock_process)

    run_ingestion_job(store, job_id, tmp_path / "storage")

    job_record = store.get_ingestion_job(job_id)
    assert job_record["status"] == "dead_letter"
    assert "Tentativi esauriti" in job_record["dead_letter_reason"]


# ==========================================
# 3. API Endpoints Tests for Progress & DLQ
# ==========================================

def test_api_progress_and_dlq_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "libraries.db"))
    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("API DLQ Lib", "Test", "private", "admin")

    job = store.start_ingestion_job(lib["id"], "test_api.pdf")
    job_id = job["id"]
    store.update_job_progress(job_id, processed_chunks=8, total_chunks=10)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_library_store] = lambda: store
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "admin", "role": "admin"}
    app.dependency_overrides[_require_role("editor")] = lambda: {"username": "admin", "role": "admin"}

    client = TestClient(app)

    # 1. Test progress endpoint
    prog_res = client.get(f"/api/libraries/{lib['id']}/ingestion-jobs/{job_id}/progress")
    assert prog_res.status_code == 200
    prog_data = prog_res.json()
    assert prog_data["processed_chunks"] == 8
    assert prog_data["total_chunks"] == 10
    assert prog_data["progress_percent"] == 80.0

    # 2. Test DLQ list before moving
    dlq_res1 = client.get(f"/api/libraries/{lib['id']}/dead-letter-jobs")
    assert dlq_res1.status_code == 200
    assert len(dlq_res1.json()["items"]) == 0

    # Move to DLQ
    store.move_to_dead_letter(job_id, "Syntax error in chunk 9")

    # 3. Test DLQ list after moving
    dlq_res2 = client.get(f"/api/libraries/{lib['id']}/dead-letter-jobs")
    assert dlq_res2.status_code == 200
    assert len(dlq_res2.json()["items"]) == 1
    assert dlq_res2.json()["items"][0]["id"] == job_id

    # Mock background run_ingestion_job so it doesn't fail on dummy document
    monkeypatch.setattr("api.libraries.run_ingestion_job", lambda *args, **kwargs: None)

    # 4. Test reprocess DLQ endpoint
    reproc_res = client.post(f"/api/libraries/{lib['id']}/dead-letter-jobs/{job_id}/reprocess")
    assert reproc_res.status_code == 200
    assert reproc_res.json()["status"] == "requeued"

    # Verify DLQ empty again
    dlq_res3 = client.get(f"/api/libraries/{lib['id']}/dead-letter-jobs")
    assert len(dlq_res3.json()["items"]) == 0
