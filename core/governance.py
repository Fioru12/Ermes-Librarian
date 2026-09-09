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
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from filelock import FileLock

_logger = logging.getLogger(__name__)

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
        with tempfile.NamedTemporaryFile(
            mode="w", dir=os.path.dirname(path), delete=False, encoding="utf-8", suffix=".tmp"
        ) as tmp:
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
            data["keys"].append(
                {
                    "key_hash": key_hash,
                    "username": username,
                    "role": role,
                    "created_at": datetime.now().isoformat(),
                }
            )
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
# Valori che sembrano una chiave ma sono pubblici: il default storico del
# config e i segnaposto di .env.example. Firmare con uno di questi rende la
# firma HMAC una decorazione, perche' chiunque abbia il repository puo'
# fabbricare voci di audit che risultano valide.
_AUDIT_SECRET_PLACEHOLDERS = {
    "ermes-audit-secret-change-in-production",
    "change_me_to_audit_secret",
    "change_me",
    "changeme",
}


def _is_usable_audit_secret(value: str) -> bool:
    return bool(value.strip()) and value.strip().lower() not in _AUDIT_SECRET_PLACEHOLDERS


def _get_audit_secret() -> bytes:
    """Ritorna la secret key per HMAC audit. Usa cfg/env o persiste su security/.audit_secret.

    Un segnaposto viene trattato come "non configurato" e non come una
    chiave: e' il caso di chi copia .env.example senza modificarlo, cioe' il
    percorso piu' probabile in una prima installazione.
    """
    from config import cfg

    if cfg.AUDIT_SECRET:
        if _is_usable_audit_secret(cfg.AUDIT_SECRET):
            return cfg.AUDIT_SECRET.encode("utf-8")
        _logger.warning(
            "ERMES_AUDIT_SECRET e' un valore segnaposto pubblico: ignorato. "
            "Viene usata una chiave generata e persistita per questa installazione."
        )
    env_secret = os.environ.get("ERMES_AUDIT_SECRET", "")
    if _is_usable_audit_secret(env_secret):
        return env_secret.encode("utf-8")

    secret_file = os.path.join(cfg.SECURITY_DIR, ".audit_secret")
    if os.path.exists(secret_file):
        try:
            with open(secret_file, encoding="utf-8") as f:
                saved = f.read().strip()
                if saved:
                    return saved.encode("utf-8")
        except Exception:
            pass

    new_secret = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(secret_file), exist_ok=True)
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(new_secret)
    except Exception as ex:
        _logger.warning("Impossibile salvare .audit_secret persistente: %s", ex)
    return new_secret.encode("utf-8")


def _sign_audit_entry(entry_str: str) -> str:
    """Crea firma HMAC-SHA256 per un entry di audit."""
    return hmac.new(_get_audit_secret(), entry_str.encode("utf-8"), hashlib.sha256).hexdigest()


def _verify_audit_signature(entry: dict) -> bool:
    """Verifica la firma HMAC di un entry di audit."""
    if "signature" not in entry:
        return False
    stored_sig = entry.pop("signature")
    entry_str = json.dumps(entry, ensure_ascii=False)
    expected_sig = _sign_audit_entry(entry_str)
    return hmac.compare_digest(stored_sig, expected_sig)


# Lock per operazioni file users
_users_lock = threading.RLock()


def _load_users(users_file: str) -> dict:
    with _users_lock:
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
    with _users_lock:
        os.makedirs(os.path.dirname(users_file), exist_ok=True)
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=os.path.dirname(users_file), delete=False, encoding="utf-8", suffix=".tmp"
            ) as tmp:
                tmp_path = tmp.name
                json.dump(data, tmp, ensure_ascii=False, indent=2)
                tmp.flush()
                with contextlib.suppress(AttributeError, OSError):
                    os.fsync(tmp.fileno())

            # Atomic rename (even on Windows)
            if os.path.exists(users_file):
                os.replace(users_file, users_file + ".bak")
            os.replace(tmp_path, users_file)
            if os.path.exists(users_file + ".bak"):
                with contextlib.suppress(BaseException):
                    os.remove(users_file + ".bak")
        except Exception as e:
            if tmp_path is not None and os.path.exists(tmp_path):
                with contextlib.suppress(BaseException):
                    os.unlink(tmp_path)
            _logger.error("_save_users: errore scrittura %s: %s", users_file, e)
            raise


_hash_lock = threading.Lock()


