import pytest
from pathlib import Path

from core.library_pack import export_library_pack, import_library_pack, KnowledgePackError
from core.library_store import LibraryStore


def test_export_and_import_knowledge_pack(tmp_path: Path):
    source_db = tmp_path / "source.sqlite3"
    target_db = tmp_path / "target.sqlite3"
    storage_dir = tmp_path / "storage"
    packs_dir = tmp_path / "packs"
    storage_dir.mkdir(parents=True)
    packs_dir.mkdir(parents=True)

    source_store = LibraryStore(source_db)
    target_store = LibraryStore(target_db)

    # 1. Setup source library with document and chunks
    lib = source_store.create_library("Manuali Tecnici", "Documentazione macchinari", "shared", owner_id="admin")
    lib_id = lib["id"]

    content = b"Manuale operativo pressa idraulica. Pressione max 200 bar."
    stored_name = "f01_manuale.txt"
    dest = storage_dir / lib_id / stored_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)

    source_store.add_document(
        library_id=lib_id,
        filename="manuale.txt",
        media_type="text/plain",
        content=content,
        storage_path=f"{lib_id}/{stored_name}",
        status="ready",
        chunks=[
            ("Manuale operativo pressa idraulica.", "Pagina 1"),
            ("Pressione max 200 bar.", "Pagina 2"),
        ],
    )

    # 2. Export package
    pack_file = packs_dir / "manuali.ermes"
    exported_path = export_library_pack(source_store, lib_id, storage_dir, pack_file)
    assert Path(exported_path).is_file()

    # 3. Import package into target store
    imported_lib = import_library_pack(
        store=target_store,
        pack_path=pack_file,
        storage_dir=storage_dir,
        owner_id="admin",
        override_name="Manuali Tecnici (Importati)",
    )

    assert imported_lib["name"] == "Manuali Tecnici (Importati)"
    new_lib_id = imported_lib["id"]

    # 4. Verify documents and chunks exist in target library
    docs = target_store.list_documents(new_lib_id)
    assert len(docs) == 1
    assert docs[0]["filename"] == "manuale.txt"
    assert docs[0]["status"] == "ready"

    chunks = target_store.get_document_chunks(new_lib_id, docs[0]["id"])
    assert len(chunks) == 2
    assert "pressa idraulica" in chunks[0]["text"]
    assert "200 bar" in chunks[1]["text"]

    # 5. Verify search works in target store via FTS5
    results, profile = target_store.search_with_profile(new_lib_id, "idraulica")
    assert len(results) >= 1
    assert "pressa idraulica" in results[0]["excerpt"]


def test_import_invalid_pack_fails(tmp_path: Path):
    fake_pack = tmp_path / "not_a_pack.ermes"
    fake_pack.write_text("corrupted", encoding="utf-8")

    store = LibraryStore(tmp_path / "test.sqlite3")
    with pytest.raises(KnowledgePackError):
        import_library_pack(store, fake_pack, tmp_path / "storage")


