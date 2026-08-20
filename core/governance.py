"""
governance.py
Gestione utenti admin/viewer e audit log amministrativo.
"""
import contextlib
import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
from datetime import datetime

from filelock import FileLock

_logger = logging.getLogger(__name__)

# ============================================================
# RBAC — Per-user API Keys
# ============================================================
# Formato: security/api_keys.json
# {"keys": [{"key_hash": "...", "username": "...", "role": "admin|editor|viewer", "created_at": "..."}]}

def _get_api_keys_file() -> str:
    from config import cfg
    return os.path.join(cfg.SECURITY_DIR, "api_keys.json")


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


_api_keys_lock = FileLock(os.path.join(os.path.dirname(__file__), ".apikeys_lock"), timeout=10)


def _load_api_keys() -> dict:
    path = _get_api_keys_file()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("keys"), list):
                    return data
        except Exception as ex:
            _logger.warning("Errore lettura api_keys: %s", ex)
    return {"keys": []}


def _save_api_keys(data: dict) -> None:
    path = _get_api_keys_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(path), delete=False, encoding="utf-8", suffix=".tmp") as tmp:
            tmp_path = tmp.name
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
        if os.path.exists(path):
            os.replace(path, path + ".bak")
        os.replace(tmp_path, path)
        if os.path.exists(path + ".bak"):
            with contextlib.suppress(BaseException):
                os.remove(path + ".bak")
    except Exception:
        if os.path.exists(tmp_path):
            with contextlib.suppress(BaseException):
                os.unlink(tmp_path)
        raise


def generate_api_key() -> str:
    """Genera una nuova API key casuale."""
    return "ermes_" + secrets.token_urlsafe(32)


def set_user_api_key(username: str, role: str = "viewer", api_key: str | None = None) -> str:
    """Crea o aggiorna una API key per un utente. Restituisce la key (mostrala una volta sola)."""
    if role not in {"admin", "editor", "viewer"}:
        raise ValueError(f"Ruolo non valido: {role}. Usa admin, editor o viewer.")

    key = api_key or generate_api_key()
    key_hash = _hash_api_key(key)

    with _api_keys_lock:
        data = _load_api_keys()
        existing = next((k for k in data["keys"] if k.get("username") == username), None)
        if existing:
            existing["key_hash"] = key_hash
            existing["role"] = role
            existing["updated_at"] = datetime.now().isoformat()
        else:
            data["keys"].append({
                "key_hash": key_hash,
                "username": username,
                "role": role,
                "created_at": datetime.now().isoformat(),
            })
        _save_api_keys(data)

    return key


def revoke_user_api_key(username: str) -> bool:
    """Rimuove la API key di un utente. Restituisce True se trovata."""
    with _api_keys_lock:
        data = _load_api_keys()
        before = len(data["keys"])
        data["keys"] = [k for k in data["keys"] if k.get("username") != username]
        if len(data["keys"]) < before:
            _save_api_keys(data)
            return True
        return False


def list_api_keys() -> list[dict]:
    """Restituisce lista utenti con API key (senza hash)."""
    data = _load_api_keys()
    return [
        {
            "username": k.get("username", ""),
            "role": k.get("role", "viewer"),
            "created_at": k.get("created_at", ""),
            "updated_at": k.get("updated_at", ""),
        }
        for k in data["keys"]
    ]


def authenticate_by_api_key(api_key: str) -> dict | None:
    """Autentica tramite API key. Restituisce {username, role} o None."""
    if not api_key:
        return None
    key_hash = _hash_api_key(api_key)
    data = _load_api_keys()
    for k in data.get("keys", []):
        if hmac.compare_digest(k.get("key_hash", ""), key_hash):
            return {"username": k.get("username", ""), "role": k.get("role", "viewer")}
    return None


# Gerarchia ruoli
ROLE_HIERARCHY = {"viewer": 0, "editor": 1, "admin": 2}


def has_min_role(user_role: str, min_role: str) -> bool:
    """Verifica che user_role sia >= min_role nella gerarchia."""
    return ROLE_HIERARCHY.get(user_role, -1) >= ROLE_HIERARCHY.get(min_role, 99)


