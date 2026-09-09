"""Protezione del login dai tentativi ripetuti (core/login_guard.py).

Prima di questi test `POST /api/auth/login` accettava un numero illimitato di
password sbagliate. Non c'era un bug da correggere: il rate limiter del
progetto esiste, e' completo e ha dieci test che passano, ma non era applicato
ad alcuna rotta — e nessun test se ne accorgeva, perche' verificavano tutti la
classe in isolamento invece del percorso reale.

`test_repeated_wrong_passwords_stop_being_accepted` chiude proprio questo: usa
l'endpoint, non il componente.
"""

import time

import pytest
from fastapi.testclient import TestClient

import api.auth
import config
from api import app
from core.login_guard import LoginGuard

PASSWORD = "StrongPassword!123"


@pytest.fixture
def logged_out(tmp_path, monkeypatch):
    """Istanza pulita con login locale configurato e nessun tentativo pregresso."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir),
        DATABASE_URL="",
        ADMIN_USERNAME="capo",
        ADMIN_PASSWORD=PASSWORD,
        API_KEY="",
        LOGIN_MAX_ATTEMPTS=3,
        LOGIN_LOCKOUT_MINUTES=15,
    )
    monkeypatch.setattr(config, "cfg", test_cfg)
    monkeypatch.setattr(api.auth, "cfg", test_cfg)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()
    return test_cfg


# ============================================================
# Il buco che questi test chiudono
# ============================================================


def test_repeated_wrong_passwords_stop_being_accepted(logged_out):
    client = TestClient(app)

    for _ in range(3):
        assert client.post("/api/auth/login", json={"username": "capo", "password": "sbagliata"}).status_code == 401

    quarto = client.post("/api/auth/login", json={"username": "capo", "password": "sbagliata"})

    assert quarto.status_code == 429
    assert "tentativi" in quarto.json()["detail"].lower()


def test_the_block_holds_even_with_the_correct_password(logged_out):
    """Altrimenti basterebbe indovinare per uscire dal blocco."""
    client = TestClient(app)
    for _ in range(3):
        client.post("/api/auth/login", json={"username": "capo", "password": "sbagliata"})

    corretta = client.post("/api/auth/login", json={"username": "capo", "password": PASSWORD})

    assert corretta.status_code == 429


def test_a_successful_login_clears_the_counter(logged_out):
    client = TestClient(app)
    for _ in range(2):
        client.post("/api/auth/login", json={"username": "capo", "password": "sbagliata"})

    assert client.post("/api/auth/login", json={"username": "capo", "password": PASSWORD}).status_code == 200

    # Il conteggio riparte: due nuovi errori non devono bastare a bloccare.
    for _ in range(2):
        assert client.post("/api/auth/login", json={"username": "capo", "password": "sbagliata"}).status_code == 401


# ============================================================
# Su cosa si conta
# ============================================================


def test_the_count_is_shared_between_instances(logged_out):
    """Con lo stato in memoria, tre istanze avrebbero concesso tre volte i
    tentativi previsti."""
    prima = LoginGuard()
    seconda = LoginGuard()

    for _ in range(3):
        prima.register_failure("10.0.0.9", "capo")

    bloccato, motivo = seconda.is_blocked("10.0.0.9", "capo")

    assert bloccato
    assert motivo


def test_another_address_is_not_blocked_by_someone_elses_attempts(logged_out):
    guard = LoginGuard()
    for _ in range(5):
        guard.register_failure("10.0.0.9", "capo")

    bloccato, _ = guard.is_blocked("10.0.0.10", "capo")

    assert not bloccato


def test_a_username_cannot_be_locked_out_from_the_outside(logged_out):
    """Se il blocco fosse per solo username, chi conosce il nome di un collega
    potrebbe lasciarlo fuori sbagliando la password apposta."""
    guard = LoginGuard()
    for indirizzo in ("10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"):
        for _ in range(5):
            guard.register_failure(indirizzo, "vittima")

    bloccato, _ = guard.is_blocked("10.0.0.99", "vittima")

    assert not bloccato


def test_a_successful_login_does_not_clear_attempts_from_other_addresses(logged_out):
    guard = LoginGuard()
    for _ in range(3):
        guard.register_failure("10.0.0.9", "capo")

    guard.register_success("192.168.1.5", "capo")

    bloccato, _ = guard.is_blocked("10.0.0.9", "capo")
    assert bloccato


# ============================================================
# Finestra temporale
# ============================================================


def test_attempts_outside_the_window_no_longer_count(logged_out, monkeypatch):
    guard = LoginGuard()
    vecchio = time.time() - (16 * 60)
    monkeypatch.setattr("core.login_guard.time.time", lambda: vecchio)
    for _ in range(5):
        guard.register_failure("10.0.0.9", "capo")
    monkeypatch.undo()

    bloccato, _ = guard.is_blocked("10.0.0.9", "capo")

    assert not bloccato
