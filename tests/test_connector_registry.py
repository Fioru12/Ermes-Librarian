"""Registro dei connettori e plugin esterni (core/connectors/registry.py).

Prima un nuovo connettore richiedeva di modificare Ermes in due punti (una
catena di `if` e una regex). Questi test coprono cio' che serve a un'azienda
per aggiungere il proprio senza toccare il repository, e i due modi in cui
quella stessa porta non deve aprirsi: codice caricato senza che nessuno
l'abbia deciso, e un connettore integrato sostituito in silenzio.
"""

import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.connectors
import api.libraries
import config
from api import app
from core.connectors import registry
from core.connectors.base import BaseConnector
from core.connectors.local_folder import LocalFolderConnector
from core.library_store import LibraryStore

PASSWORD_ADMIN = "AdminStrongPass!123"

PLUGIN_SOURCE = textwrap.dedent(
    """
    from core.connectors.base import BaseConnector, RemoteDocument
    from core.connectors.registry import register_connector


    class ErpConnector(BaseConnector):
        def test_connection(self):
            return True, "ERP raggiungibile: " + self.config.get("host", "")

        def fetch_documents(self):
            return [
                RemoteDocument(
                    id="1", name="scheda.txt", content=b"Scheda prodotto", media_type="text/plain",
                    source_url="erp://1", last_modified="2026-09-25T00:00:00+00:00",
                )
            ]


    register_connector("erp_aziendale", ErpConnector)
    """
)


@pytest.fixture(autouse=True)
def _clean_registry():
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()


@pytest.fixture
def plugin_dir(tmp_path, monkeypatch):
    (tmp_path / "plugin_erp_test.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
    (tmp_path / "plugin_vuoto_test.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for name in ("plugin_erp_test", "plugin_vuoto_test"):
        sys.modules.pop(name, None)


@pytest.fixture
def admin_client(tmp_path: Path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    def client_with(plugins: str) -> TestClient:
        test_cfg = config.cfg.replace(
            BASE_DIR=str(app_dir),
            DATABASE_URL="",
            ADMIN_USERNAME="admin_user",
            ADMIN_PASSWORD=PASSWORD_ADMIN,
            API_KEY="",
            CONNECTOR_PLUGINS=plugins,
        )
        for module in (config, api.auth, api.libraries, api.connectors):
            monkeypatch.setattr(module, "cfg", test_cfg)
        monkeypatch.setattr(api.libraries, "_store", LibraryStore(test_cfg.LIBRARY_DB_PATH))
        api.auth.session_store.clear()
        api.auth.login_guard.clear()
        client = TestClient(app)
        assert client.post("/api/auth/login", json={"username": "admin_user", "password": PASSWORD_ADMIN}).status_code == 200
        return client

    return client_with


def test_builtin_types_are_all_registered():
    assert registry.available_types() == sorted(
        ["confluence", "google_drive", "local_folder", "microsoft_graph", "s3_bucket", "web_scraper", "webdav"]
    )


def test_a_listed_plugin_is_usable_through_the_api(plugin_dir, admin_client):
    client = admin_client("plugin_erp_test")

    types = client.get("/api/connectors/types").json()["types"]
    assert {"type": "erp_aziendale", "builtin": False} in types
    assert {"type": "local_folder", "builtin": True} in types

    res = client.post("/api/connectors/test", json={"type": "erp_aziendale", "config": {"host": "erp.intranet"}})
    assert res.status_code == 200
    assert res.json() == {"ok": True, "message": "ERP raggiungibile: erp.intranet", "type": "erp_aziendale"}


def test_an_installed_but_unlisted_plugin_is_not_loaded(plugin_dir, admin_client):
    # Il modulo e' importabile (e' su sys.path), ma nessuno l'ha elencato.
    client = admin_client("")
    assert "erp_aziendale" not in [t["type"] for t in client.get("/api/connectors/types").json()["types"]]
    res = client.post("/api/connectors/test", json={"type": "erp_aziendale", "config": {}})
    assert res.status_code == 400


@pytest.mark.parametrize("plugins", ["plugin_che_non_esiste", "plugin_vuoto_test"])
def test_a_broken_plugin_fails_loudly_not_silently(plugin_dir, admin_client, plugins):
    client = admin_client(plugins)
    assert client.get("/api/connectors/types").status_code == 503
    assert client.post("/api/connectors/test", json={"type": "webdav", "config": {}}).status_code == 503


def test_a_plugin_cannot_replace_a_builtin_connector():
    class Impostore(BaseConnector):
        def test_connection(self):
            return True, ""

        def fetch_documents(self):
            return []

    with pytest.raises(ValueError, match="gia' registrato"):
        registry.register_connector("local_folder", Impostore)
    assert registry.create_connector("local_folder", {"folder_path": "."}).__class__ is LocalFolderConnector


@pytest.mark.parametrize("name", ["", "Erp", "erp-aziendale", "1erp", "e" * 65])
def test_invalid_type_names_are_rejected(name):
    class Qualunque(BaseConnector):
        def test_connection(self):
            return True, ""

        def fetch_documents(self):
            return []

    with pytest.raises(ValueError):
        registry.register_connector(name, Qualunque)


def test_only_base_connector_subclasses_can_register():
    with pytest.raises(TypeError):
        registry.register_connector("oggetto_qualunque", object)  # type: ignore[arg-type]