# ============================================================
# AUDIT SECURITY - HMAC per integrità log
# ============================================================
_audit_secret = os.environ.get("ERMES_AUDIT_SECRET", "")

def _get_audit_secret() -> bytes:
    """Ritorna la secret key per HMAC audit. Genera una se non impostata."""
    global _audit_secret
    if not _audit_secret:
        _audit_secret = secrets.token_hex(32)
        _logger.warning("ERMES_AUDIT_SECRET non impostata. Generata secret temporanea.")
    return _audit_secret.encode()

def _sign_audit_entry(entry_str: str) -> str:
    """Crea firma HMAC-SHA256 per un entry di audit."""
    return hmac.new(
        _get_audit_secret(),
        entry_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def _verify_audit_signature(entry: dict) -> bool:
    """Verifica la firma HMAC di un entry di audit."""
    if "signature" not in entry:
        return False
    stored_sig = entry.pop("signature")
    entry_str = json.dumps(entry, ensure_ascii=False)
    expected_sig = _sign_audit_entry(entry_str)
    return hmac.compare_digest(stored_sig, expected_sig)

# Lock per operazioni file users
_users_lock = FileLock(os.path.join(os.path.dirname(__file__), ".users_lock"), timeout=10)


def _load_users(users_file: str) -> dict:
    if os.path.exists(users_file):
        try:
            with open(users_file, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("users", []), list):
                    return data
        except Exception as ex:
            _logger.warning("_load_users: errore lettura %s: %s", users_file, ex)
    return {"users": []}


def _save_users(users_file: str, data: dict) -> None:
    """Salva file utenti in modo atomico usando tempfile + rename."""
    os.makedirs(os.path.dirname(users_file), exist_ok=True)

    # Scrivi su file temporaneo prima
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=os.path.dirname(users_file),
            delete=False,
            encoding='utf-8',
            suffix='.tmp'
        ) as tmp:
            tmp_path = tmp.name
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            # Forza sincronizzazione disco
            with contextlib.suppress(AttributeError, OSError):
                os.fsync(tmp.fileno())

        # Atomic rename (even on Windows)
        if os.path.exists(users_file):
            os.replace(users_file, users_file + '.bak')
        os.replace(tmp_path, users_file)
        if os.path.exists(users_file + '.bak'):
            with contextlib.suppress(BaseException):
                os.remove(users_file + '.bak')
    except Exception as e:
        if os.path.exists(tmp_path):
            with contextlib.suppress(BaseException):
                os.unlink(tmp_path)
        _logger.error("_save_users: errore scrittura %s: %s", users_file, e)
        raise


def _hash_password(password: str, salt: str) -> str:
    raw = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return raw.hex()


def ensure_default_admin(users_file: str, username: str, password: str) -> None:
    """Se ADMIN_PASSWORD è impostata, garantisce che esista l'utente admin con password aggiornata."""
    if not password:
        return

    with _users_lock:
        data = _load_users(users_file)
        user = next((u for u in data["users"] if u.get("username") == username), None)
        if user is None:
            salt = secrets.token_hex(16)
            data["users"].append(
                {
                    "username": username,
                    "role": "admin",
                    "active": True,
                    "salt": salt,
                    "password_hash": _hash_password(password, salt),
                    "created_at": datetime.now().isoformat(),
                }
            )
        else:
            salt = secrets.token_hex(16)
            user["salt"] = salt
            user["password_hash"] = _hash_password(password, salt)
            user["role"] = "admin"
            user["active"] = True
            user["updated_at"] = datetime.now().isoformat()
        _save_users(users_file, data)


