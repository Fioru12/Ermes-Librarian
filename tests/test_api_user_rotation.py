import asyncio

from api.users import rotate_api_key
import core.governance as governance


def test_rotating_api_key_preserves_existing_role(monkeypatch):
    recorded: dict[str, str] = {}
    monkeypatch.setattr(governance, "list_api_keys", lambda: [{"username": "maria", "role": "editor"}])
    monkeypatch.setattr(governance, "revoke_user_api_key", lambda username: username == "maria")
    monkeypatch.setattr(
        governance,
        "set_user_api_key",
        lambda username, role: recorded.update({"username": username, "role": role}) or "rotated-key",
    )
    monkeypatch.setattr(governance, "append_audit", lambda *_args, **_kwargs: None)

    response = asyncio.run(rotate_api_key("maria", {"username": "admin", "role": "admin"}))

    assert recorded == {"username": "maria", "role": "editor"}
    assert response["role"] == "editor"
