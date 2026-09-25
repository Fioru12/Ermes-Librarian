"""Cache di ricerca con piu' repliche (core/search_cache.py).

La cache vive nel processo e il chart Helm parte con due repliche.
invalidate() svuota solo la replica che riceve la modifica: prima del
contatore di generazione sul database, revocato l'accesso a un documento,
sull'altra replica l'utente escluso ne riceveva ancora gli estratti fino al
TTL. Qui due LibraryStore sullo stesso file sono due repliche; la replica B
lavora con una propria cache in memoria, come un processo separato.
"""

import pytest

import core.library_store as library_store_module
from core.library_store import LibraryStore
from core.search_cache import SemanticSearchCache, reset_search_cache

BOB = {"username": "bob", "role": "viewer"}


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_search_cache()
    yield
    reset_search_cache()


@pytest.fixture
def replicas(tmp_path, monkeypatch):
    path = tmp_path / "ermes.sqlite3"
    a, b = LibraryStore(path), LibraryStore(path)
    cache_b = SemanticSearchCache()
    real = library_store_module.get_search_cache

    class OnReplicaB:
        """Durante il blocco, LibraryStore usa la cache della replica B."""

        def __enter__(self):
            monkeypatch.setattr(library_store_module, "get_search_cache", lambda: cache_b)

        def __exit__(self, *_):
            monkeypatch.setattr(library_store_module, "get_search_cache", real)

    return a, b, OnReplicaB


def _library(store: LibraryStore) -> tuple[str, str]:
    library = store.create_library("Riservate", "", "private", owner_id="alice")
    document = store.add_document(
        library["id"],
        "stipendi.txt",
        "text/plain",
        b"Gli stipendi vengono erogati il ventisette.",
        "x/stipendi.txt",
        chunks=[("Gli stipendi vengono erogati il ventisette.", "Pagina 1")],
    )
    store.set_library_member(library["id"], "bob", "viewer")
    return library["id"], document["id"]


def _filenames(store: LibraryStore, library_id: str) -> set[str]:
    results, _ = store.search_with_profile(library_id, "ventisette", actor=BOB)
    return {r["filename"] for r in results}


def test_revoking_access_on_one_replica_takes_effect_on_the_other(replicas):
    a, b, on_replica_b = replicas
    library_id, document_id = _library(a)
    assert _filenames(a, library_id) == {"stipendi.txt"}  # cache di A popolata

    with on_replica_b():
        b.set_document_acl(library_id, document_id, ["carol"])

    assert _filenames(a, library_id) == set()


def test_reindexing_on_one_replica_takes_effect_on_the_other(replicas):
    # Stesso numero di documenti, testo diverso: il conteggio non se ne
    # accorge, la generazione si'.
    a, b, on_replica_b = replicas
    library_id, document_id = _library(a)
    assert _filenames(a, library_id) == {"stipendi.txt"}

    with on_replica_b():
        b.replace_document_index(
            library_id, document_id, "Le ferie si chiedono in anticipo.", 1, [("Le ferie si chiedono in anticipo.", "P1")]
        )

    assert _filenames(a, library_id) == set()


def test_a_result_computed_before_a_change_is_not_served_after_it():
    # La generazione si legge prima di cercare: una modifica arrivata durante
    # la ricerca non deve far sopravvivere il risultato vecchio.
    cache = SemanticSearchCache()
    cache.put("lib", "stipendi", 1, [{"filename": "stipendi.txt"}], {"mode": "keyword"}, generation=4)
    assert cache.get("lib", "stipendi", 1, generation=4) is not None
    assert cache.get("lib", "stipendi", 1, generation=5) is None
