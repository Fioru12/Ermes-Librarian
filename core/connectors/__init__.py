"""
core/connectors/__init__.py
Enterprise Connectors package for Ermes.
"""

from core.connectors.base import BaseConnector, DeltaSyncResult, RemoteDocument, SyncResult
from core.connectors.confluence import ConfluenceConnector
from core.connectors.google_drive import GoogleDriveConnector
from core.connectors.local_folder import LocalFolderConnector
from core.connectors.microsoft_graph import MicrosoftGraphConnector
from core.connectors.s3_bucket import S3BucketConnector
from core.connectors.web_scraper import WebScraperConnector
from core.connectors.webdav import WebDAVConnector

__all__ = [
    "BaseConnector",
    "RemoteDocument",
    "SyncResult",
    "DeltaSyncResult",
    "LocalFolderConnector",
    "MicrosoftGraphConnector",
    "GoogleDriveConnector",
    "ConfluenceConnector",
    "WebScraperConnector",
    "S3BucketConnector",
    "WebDAVConnector",
]

