"""Watched import folders and chat channel integrations."""

from __future__ import annotations

import os
import uuid

from core.database_backend import INTEGRITY_ERRORS
from core.library_store.base import StoreBase
from core.library_store.common import (
    LibraryNotFoundError,
)


class SourcesMixin(StoreBase):
    def add_import_source(self, library_id: str, path: str, created_by: str = "") -> dict:
        """Register one watched folder. The path must be unique per library."""
        self.get_library(library_id)
        now = self._timestamp()
        normalized = os.path.normpath(path)
        with self._lock, self._connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO import_sources (id, library_id, path, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), library_id, normalized, created_by, now),
                )
            except INTEGRITY_ERRORS as error:
                raise ValueError("Sorgente già registrata per questa biblioteca") from error
        return self.get_import_source(library_id, normalized)

    def get_import_source(self, library_id: str, path: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM import_sources WHERE library_id = ? AND path = ?",
                (library_id, path),
            ).fetchone()
        if row is None:
            raise LibraryNotFoundError(path)
        return self._row(row)

    def get_import_source_by_id(self, library_id: str, source_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM import_sources WHERE library_id = ? AND id = ?",
                (library_id, source_id),
            ).fetchone()
        if row is None:
            raise LibraryNotFoundError(source_id)
        return self._row(row)

    def list_import_sources(self, library_id: str, actor: dict | None = None) -> list[dict]:
        self.get_library(library_id, actor)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM import_sources WHERE library_id = ? ORDER BY created_at",
                (library_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def list_all_import_sources(self) -> list[dict]:
        """List every registered import source across all libraries for the sync watcher."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT import_sources.*, libraries.name AS library_name
                FROM import_sources
                JOIN libraries ON libraries.id = import_sources.library_id
                ORDER BY import_sources.created_at
                """
            ).fetchall()
        return [self._row(row) for row in rows]

    def remove_import_source(self, library_id: str, source_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM import_sources WHERE library_id = ? AND id = ?",
                (library_id, source_id),
            )
            return bool(cursor.rowcount and cursor.rowcount > 0)

    def touch_import_source(self, library_id: str, source_id: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE import_sources SET last_scan_at = ? WHERE library_id = ? AND id = ?",
                (self._timestamp(), library_id, source_id),
            )

    def add_chat_integration(
        self, library_id: str, platform: str, external_channel_id: str, created_by: str = ""
    ) -> dict:
        """Bind one external chat channel to this library. A channel can point to only one library."""
        self.get_library(library_id)
        now = self._timestamp()
        integration_id = str(uuid.uuid4())
        with self._lock, self._connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO chat_integrations (id, library_id, platform, external_channel_id, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (integration_id, library_id, platform, external_channel_id, created_by, now),
                )
            except INTEGRITY_ERRORS as error:
                raise ValueError("Questo canale è già collegato a una biblioteca") from error
        return self.get_chat_integration_by_id(library_id, integration_id)

    def get_chat_integration_by_id(self, library_id: str, integration_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM chat_integrations WHERE library_id = ? AND id = ?",
                (library_id, integration_id),
            ).fetchone()
        if row is None:
            raise LibraryNotFoundError(integration_id)
        return self._row(row)

    def get_chat_integration_by_channel(self, platform: str, external_channel_id: str) -> dict | None:
        """Routing lookup used by the inbound webhook: no ownership check, the
        destination library was already decided when the channel was registered."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM chat_integrations WHERE platform = ? AND external_channel_id = ?",
                (platform, external_channel_id),
            ).fetchone()
        return self._row(row) if row is not None else None

    def list_chat_integrations(self, library_id: str, actor: dict | None = None) -> list[dict]:
        self.get_library(library_id, actor)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM chat_integrations WHERE library_id = ? ORDER BY created_at",
                (library_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def remove_chat_integration(self, library_id: str, integration_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM chat_integrations WHERE library_id = ? AND id = ?",
                (library_id, integration_id),
            )
            return bool(cursor.rowcount and cursor.rowcount > 0)
