"""Confronto fra versioni di un documento (core/version_diff.py, voce 2.2 del piano)."""

from fastapi.testclient import TestClient

from api import app
from api.libraries import _verify_api_key, get_library_store
from config import cfg
from core.document_parser import SourceUnit
from core.library_store import LibraryStore
from core.version_diff import compare_units
from tests.library_api_cfg import LIBRARIES_CFG_TARGETS


def _u(locator: str, text: str) -> SourceUnit:
    return SourceUnit(text, locator)


def test_changed_added_and_removed_sections_are_reported_by_section():
    prima = [
        _u("Sezione: Ferie", "Le ferie si chiedono con dieci giorni di anticipo. Il portale e' quello presenze."),
        _u("Sezione: Trasferte", "Rimborso a 0,35 euro al km."),
        _u("Sezione: Orario", "Dalle 8:30 alle 17:30."),
    ]
    dopo = [
        _u("Sezione: Ferie", "Le ferie si chiedono con quindici giorni di anticipo. Il portale e' quello presenze."),
        _u("Sezione: Orario", "Dalle   8:30 alle 17:30."),
        _u("Sezione: Lavoro agile", "Due giorni a settimana."),
    ]

    changes = {c.locator: c for c in compare_units(prima, dopo)}

    assert changes["Sezione: Ferie"].kind == "changed"
    assert changes["Sezione: Ferie"].before == ["Le ferie si chiedono con dieci giorni di anticipo."]
    assert changes["Sezione: Ferie"].after == ["Le ferie si chiedono con quindici giorni di anticipo."]
    assert changes["Sezione: Lavoro agile"].kind == "added"
    assert changes["Sezione: Trasferte"].kind == "removed"
    assert "Sezione: Orario" not in changes, "solo spazi diversi non e' una modifica"


def test_identical_versions_have_no_changes():
    unita = [_u("Pagina 1", "Testo.")]

    assert compare_units(unita, list(unita)) == []


def test_the_api_compares_two_uploaded_versions_and_hides_them_from_who_cannot_open_the_document(tmp_path, monkeypatch):
    test_cfg = cfg.replace(BASE_DIR=str(tmp_path), API_KEY="")
    for target in LIBRARIES_CFG_TARGETS:
        monkeypatch.setattr(target, test_cfg)
    monkeypatch.setattr("core.ingestion_service.embed_texts", lambda texts: [])
    store = LibraryStore(tmp_path / "versioni.sqlite3")
    app.dependency_overrides[get_library_store] = lambda: store
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "owner", "role": "editor"}
    try:
        client = TestClient(app)
        library_id = client.post("/api/libraries", json={"name": "Qualita", "visibility": "private"}).json()["id"]
        for testo in (
            b"# Procedura\n\n## Registrazione\n\nEntro un giorno.\n",
            b"# Procedura\n\n## Registrazione\n\nEntro due giorni.\n",
        ):
            caricato = client.post(
                f"/api/libraries/{library_id}/documents", files={"file": ("pq07.md", testo, "text/markdown")}
            )
            assert caricato.status_code == 201
        document_id = caricato.json()["id"]

        esito = client.get(f"/api/libraries/{library_id}/documents/{document_id}/versions/compare?from=1&to=2")

        assert esito.status_code == 200
        assert esito.json()["changes"] == [
            {
                "locator": "Sezione: Registrazione",
                "kind": "changed",
                "before": ["Entro un giorno."],
                "after": ["Entro due giorni."],
            }
        ]

        store.set_library_member(library_id, "bob", "viewer")
        store.set_document_acl(library_id, document_id, ["owner"])
        app.dependency_overrides[_verify_api_key] = lambda: {"username": "bob", "role": "viewer"}
        negato = client.get(f"/api/libraries/{library_id}/documents/{document_id}/versions/compare?from=1&to=2")
        assert negato.status_code == 404
        assert client.get(f"/api/libraries/{library_id}/documents/x/versions/compare?from=1&to=9").status_code == 404
    finally:
        app.dependency_overrides.clear()
