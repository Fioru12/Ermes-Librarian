"""Smoke test: l'applicazione deve essere importabile.

Il 2026-08-25 un'annotazione ``BackgroundTasks | None`` introdotta da un fix
mypy ha impedito l'avvio del backend a runtime (Pydantic rifiuta quel tipo come
campo). Questo test esiste per accorgersene in CI invece che al doppio clic
sullo shortcut: se ``import api`` fallisce, nessun endpoint risponde.
"""

from __future__ import annotations

def test_app_is_importable_and_has_routes():
    import api

    assert api.app is not None
    assert len(api.app.routes) > 50  # sanity: le route principali sono registrate


def test_upload_route_accepts_background_tasks_dependency():
    """La route di upload deve registrarsi senza errori Pydantic (regressione)."""
    from fastapi.routing import APIRoute

    import api

    paths = {getattr(r, "path", "") for r in api.app.routes if isinstance(r, APIRoute)}
    assert "/api/libraries/{library_id}/documents" in paths or any(
        p.endswith("/{library_id}/documents") for p in paths
    )
