"""Verifica di coerenza tra righe SQLite, originali su disco e indice derivato.

Il database è la fonte di verità; un backup/restore parziale o un upload
fallito a metà può produrre quattro derive. Ogni test ne copre una, più il
caso sano: il report deve dire esplicitamente cosa non torna, invece di
lasciare scoprire al download fallito che qualcosa era storto.
"""
from pathlib import Path

from core.library_store import LibraryStore


def _seed_healthy_document(store: LibraryStore, storage_root: Path, filename: str = "manuale.md") -> dict:
    library = store.create_library("Procedure", "", "private", owner_id="alice")
    library_dir = storage_root / library["id"]
    library_dir.mkdir(parents=True, exist_ok=True)
    file_path = library_dir / filename
    file_path.write_bytes(b"# Manuale\nContenuto indicizzabile.")
    document = store.add_document(
        library_id=library["id"],
        filename=filename,
        media_type="text/markdown",
        content=file_path.read_bytes(),
        storage_path=f"{library['id']}/{filename}",
        extracted_text="Contenuto indicizzabile.",
        source_units=1,
        status="ready",
        chunks=[("Contenuto indicizzabile.", "Pagina 1")],
    )
    return {"library": library, "document": document}


def test_a_consistent_index_reports_ok(tmp_path: Path):
    store = LibraryStore(tmp_path / "ok.sqlite3")
    seeded = _seed_healthy_document(store, tmp_path / "storage")
    store.store_chunk_embeddings(
        seeded["library"]["id"], seeded["document"]["id"],
        [[0.1, 0.2]], "test-embed-model",
    )

    report = store.verify_index_consistency(tmp_path / "storage", expected_embed_model="test-embed-model")

    assert report["ok"] is True
    assert report["issue_count"] == 0
    assert report["checked_documents"] == 1


def test_a_missing_original_file_is_reported(tmp_path: Path):
    store = LibraryStore(tmp_path / "missing.sqlite3")
    seeded = _seed_healthy_document(store, tmp_path / "storage")
    (tmp_path / "storage" / seeded["library"]["id"] / "manuale.md").unlink()

    report = store.verify_index_consistency(tmp_path / "storage")

    assert report["ok"] is False
    assert [item["document_id"] for item in report["missing_originals"]] == [seeded["document"]["id"]]


def test_an_orphan_file_with_no_row_is_reported(tmp_path: Path):
    store = LibraryStore(tmp_path / "orphan.sqlite3")
    _seed_healthy_document(store, tmp_path / "storage")
    # Upload fallito tra la scrittura del file e l'insert: il file resta.
    orphan_dir = tmp_path / "storage" / "some-library"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "abc_fantasma.md").write_bytes(b"mai referenziato")

    report = store.verify_index_consistency(tmp_path / "storage")

    assert report["ok"] is False
    assert report["orphan_files"] == ["some-library/abc_fantasma.md"]


def test_a_ready_document_without_chunks_is_reported(tmp_path: Path):
    """Un documento 'ready' senza chunk è invisibile alla ricerca: deve essere
    segnalato invece di sembrare sano."""
    store = LibraryStore(tmp_path / "nochunks.sqlite3")
    seeded = _seed_healthy_document(store, tmp_path / "storage")
    with store._connection() as connection:
        connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (seeded["document"]["id"],))

    report = store.verify_index_consistency(tmp_path / "storage")

    assert report["ok"] is False
    assert report["ready_without_chunks"] == [seeded["document"]["id"]]


def test_partially_embedded_and_model_mismatch_are_reported(tmp_path: Path):
    store = LibraryStore(tmp_path / "embeds.sqlite3")
    seeded = _seed_healthy_document(store, tmp_path / "storage")
    document_id = seeded["document"]["id"]
    # Due chunk ma embedding su uno solo, e con un modello diverso dall'atteso.
    with store._connection() as connection:
        connection.execute("INSERT INTO document_chunks (id, document_id, ordinal, text, created_at) VALUES (?, ?, ?, ?, ?)",
                           ("chunk-extra", document_id, 1, "Secondo passaggio.", "2026-01-01"))
        connection.execute("UPDATE document_chunks SET embedding_json = '[0.1]', embedding_model = 'vecchio-modello' WHERE document_id = ? AND ordinal = 0", (document_id,))

    report = store.verify_index_consistency(tmp_path / "storage", expected_embed_model="modello-attuale")

    assert report["partially_embedded_documents"] == [document_id]
    assert report["embedding_model_mismatch_documents"] == [document_id]
    assert report["ok"] is False
