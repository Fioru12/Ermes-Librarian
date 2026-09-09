"""Sessioni condivise fra istanze (core/session_store.py).

Il difetto che questi test chiudono non era un errore di logica ma una scelta
di collocazione: le sessioni stavano in un dizionario di modulo, quindi
esistevano solo dentro il processo che le aveva create. Con una sola istanza
non si vedeva nulla; con due dietro un bilanciatore l'utente veniva
disconnesso a richieste alterne.

`test_a_second_instance_sees_a_session_created_by_the_first` e' la prova
diretta: due SessionStore distinti — come due processi distinti — che puntano
allo stesso archivio. Con l'implementazione precedente non condividevano
niente.
"""

import time

import pytest

import config
from core.session_store import SessionStore, _fingerprint


@pytest.fixture
def shared_db(tmp_path, monkeypatch):
    """Un archivio condiviso, come lo sarebbe fra istanze della stessa app."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(BASE_DIR=str(app_dir), DATABASE_URL="")
    monkeypatch.setattr(config, "cfg", test_cfg)
    return test_cfg


def _in_an_hour() -> float:
    return time.time() + 3600


# ============================================================
# Il punto: due processi, lo stesso archivio
# ============================================================


def test_a_second_instance_sees_a_session_created_by_the_first(shared_db):
    prima = SessionStore()
    seconda = SessionStore()

    prima.create("token-di-mario", {"username": "mario", "role": "editor"}, _in_an_hour())

    assert seconda.get("token-di-mario") == {"username": "mario", "role": "editor"}


def test_logout_on_one_instance_ends_the_session_on_the_other(shared_db):
    prima = SessionStore()
    seconda = SessionStore()
    prima.create("token-condiviso", {"username": "mario", "role": "viewer"}, _in_an_hour())

    prima.delete("token-condiviso")

    assert seconda.get("token-condiviso") is None


def test_disabling_a_user_closes_the_sessions_held_by_every_instance(shared_db):
    """Il caso peggiore del vecchio comportamento: si revoca un accesso e
    l'utente resta dentro sulle altre istanze fino alla scadenza."""
    prima = SessionStore()
    seconda = SessionStore()
    prima.create("sessione-desktop", {"username": "licenziato", "role": "admin"}, _in_an_hour())
    seconda.create("sessione-telefono", {"username": "licenziato", "role": "admin"}, _in_an_hour())
    prima.create("sessione-altra-persona", {"username": "collega", "role": "viewer"}, _in_an_hour())

    chiuse = seconda.delete_for_user("licenziato")

    assert chiuse == 2
    assert prima.get("sessione-desktop") is None
    assert prima.get("sessione-telefono") is None
    assert prima.get("sessione-altra-persona") is not None


# ============================================================
# Il token non viene mai scritto in chiaro
# ============================================================


def test_the_raw_token_is_never_stored(shared_db):
    """Su un archivio durevole il token in chiaro sarebbe una credenziale
    pronta all'uso per chiunque legga il database."""
    store = SessionStore()
    store.create("token-segreto", {"username": "mario", "role": "viewer"}, _in_an_hour())

    righe = store._connection().execute("SELECT token_hash FROM browser_sessions", ())

    memorizzati = [riga["token_hash"] for riga in righe]
    assert "token-segreto" not in memorizzati
    assert _fingerprint("token-segreto") in memorizzati


def test_a_token_that_was_never_issued_is_rejected(shared_db):
    store = SessionStore()

    assert store.get("token-mai-emesso") is None
    assert store.get(None) is None
    assert store.get("") is None


# ============================================================
# Scadenza
# ============================================================


def test_an_expired_session_is_refused_and_removed(shared_db):
    store = SessionStore()
    store.create("token-scaduto", {"username": "mario", "role": "viewer"}, time.time() - 1)

    assert store.get("token-scaduto") is None
    assert store.count() == 0


def test_purge_removes_only_the_expired_ones(shared_db):
    store = SessionStore()
    store.create("vecchia", {"username": "mario", "role": "viewer"}, time.time() - 10)
    store.create("valida", {"username": "mario", "role": "viewer"}, _in_an_hour())

    rimosse = store.purge_expired()

    assert rimosse == 1
    assert store.get("valida") is not None


# ============================================================
# Percorso HTTP completo
# ============================================================


def test_a_login_survives_a_restart_of_the_process(shared_db, monkeypatch):
    """Un rilascio non deve disconnettere tutti.

    Il riavvio e' simulato sostituendo lo store con uno nuovo, che e'
    esattamente cio' che accadeva a ogni avvio: prima il dizionario ripartiva
    vuoto, ora l'archivio e' ancora li'.
    """
    from fastapi.testclient import TestClient

    import api.auth
    from api import app

    test_cfg = shared_db.replace(ADMIN_USERNAME="capo", ADMIN_PASSWORD="StrongPassword!123", API_KEY="")
    monkeypatch.setattr(config, "cfg", test_cfg)
    monkeypatch.setattr(api.auth, "cfg", test_cfg)
    api.auth.session_store.clear()

    client = TestClient(app)
    assert (
        client.post("/api/auth/login", json={"username": "capo", "password": "StrongPassword!123"}).status_code == 200
    )
    assert client.get("/api/auth/me").status_code == 200

    # "Riavvio": nuovo store, stesso archivio, stesso cookie del browser.
    monkeypatch.setattr(api.auth, "session_store", SessionStore())

    assert client.get("/api/auth/me").status_code == 200