def test_library_pack_api_endpoints(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    from api import app
    from api.auth import session_store
    from config import cfg

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = cfg.replace(
        BASE_DIR=str(app_dir), ADMIN_USERNAME="admin", ADMIN_PASSWORD="admin_password_123!", API_KEY=""
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    session_store.clear()

    import api.libraries

    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    lib = store.create_library("Catalogo", "Catalogo Ricambi", "shared", owner_id="admin")

    client = TestClient(app)
    assert (
        client.post("/api/auth/login", json={"username": "admin", "password": "admin_password_123!"}).status_code == 200
    )

    # Test export API
    export_resp = client.get(f"/api/libraries/{lib['id']}/export")
    assert export_resp.status_code == 200
    assert "application/gzip" in export_resp.headers["content-type"]
    assert export_resp.content.startswith(b"\x1f\x8b")  # GZIP header

    # Test import API
    import_resp = client.post(
        "/api/libraries/import-pack",
        files={"file": ("catalogo_clone.ermes", export_resp.content, "application/gzip")},
        data={"name": "Catalogo Clonato"},
    )
    assert import_resp.status_code == 201
    imported_data = import_resp.json()
    assert imported_data["name"] == "Catalogo Clonato"


def _pack_bytes(documents: list[dict], files: dict[str, bytes] | None = None) -> bytes:
    """Costruisce un .ermes a mano: e' cio' che farebbe chi lo manipola."""
    import io
    import json
    import tarfile

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:

        def _add(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        _add("manifest.json", json.dumps({"library": {"name": "Ostile"}}).encode())
        _add("documents.json", json.dumps(documents).encode())
        for name, data in (files or {}).items():
            _add(name, data)
    return buffer.getvalue()


def test_manifest_filename_is_sanitized_like_an_upload(tmp_path: Path):
    """Il nome del documento viene dal manifest, cioe' dall'autore
    dell'archivio. Fino al 18 settembre 2026 finiva nel percorso di
    destinazione cosi' com'era: ora passa dalle stesse regole di un upload
    (basename, caratteri ammessi, estensione nota)."""
    store = LibraryStore(tmp_path / "db.sqlite3")
    storage = tmp_path / "storage"

    pack = tmp_path / "traversal.ermes"
    pack.write_bytes(_pack_bytes([{"document": {"id": "d1", "filename": "../../evaso.txt"}, "chunks": []}]))
    library = import_library_pack(store, pack, storage)
    scritti = [p for p in storage.rglob("*") if p.is_file()]
    assert scritti and all(p.is_relative_to(storage / library["id"]) for p in scritti)
    assert all(p.name.endswith("_evaso.txt") for p in scritti)
    assert not (tmp_path / "evaso.txt").exists()

    pack = tmp_path / "estensione.ermes"
    pack.write_bytes(_pack_bytes([{"document": {"id": "d1", "filename": "payload.exe"}, "chunks": []}]))
    with pytest.raises(KnowledgePackError, match="nome di documento"):
        import_library_pack(store, pack, storage)


def test_oversized_member_is_rejected_before_being_read(tmp_path: Path):
    """La dimensione decompressa e' nell'intestazione del membro: si rifiuta
    da li', senza leggere il contenuto — quindi una bomba gz non si espande."""
    store = LibraryStore(tmp_path / "db.sqlite3")
    pack = tmp_path / "bomba.ermes"
    pack.write_bytes(
        _pack_bytes(
            [{"document": {"id": "d1", "filename": "grande.txt"}, "chunks": []}],
            files={"files/d1_grande.txt": b"\0" * 2048},
        )
    )
    with pytest.raises(KnowledgePackError, match="limite per file"):
        import_library_pack(store, pack, tmp_path / "storage", max_member_bytes=1024)


def test_import_api_streams_to_disk_and_caps_the_pack(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    from api import app
    from api.auth import session_store
    from config import cfg

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = cfg.replace(
        BASE_DIR=str(app_dir),
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="admin_password_123!",
        API_KEY="",
        ADMIN_MAX_UPLOAD_MB=1,
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    session_store.clear()
    import api.libraries

    monkeypatch.setattr(api.libraries, "_store", None)
    client = TestClient(app)
    assert (
        client.post("/api/auth/login", json={"username": "admin", "password": "admin_password_123!"}).status_code == 200
    )

    # 1 MB per file x fattore 20 = 20 MB: 21 MB di archivio vengono rifiutati.
    from core.library_pack import MAX_TOTAL_BYTES_FACTOR

    troppo = b"\0" * ((MAX_TOTAL_BYTES_FACTOR + 1) * 1024 * 1024)
    resp = client.post("/api/libraries/import-pack", files={"file": ("x.ermes", troppo, "application/gzip")})
    assert resp.status_code == 413

    resp = client.post("/api/libraries/import-pack", files={"file": ("x.ermes", b"", "application/gzip")})
    assert resp.status_code == 400