def authenticate_user(users_file: str, username: str, password: str) -> dict | None:
    """Autentica utente con timing-safe comparison."""
    with _users_lock:
        data = _load_users(users_file)
        user = next((u for u in data["users"] if u.get("username") == username), None)

        # SECURITY: Timing-safe password check anche quando user non trovato
        # Usa un salt casuale per ogni tentativo per evitare timing e user enumeration
        if not user:
            _hash_password(password, secrets.token_hex(16))  # Hash dummy per timing match
            return None

        if not user.get("active", True):
            return None

        salt = user.get("salt", "")
        expected = user.get("password_hash", "")
        got = _hash_password(password, salt)

        if hmac.compare_digest(got, expected):
            return {"username": user["username"], "role": user.get("role", "viewer")}
        return None


def validate_admin_user(admin_user: dict | None) -> bool:
    """
    Valida che l'utente admin in session state sia valido e attivo.

    Args:
        admin_user: Dizionario utente da session state

    Returns:
        True se valido e attivo, False altrimenti
    """
    if admin_user is None:
        return False

    # Verifica struttura
    if not isinstance(admin_user, dict):
        return False

    username = admin_user.get("username")
    role = admin_user.get("role")

    if not username or not isinstance(username, str):
        return False

    if not role or not isinstance(role, str):
        return False

    # Verifica che sia admin
    return role == "admin"


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Valida la forza della password secondo requisiti di sicurezza.

    Requisiti:
    - Almeno 8 caratteri
    - Almeno una lettera maiuscola
    - Almeno una lettera minuscola
    - Almeno un numero
    - Almeno un carattere speciale

    Args:
        password: Password da validare

    Returns:
        (valida, messaggio_errore)
    """
    if not password:
        return False, "La password non può essere vuota"

    if len(password) < 8:
        return False, "La password deve avere almeno 8 caratteri"

    if not any(c.isupper() for c in password):
        return False, "La password deve contenere almeno una lettera maiuscola"

    if not any(c.islower() for c in password):
        return False, "La password deve contenere almeno una lettera minuscola"

    if not any(c.isdigit() for c in password):
        return False, "La password deve contenere almeno un numero"

    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "La password deve contenere almeno un carattere speciale"

    return True, ""


def create_or_update_user(
    users_file: str,
    username: str,
    role: str,
    password: str,
    active: bool = True,
) -> None:
    with _users_lock:
        data = _load_users(users_file)
        user = next((u for u in data["users"] if u.get("username") == username), None)
        if user is None:
            salt = secrets.token_hex(16)
            user = {
                "username": username,
                "created_at": datetime.now().isoformat(),
            }
            data["users"].append(user)
        else:
            salt = user.get("salt") or secrets.token_hex(16)

        user["role"] = role
        user["active"] = bool(active)
        user["salt"] = salt
        if password:
            user["password_hash"] = _hash_password(password, salt)
        user["updated_at"] = datetime.now().isoformat()
        _save_users(users_file, data)


def list_users(users_file: str) -> list[dict]:
    data = _load_users(users_file)
    out = []
    for u in data["users"]:
        out.append(
            {
                "username": u.get("username", ""),
                "role": u.get("role", "viewer"),
                "active": bool(u.get("active", True)),
            }
        )
    return sorted(out, key=lambda x: x["username"].lower())


def append_audit(audit_file: str, action: str, actor: str, detail: dict | None = None) -> None:
    """
    Aggiunge un entry di audit con firma HMAC per integrità.

    Il campo 'signature' garantisce che l'entry non sia stata manipolata.
    Per verificare: _verify_audit_signature(entry)
    """
    os.makedirs(os.path.dirname(audit_file), exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(),
        "action": action,
        "actor": actor,
        "detail": detail or {},
    }
    # Calcola firma HMAC per integrità
    entry_str = json.dumps(entry, ensure_ascii=False)
    entry["signature"] = _sign_audit_entry(entry_str)
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def verify_audit_log_integrity(audit_file: str) -> tuple[int, int]:
    """
    Verifica l'integrità di tutti gli entry nel file di audit.

    Returns:
        (total_entries, valid_entries)
    """
    if not os.path.exists(audit_file):
        return 0, 0

    total = 0
    valid = 0
    with open(audit_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                entry = json.loads(line)
                if _verify_audit_signature(entry.copy()):
                    valid += 1
            except Exception:
                pass
    return total, valid
