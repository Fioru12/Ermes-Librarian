"""Direct coverage for core/ingestion_service.py::process_ingestion_job.

Previously untested: existing library tests exercise LibraryStore's job
bookkeeping (start/finish_ingestion_job) directly, but never the real
parse -> chunk -> embed -> index pipeline, including its failure-path
status transitions users see as "document failed to index".
"""
from pathlib import Path

from core.ingestion_service import process_ingestion_job
from core.library_store import LibraryStore


def _seed_document(store: LibraryStore, storage_root: Path, filename: str, content: bytes) -> tuple[dict, dict]:
    library = store.create_library("Procedure")
    file_path = storage_root / filename
    file_path.write_bytes(content)
    document = store.add_document(
        library_id=library["id"],
        filename=filename,
        media_type="text/markdown",
        content=content,
        storage_path=str(file_path),
        status="processing",
    )
    job = store.start_ingestion_job(library["id"], filename, document_id=document["id"])
    return library, {**document, "job_id": job["id"]}


def test_process_ingestion_job_indexes_a_real_document_and_marks_it_ready(tmp_path: Path):
    store = LibraryStore(tmp_path / "jobs.sqlite3")
    library, document = _seed_document(
        store, tmp_path, "procedura.md",
        b"# Procedura\nLe richieste vanno inviate al responsabile entro cinque giorni.",
    )

    process_ingestion_job(store, document["job_id"], tmp_path)

    updated = store.get_document(library["id"], document["id"])
    assert updated["status"] == "ready"
    assert updated["source_units"] >= 1
    job = store.get_ingestion_job(document["job_id"])
    assert job["status"] == "ready"
    assert job["error_message"] == ""

    results = store.search_documents(library["id"], "responsabile", limit=3)
    assert results and results[0]["filename"] == "procedura.md"


def test_process_ingestion_job_marks_a_textless_document_failed_not_silently_ready(tmp_path: Path):
    store = LibraryStore(tmp_path / "jobs_failed.sqlite3")
    # An empty file parses to zero extractable units — the pipeline must
    # reject it explicitly rather than index an empty, useless document.
    library, document = _seed_document(store, tmp_path, "vuoto.md", b"")

    process_ingestion_job(store, document["job_id"], tmp_path)

    updated = store.get_document(library["id"], document["id"])
    assert updated["status"] == "failed"
    job = store.get_ingestion_job(document["job_id"])
    assert job["status"] == "failed"
    assert job["error_message"]


def test_process_ingestion_job_rejects_a_document_stored_outside_the_storage_root(tmp_path: Path):
    """Defence in depth: even if a document row ever pointed outside the
    library storage tree, ingestion must refuse to read it rather than
    silently following the path."""
    store = LibraryStore(tmp_path / "jobs_traversal.sqlite3")
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    outside_file = tmp_path / "outside.md"
    outside_file.write_bytes(b"# Fuori dal perimetro consentito")

    library = store.create_library("Procedure")
    document = store.add_document(
        library_id=library["id"],
        filename="outside.md",
        media_type="text/markdown",
        content=b"# Fuori dal perimetro consentito",
        storage_path=str(outside_file),
        status="processing",
    )
    job = store.start_ingestion_job(library["id"], "outside.md", document_id=document["id"])

    process_ingestion_job(store, job["id"], storage_root)

    updated = store.get_document(library["id"], document["id"])
    assert updated["status"] == "failed"
    job_after = store.get_ingestion_job(job["id"])
    assert job_after["status"] == "failed"


def test_process_ingestion_job_is_a_noop_for_an_already_claimed_job(tmp_path: Path):
    """claim_ingestion_job only succeeds once (status transitions queued ->
    processing); a second call for the same job_id must not double-process
    or raise."""
    store = LibraryStore(tmp_path / "jobs_claimed.sqlite3")
    library, document = _seed_document(store, tmp_path, "doc.md", b"# Contenuto")

    process_ingestion_job(store, document["job_id"], tmp_path)
    # The job is no longer "queued", so a second run must return quietly.
    process_ingestion_job(store, document["job_id"], tmp_path)

    updated = store.get_document(library["id"], document["id"])
    assert updated["status"] == "ready"
