"""Logging strutturato e correlazione delle richieste.

Nel percorso di prodotto non esisteva alcuna configurazione di logging: gli
avvisi scritti nel codice finivano sul gestore di ultima istanza di Python,
cioe' stderr senza formato, e tutto cio' che stava sotto WARNING non veniva
emesso affatto. In azienda quei log finiscono in un aggregatore che li
interroga per campi, e una riga di testo libero li' dentro non e'
consultabile.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

import config
from api import app
from core.logging_setup import JsonFormatter, actor_var, configure_logging, request_id_var


@pytest.fixture(autouse=True)
def restore_logging():
    """Il logging e' stato globale: va rimesso com'era per non disturbare gli altri test."""
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    yield
    root.handlers = previous_handlers
    root.setLevel(previous_level)


def _emit(formatter, **extra):
    record = logging.LogRecord("ermes.test", logging.INFO, __file__, 10, "documento caricato", (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(formatter.format(record))


# ============================================================
# Formato JSON
# ============================================================


def test_an_event_becomes_one_json_line_with_separate_fields():
    riga = _emit(JsonFormatter())

    assert riga["level"] == "INFO"
    assert riga["logger"] == "ermes.test"
    assert riga["message"] == "documento caricato"
    assert riga["ts"].startswith("20")


def test_context_passed_by_the_caller_is_emitted_as_fields():
    """Il senso del formato: poter interrogare per campo, non per sottostringa."""
    riga = _emit(JsonFormatter(), library_id="hr", duration_ms=12.5)

    assert riga["library_id"] == "hr"
    assert riga["duration_ms"] == 12.5


def test_an_unserializable_field_does_not_lose_the_event():
    """Un evento perso e' peggio di un campo approssimato, e succede proprio
    quando serve leggerlo."""

    class Strano:
        def __repr__(self):
            return "<oggetto strano>"

    riga = _emit(JsonFormatter(), oggetto=Strano())

    assert riga["message"] == "documento caricato"
    assert "strano" in riga["oggetto"]


def test_an_exception_is_carried_in_the_event():
    try:
        raise ValueError("qualcosa e' andato storto")
    except ValueError:
        import sys

        record = logging.LogRecord("ermes.test", logging.ERROR, __file__, 10, "errore", (), sys.exc_info())
    riga = json.loads(JsonFormatter().format(record))

    assert "ValueError" in riga["exception"]


# ============================================================
# Contesto della richiesta
# ============================================================


def test_the_request_id_is_attached_to_every_line_of_that_request():
    configure_logging(config.cfg.replace(LOG_FORMAT="json", LOG_LEVEL="INFO"))
    token = request_id_var.set("abc123")
    actor_token = actor_var.set("mario")
    try:
        record = logging.LogRecord("ermes.test", logging.INFO, __file__, 10, "ricerca", (), None)
        for filtro in logging.getLogger().handlers[0].filters:
            filtro.filter(record)
    finally:
        request_id_var.reset(token)
        actor_var.reset(actor_token)

    assert record.request_id == "abc123"
    assert record.actor == "mario"


def test_without_a_request_no_context_is_invented():
    configure_logging(config.cfg.replace(LOG_FORMAT="json"))
    record = logging.LogRecord("ermes.test", logging.INFO, __file__, 10, "avvio", (), None)

    for filtro in logging.getLogger().handlers[0].filters:
        filtro.filter(record)

    assert not hasattr(record, "request_id")


# ============================================================
# Percorso HTTP
# ============================================================


def test_the_response_carries_a_request_id(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(BASE_DIR=str(app_dir), ADMIN_PASSWORD="StrongPassword!123", API_KEY="")
    monkeypatch.setattr(config, "cfg", test_cfg)

    risposta = TestClient(app).get("/health")

    assert risposta.headers.get("X-Request-ID")


def test_an_id_supplied_by_the_proxy_is_kept(tmp_path, monkeypatch):
    """Cosi' la stessa richiesta e' rintracciabile dal reverse proxy fino a Ermes."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.setattr(config, "cfg", config.cfg.replace(BASE_DIR=str(app_dir)))

    risposta = TestClient(app).get("/health", headers={"X-Request-ID": "proxy-42"})

    assert risposta.headers["X-Request-ID"] == "proxy-42"


def test_a_hostile_id_from_outside_is_sanitised(tmp_path, monkeypatch):
    """L'id finisce nei log: se passasse intatto si potrebbero iniettare righe."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.setattr(config, "cfg", config.cfg.replace(BASE_DIR=str(app_dir)))

    risposta = TestClient(app).get("/health", headers={"X-Request-ID": 'x"\n{"level":"ERROR"}'})

    restituito = risposta.headers["X-Request-ID"]
    assert "\n" not in restituito
    assert '"' not in restituito


def test_a_very_long_id_is_truncated(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.setattr(config, "cfg", config.cfg.replace(BASE_DIR=str(app_dir)))

    risposta = TestClient(app).get("/health", headers={"X-Request-ID": "a" * 500})

    assert len(risposta.headers["X-Request-ID"]) <= 64


# ============================================================
# Configurazione
# ============================================================


def test_the_text_format_stays_the_default():
    """Durante lo sviluppo una riga leggibile serve piu' di un oggetto JSON."""
    configure_logging(config.cfg.replace(LOG_FORMAT="text"))

    assert type(logging.getLogger().handlers[0].formatter).__name__ == "TextFormatter"


def test_the_json_format_is_selected_by_configuration():
    configure_logging(config.cfg.replace(LOG_FORMAT="json"))

    assert type(logging.getLogger().handlers[0].formatter).__name__ == "JsonFormatter"


def test_configuring_twice_does_not_duplicate_the_output():
    """Handler accumulati significano ogni riga emessa piu' volte."""
    configure_logging(config.cfg.replace(LOG_FORMAT="json"))
    configure_logging(config.cfg.replace(LOG_FORMAT="json"))

    assert len(logging.getLogger().handlers) == 1
