"""Unit tests for S3BucketConnector in core/connectors/s3_bucket.py."""

import io
from datetime import datetime
from unittest.mock import MagicMock

from core.connectors.s3_bucket import S3BucketConnector



def test_s3_connector_test_connection_missing_bucket():
    connector = S3BucketConnector({"bucket_name": ""})
    ok, msg = connector.test_connection()
    assert ok is False
    assert "non specificato" in msg


def test_s3_connector_test_connection_success():
    connector = S3BucketConnector({"bucket_name": "company-docs"})
    mock_client = MagicMock()
    mock_client.head_bucket.return_value = {}
    connector._client = mock_client

    ok, msg = connector.test_connection()
    assert ok is True
    assert "raggiungibile" in msg
    mock_client.head_bucket.assert_called_once_with(Bucket="company-docs")


def test_s3_connector_test_connection_failure():
    connector = S3BucketConnector({"bucket_name": "private-bucket"})
    mock_client = MagicMock()
    mock_client.head_bucket.side_effect = Exception("403 Forbidden")
    connector._client = mock_client

    ok, msg = connector.test_connection()
    assert ok is False
    assert "403 Forbidden" in msg


def test_s3_connector_fetch_documents_filters_and_extracts():
    connector = S3BucketConnector({
        "bucket_name": "docs-bucket",
        "prefix": "hr/",
        "max_files": 10,
    })
    mock_client = MagicMock()
    mock_client.head_bucket.return_value = {}

    # Setup paginator
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "hr/policy.pdf", "Size": 1024, "LastModified": datetime(2026, 1, 1), "ETag": '"abc123etag"'},
                {"Key": "hr/notes.md", "Size": 512, "LastModified": datetime(2026, 1, 2), "ETag": '"def456etag"'},
                {"Key": "hr/subfolder/", "Size": 0, "LastModified": datetime(2026, 1, 1)},  # directory -> skip
                {"Key": "hr/program.exe", "Size": 2048, "LastModified": datetime(2026, 1, 1)},  # unsupported ext -> skip
            ]
        }
    ]
    mock_client.get_paginator.return_value = mock_paginator

    def _mock_get_object(*args, **kwargs):
        key = kwargs.get("Key")
        if key == "hr/policy.pdf":
            return {"Body": io.BytesIO(b"%PDF-1.4 mock pdf content")}
        if key == "hr/notes.md":
            return {"Body": io.BytesIO(b"# HR Notes\nSample markdown.")}
        raise FileNotFoundError(str(key))



    mock_client.get_object.side_effect = _mock_get_object
    connector._client = mock_client

    docs = connector.fetch_documents()
    assert len(docs) == 2

    pdf_doc = next(d for d in docs if d.name == "policy.pdf")
    assert pdf_doc.id == "s3://docs-bucket/hr/policy.pdf"
    assert pdf_doc.content == b"%PDF-1.4 mock pdf content"
    assert pdf_doc.media_type == "application/pdf"
    assert pdf_doc.metadata["etag"] == "abc123etag"

    md_doc = next(d for d in docs if d.name == "notes.md")
    assert md_doc.id == "s3://docs-bucket/hr/notes.md"
    assert md_doc.content == b"# HR Notes\nSample markdown."
    assert md_doc.media_type == "text/markdown"
