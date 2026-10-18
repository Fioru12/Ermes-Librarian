"""Smoke test: l'applicazione deve essere importabile.

Il 2026-08-25 un'annotazione ``BackgroundTasks | None`` introdotta da un fix
mypy ha impedito l'avvio del backend a runtime (Pydantic rifiuta quel tipo come
campo). Questo test esiste per accorgersene in CI invece che al doppio clic
sullo shortcut: se ``import api`` fallisce, nessun endpoint risponde.
"""

from __future__ import annotations


def _api_paths() -> set[str]:
    """Percorsi esposti, letti dallo schema OpenAPI: da FastAPI 0.143 `app.routes` contiene
    anche rotte raggruppate in oggetti interni, e contarle non e' piu' affidabile."""
    import api

    return set(api.app.openapi()["paths"])


def test_app_is_importable_and_has_routes():
    import api

    assert api.app is not None
    assert len(_api_paths()) > 50  # sanity: le route principali sono registrate


def test_v1_aliases_cover_the_api():
    """Ogni percorso /api/... ha il suo alias /v1/api/... (retrocompatibilita')."""
    paths = _api_paths()
    mancanti = sorted(p for p in paths if p.startswith("/api/") and f"/v1{p}" not in paths)
    assert not mancanti, f"Senza alias /v1: {mancanti[:10]}"


def test_upload_route_accepts_background_tasks_dependency():
    """La route di upload deve registrarsi senza errori Pydantic (regressione)."""
    paths = _api_paths()
    assert "/api/libraries/{library_id}/documents" in paths or any(p.endswith("/{library_id}/documents") for p in paths)
