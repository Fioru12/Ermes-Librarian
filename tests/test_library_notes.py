"""Note personali per biblioteca (core/library_store.py, api/libraries.py)."""

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.libraries
import config
from api import app
from core.library_store import LibraryAccessError, LibraryNotFoundError, LibraryStore

BOB = {"username": "bob", "role": "viewer"}
CAROL = {"username": "carol", "role": "viewer"}


def _store(tmp_path, db_path=None) -> tuple[LibraryStore, str]:
    store = LibraryStore(db_path or tmp_path / "s.sqlite3")
    library = store.create_library("Amministrazione", "", "private", owner_id="alice")
    store.set_library_member(library["id"], "bob", "viewer")
    store.set_library_member(library["id"], "carol", "viewer")
    return store, library["id"]


def test_notes_are_private_to_their_author(tmp_path):
    store, library_id = _store(tmp_path)
    note = store.create_note(library_id, BOB, "Scadenze", "Nota spese entro il quinto giorno.")

    assert [n["id"] for n in store.list_notes(library_id, BOB)] == [note["id"]]
    assert store.list_notes(library_id, CAROL) == []
    with pytest.raises(LibraryNotFoundError):
        store.get_note(library_id, note["id"], CAROL)
    with pytest.raises(LibraryNotFoundError):
        store.delete_note(library_id, note["id"], CAROL)
    assert store.get_note(library_id, note["id"], BOB)["body"] == "Nota spese entro il quinto giorno."


def test_losing_library_access_hides_your_own_notes(tmp_path):
    store, library_id = _store(tmp_path)
    store.create_note(library_id, BOB, "Scadenze", "testo")
    store.remove_library_member(library_id, "bob")
    with pytest.raises(LibraryAccessError):
        store.list_notes(library_id, BOB)


def test_sources_are_kept_and_sanitised(tmp_path):
    store, library_id = _store(tmp_path)
    note = store.create_note(
        library_id,
        BOB,
        "",
        "Da una risposta",
        [{"filename": "nota-spese.md", "version": 2, "locator": "Sezione 1", "excerpt": "x" * 5000, "script": "<b>"}],
    )
    assert note["title"] == "Da una risposta"
    assert note["sources"] == [{"filename": "nota-spese.md", "version": 2, "locator": "Sezione 1", "excerpt": "x" * 2000}]


def test_update_and_empty_notes(tmp_path):
    store, library_id = _store(tmp_path)
    with pytest.raises(ValueError):
        store.create_note(library_id, BOB, "  ", "  ")
    note = store.create_note(library_id, BOB, "T", "B")
    assert store.update_note(library_id, note["id"], BOB, None, "Nuovo testo")["body"] == "Nuovo testo"
    with pytest.raises(LibraryNotFoundError):
        store.update_note(library_id, note["id"], CAROL, "rubata", None)


def test_notes_go_away_with_the_library(tmp_path):
    store, library_id = _store(tmp_path)
    store.create_note(library_id, BOB, "T", "B")
    store.delete_library(library_id)
    with store._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM library_notes").fetchone()[0] == 0


def test_notes_api_round_trip(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(BASE_DIR=str(app_dir), DATABASE_URL="", API_KEY="chiave-note-test-4b8e")
    for module in (config, api.auth, api.libraries):
        monkeypatch.setattr(module, "cfg", test_cfg)
    store, library_id = _store(tmp_path, db_path=test_cfg.LIBRARY_DB_PATH)
    monkeypatch.setattr(api.libraries, "_store", store)
    client = TestClient(app)
    auth = {"Authorization": "Bearer chiave-note-test-4b8e"}
    base = f"/api/libraries/{library_id}/notes"

    created = client.post(base, headers=auth, json={"title": "Scadenze", "body": "Entro il quinto giorno", "sources": [{"filename": "nota-spese.md"}]})
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]
    assert [n["id"] for n in client.get(base, headers=auth).json()["items"]] == [note_id]
    assert client.patch(f"{base}/{note_id}", headers=auth, json={"title": "Scadenze mensili"}).json()["title"] == "Scadenze mensili"
    assert client.post(base, headers=auth, json={"title": "", "body": ""}).status_code == 400
    assert client.delete(f"{base}/{note_id}", headers=auth).status_code == 204
    assert client.get(base, headers=auth).json()["items"] == []
    assert client.get(base).status_code == 401
