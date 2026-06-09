from core.governance import (
    append_audit,
    authenticate_user,
    create_or_update_user,
    ensure_default_admin,
    list_users,
)


def test_default_admin_and_auth(tmp_path):
    users_file = tmp_path / "users.json"
    ensure_default_admin(str(users_file), "admin", "secret123")

    user = authenticate_user(str(users_file), "admin", "secret123")
    assert user is not None
    assert user["role"] == "admin"


def test_create_update_user(tmp_path):
    users_file = tmp_path / "users.json"
    create_or_update_user(str(users_file), "viewer1", "viewer", "pwd", active=True)
    users = list_users(str(users_file))
    assert any(u["username"] == "viewer1" and u["role"] == "viewer" for u in users)

    create_or_update_user(str(users_file), "viewer1", "admin", "newpwd", active=False)
    users2 = list_users(str(users_file))
    assert any(u["username"] == "viewer1" and u["role"] == "admin" and not u["active"] for u in users2)


def test_append_audit(tmp_path):
    audit_file = tmp_path / "audit.jsonl"
    append_audit(str(audit_file), "action_test", "admin", {"k": "v"})
    content = audit_file.read_text(encoding="utf-8")
    assert "action_test" in content
    assert "admin" in content
