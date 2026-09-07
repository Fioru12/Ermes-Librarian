"""
core/connectors/__init__.py
Enterprise Connectors package for Ermes.
"""

from core.connectors.base import BaseConnector, RemoteDocument, SyncResult

__all__ = ["BaseConnector", "RemoteDocument", "SyncResult"]
