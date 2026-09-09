"""Propagazione ACL OIDC: i gruppi SSO diventano ruoli sulle biblioteche.

Regole verificate:
- il mapping gruppi->biblioteca si gestisce via API admin (PUT/GET/DELETE)
  ed e' persistito in security/oidc_group_mappings.json;
- un utente OIDC che appartiene a un gruppo mappato vede la biblioteca
  nell'elenco e puo' accedervi ANCHE SENZA membership diretta;
- nessun gruppo puo' dare admin: solo viewer/editor;
- un utente OIDC senza gruppi mappati non vede nulla di nuovo.
"""

from fastapi.testclient import TestClient

from api import app
from api.auth import session_store
from config import cfg
from core.governance import (
    load_oidc_group_mappings,
    oidc_group_roles_for_user,
    remove_oidc_group_mapping,
    resolve_oidc_group_role,
    set_oidc_group_mapping,
)


def api_client_factory(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = cfg.replace(
        BASE_DIR=str(app_dir),
        ADMIN_USERNAME="owner",
        ADMIN_PASSWORD="StrongPassword!123",
        API_KEY="",
        OIDC_ENABLED=True,
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    session_store.clear()
    return TestClient(app), test_cfg


def _login_oidc(client, monkeypatch, groups):
    """Crea una sessione browser OIDC con i gruppi indicati."""
    oidc_user = {"username": "sso.utente", "role": "viewer", "provider": "oidc", "groups": groups}
    monkeypatch.setattr("api.auth._validate_oidc_jwt", lambda token: oidc_user)
    response = client.post("/api/auth/oidc/session", json={"id_token": "fake.jwt.token"})
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "oidc"


# ============================================================
# Unitari su core/governance
# ============================================================


def test_mapping_crud_and_resolution(tmp_path, monkeypatch):
    import pytest

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.setattr("config.cfg", cfg.replace(BASE_DIR=str(app_dir)))

    entry = set_oidc_group_mapping("hr", "lib-1", "viewer")
    assert entry["role"] == "viewer"
    set_oidc_group_mapping("hr", "lib-1", "editor")  # upsert
    set_oidc_group_mapping("management", "lib-1", "viewer")

    assert resolve_oidc_group_role(["hr"], "lib-1") == "editor"
    assert resolve_oidc_group_role(["management"], "lib-1") == "viewer"
    assert resolve_oidc_group_role(["hr", "management"], "lib-1") == "editor"  # il migliore
    assert resolve_oidc_group_role(["sconosciuto"], "lib-1") is None
    assert resolve_oidc_group_role(None, "lib-1") is None

    roles = oidc_group_roles_for_user(["hr", "management"])
    assert roles == {"lib-1": "editor"}

    assert remove_oidc_group_mapping("hr", "lib-1") is True
    assert remove_oidc_group_mapping("hr", "lib-1") is False
    remaining = load_oidc_group_mappings()
    assert [(m["group"], m["library_id"], m["role"]) for m in remaining] == [("management", "lib-1", "viewer")]

    with pytest.raises(ValueError):
        set_oidc_group_mapping("it", "lib-1", "admin")  # i gruppi non danno mai admin


# ============================================================
# E2E: sessione OIDC -> accesso alle biblioteche
# ============================================================


def test_oidc_group_grants_access_without_membership(tmp_path, monkeypatch):
    client, _ = api_client_factory(tmp_path, monkeypatch)
    import api.libraries

    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Riservata HR", "", "private", owner_id="owner")
    set_oidc_group_mapping("hr", library["id"], "viewer")
    assert (
        client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    )

    # Utente SSO nel gruppo hr: vede la biblioteca privata nell'elenco
    # e puo' leggerla, senza nessuna membership diretta.
    _login_oidc(client, monkeypatch, groups=["hr", "tutti"])
    listing = client.get("/api/libraries").json()
    items = listing["items"] if isinstance(listing, dict) else listing
    assert [item["id"] for item in items] == [library["id"]]
    assert items[0]["access_role"] == "viewer"
    assert client.get(f"/api/libraries/{library['id']}").status_code == 200


def test_oidc_user_without_mapped_group_sees_nothing(tmp_path, monkeypatch):
    client, _ = api_client_factory(tmp_path, monkeypatch)
    import api.libraries

    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Riservata", "", "private", owner_id="owner")
    set_oidc_group_mapping("hr", library["id"], "viewer")

    _login_oidc(client, monkeypatch, groups=["vendite"])
    listing = client.get("/api/libraries").json()
    assert (listing["items"] if isinstance(listing, dict) else listing) == []
    assert client.get(f"/api/libraries/{library['id']}").status_code == 404


def test_group_mapping_apis_require_admin(tmp_path, monkeypatch):
    client, _ = api_client_factory(tmp_path, monkeypatch)
    import api.libraries

    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("B", "", "private", owner_id="owner")
    assert (
        client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    )

    created = client.put(
        "/api/admin/oidc/group-mappings", json={"group": "hr", "library_id": library["id"], "role": "editor"}
    )
    assert created.status_code == 200, created.text

    listed = client.get("/api/admin/oidc/group-mappings").json()["mappings"]
    assert listed[0]["group"] == "hr" and listed[0]["role"] == "editor"

    deleted = client.request(
        "DELETE", "/api/admin/oidc/group-mappings", json={"group": "hr", "library_id": library["id"]}
    )
    assert deleted.status_code == 200

    # Utente OIDC non-admin: gestione mapping vietata.
    _login_oidc(client, monkeypatch, groups=["hr"])
    assert client.get("/api/admin/oidc/group-mappings").status_code == 403