def _hash_password(password: str, salt: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt_bytes = (salt if salt else "ermes_fallback_salt").encode("utf-8")
    h = hashlib.sha256(salt_bytes + pwd_bytes).digest()
    for _ in range(5000):
        h = hashlib.sha256(h + salt_bytes + pwd_bytes).digest()
    return h.hex()


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
            _save_users(users_file, data)
        else:
            existing_hash = user.get("password_hash", "")
            salt = user.get("salt", "")
            if not salt or not existing_hash or not hmac.compare_digest(_hash_password(password, salt), existing_hash):
                new_salt = secrets.token_hex(16)
                user["salt"] = new_salt
                user["password_hash"] = _hash_password(password, new_salt)
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
            user_entry: dict[str, Any] = {
                "username": username,
                "created_at": datetime.now().isoformat(),
            }
            user = user_entry
            data["users"].append(user)
        else:
            salt = user.get("salt") or secrets.token_hex(16)

        user["role"] = role
        user["active"] = active
        user["salt"] = salt
        if password:
            user["password_hash"] = _hash_password(password, salt)
        user["updated_at"] = datetime.now().isoformat()
        _save_users(users_file, data)


# ============================================================
# Mapping gruppi OIDC -> ruoli biblioteca (SSO -> ACL)
# ============================================================
# Persistito in data/oidc_group_mappings.json. Struttura:
#   {"mappings": [{"group": "hr-team", "library_id": "lib_x", "role": "viewer"}, ...]}
# I gruppi possono solo concedere viewer/editor, mai admin: l'elevazione a
# admin deve restare un'azione umana esplicita (principio di minor privilegio).

_OIDC_MAPPINGS_LOCK = threading.Lock()


def _oidc_mappings_path() -> str:
    from config import cfg

    data_dir = Path(getattr(cfg, "BASE_DIR", ".")) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "oidc_group_mappings.json")


def load_oidc_group_mappings() -> list[dict]:
    path = _oidc_mappings_path()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return []
    except Exception as error:
        _logger.warning("Impossibile leggere %s: %s", path, error)
        return []
    mappings = data.get("mappings")
    return mappings if isinstance(mappings, list) else []


def set_oidc_group_mapping(group: str, library_id: str, role: str) -> dict:
    """Aggiunge o aggiorna un mapping gruppo->biblioteca. Valida che la
    biblioteca esista; l'idempotenza è completa (upsert per chiave)."""
    if role not in {"viewer", "editor"}:
        raise ValueError("Il ruolo da gruppo SSO può essere solo viewer o editor")
    with _OIDC_MAPPINGS_LOCK:
        mappings = load_oidc_group_mappings()
        entry = {"group": group, "library_id": library_id, "role": role}
        mappings = [m for m in mappings if not (m.get("group") == group and m.get("library_id") == library_id)]
        mappings.append(entry)
        with open(_oidc_mappings_path(), "w", encoding="utf-8") as handle:
            json.dump({"mappings": mappings}, handle, indent=2, ensure_ascii=False)
    return entry


def remove_oidc_group_mapping(group: str, library_id: str) -> bool:
    with _OIDC_MAPPINGS_LOCK:
        mappings = load_oidc_group_mappings()
        kept = [m for m in mappings if not (m.get("group") == group and m.get("library_id") == library_id)]
        if len(kept) == len(mappings):
            return False
        with open(_oidc_mappings_path(), "w", encoding="utf-8") as handle:
            json.dump({"mappings": kept}, handle, indent=2, ensure_ascii=False)
    return True


def resolve_oidc_group_role(groups: list[str] | None, library_id: str) -> str | None:
    """Ruolo concesso dai gruppi OIDC dell'utente su una biblioteca.

    Se più gruppi mappano sulla stessa biblioteca vince il privilegio più
    alto (editor > viewer). Nessun gruppo -> None.
    """
    if not groups:
        return None
    group_set = set(groups)
    roles = [
        m.get("role")
        for m in load_oidc_group_mappings()
        if m.get("library_id") == library_id and m.get("group") in group_set
    ]
    if "editor" in roles:
        return "editor"
    if "viewer" in roles:
        return "viewer"
    return None


def oidc_group_roles_for_user(groups: list[str] | None) -> dict[str, str]:
    """Mappa {library_id: ruolo_effettivo} per tutti i gruppi dell'utente.

    Usato dal listing biblioteche per la scoperta via SSO: una biblioteca
    raggiungibile solo via gruppo appare nell'elenco senza membership diretta.
    """
    if not groups:
        return {}
    group_set = set(groups)
    effective: dict[str, str] = {}
    for mapping in load_oidc_group_mappings():
        if mapping.get("group") not in group_set:
            continue
        library_id = mapping.get("library_id")
        role = mapping.get("role")
        if not library_id or role not in {"viewer", "editor"}:
            continue
        if effective.get(library_id) != "editor":
            effective[library_id] = role
    return effective


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
