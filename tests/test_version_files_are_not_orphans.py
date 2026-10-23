"""Le versioni precedenti di un documento NON sono file orfani.

Rimettere un file con lo stesso nome crea una nuova versione con un nuovo percorso di storage; il
vecchio resta referenziato solo da `document_versions`. La verifica di coerenza guardava soltanto
`documents`, quindi segnalava lo storico come orfano (anche nella scheda Stato del sistema), e
`scripts/cleanup_orphan_storage.py --confirm` lo avrebbe cancellato.
"""

from pathlib import Path

from core.library_store import LibraryStore


def _store_with_two_versions(tmp_path: Path):
    storage = tmp_path / "storage"
    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("Lib", "", "private", "admin")
    files = {}
    for versione, path in ((1, f"{lib['id']}/aaa_manuale.pdf"), (2, f"{lib['id']}/bbb_manuale.pdf")):
        contenuto = f"versione {versione}".encode()
        (storage / lib["id"]).mkdir(parents=True, exist_ok=True)
        (storage / path).write_bytes(contenuto)
        store.add_document(library_id=lib["id"], filename="manuale.pdf", media_type="application/pdf",
                           content=contenuto, storage_path=path)
        files[versione] = path
    return store, storage, files


def test_the_original_of_an_older_version_is_not_reported_as_an_orphan(tmp_path):
    store, storage, files = _store_with_two_versions(tmp_path)
    report = store.verify_index_consistency(str(storage), "any-model")
    assert files[1] not in report["orphan_files"], "il file della versione 1 e' referenziato da document_versions"
    assert files[2] not in report["orphan_files"]
    assert report["orphan_files"] == []


def test_a_file_nobody_references_is_still_an_orphan(tmp_path):
    store, storage, _ = _store_with_two_versions(tmp_path)
    (storage / "vero-orfano.bin").write_bytes(b"x")
    report = store.verify_index_consistency(str(storage), "any-model")
    assert report["orphan_files"] == ["vero-orfano.bin"]
