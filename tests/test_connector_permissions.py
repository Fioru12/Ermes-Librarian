"""Permessi ereditati dalle fonti collegate (voce 1.6 del piano).

Un file che sull'origine vedono in pochi non deve diventare visibile a tutta
la biblioteca perche' e' arrivato da un connettore.
"""

import httpx
import pytest

from core.connector_ingest import import_remote_document, resolve_principals
from core.connectors.base import RemoteDocument
from core.connectors.google_drive import GoogleDriveConnector, drive_permissions_to_principals
from core.connectors.microsoft_graph import MicrosoftGraphConnector, graph_permissions_to_principals
from core.library_store import LibraryStore

ALICE = {"username": "alice", "role": "viewer"}
BOB = {"username": "bob", "role": "viewer"}


class _Storage:
    def save(self, path, content):
        self.saved = path


def _doc(content: bytes, principals, name: str = "contratto.md") -> RemoteDocument:
    return RemoteDocument(
        id=name,
        name=name,
        content=content,
        media_type="text/markdown",
        source_url="",
        last_modified="",
        allowed_principals=principals,
    )


@pytest.fixture
def biblioteca(tmp_path, monkeypatch):
    monkeypatch.setattr("core.connector_ingest._known_usernames", lambda: {"alice": "alice", "bob": "bob"})
    store = LibraryStore(tmp_path / "ermes.sqlite3")
    library = store.create_library("Amministrazione", "", "private", owner_id="owner")
    for user in ("alice", "bob"):
        store.set_library_member(library["id"], user, "viewer")
    return store, library["id"]


def _visibili(store, library_id, actor) -> set[str]:
    return {d["filename"] for d in store.list_documents(library_id, actor)}


def test_a_file_shared_with_one_person_stays_visible_only_to_them(biblioteca):
    store, library_id = biblioteca

    esito = import_remote_document(
        store, library_id, _doc(b"# Contratto\n\nRiservato", ("alice@azienda.example", "alice")), {}, _Storage()
    )

    assert esito == "imported"
    assert _visibili(store, library_id, ALICE) == {"contratto.md"}
    assert _visibili(store, library_id, BOB) == set()
    assert store.search_with_profile(library_id, "riservato", actor=BOB)[0] == []


def test_unknown_permissions_follow_the_library_rules(biblioteca):
    store, library_id = biblioteca

    import_remote_document(store, library_id, _doc(b"# Procedura\n\nPer tutti", None), {}, _Storage())

    assert _visibili(store, library_id, BOB) == {"contratto.md"}


def test_permissions_nobody_matches_close_the_file_to_the_owner(biblioteca):
    store, library_id = biblioteca

    import_remote_document(store, library_id, _doc(b"# Contratto", ()), {}, _Storage())

    assert _visibili(store, library_id, ALICE) == set()
    assert _visibili(store, library_id, {"username": "owner", "role": "viewer"}) == {"contratto.md"}


def test_a_permission_removed_at_the_source_disappears_on_the_next_sync(biblioteca):
    store, library_id = biblioteca
    indice: dict[str, str] = {}
    contenuto = b"# Contratto\n\nRiservato"
    import_remote_document(store, library_id, _doc(contenuto, ("alice", "bob")), indice, _Storage())
    assert _visibili(store, library_id, BOB) == {"contratto.md"}

    esito = import_remote_document(store, library_id, _doc(contenuto, ("alice",)), indice, _Storage())

    assert esito == "duplicate", "il file non e' cambiato: solo i permessi"
    assert _visibili(store, library_id, BOB) == set()
    assert _visibili(store, library_id, ALICE) == {"contratto.md"}


def test_source_names_are_translated_to_ermes_usernames():
    noti = {"mario.rossi": "Mario.Rossi"}

    assert resolve_principals(("AZIENDA\\mario.rossi", "luca@azienda.example", " "), noti) == [
        "Mario.Rossi",
        "luca@azienda.example",
    ]


# ============================================================
# Cosa dice l'origine
# ============================================================


def test_graph_permissions_open_to_the_organisation_add_no_restriction():
    assert graph_permissions_to_principals([{"link": {"scope": "organization"}}]) is None
    assert graph_permissions_to_principals(
        [
            {"grantedToV2": {"user": {"email": "alice@azienda.example"}}},
            {"grantedToIdentitiesV2": [{"siteUser": {"loginName": "bob@azienda.example"}}]},
        ]
    ) == ("alice@azienda.example", "bob@azienda.example")


def test_drive_permissions_for_anyone_or_the_domain_add_no_restriction():
    assert drive_permissions_to_principals([{"type": "domain", "domain": "azienda.example"}]) is None
    assert drive_permissions_to_principals([{"type": "user", "emailAddress": "alice@azienda.example"}]) == (
        "alice@azienda.example",
    )


def _client_che_risponde(monkeypatch, modulo, gestore):
    vero = httpx.Client

    def fabbrica(*args, **kwargs):
        kwargs.pop("timeout", None)
        return vero(transport=httpx.MockTransport(gestore))

    monkeypatch.setattr(f"{modulo}.httpx.Client", fabbrica)


def test_unreadable_graph_permissions_close_the_file(monkeypatch):
    connettore = MicrosoftGraphConnector({"tenant_id": "t", "client_id": "c", "client_secret": "s", "drive_id": "d"})
    monkeypatch.setattr(connettore, "_get_access_token", lambda: "token")

    def gestore(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/root/children"):
            return httpx.Response(
                200,
                json={
                    "value": [{"id": "1", "name": "a.md", "file": {}, "@microsoft.graph.downloadUrl": "https://x/dl"}]
                },
            )
        if request.url.path.endswith("/permissions"):
            return httpx.Response(403, json={})
        return httpx.Response(200, content=b"# A")

    _client_che_risponde(monkeypatch, "core.connectors.microsoft_graph", gestore)

    (documento,) = connettore.fetch_documents()

    assert documento.allowed_principals == ()


def test_drive_files_carry_who_can_see_them(monkeypatch):
    connettore = GoogleDriveConnector({"access_token": "token", "folder_id": "cartella"})

    def gestore(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/permissions"):
            return httpx.Response(
                200, json={"permissions": [{"type": "user", "emailAddress": "alice@azienda.example"}]}
            )
        if "alt=media" in str(request.url):
            return httpx.Response(200, content=b"# A")
        return httpx.Response(200, json={"files": [{"id": "1", "name": "a.md", "mimeType": "text/markdown"}]})

    _client_che_risponde(monkeypatch, "core.connectors.google_drive", gestore)

    (documento,) = connettore.fetch_documents()

    assert documento.allowed_principals == ("alice@azienda.example",)


def test_inheritance_can_be_turned_off_explicitly(monkeypatch):
    connettore = GoogleDriveConnector({"access_token": "token", "inherit_permissions": False})

    assert connettore._file_principals(None, {}, "1") is None  # type: ignore[arg-type]
