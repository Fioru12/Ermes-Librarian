import json
import os


from core.governance import (
    _load_users, _save_users, _sign_audit_entry, _verify_audit_signature,
    _hash_password, authenticate_user, validate_admin_user,
    validate_password_strength, create_or_update_user, list_users,
    ensure_default_admin, append_audit, verify_audit_log_integrity,
)


class TestUserPersistence:
    def test_load_users_empty(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        data = _load_users(path)
        assert data == {"users": []}

    def test_save_and_load_users(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        data = {"users": [{"username": "test", "role": "admin"}]}
        _save_users(path, data)
        loaded = _load_users(path)
        assert loaded == data

    def test_save_creates_parent_dir(self, temp_dir):
        path = os.path.join(temp_dir, "sub", "users.json")
        _save_users(path, {"users": []})
        assert os.path.exists(path)

    def test_corrupted_json_fallback(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        with open(path, "w") as f:
            f.write("not json")
        data = _load_users(path)
        assert data == {"users": []}


class TestCreateUpdateUser:
    def test_create_user(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        create_or_update_user(path, "alice", "admin", "Pass123!")
        users = list_users(path)
        assert len(users) == 1
        assert users[0]["username"] == "alice"
        assert users[0]["role"] == "admin"

    def test_create_multiple_users(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        create_or_update_user(path, "alice", "admin", "Pass123!")
        create_or_update_user(path, "bob", "viewer", "Pass456!")
        users = list_users(path)
        assert len(users) == 2

    def test_update_user_role(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        create_or_update_user(path, "alice", "viewer", "Pass123!")
        create_or_update_user(path, "alice", "admin", "")
        users = list_users(path)
        assert len(users) == 1
        assert users[0]["role"] == "admin"

    def test_list_users_sorted(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        create_or_update_user(path, "zara", "viewer", "Pass123!")
        create_or_update_user(path, "anna", "admin", "Pass456!")
        users = list_users(path)
        assert users[0]["username"] == "anna"
        assert users[1]["username"] == "zara"


class TestAuthenticate:
    def test_authenticate_valid(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        create_or_update_user(path, "alice", "admin", "StrongP@ss1")
        result = authenticate_user(path, "alice", "StrongP@ss1")
        assert result is not None
        assert result["username"] == "alice"
        assert result["role"] == "admin"

    def test_authenticate_wrong_password(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        create_or_update_user(path, "alice", "admin", "CorrectP@ss1")
        result = authenticate_user(path, "alice", "WrongP@ss1")
        assert result is None

    def test_authenticate_unknown_user(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        result = authenticate_user(path, "nonexistent", "any")
        assert result is None


class TestEnsureDefaultAdmin:
    def test_creates_admin(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        ensure_default_admin(path, "admin", "AdminP@ss1")
        users = list_users(path)
        assert len(users) == 1
        assert users[0]["username"] == "admin"
        assert users[0]["role"] == "admin"

    def test_skips_if_no_password(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        ensure_default_admin(path, "admin", "")
        users = list_users(path)
        assert len(users) == 0

    def test_does_not_duplicate(self, temp_dir):
        path = os.path.join(temp_dir, "users.json")
        ensure_default_admin(path, "admin", "AdminP@ss1")
        ensure_default_admin(path, "admin", "AdminP@ss1")
        users = list_users(path)
        assert len(users) == 1


class TestValidateAdminUser:
    def test_none_is_invalid(self):
        assert validate_admin_user(None) is False

    def test_valid_admin(self):
        assert validate_admin_user({"username": "admin", "role": "admin"}) is True

    def test_viewer_is_invalid(self):
        assert validate_admin_user({"username": "bob", "role": "viewer"}) is False

    def test_missing_role_is_invalid(self):
        assert validate_admin_user({"username": "admin"}) is False


class TestPasswordStrength:
    def test_valid_password(self):
        ok, msg = validate_password_strength("StrongP@ss1")
        assert ok is True
        assert msg == ""

    def test_too_short(self):
        ok, msg = validate_password_strength("Ab1@")
        assert ok is False
        assert "8 caratteri" in msg

    def test_no_uppercase(self):
        ok, msg = validate_password_strength("weakpass1@")
        assert ok is False

    def test_no_lowercase(self):
        ok, msg = validate_password_strength("WEAKPASS1@")
        assert ok is False

    def test_no_digit(self):
        ok, msg = validate_password_strength("WeakPass@")
        assert ok is False

    def test_no_special(self):
        ok, msg = validate_password_strength("WeakPass1")
        assert ok is False

    def test_empty_password(self):
        ok, msg = validate_password_strength("")
        assert ok is False
        assert "vuota" in msg


class TestAuditLog:
    def test_sign_and_verify_entry(self):
        entry = {"action": "test", "actor": "admin", "ts": "2026-01-01T00:00:00"}
        entry_str = json.dumps(entry, ensure_ascii=False)
        sig = _sign_audit_entry(entry_str)
        assert isinstance(sig, str) and len(sig) == 64

    def test_verify_corrupted(self):
        entry = {"action": "test", "actor": "admin", "ts": "2026-01-01T00:00:00"}
        entry_str = json.dumps(entry, ensure_ascii=False)
        sig = _sign_audit_entry(entry_str)
        entry["signature"] = sig
        assert _verify_audit_signature(entry.copy()) is True
        entry["action"] = "tampered"
        assert _verify_audit_signature(entry.copy()) is False

    def test_verify_missing_signature(self):
        entry = {"action": "test", "actor": "admin"}
        assert _verify_audit_signature(entry) is False

    def test_append_and_verify(self, temp_dir):
        audit_file = os.path.join(temp_dir, "audit.jsonl")
        append_audit(audit_file, "test_action", "admin", {"key": "val"})
        total, valid = verify_audit_log_integrity(audit_file)
        assert total == 1
        assert valid == 1

    def test_verify_empty_file(self, temp_dir):
        audit_file = os.path.join(temp_dir, "audit.jsonl")
        total, valid = verify_audit_log_integrity(audit_file)
        assert total == 0
        assert valid == 0

    def test_multiple_audit_entries(self, temp_dir):
        audit_file = os.path.join(temp_dir, "audit.jsonl")
        for i in range(3):
            append_audit(audit_file, f"action{i}", "admin")
        total, valid = verify_audit_log_integrity(audit_file)
        assert total == 3
        assert valid == 3


class TestHashPassword:
    def test_hashing_produces_different_hash_for_same_password(self):
        # Different salts should produce different hashes
        h1 = _hash_password("SameP@ss1", salt="aaaaaaaaaaaaaaaa")
        h2 = _hash_password("SameP@ss1", salt="bbbbbbbbbbbbbbbb")
        assert h1 != h2

    def test_hash_hex_format(self):
        h = _hash_password("TestP@ss1", salt="1234567890abcdef")
        assert isinstance(h, str)
        assert len(h) > 0
        # Should be hex chars only
        int(h, 16)
