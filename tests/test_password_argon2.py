"""Password locali: Argon2id, con migrazione trasparente dagli hash precedenti.

Fino al 18 settembre 2026 gli hash erano SHA-256 salato iterato 5000 volte,
mentre la documentazione dichiarava PBKDF2/Argon2. Ora la documentazione e'
vera. Gli utenti gia' salvati non vengono bloccati ne' costretti a cambiare
password: al primo accesso riuscito l'hash viene riscritto.
"""

import json

from core import governance
from core.governance import (
    _hash_password,
    _verify_password,
    authenticate_user,
    create_or_update_user,
    ensure_default_admin,
)


def _users_file(tmp_path, users):
    path = tmp_path / "security" / "users.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"users": users}), encoding="utf-8")
    return str(path)


def _stored(path, username):
    data = json.loads(open(path, encoding="utf-8").read())
    return next(u for u in data["users"] if u["username"] == username)


def test_new_users_get_argon2id(tmp_path):
    path = _users_file(tmp_path, [])
    create_or_update_user(path, "anna", "viewer", "Segreta!123")
    utente = _stored(path, "anna")
    assert utente["password_hash"].startswith("$argon2id$")
    assert utente["salt"] == ""
    assert authenticate_user(path, "anna", "Segreta!123") == {"username": "anna", "role": "viewer"}
    assert authenticate_user(path, "anna", "sbagliata") is None


def test_legacy_hash_still_logs_in_and_is_rewritten_once(tmp_path):
    salt = "0123456789abcdef"
    path = _users_file(
        tmp_path,
        [
            {
                "username": "vecchio",
                "role": "editor",
                "active": True,
                "salt": salt,
                "password_hash": _hash_password("Vecchia!123", salt),
            }
        ],
    )
    assert authenticate_user(path, "vecchio", "sbagliata") is None
    assert _stored(path, "vecchio")["salt"] == salt  # un tentativo fallito non riscrive nulla

    assert authenticate_user(path, "vecchio", "Vecchia!123") == {"username": "vecchio", "role": "editor"}
    dopo = _stored(path, "vecchio")
    assert dopo["password_hash"].startswith("$argon2id$")
    assert dopo["salt"] == ""

    assert authenticate_user(path, "vecchio", "Vecchia!123") is not None
    assert _stored(path, "vecchio")["password_hash"] == dopo["password_hash"]  # non riscritto ogni volta


def test_default_admin_is_upgraded_without_changing_the_password(tmp_path):
    salt = "fedcba9876543210"
    path = _users_file(
        tmp_path,
        [
            {
                "username": "admin",
                "role": "admin",
                "active": True,
                "salt": salt,
                "password_hash": _hash_password("Admin!123", salt),
            }
        ],
    )
    ensure_default_admin(path, "admin", "Admin!123")
    assert _stored(path, "admin")["password_hash"].startswith("$argon2id$")
    assert authenticate_user(path, "admin", "Admin!123") is not None

    ensure_default_admin(path, "admin", "Ruotata!456")
    assert authenticate_user(path, "admin", "Admin!123") is None
    assert authenticate_user(path, "admin", "Ruotata!456") is not None


def test_verify_password_rejects_garbage_hashes_without_raising():
    assert _verify_password("x", "$argon2id$non-e-un-hash", "") == (False, False)
    assert _verify_password("x", "", "") == (False, False)
    assert _verify_password("x", "deadbeef", "") == (False, False)


def test_unknown_user_costs_about_as_much_as_a_known_one(tmp_path, monkeypatch):
    """Il tempo di risposta non deve dire se il nome utente esiste."""
    chiamate = []

    class _Spia:
        def verify(self, stored, password):
            chiamate.append(stored)
            return True

    monkeypatch.setattr(governance, "_argon2", _Spia())
    path = _users_file(tmp_path, [])
    assert authenticate_user(path, "nessuno", "qualcosa") is None
    assert chiamate == [governance._DUMMY_ARGON2_HASH]
