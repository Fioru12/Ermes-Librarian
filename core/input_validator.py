"""
input_validator.py
Validazione centralizzata degli input utente.
Previene: path traversal, injection, file upload abuse, ecc.
"""
import os
import re
from pathlib import Path

# ============================================================
# CONFIGURAZIONI
# ============================================================
MAX_FILENAME_LENGTH = 255
MAX_USERNAME_LENGTH = 32
MAX_QUERY_LENGTH = 2000
MAX_MODULE_NAME_LENGTH = 64
ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".pdf", ".docx"}
MAX_FILE_SIZE_MB = 50


# ============================================================
# VALIDATORI GENERICI
# ============================================================

def is_safe_string(text: str, max_len: int = 1000, allow_special: bool = False) -> bool:
    """
    Verifica se stringa è sicura (no null bytes, no path traversal, ecc).

    Args:
        text: Stringa da validare
        max_len: Lunghezza massima
        allow_special: Se permettere caratteri speciali

    Returns:
        True se sicura, False altrimenti
    """
    if not isinstance(text, str) or not text:
        return False

    if len(text) > max_len:
        return False

    # Null bytes - SEMPRE pericoloso
    if '\0' in text:
        return False

    # Path traversal - SEMPRE pericoloso
    if '..' in text or '~' in text:
        return False

    return allow_special or bool(re.match(r'^[a-zA-Z0-9\s\-_.àèéìòù()]+$', text))


def is_safe_module_name(module_name: str) -> bool:
    """
    Valida nome modulo (directory name).
    Allineato con api.py (_resolve_module_name).
    Permette lettere, numeri, underscore, trattini — max 80 caratteri.

    Args:
        module_name: Nome modulo

    Returns:
        True se valido, False altrimenti
    """
    if not module_name or len(module_name) > MAX_MODULE_NAME_LENGTH:
        return False

    if not re.match(r'^[A-Za-z0-9_-]{1,80}$', module_name):
        return False

    # No path traversal (doppia sicurezza)
    return not ('..' in module_name or '/' in module_name or '\\' in module_name)


def is_safe_username(username: str) -> bool:
    """
    Valida username.

    Args:
        username: Username

    Returns:
        True se valido, False altrimenti
    """
    if not username or len(username) > MAX_USERNAME_LENGTH:
        return False

    # Alphanumeric + underscore (standard username format)
    return re.match(r'^[a-zA-Z0-9_-]+$', username)


def is_safe_query(query: str) -> tuple[bool, str]:
    """
    Valida query utente.

    Returns:
        (valid: bool, reason: str)
    """
    if not query:
        return False, "Query vuota"

    if len(query) > MAX_QUERY_LENGTH:
        return False, f"Query troppo lunga (max {MAX_QUERY_LENGTH} caratteri)"

    # Null bytes - NO
    if '\0' in query:
        return False, "Query contiene caratteri non validi"

    return True, ""


# ============================================================
# VALIDATORI FILE
# ============================================================

def is_safe_filename(filename: str) -> tuple[bool, str]:
    """
    Valida nome file (per upload).

    Returns:
        (valid: bool, reason: str)
    """
    if not filename:
        return False, "Nome file vuoto"

    if len(filename) > MAX_FILENAME_LENGTH:
        return False, f"Nome file troppo lungo (max {MAX_FILENAME_LENGTH} caratteri)"

    # No path separators
    if '/' in filename or '\\' in filename:
        return False, "Percorso non permettito nel nome file"

    # No null bytes
    if '\0' in filename:
        return False, "Nome file contiene caratteri non validi"

    # No path traversal
    if '..' in filename:
        return False, "Path traversal non permesso"

    # Get extension
    _, ext = os.path.splitext(filename)
    if ext.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(ALLOWED_UPLOAD_EXTENSIONS)
        return False, f"Tipo file non supportato. Supportati: {allowed}"

    return True, ""


def is_safe_file_size(file_size_bytes: int) -> tuple[bool, str]:
    """
    Valida dimensione file.

    Returns:
        (valid: bool, reason: str)
    """
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024

    if file_size_bytes == 0:
        return False, "File vuoto"

    if file_size_bytes > max_bytes:
        return False, f"File troppo grande (max {MAX_FILE_SIZE_MB} MB)"

    return True, ""


def sanitize_filename(filename: str) -> str:
    """
    Sanitizza nome file rimuovendo caratteri pericolosi.

    Args:
        filename: Nome file da sanitizzare

    Returns:
        Nome file sanitizzato
    """
    # Rimuovi percorsi
    filename = os.path.basename(filename)

    # Sostituisci caratteri problematici con underscore
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

    # Rimuovi .. e path traversal tentatives
    filename = filename.replace('..', '')

    # Se vuoto dopo sanitizzazione, dai default
    if not filename:
        filename = 'file.txt'

    return filename


# ============================================================
# VALIDATORI PERCORSI
# ============================================================

def is_safe_path(path: str, base_dir: str) -> tuple[bool, str]:
    """
    Verifica che path sia dentro base_dir (no path traversal).

    Args:
        path: Percorso da validare
        base_dir: Directory base permessa

    Returns:
        (valid: bool, reason: str)
    """
    try:
        # Resolve to absolute paths
        base = Path(base_dir).resolve()
        target = Path(path).resolve()

        # Check if target è dentro base
        target.relative_to(base)

        return True, ""
    except ValueError:
        return False, "Percorso non permesso (outside base directory)"
    except Exception as e:
        return False, f"Errore validazione percorso: {str(e)}"


# ============================================================
# VALIDATORI CONFIGURAZIONE
# ============================================================

def is_safe_password(password: str) -> tuple[bool, str]:
    """
    Valida password per robustezza minima.

    Returns:
        (valid: bool, reason: str)
    """
    if not password or len(password) < 3:
        return False, "Password troppo corta (minimo 3 caratteri)"

    if len(password) > 128:
        return False, "Password troppo lunga"

    return True, ""


def is_safe_role(role: str) -> bool:
    """Valida role utente (whitelist)."""
    return role in {"admin", "viewer"}


# ============================================================
# BATCH VALIDATORS
# ============================================================

def validate_file_upload(filename: str, file_size_bytes: int) -> tuple[bool, str]:
    """
    Valida file upload completo.

    Returns:
        (valid: bool, reason: str)
    """
    valid, reason = is_safe_filename(filename)
    if not valid:
        return False, reason

    valid, reason = is_safe_file_size(file_size_bytes)
    if not valid:
        return False, reason

    return True, ""


def validate_user_input(username: str, password: str, role: str) -> tuple[bool, str]:
    if not is_safe_username(username):
        return False, f"Username non valido (max {MAX_USERNAME_LENGTH} char, alphanumeric + _-)"

    valid, reason = is_safe_password(password)
    if not valid:
        return False, reason

    if not is_safe_role(role):
        return False, "Role non valido. Usare: admin, viewer"

    return True, ""


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
