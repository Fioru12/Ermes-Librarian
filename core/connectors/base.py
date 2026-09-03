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
