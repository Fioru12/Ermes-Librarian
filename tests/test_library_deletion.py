"""Cancellazione di documenti e biblioteche: righe DB, file storage, permessi."""
from pathlib import Path

from core.library_store import LibraryNotFoundError, LibraryStore


def _make_store_with_document(tmp_path: Path) -> tuple[LibraryStore, dict, dict, Path]:
    store = LibraryStore(tmp_path / "knowledge.sqlite3")
    library = store.create_library("Da eliminare", "", "private")
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    doc_dir = storage_root / library["id"]
    doc_dir.mkdir()
    original = doc_dir / "doc.md"
    original.write_bytes(b"contenuto")
    document = store.add_document(
        library_id=library["id"],
        filename="doc.md",
        media_type="text/markdown",
        content=b"contenuto",
        storage_path=str(original),
        extracted_text="contenuto",
        chunks=[("contenuto", "Sezione: Unica")],
    )
    return store, library, document, storage_root


def test_delete_document_removes_rows_and_reports_storage_path(tmp_path: Path):
    store, library, document, _ = _make_store_with_document(tmp_path)

    paths = store.delete_document(library["id"], document["id"])

    assert paths == [str(tmp_path / "storage" / library["id"] / "doc.md")]
    assert store.list_documents(library["id"]) == []
    assert store.search_documents(library["id"], "contenuto") == []
    try:
        store.get_document(library["id"], document["id"])
        raise AssertionError("get_document doveva sollevare LibraryNotFoundError")
    except LibraryNotFoundError:
        pass


def test_delete_missing_document_raises(tmp_path: Path):
    store, library, _, _ = _make_store_with_document(tmp_path)

    try:
        store.delete_document(library["id"], "id-inesistente")
        raise AssertionError("doveva sollevare LibraryNotFoundError")
    except LibraryNotFoundError:
        pass


def test_delete_library_removes_everything_and_reports_paths(tmp_path: Path):
    store, library, document, _ = _make_store_with_document(tmp_path)

    paths = store.delete_library(library["id"])

    assert paths == [str(tmp_path / "storage" / library["id"] / "doc.md")]
    assert store.list_libraries() == []
    try:
        store.get_document(library["id"], document["id"])
        raise AssertionError("get_document doveva sollevare LibraryNotFoundError")
    except LibraryNotFoundError:
        pass


def test_unlink_storage_paths_removes_file_and_empty_dirs(tmp_path: Path):
    from api.libraries import _unlink_storage_paths

    store, library, document, storage_root = _make_store_with_document(tmp_path)
    original = Path(document["storage_path"])
    assert original.is_file()

    _unlink_storage_paths(store.delete_document(library["id"], document["id"]), root=storage_root)

    assert not original.is_file()
    # le cartelle documento/biblioteca vuote vengono compattate verso la radice
    assert not (storage_root / library["id"]).exists()


def test_unlink_storage_paths_never_escapes_the_root(tmp_path: Path):
    from api.libraries import _unlink_storage_paths

    outside = tmp_path / "fuori.md"
    outside.write_bytes(b"da non toccare")
    storage_root = tmp_path / "storage"
    storage_root.mkdir()

    _unlink_storage_paths([str(outside), "..\\escape.md"], root=storage_root)

    assert outside.is_file()
    # "..\\escape.md" non deve creare né cancellare nulla fuori dalla root
    assert not (tmp_path / "escape.md").exists()
