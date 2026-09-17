"""Il cookie di sessione e' Secure quando la richiesta e' arrivata in HTTPS.

Fino al 18 settembre 2026 il flag dipendeva dall'indirizzo di bind: Secure
solo se ERMES_HOST non era 127.0.0.1, localhost o 0.0.0.0. Ma 0.0.0.0 e'
cio' che docker-compose.yml imposta — e cio' che serve dietro qualunque
reverse proxy — quindi in ogni deploy Docker dietro TLS il cookie non era
mai Secure, e il browser lo avrebbe mandato anche su un link http:// verso lo
stesso host. La decisione va presa sulla richiesta, non sul bind.
"""

import pytest
from fastapi.testclient import TestClient

import api.auth
import config
from api import app

PASSWORD = "StrongPassword!123"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    def _configura(cookie_secure: str = "auto", host: str = "0.0.0.0"):  # nosec B104
        test_cfg = config.cfg.replace(
            BASE_DIR=str(tmp_path),
            HOST=host,
            ADMIN_USERNAME="capo",
            ADMIN_PASSWORD=PASSWORD,
            API_KEY="",
            COOKIE_SECURE=cookie_secure,
        )
        for percorso in ("config.cfg", "api.auth.cfg"):
            monkeypatch.setattr(percorso, test_cfg)
        api.auth.session_store.clear()
        api.auth.login_guard.clear()
        return test_cfg

    return _configura


def _set_cookie(base_url: str, headers: dict | None = None) -> str:
    client = TestClient(app, base_url=base_url)
    risposta = client.post("/api/auth/login", json={"username": "capo", "password": PASSWORD}, headers=headers or {})
    assert risposta.status_code == 200
    return risposta.headers["set-cookie"].lower()


def test_bound_to_all_interfaces_over_https_is_secure(istanza):
    istanza(host="0.0.0.0")  # nosec B104
    assert "secure" in _set_cookie("https://ermes.example")


def test_forwarded_proto_from_the_proxy_is_honoured(istanza):
    istanza()
    assert "secure" in _set_cookie("http://app:8502", {"X-Forwarded-Proto": "https"})


def test_plain_http_stays_usable_for_local_development(istanza):
    istanza()
    assert "secure" not in _set_cookie("http://127.0.0.1:8502")


def test_explicit_setting_overrides_the_request(istanza):
    istanza(cookie_secure="1")
    assert "secure" in _set_cookie("http://127.0.0.1:8502")
    istanza(cookie_secure="0")
    assert "secure" not in _set_cookie("https://ermes.example")
