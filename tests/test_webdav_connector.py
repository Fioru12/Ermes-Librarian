"""Unit tests for WebDAVConnector in core/connectors/webdav.py."""

from unittest.mock import MagicMock, patch

from core.connectors.webdav import WebDAVConnector


MOCK_PROPFIND_RESPONSE = """<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/user/docs/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/user/docs/manual.pdf</d:href>
    <d:propstat>
      <d:prop>
        <d:displayname>manual.pdf</d:displayname>
        <d:getcontentlength>2048</d:getcontentlength>
        <d:getlastmodified>Mon, 01 Jan 2026 10:00:00 GMT</d:getlastmodified>
        <d:resourcetype/>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/user/docs/notes.txt</d:href>
    <d:propstat>
      <d:prop>
        <d:displayname>notes.txt</d:displayname>
        <d:getcontentlength>128</d:getcontentlength>
        <d:getlastmodified>Tue, 02 Jan 2026 12:00:00 GMT</d:getlastmodified>
        <d:resourcetype/>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/user/docs/archive.zip</d:href>
    <d:propstat>
      <d:prop>
        <d:displayname>archive.zip</d:displayname>
        <d:getcontentlength>9999</d:getcontentlength>
        <d:resourcetype/>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>"""


def test_webdav_connector_test_connection_missing_url():
    connector = WebDAVConnector({"base_url": ""})
    ok, msg = connector.test_connection()
    assert ok is False
    assert "non specificato" in msg


def test_webdav_connector_test_connection_success():
    connector = WebDAVConnector({
        "base_url": "https://nextcloud.example.com/remote.php/dav/files/user/",
        "username": "alice",
        "password": "secret_token",
    })

    mock_resp = MagicMock(status_code=207, text=MOCK_PROPFIND_RESPONSE)
    with patch("httpx.Client.request", return_value=mock_resp):
        ok, msg = connector.test_connection()
        assert ok is True
        assert "raggiungibile" in msg


def test_webdav_connector_test_connection_unauthorized():
    connector = WebDAVConnector({
        "base_url": "https://nextcloud.example.com/remote.php/dav/files/user/",
        "username": "alice",
        "password": "wrong_password",
    })

    mock_resp = MagicMock(status_code=401, text="Unauthorized")
    with patch("httpx.Client.request", return_value=mock_resp):
        ok, msg = connector.test_connection()
        assert ok is False
        assert "Autenticazione WebDAV fallita" in msg


def test_webdav_connector_fetch_documents():
    connector = WebDAVConnector({
        "base_url": "https://nextcloud.example.com/remote.php/dav/files/user/",
        "username": "alice",
        "password": "token",
        "max_files": 10,
    })

    def _mock_request(method, url, **kwargs):
        if method == "PROPFIND":
            return MagicMock(status_code=207, content=MOCK_PROPFIND_RESPONSE.encode("utf-8"), text=MOCK_PROPFIND_RESPONSE)
        raise ValueError(f"Unexpected method: {method}")

    def _mock_get(url, **kwargs):
        if "manual.pdf" in url:
            return MagicMock(status_code=200, content=b"%PDF-1.4 manual contents")
        if "notes.txt" in url:
            return MagicMock(status_code=200, content=b"Plain text notes")
        return MagicMock(status_code=404, content=b"Not found")

    with patch("httpx.Client.request", side_effect=_mock_request), patch("httpx.Client.get", side_effect=_mock_get):
        docs = connector.fetch_documents()
        assert len(docs) == 2

        names = {d.name for d in docs}
        assert "manual.pdf" in names
        assert "notes.txt" in names
        assert "archive.zip" not in names  # Unsupported extension

        pdf_doc = next(d for d in docs if d.name == "manual.pdf")
        assert pdf_doc.content == b"%PDF-1.4 manual contents"
        assert pdf_doc.media_type == "application/pdf"
        assert pdf_doc.metadata["size"] == 2048

        txt_doc = next(d for d in docs if d.name == "notes.txt")
        assert txt_doc.content == b"Plain text notes"
        assert txt_doc.media_type == "text/plain"
