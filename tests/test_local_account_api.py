import asyncio
from dataclasses import replace

import pytest
from fastapi import HTTPException

from api.users import create_local_account, CreateLocalAccountRequest, update_local_account, UpdateLocalAccountRequest
from config import cfg


def test_creating_local_account_validates_password_and_does_not_return_it(tmp_path, monkeypatch):
    test_cfg = replace(cfg, BASE_DIR=str(tmp_path), ADMIN_PASSWORD="StrongAdmin!123")
    monkeypatch.setattr("api.users.cfg", test_cfg)

    response = asyncio.run(
        create_local_account(
            CreateLocalAccountRequest(username="maria", role="editor", password="StrongUser!123"),
            {"username": "admin", "role": "admin"},
        )
    )

    assert response == {"success": True, "username": "maria", "role": "editor", "message": "Account locale creato"}
    assert "StrongUser!123" not in (tmp_path / "logs" / "audit_admin.jsonl").read_text(encoding="utf-8")


def test_creating_local_account_rejects_weak_or_duplicate_credentials(tmp_path, monkeypatch):
    test_cfg = replace(cfg, BASE_DIR=str(tmp_path), ADMIN_PASSWORD="StrongAdmin!123")
    monkeypatch.setattr("api.users.cfg", test_cfg)
    actor = {"username": "admin", "role": "admin"}

    with pytest.raises(HTTPException, match="maiuscola"):
        asyncio.run(create_local_account(CreateLocalAccountRequest(username="maria", role="viewer", password="weakpass1!"), actor))

    asyncio.run(create_local_account(CreateLocalAccountRequest(username="maria", role="viewer", password="StrongUser!123"), actor))
    with pytest.raises(HTTPException, match="Esiste gia"):
        asyncio.run(create_local_account(CreateLocalAccountRequest(username="maria", role="viewer", password="AnotherStrong!123"), actor))


def test_updating_local_account_never_audits_password_and_keeps_an_active_admin(tmp_path, monkeypatch):
    test_cfg = replace(cfg, BASE_DIR=str(tmp_path), ADMIN_PASSWORD="StrongAdmin!123")
    monkeypatch.setattr("api.users.cfg", test_cfg)
    actor = {"username": "admin", "role": "admin"}
    asyncio.run(create_local_account(CreateLocalAccountRequest(username="maria", role="viewer", password="StrongUser!123"), actor))
    asyncio.run(create_local_account(CreateLocalAccountRequest(username="anna", role="admin", password="StrongAdmin!456"), actor))

    response = asyncio.run(
        update_local_account(
            "maria",
            UpdateLocalAccountRequest(role="editor", password="ChangedUser!456", active=False),
            actor,
        )
    )
    assert response == {"success": True, "username": "maria", "role": "editor", "active": False, "message": "Account locale aggiornato"}
    audit_text = (tmp_path / "logs" / "audit_admin.jsonl").read_text(encoding="utf-8")
    assert "ChangedUser!456" not in audit_text
    assert '"password_changed": true' in audit_text

    with pytest.raises(HTTPException, match="almeno un amministratore"):
        asyncio.run(update_local_account("anna", UpdateLocalAccountRequest(role="viewer"), actor))
    with pytest.raises(HTTPException, match="tuo stesso"):
        asyncio.run(update_local_account("anna", UpdateLocalAccountRequest(active=False), {"username": "anna", "role": "admin"}))
