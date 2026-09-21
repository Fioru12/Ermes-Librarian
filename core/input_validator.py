"""
input_validator.py
Validazione e sanitizzazione dei nomi caricati dagli utenti; verifica che il
contenuto di un file corrisponda al tipo dichiarato prima del parsing.
"""

import os
import re


def sanitize_username(username: str) -> str:
    sanitized = re.sub(r"[^a-z0-9._-]", "", (username or "").strip().lower())
    return sanitized[:50]


def sanitize_upload_name(name: str) -> str | None:
    safe_name = os.path.basename((name or "").strip()).replace("\x00", "")
    if not safe_name or safe_name in {".", ".."}:
        return None
    if not re.fullmatch(r"[A-Za-z0-9._ -]{1,120}", safe_name):
        return None
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in {".txt", ".md", ".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".rtf"}:
        return None
    return safe_name


def matches_expected_file_signature(uploaded_file, safe_name: str) -> bool:
    header = bytes(uploaded_file.getbuffer()[:8])
    ext = os.path.splitext(safe_name)[1].lower()
    if ext == ".pdf":
        return header.startswith(b"%PDF-")
    if ext in {".docx", ".xlsx", ".pptx"}:
        return header.startswith(b"PK\x03\x04")
    if ext in {".txt", ".md", ".csv"}:
        return b"\x00" not in bytes(uploaded_file.getbuffer()[:1024])
    if ext == ".rtf":
        return header.startswith(b"{\\rtf") or b"\x00" not in bytes(uploaded_file.getbuffer()[:1024])
    return False


def validate_and_scan_document(name: str, content: bytes) -> tuple[bool, str]:
    """Valida nome, estensione, magic bytes e sicurezza del contenuto del documento.

    Restituisce (True, safe_name) se il file è valido e sicuro,
    (False, motivo_rifiuto) se il file non è valido o contiene minacce rilevate.
    """
    safe_name = sanitize_upload_name(name)
    if not safe_name:
        return False, "Nome file non valido o estensione non supportata"

    if not content:
        return False, "File vuoto non supportato"

    ext = os.path.splitext(safe_name)[1].lower()
    header = content[:8]
    if ext == ".pdf" and not header.startswith(b"%PDF-"):
        return False, "Il file non corrisponde alla firma di un documento PDF valido"
    if ext in {".docx", ".xlsx", ".pptx"} and not header.startswith(b"PK\x03\x04"):
        return False, "Il file non corrisponde alla firma di un archivio Office valido"
    if ext in {".txt", ".md", ".csv"} and b"\x00" in content[:1024]:
        return False, "Il file contiene caratteri nulli non consentiti per file di testo"
    if ext == ".rtf" and not (header.startswith(b"{\\rtf") or b"\x00" not in content[:1024]):
        return False, "Il file non corrisponde alla firma di un documento RTF valido"

    from core.security_scanner import scan_document

    scan_res = scan_document(safe_name, content)
    if not scan_res.is_safe:
        return False, f"File rifiutato per sicurezza [{scan_res.threat_name}]: {scan_res.details}"

    return True, safe_name

