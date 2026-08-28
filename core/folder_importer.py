"""Importazione documenti da cartelle registrate (Modello A).

Filosofia: i diritti sulle cartelle li ha l'account con cui gira Ermes, NON
gli utenti. Qui non vengono mai salvate credenziali: solo il percorso. La
scansione importa i file supportati (.txt/.pdf/.docx), salta i duplicati per
hash del contenuto e registra gli errori senza interrompere il batch.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from core.library_store import storage_relative_path

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx"}

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}

MAX_IMPORT_FILE_BYTES = 50 * 1024 * 1024  # allineato a un limite prudenziale


def scan_import_source(
    store,
    library_id: str,
    source: dict,
    storage_dir: str,
) -> dict:
    """Scan one registered folder and import new documents.

    Returns counts so the API can report exactly what happened. A file that
    cannot be read is counted as failed, never fatal for the rest of the batch.

    `storage_dir` was accepted but never used: this called store.add_document
    with a storage_path pointing under Ermes' own storage tree, but never
    actually copied the file's bytes there — add_document only records
    metadata, it does not write to disk (the upload endpoint in
    api/libraries.py writes the file itself before calling add_document).
    Every scan "succeeded" (imported: [...]), and every one of those imports
    then failed ingestion with "Originale non disponibile", because the row
    pointed at a file that was never created. Found by actually running the
    feature through the browser, not by reading the code.
    """
    root = Path(source["path"])
    result = {"path": source["path"], "imported": [], "skipped_duplicates": [], "skipped_unsupported": [], "failed": []}
    if not root.exists() or not root.is_dir():
        result["failed"].append({"file": str(root), "error": "Cartella non raggiungibile dall'account del server"})
        return result

    known_hashes = store.existing_content_hashes(library_id)
    all_files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p).lower())
    files = []
    for candidate in all_files:
        if candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(candidate)
        else:
            result["skipped_unsupported"].append(candidate.name)
    for file_path in files:
        try:
            if file_path.stat().st_size > MAX_IMPORT_FILE_BYTES:
                result["failed"].append({"file": file_path.name, "error": "File troppo grande"})
                continue
            content = file_path.read_bytes()
            if not content:
                result["failed"].append({"file": file_path.name, "error": "File vuoto"})
                continue
            digest = hashlib.sha256(content).hexdigest()
            if digest in known_hashes:
                result["skipped_duplicates"].append(file_path.name)
                continue
            extension = file_path.suffix.lower()
            stored_filename = f"{digest[:12]}_{file_path.name}"
            destination = Path(storage_dir) / library_id / stored_filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            document = store.add_document(
                library_id=library_id,
                filename=file_path.name,
                media_type=MEDIA_TYPES[extension],
                content=content,
                storage_path=storage_relative_path(library_id, stored_filename),
                status="queued",
                chunks=[],
            )
            job = store.start_ingestion_job(library_id, file_path.name, document_id=document["id"])
            known_hashes.add(digest)
            result["imported"].append({"filename": file_path.name, "document_id": document["id"], "job_id": job["id"]})
        except Exception as error:  # un file corrotto non ferma la scansione
            result["failed"].append({"file": file_path.name, "error": str(error)})
    store.touch_import_source(library_id, source["id"])
    return result
