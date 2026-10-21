"""Il visualizzatore PDF apre i documenti "inline"; tutto il resto deve restare un download.

Il tipo di un file lo dichiara chi lo carica. Senza questo controllo, un `.txt` caricato come
`text/html` e richiesto con `?inline=true` veniva aperto come pagina sotto il dominio dell'app.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.libraries import _verify_api_key, get_library_store, router
from api.security_headers import content_security_policy
from config import cfg
from core.library_store import LibraryStore

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _client_with(tmp_path: Path, monkeypatch, filename: str, media_type: str, content: bytes):
    monkeypatch.setattr(cfg, "LIBRARY_DB_PATH", str(tmp_path / "libraries.db"))
    monkeypatch.setattr(cfg, "LIBRARY_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(cfg, "STORAGE_BACKEND", "local")
    # Il download scrive nel registro di audit: non su quello vero del progetto.
    monkeypatch.setattr(cfg, "AUDIT_FILE", str(tmp_path / "audit.jsonl"), raising=False)
    store = LibraryStore(tmp_path / "libraries.db")
    lib = store.create_library("Lib", "", "private", "testuser")
    doc = store.add_document(
        library_id=lib["id"], filename=filename, media_type=media_type, content=content,
        storage_path=f"{lib['id']}/{filename}",
    )
    folder = tmp_path / "storage" / lib["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_bytes(content)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_library_store] = lambda: store
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "testuser", "role": "admin"}
    return TestClient(app), f"/api/libraries/{lib['id']}/documents/{doc['id']}/download"


def test_a_real_pdf_opens_inline_with_a_fixed_type(tmp_path, monkeypatch):
    client, url = _client_with(tmp_path, monkeypatch, "manuale.pdf", "application/octet-stream", PDF)
    res = client.get(url, params={"inline": "true"})
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"].startswith("inline")


@pytest.mark.parametrize(
    "filename, media_type, content",
    [
        ("pagina.txt", "text/html", b"<h1>iniettato</h1><script>alert(1)</script>"),
        ("immagine.svg", "image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>"),
        ("finto.pdf", "application/pdf", b"<html>non e' un PDF</html>"),
        ("manuale.docx", "application/pdf", PDF),
    ],
)
def test_anything_that_is_not_a_real_pdf_is_always_a_download(tmp_path, monkeypatch, filename, media_type, content):
    client, url = _client_with(tmp_path, monkeypatch, filename, media_type, content)
    res = client.get(url, params={"inline": "true"})
    assert res.headers["content-disposition"].startswith("attachment")


def test_without_inline_even_a_pdf_is_a_download(tmp_path, monkeypatch):
    client, url = _client_with(tmp_path, monkeypatch, "manuale.pdf", "application/pdf", PDF)
    assert client.get(url).headers["content-disposition"].startswith("attachment")


def test_only_the_document_download_may_be_framed_by_this_app():
    scarico = content_security_policy("/api/libraries/abc/documents/def/download")
    assert "frame-ancestors 'self'" in scarico
    assert content_security_policy("/v1/api/libraries/abc/documents/def/download") == scarico
    # tutto il resto continua a vietare l'incorporamento
    for path in ("/", "/api/libraries", "/api/libraries/abc/documents/def/download-url", "/api/libraries/abc/documents/def/download/x"):
        assert "frame-ancestors 'none'" in content_security_policy(path), path
