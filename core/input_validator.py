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
    if ext not in {".txt", ".md", ".pdf", ".docx", ".xlsx"}:
        return None
    return safe_name


def matches_expected_file_signature(uploaded_file, safe_name: str) -> bool:
    header = bytes(uploaded_file.getbuffer()[:8])
    ext = os.path.splitext(safe_name)[1].lower()
    if ext == ".pdf":
        return header.startswith(b"%PDF-")
    if ext in {".docx", ".xlsx"}:
        return header.startswith(b"PK\x03\x04")
    if ext in {".txt", ".md"}:
        return b"\x00" not in bytes(uploaded_file.getbuffer()[:1024])
    return False
