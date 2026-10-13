"""Il tetto ai candidati lessicali (core/library_store.py).

Il punteggio finale si calcola in Python su ogni candidato; prima del tetto
una parola comune ne portava decine di migliaia (3,2 s nel caso peggiore a
50.000 passaggi). Ora il database li ordina per rilevanza full-text e si
tengono i primi. I test abbassano il tetto invece di creare migliaia di
passaggi, come quelli sul limite di variabili SQL.
"""

import core.library_store as library_store_module
from core.library_store import LibraryStore


def _library_with(store: LibraryStore, name: str, passages: list[str]) -> str:
    library = store.create_library(name, "", "private", owner_id="alice")
    store.add_document(
        library["id"],
        f"{name}.txt",
        "text/plain",
        "\n".join(passages).encode("utf-8"),
        f"{library['id']}/{name}.txt",
        chunks=[(text, f"Passaggio {i + 1}") for i, text in enumerate(passages)],
    )
    return library["id"]


def test_the_relevant_passage_survives_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(library_store_module, "_MAX_KEYWORD_CANDIDATES", 5)
    store = LibraryStore(tmp_path / "ermes.sqlite3")
    filler = [f"Il fornitore numero {i} consegna il materiale in magazzino." for i in range(60)]
    library_id = _library_with(
        store, "Acquisti", [*filler, "Il fornitore di toner consegna le cartucce entro tre giorni."]
    )

    results, _ = store.search_with_profile(library_id, "fornitore toner cartucce")

    assert results, "nessun risultato: il tetto ha tagliato anche il passaggio pertinente"
    assert "toner" in results[0]["excerpt"]


def test_another_library_cannot_fill_the_cap(tmp_path, monkeypatch):
    # Senza il filtro per biblioteca dentro la query full-text, i primi N per
    # rilevanza potrebbero essere tutti di un'altra biblioteca, e questa
    # risulterebbe vuota pur contenendo la risposta.
    monkeypatch.setattr(library_store_module, "_MAX_KEYWORD_CANDIDATES", 5)
    store = LibraryStore(tmp_path / "ermes.sqlite3")
    _library_with(store, "Rumore", [f"Scadenza scadenza scadenza numero {i}." for i in range(60)])
    target = _library_with(store, "Amministrazione", ["La scadenza della nota spese e' il giorno cinque."])

    results, _ = store.search_with_profile(target, "scadenza")

    assert [r["filename"] for r in results] == ["Amministrazione.txt"]
