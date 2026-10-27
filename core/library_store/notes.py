"""Personal notes attached to a library."""

from __future__ import annotations

import json
import uuid

from core.library_store.base import StoreBase
from core.library_store.common import (
    LibraryNotFoundError,
)


class NotesMixin(StoreBase):
    # ============================================================
    # Note personali (come le note di NotebookLM)
    # ============================================================
    # Private: le vede solo chi le ha scritte, e solo finche' puo' ancora
    # aprire la biblioteca. Le fonti sono salvate con la nota, cosi' una nota
    # presa da una risposta resta verificabile anche dopo che la risposta non
    # e' piu' a schermo.

    _NOTE_MAX_TITLE = 200
    _NOTE_MAX_BODY = 20_000
    _NOTE_MAX_SOURCES = 20

    def _clean_note_sources(self, sources: list[dict] | None) -> list[dict]:
        keys = ("document_id", "filename", "version", "locator", "excerpt")
        cleaned: list[dict] = []
        for source in (sources or [])[: self._NOTE_MAX_SOURCES]:
            if isinstance(source, dict):
                item = {k: source.get(k) for k in keys if source.get(k) is not None}
                if "excerpt" in item:
                    item["excerpt"] = str(item["excerpt"])[:2000]
                cleaned.append(item)
        return cleaned

    def _note_row(self, row) -> dict:
        note = self._row(row)
        note["sources"] = json.loads(note.pop("sources_json") or "[]")
        return note

    def list_notes(self, library_id: str, actor: dict) -> list[dict]:
        self.get_library(library_id, actor)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM library_notes WHERE library_id = ? AND owner = ? ORDER BY updated_at DESC",
                (library_id, actor["username"]),
            ).fetchall()
        return [self._note_row(r) for r in rows]

    def create_note(
        self, library_id: str, actor: dict, title: str, body: str, sources: list[dict] | None = None
    ) -> dict:
        self.get_library(library_id, actor)
        title, body = title.strip()[: self._NOTE_MAX_TITLE], body.strip()[: self._NOTE_MAX_BODY]
        if not title and not body:
            raise ValueError("Nota vuota")
        now = self._timestamp()
        note_id = str(uuid.uuid4())
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO library_notes (id, library_id, owner, title, body, sources_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    library_id,
                    actor["username"],
                    title or body[:60],
                    body,
                    json.dumps(self._clean_note_sources(sources), ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_note(library_id, note_id, actor)

    def get_note(self, library_id: str, note_id: str, actor: dict) -> dict:
        self.get_library(library_id, actor)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM library_notes WHERE id = ? AND library_id = ? AND owner = ?",
                (note_id, library_id, actor["username"]),
            ).fetchone()
        # Stessa risposta per "non esiste" e "e' di un altro": non si rivela
        # che una nota altrui esiste.
        if row is None:
            raise LibraryNotFoundError(note_id)
        return self._note_row(row)

    def update_note(self, library_id: str, note_id: str, actor: dict, title: str | None, body: str | None) -> dict:
        current = self.get_note(library_id, note_id, actor)
        new_title = (current["title"] if title is None else title.strip())[: self._NOTE_MAX_TITLE]
        new_body = (current["body"] if body is None else body.strip())[: self._NOTE_MAX_BODY]
        if not new_title and not new_body:
            raise ValueError("Nota vuota")
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE library_notes SET title = ?, body = ?, updated_at = ? WHERE id = ? AND owner = ?",
                (new_title, new_body, self._timestamp(), note_id, actor["username"]),
            )
        return self.get_note(library_id, note_id, actor)

    def delete_note(self, library_id: str, note_id: str, actor: dict) -> None:
        self.get_note(library_id, note_id, actor)
        with self._lock, self._connection() as connection:
            connection.execute(
                "DELETE FROM library_notes WHERE id = ? AND owner = ?", (note_id, actor["username"])
            )
