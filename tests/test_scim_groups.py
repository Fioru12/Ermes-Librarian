"""SCIM 2.0 Groups (api/scim.py, core/scim_groups.py).

Prima di questa risorsa i gruppi arrivavano solo dal token OIDC: un utente
provisionato da SCIM che entrava con password o chiave API non ne aveva, e
l'identity provider non poteva togliere l'accesso a chi cambia reparto. Qui
l'accesso si verifica sempre dal lato che conta — la biblioteca vista
dall'utente — non solo dalla risposta SCIM.
"""

import pytest
from fastapi.testclient import TestClient

import api.scim
import config
from api import app
from core.governance import create_or_update_user, set_oidc_group_mapping
from core.library_store import LibraryAccessError, LibraryStore
from core.scim_groups import effective_groups, scim_group_store

TOKEN = "scim-groups-test-token-9f2c"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir), DATABASE_URL="", SCIM_ENABLED=True, SCIM_TOKEN=TOKEN, API_KEY=""
    )
    monkeypatch.setattr(config, "cfg", test_cfg)
    monkeypatch.setattr(api.scim, "cfg", test_cfg)
    for username in ("mario", "lucia"):
        create_or_update_user(test_cfg.USERS_FILE, username, "viewer", "Password-Robusta!123")
    scim_group_store.clear()

    store = LibraryStore(tmp_path / "libs.sqlite3")
    library = store.create_library("Finanza", "", "private", owner_id="direzione")
    set_oidc_group_mapping("Finanza-Team", library["id"], "viewer")
    yield TestClient(app), store, library["id"]
    scim_group_store.clear()


def _can_open(store: LibraryStore, library_id: str, username: str) -> bool:
    actor = {"username": username, "role": "viewer"}  # login locale: nessun claim OIDC
    try:
        store.get_library(library_id, actor)
    except LibraryAccessError:
        return False
    return True


def _create(client: TestClient, members: list[str]) -> dict:
    res = client.post(
        "/scim/v2/Groups",
        headers=AUTH,
        json={"displayName": "Finanza-Team", "members": [{"value": m} for m in members]},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_group_membership_grants_library_access_to_a_non_oidc_user(env):
    client, store, library_id = env
    assert not _can_open(store, library_id, "mario")

    _create(client, ["mario"])

    assert _can_open(store, library_id, "mario")
    assert not _can_open(store, library_id, "lucia")
    assert [lib["id"] for lib in store.list_libraries({"username": "mario", "role": "viewer"})] == [library_id]


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "remove", "path": 'members[value eq "mario"]'},  # forma Entra ID
        {"op": "remove", "path": "members", "value": [{"value": "mario"}]},  # forma Okta
        {"op": "Remove", "path": "members"},  # tutti i membri
    ],
)
def test_removing_a_member_revokes_access(env, operation):
    client, store, library_id = env
    group = _create(client, ["mario"])
    assert _can_open(store, library_id, "mario")

    res = client.patch(
        f"/scim/v2/Groups/{group['id']}",
        headers=AUTH,
        json={"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"], "Operations": [operation]},
    )

    assert res.status_code == 200, res.text
    assert res.json()["members"] == []
    assert not _can_open(store, library_id, "mario")


def test_add_member_via_patch(env):
    client, store, library_id = env
    group = _create(client, [])
    res = client.patch(
        f"/scim/v2/Groups/{group['id']}",
        headers=AUTH,
        json={"Operations": [{"op": "add", "path": "members", "value": [{"value": "Lucia"}]}]},
    )
    assert res.status_code == 200
    assert [m["value"] for m in res.json()["members"]] == ["lucia"]
    assert _can_open(store, library_id, "lucia")


def test_unknown_members_are_rejected_not_reserved_for_later(env):
    client, _, _ = env
    res = client.post(
        "/scim/v2/Groups", headers=AUTH, json={"displayName": "Finanza-Team", "members": [{"value": "futuro"}]}
    )
    assert res.status_code == 400
    assert scim_group_store.find_by_display_name("Finanza-Team") is None


def test_a_failing_patch_applies_nothing(env):
    client, store, library_id = env
    group = _create(client, ["mario"])
    res = client.patch(
        f"/scim/v2/Groups/{group['id']}",
        headers=AUTH,
        json={
            "Operations": [
                {"op": "remove", "path": 'members[value eq "mario"]'},
                {"op": "add", "path": "members", "value": [{"value": "inesistente"}]},
            ]
        },
    )
    assert res.status_code == 400
    assert _can_open(store, library_id, "mario")


def test_deleting_a_user_removes_them_from_groups(env):
    client, _, _ = env
    _create(client, ["mario"])
    assert client.delete("/scim/v2/Users/mario", headers=AUTH).status_code == 204
    assert effective_groups({"username": "mario"}) == []


def test_deleting_the_group_revokes_access(env):
    client, store, library_id = env
    group = _create(client, ["mario"])
    assert client.delete(f"/scim/v2/Groups/{group['id']}", headers=AUTH).status_code == 204
    assert not _can_open(store, library_id, "mario")
    assert client.get(f"/scim/v2/Groups/{group['id']}", headers=AUTH).status_code == 404


def test_rename_filter_and_duplicate_names(env):
    client, _, _ = env
    group = _create(client, ["mario"])
    assert client.post("/scim/v2/Groups", headers=AUTH, json={"displayName": "Finanza-Team"}).status_code == 409

    found = client.get("/scim/v2/Groups", headers=AUTH, params={"filter": 'displayName eq "Finanza-Team"'}).json()
    assert found["totalResults"] == 1 and found["Resources"][0]["id"] == group["id"]

    res = client.patch(
        f"/scim/v2/Groups/{group['id']}",
        headers=AUTH,
        json={"Operations": [{"op": "replace", "value": {"displayName": "Tesoreria"}}]},
    )
    assert res.json()["displayName"] == "Tesoreria"
    assert effective_groups({"username": "mario"}) == ["Tesoreria"]


def test_groups_require_scim_auth(env):
    client, _, _ = env
    assert client.get("/scim/v2/Groups").status_code == 401
    assert client.post("/scim/v2/Groups", json={"displayName": "X"}).status_code == 401


def test_oidc_token_groups_and_scim_groups_are_merged(env):
    client, _, _ = env
    _create(client, ["mario"])
    oidc_actor = {"username": "mario", "provider": "oidc", "groups": ["Da-Token"]}
    assert effective_groups(oidc_actor) == ["Da-Token", "Finanza-Team"]
    # Un client non OIDC non puo' dichiararsi gruppi da solo.
    assert effective_groups({"username": "lucia", "groups": ["Finanza-Team"]}) == []
