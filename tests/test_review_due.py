"""Scadenze di revisione dei documenti (voce 2.3 del piano)."""

import pytest
from fastapi.testclient import TestClient

from api import app
from api.libraries import _verify_api_key, get_library_store
from config import cfg
from core.library_store import LibraryStore
from tests.library_api_cfg import LIBRARIES_CFG_TARGETS


def _doc(store, library_id, name):
    return store.add_document(
        library_id, name, "text/markdown", name.encode(), f"x/{name}", chunks=[("testo", "Sezione: A")]
    )


def test_overdue_and_upcoming_reviews_are_listed_most_urgent_first(tmp_path):
    store = LibraryStore(tmp_path / "ermes.sqlite3")
    library_id = store.create_library("Qualita", owner_id="owner")["id"]
    for name, scadenza in (
        ("dvr.md", "2026-12-15"),
        ("pq07.md", "2026-10-01"),
        ("lontano.md", "2027-06-01"),
        ("senza.md", ""),
    ):
        store.set_review_due(library_id, _doc(store, library_id, name)["id"], scadenza)

    due = store.documents_due_for_review(library_id, None, today="2026-10-28", within_days=60)

    assert [(d["filename"], d["status"], d["days_left"]) for d in due] == [
        ("pq07.md", "overdue", -27),
        ("dvr.md", "due_soon", 48),
    ]


def test_an_invalid_date_is_refused_and_an_empty_one_clears_the_deadline(tmp_path):
    store = LibraryStore(tmp_path / "ermes.sqlite3")
    library_id = store.create_library("Qualita", owner_id="owner")["id"]
    document_id = _doc(store, library_id, "pq07.md")["id"]

    with pytest.raises(ValueError):
        store.set_review_due(library_id, document_id, "2026-02-30")
    store.set_review_due(library_id, document_id, "2026-10-01")
    store.set_review_due(library_id, document_id, "")

    assert store.documents_due_for_review(library_id, None, "2026-10-28", 30) == []


def test_reviews_respect_who_can_see_the_document(tmp_path, monkeypatch):
    test_cfg = cfg.replace(BASE_DIR=str(tmp_path), API_KEY="")
    for target in LIBRARIES_CFG_TARGETS:
        monkeypatch.setattr(target, test_cfg)
    store = LibraryStore(tmp_path / "ermes.sqlite3")
    library_id = store.create_library("Qualita", "", "private", owner_id="owner")["id"]
    document_id = _doc(store, library_id, "riservato.md")["id"]
    store.set_library_member(library_id, "bob", "viewer")
    store.set_document_acl(library_id, document_id, ["owner"])
    app.dependency_overrides[get_library_store] = lambda: store
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "owner", "role": "editor"}
    try:
        client = TestClient(app)
        impostata = client.put(
            f"/api/libraries/{library_id}/documents/{document_id}/review-due", json={"review_due": "2026-10-01"}
        )
        assert impostata.status_code == 200
        url = f"/api/libraries/{library_id}/reviews-due?today=2026-10-28"
        assert [d["filename"] for d in client.get(url).json()["items"]] == ["riservato.md"]
        assert (
            client.put(
                f"/api/libraries/{library_id}/documents/{document_id}/review-due", json={"review_due": "28/10/2026"}
            ).status_code
            == 422
        )

        app.dependency_overrides[_verify_api_key] = lambda: {"username": "bob", "role": "viewer"}
        assert client.get(url).json()["items"] == []
    finally:
        app.dependency_overrides.clear()
