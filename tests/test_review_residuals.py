"""Sei residui di una revisione esterna, chiusi il 18 settembre 2026.

Ognuno era vero e piccolo; insieme sono il tipo di scarto fra "scritto" e
"funzionante" che questo repository dichiara di non tollerare.
"""

import threading

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.libraries
import config
from api import app
from config.validation import check_configuration
from core import evidence_assistant
from core.database_backend import PostgresBackend

PASSWORD = "StrongPassword!123"


# ------------------------------------------------------------------ 5. webhook


def _cfg(**overrides):
    base = {"API_KEY": "", "ADMIN_PASSWORD": PASSWORD, "OIDC_ENABLED": False, "HOST": "127.0.0.1"}
    base.update(overrides)
    return config.cfg.replace(**base)


@pytest.mark.parametrize(
    "campo",
    [
        "TEAMS_WEBHOOK_SECRET",
        "SLACK_SIGNING_SECRET",
        "SLACK_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_WEBHOOK_SECRET",
    ],
)
def test_a_placeholder_webhook_secret_is_fatal_not_a_valid_key(campo):
    """`.env.example` suggerisce CHANGE_ME: copiato tale e quale, firmava
    richieste che chiunque conosca il progetto puo' riprodurre."""
    problemi = check_configuration(_cfg(**{campo: "CHANGE_ME"}))
    colpito = [p for p in problemi if p.setting == f"ERMES_{campo}"]
    assert colpito and colpito[0].severity == "fatal"
    assert not [p for p in check_configuration(_cfg(**{campo: "a" * 40})) if p.setting == f"ERMES_{campo}"]


# ------------------------------------------------------------------ 3. openrouter


def test_openrouter_never_receives_an_ollama_model_name(monkeypatch):
    monkeypatch.setattr(
        evidence_assistant, "cfg", config.cfg.replace(DEFAULT_MODEL_ID="qwen3.5:9b", OPENROUTER_MODEL="")
    )
    modello = evidence_assistant.openrouter_model_id()
    assert "/" in modello and ":9b" not in modello

    monkeypatch.setattr(evidence_assistant, "cfg", config.cfg.replace(OPENROUTER_MODEL="mistralai/mistral-small"))
    assert evidence_assistant.openrouter_model_id() == "mistralai/mistral-small"


# ------------------------------------------------------------------ 2. restore version


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir), DATABASE_URL="", ADMIN_USERNAME="capo", ADMIN_PASSWORD=PASSWORD, API_KEY=""
    )
    for percorso in ("config.cfg", "api.auth.cfg", "api.libraries.cfg"):
        monkeypatch.setattr(percorso, test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()
    return test_cfg


def test_restoring_a_version_records_a_relative_storage_path(istanza):
    """Ogni altro documento salva `library_id/file`; il restore salvava il
    percorso assoluto della macchina, e un backup ripristinato altrove
    perdeva l'originale."""
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": "capo", "password": PASSWORD}).status_code == 200
    lib = client.post("/api/libraries", json={"name": "Versioni", "visibility": "private"}).json()["id"]
    up = client.post(
        f"/api/libraries/{lib}/documents",
        files={"file": ("policy.md", b"# Policy\nVersione uno della policy ferie.", "text/markdown")},
    )
    assert up.status_code == 201, up.text
    doc = up.json()["id"]
    up2 = client.post(
        f"/api/libraries/{lib}/documents",
        files={"file": ("policy.md", b"# Policy\nVersione due della policy ferie.", "text/markdown")},
    )
    assert up2.status_code == 201, up2.text
    doc2 = up2.json()["id"]
    del doc

    versioni = client.get(f"/api/libraries/{lib}/documents/{doc2}/versions").json()["items"]
    assert versioni, "nessuna versione elencata"
    piu_vecchia = min(v["version"] for v in versioni)
    ripristino = client.post(f"/api/libraries/{lib}/documents/{doc2}/versions/{piu_vecchia}/restore")
    assert ripristino.status_code in (200, 201), ripristino.text

    store = api.libraries.get_library_store()
    nuovo = store.get_document(lib, ripristino.json()["id"])
    assert nuovo["storage_path"].startswith(f"{lib}/"), nuovo["storage_path"]
    assert not nuovo["storage_path"].startswith(("/", "C:", "\\"))


# ------------------------------------------------------------------ 4. postgres lock


class _FakeCursor:
    def __init__(self, backend_log, gate):
        self._log, self._gate = backend_log, gate
        self.description = None
        self.rowcount = 0

    def execute(self, sql, params=None):
        self._gate.enter()
        self._log.append(sql)
        self._gate.leave()

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Gate:
    """Conta quanti cursori sono attivi nello stesso istante."""

    def __init__(self):
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def enter(self):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        threading.Event().wait(0.01)

    def leave(self):
        with self._lock:
            self.active -= 1


class _FakeConnection:
    def __init__(self, gate):
        self.log: list[str] = []
        self._gate = gate

    def cursor(self):
        return _FakeCursor(self.log, self._gate)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_postgres_backend_serialises_concurrent_access(monkeypatch):
    """Una connessione psycopg non e' thread-safe. Prima del lock, due rotte
    sincrone servite dal pool di uvicorn potevano aprire due cursori insieme."""
    gate = _Gate()
    backend = PostgresBackend.__new__(PostgresBackend)
    backend._connection = _FakeConnection(gate)
    backend._serial = threading.RLock()

    fili = [threading.Thread(target=backend.execute, args=("SELECT 1",)) for _ in range(8)]
    for f in fili:
        f.start()
    for f in fili:
        f.join()

    assert len(backend._connection.log) == 8
    assert gate.max_active == 1
