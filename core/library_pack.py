"""Export and import portable Knowledge Packs (.ermes bundles).

A Knowledge Pack is a self-contained, portable archive (.ermes / tar.gz) containing:
- Library metadata and assistant policies (manifest.json)
- Document structures, versions, and chunks (documents.json)
- Original document binaries (files/)

Allows seamless offline backup, sharing, and cross-instance distribution.
"""
from __future__ import annotations

import contextlib
import io
import json
import tarfile
import uuid
from datetime import datetime
from pathlib import Path

from core.library_store import LibraryStore, resolve_storage_path, storage_relative_path


class KnowledgePackError(Exception):
    """Raised when knowledge pack export or import fails."""


def export_library_pack(
    store: LibraryStore,
    library_id: str,
    storage_dir: str | Path,
    output_path: str | Path,
    actor: dict | None = None,
) -> str:
    """Export an entire library with documents and chunks into a portable .ermes bundle."""
    library = store.get_library(library_id, actor)
    documents = store.list_documents(library_id, actor)
    storage_root = Path(storage_dir)

    manifest = {
        "format": "ermes_knowledge_pack",
        "version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "library": {
            "name": library["name"],
            "description": library.get("description", ""),
            "visibility": library.get("visibility", "private"),
            "assistant_mode": library.get("assistant_mode", "evidence_only"),
            "assistant_provider": library.get("assistant_provider", "local_ollama"),
            "assistant_model": library.get("assistant_model", ""),
        },
        "document_count": len(documents),
    }

    doc_records = []
    for doc in documents:
        doc_id = doc["id"]
        chunks = store.get_document_chunks(library_id, doc_id, actor)
        versions = store.list_document_versions(library_id, doc_id, actor)
        doc_records.append({
            "document": doc,
            "chunks": chunks,
            "versions": versions,
        })

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(out_file, "w:gz") as tar:
        # Add manifest.json
        manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))

        # Add documents.json
        docs_bytes = json.dumps(doc_records, indent=2, ensure_ascii=False).encode("utf-8")
        info = tarfile.TarInfo(name="documents.json")
        info.size = len(docs_bytes)
        tar.addfile(info, io.BytesIO(docs_bytes))

        # Add original files
        for doc in documents:
            storage_path = doc.get("storage_path")
            if storage_path:
                try:
                    local_file = resolve_storage_path(storage_path, storage_root)
                    if local_file.is_file():
                        arcname = f"files/{doc['id']}_{doc['filename']}"
                        tar.add(str(local_file), arcname=arcname)
                except Exception:
                    pass

    return str(out_file)


def import_library_pack(
    store: LibraryStore,
    pack_path: str | Path,
    storage_dir: str | Path,
    owner_id: str = "admin",
    override_name: str = "",
) -> dict:
    """Import a .ermes knowledge pack and create a new library with all documents and chunks."""
    pack_file = Path(pack_path)
    if not pack_file.is_file():
        raise KnowledgePackError(f"File pacchetto non trovato: {pack_path}")

    storage_root = Path(storage_dir)

    try:
        tar = tarfile.open(pack_file, "r:gz")
    except Exception as e:
        raise KnowledgePackError(f"File pacchetto non valido o corrotto: {e}") from e

    try:
        # Validate members against directory traversal
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in member.name:
                raise KnowledgePackError("Pacchetto non valido: percorso sospetto rilevato")

        # Read manifest
        try:
            manifest_member = tar.extractfile("manifest.json")
            if manifest_member is None:
                raise KnowledgePackError("Manifest mancante nel pacchetto")
            manifest = json.loads(manifest_member.read().decode("utf-8"))
        except Exception as e:
            raise KnowledgePackError(f"Impossibile leggere il manifest del pacchetto: {e}") from e

        # Read documents
        try:
            docs_member = tar.extractfile("documents.json")
            if docs_member is None:
                raise KnowledgePackError("Dati documenti mancanti nel pacchetto")
            doc_records = json.loads(docs_member.read().decode("utf-8"))
        except Exception as e:
            raise KnowledgePackError(f"Impossibile leggere i documenti del pacchetto: {e}") from e

        # Create library
        lib_meta = manifest.get("library", {})
        lib_name = override_name.strip() or lib_meta.get("name", "Biblioteca Importata")
        visibility = lib_meta.get("visibility", "private")
        if visibility not in {"private", "shared"}:
            visibility = "private"

        library = store.create_library(
            name=lib_name,
            description=lib_meta.get("description", ""),
            visibility=visibility,
            owner_id=owner_id,
        )
        library_id = library["id"]

        # Restore assistant policy if present
        if "assistant_mode" in lib_meta:
            mode = lib_meta.get("assistant_mode", "evidence_only")
            provider = lib_meta.get("assistant_provider", "")
            with contextlib.suppress(Exception):
                store.set_assistant_policy(
                    library_id=library_id,
                    mode=mode,
                    provider_name=provider,
                )

        # Extract files and recreate documents
        target_storage = storage_root / library_id
        target_storage.mkdir(parents=True, exist_ok=True)

        for record in doc_records:
            if not isinstance(record, dict):
                continue
            doc_meta: dict = record.get("document") or {}
            chunks: list = record.get("chunks") or []
            filename = doc_meta.get("filename", "documento.txt")
            media_type = doc_meta.get("media_type", "text/plain")

            # Check if file binary exists in archive
            arcname = f"files/{doc_meta['id']}_{filename}"
            file_content = b""
            try:
                extracted_file = tar.extractfile(arcname)
                if extracted_file:
                    file_content = extracted_file.read()
            except Exception:
                pass

            stored_filename = f"{uuid.uuid4().hex[:12]}_{filename}"
            dest_file = target_storage / stored_filename
            dest_file.write_bytes(file_content)

            chunk_tuples = [(c.get("text", ""), c.get("source_locator", "")) for c in chunks]

            _doc = store.add_document(
                library_id=library_id,
                filename=filename,
                media_type=media_type,
                content=file_content,
                storage_path=storage_relative_path(library_id, stored_filename),
                status=doc_meta.get("status", "ready"),
                chunks=chunk_tuples,
            )

        return store.get_library(library_id)
    finally:
        tar.close()
