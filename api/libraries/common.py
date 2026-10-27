"""Shared pieces of the library endpoints: the store singleton and permission/storage helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from config import cfg
from core.library_store import (
    LibraryAccessError,
    LibraryNotFoundError,
    LibraryStore,
    resolve_storage_path,
)

_store: LibraryStore | None = None


def get_library_store() -> LibraryStore:
    """Singleton legato al percorso configurato.

    Se cfg cambia (test con BASE_DIR temporanei, o un deployment che ripunta
    altrove), l'istanza vecchia punta a un file magari piu' esistente: la si
    ricrea invece di restituire un store morto.
    """
    global _store
    if _store is None or Path(_store.database_path) != Path(cfg.LIBRARY_DB_PATH):
        _store = LibraryStore(cfg.LIBRARY_DB_PATH)
    return _store


def _require_library_member_manager(store: LibraryStore, library_id: str, actor: dict) -> None:
    try:
        if not store.can_manage_library_members(library_id, actor):
            raise HTTPException(
                status_code=403, detail="Solo il proprietario, un manager o un amministratore possono gestire i collaboratori"
            )
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


def _unlink_storage_paths(paths: list[str], root: str | Path | None = None) -> None:
    """Unlink storage files returned by the store, never outside the root.

    The storage root is owned by the API layer (same boundary as reindex);
    path safety mirrors resolve_storage_path + relative_to there. `root`
    defaults to the configured storage dir; tests may pass a narrower root.
    """
    root = Path(root or cfg.LIBRARY_STORAGE_DIR).resolve()
    for rel in paths:
        try:
            target = resolve_storage_path(rel, cfg.LIBRARY_STORAGE_DIR)
            target.resolve().relative_to(root)
        except (ValueError, OSError):
            continue
        try:
            target.unlink(missing_ok=True)
        except OSError:
            continue
        parent = target.parent
        for _ in range(3):
            if parent == root or root not in parent.parents:
                break
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
