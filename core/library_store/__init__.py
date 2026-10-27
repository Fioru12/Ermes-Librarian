"""Persistence layer for Ermes Knowledge libraries.

SQLite keeps the first local-first release easy to run. This package owns the
domain contract so a later PostgreSQL implementation can replace it without
changing the API surface.

`LibraryStore` is composed from one mixin per area (documents, ingestion,
search, notes, sources, privacy) on top of `StoreBase`, which owns database
access, access rules, libraries and members.
"""

from __future__ import annotations

from core.library_store.common import (
    _QUERY_STOPWORDS,
    LibraryAccessError,
    LibraryNotFoundError,
    resolve_storage_path,
    storage_relative_path,
)
from core.library_store.documents import DocumentsMixin
from core.library_store.ingestion import IngestionMixin
from core.library_store.notes import NotesMixin
from core.library_store.privacy import PrivacyMixin
from core.library_store.search import SearchMixin
from core.library_store.sources import SourcesMixin

__all__ = [
    "_QUERY_STOPWORDS",
    "LibraryAccessError",
    "LibraryNotFoundError",
    "LibraryStore",
    "resolve_storage_path",
    "storage_relative_path",
]


class LibraryStore(DocumentsMixin, IngestionMixin, SearchMixin, SourcesMixin, NotesMixin, PrivacyMixin):
    pass
