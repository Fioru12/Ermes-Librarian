import threading
from pathlib import Path

from core.folder_watcher import start_folder_watcher_thread, sync_all_sources
from core.library_store import LibraryStore


def test_folder_watcher_syncs_sources_and_processes_jobs(tmp_path: Path):
    db_path = tmp_path / "test_watcher.sqlite3"
    storage_dir = tmp_path / "storage"
    external_folder = tmp_path / "watched_folder"
    external_folder.mkdir(parents=True)
    storage_dir.mkdir(parents=True)

    store = LibraryStore(db_path)
    library = store.create_library("Cartella Automatica", owner_id="admin")
    store.add_import_source(library["id"], str(external_folder))

    # Add a document to the watched folder
    doc_file = external_folder / "procedura.txt"
    doc_file.write_text("La procedura operativa per l'autolavaggio.", encoding="utf-8")

    # Run sync
    summary = sync_all_sources(store, storage_dir)

    assert summary["scanned_sources"] == 1
    assert summary["total_imported"] == 1

    # Verify document is ready in store
    docs = store.list_documents(library["id"])
    assert len(docs) == 1
    assert docs[0]["filename"] == "procedura.txt"
    assert docs[0]["status"] == "ready"

    # Search should find the new document
    results, profile = store.search_with_profile(library["id"], "autolavaggio")
    assert len(results) == 1
    assert "autolavaggio" in results[0]["excerpt"].lower()

    # Second sync should find 0 new documents
    summary2 = sync_all_sources(store, storage_dir)
    assert summary2["total_imported"] == 0


def test_folder_watcher_thread_lifecycle(tmp_path: Path):
    db_path = tmp_path / "test_lifecycle.sqlite3"
    storage_dir = tmp_path / "storage"
    store = LibraryStore(db_path)

    stop_event = threading.Event()
    thread = start_folder_watcher_thread(store, storage_dir, interval_sec=1, stop_event=stop_event)
    assert thread.is_alive()

    # Stop thread
    stop_event.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
