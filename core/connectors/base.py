"""
core/connectors/base.py
Base abstractions for Enterprise Cloud Connectors in Ermes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class RemoteDocument:
    id: str
    name: str
    content: bytes
    media_type: str
    source_url: str
    last_modified: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SyncResult:
    connector_type: str
    total_found: int
    synced_count: int
    errors: list[str] = field(default_factory=list)
    synced_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class DeltaSyncResult:
    connector_type: str
    updated_documents: list[RemoteDocument]
    deleted_document_ids: list[str] = field(default_factory=list)
    next_delta_token: str | None = None
    errors: list[str] = field(default_factory=list)
    synced_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class BaseConnector(ABC):
    """Abstract base class for all enterprise content connectors."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Verify authentication and reachability to the remote source."""
        pass

    @abstractmethod
    def fetch_documents(self) -> list[RemoteDocument]:
        """Fetch updated documents from the remote source."""
        pass

    def fetch_delta(self, delta_token: str | None = None) -> DeltaSyncResult:
        """Fetch incremental changes (new/updated documents and deleted document ids) since delta_token.

        Connectors without native cursor/delta token APIs fall back to full scan.
        """
        try:
            docs = self.fetch_documents()
            return DeltaSyncResult(
                connector_type=self.__class__.__name__,
                updated_documents=docs,
                deleted_document_ids=[],
                next_delta_token=None,
            )
        except Exception as e:
            return DeltaSyncResult(
                connector_type=self.__class__.__name__,
                updated_documents=[],
                deleted_document_ids=[],
                next_delta_token=delta_token,
                errors=[str(e)],
            )
