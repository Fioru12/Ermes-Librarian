"""Webhook Slack/Teams (api/chat_webhooks.py): verifica firma, routing
canale -> biblioteca, risposta evidence-first identica a /{library_id}/ask.

Le firme sono calcolate qui con lo stesso algoritmo standard delle due
piattaforme (HMAC-SHA256), non copiando la funzione che le verifica — un test
che ricalcola con la funzione stessa non proverebbe nulla.
"""
import base64
import hashlib
import hmac
import time
from dataclasses import replace

from fastapi.testclient import TestClient

from api import app
from api.auth import _SESSIONS
from config import cfg


def _client(tmp_path, monkeypatch, *, slack_secret="slack-test-secret", teams_secret=None):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    if teams_secret is None:
        teams_secret = base64.b64encode(b"teams-raw-secret-bytes").decode()
    test_cfg = replace(
        cfg, BASE_DIR=str(app_dir), ADMIN_USERNAME="owner", ADMIN_PASSWORD="StrongPassword!123", API_KEY="",
        SLACK_SIGNING_SECRET=slack_secret, TEAMS_WEBHOOK_SECRET=teams_secret, SLACK_BOT_TOKEN="",
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    monkeypatch.setattr("api.chat_webhooks.cfg", test_cfg)
    _SESSIONS.clear()
    client = TestClient(app)
    import api.libraries
    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    assert client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    library = store.create_library("Archivio", "", "private", owner_id="owner")
    return client, store, library, test_cfg


def _slack_signed_headers(secret: str, body: bytes, timestamp: str | None = None) -> dict:
    timestamp = timestamp or str(int(time.time()))
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    signature = "v0=" + hmac.new(secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    return {"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature}


def _teams_authorization(secret_b64: str, body: bytes) -> str:
    key = base64.b64decode(secret_b64)
    digest = base64.b64encode(hmac.new(key, body, hashlib.sha256).digest()).decode()
    return f"HMAC {digest}"


def test_slack_slash_command_with_valid_signature_answers_from_the_bound_library(tmp_path, monkeypatch):
    client, store, library, test_cfg = _client(tmp_path, monkeypatch)
    client.post(
        f"/api/libraries/{library['id']}/documents",
        files={"file": ("ferie.txt", b"La pausa pranzo dura 60 minuti.", "text/plain")},
    )
    client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "slack", "external_channel_id": "C1"})

    body = b"text=Quanto+dura+la+pausa+pranzo%3F&channel_id=C1"
    headers = _slack_signed_headers(test_cfg.SLACK_SIGNING_SECRET, body)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    response = client.post("/api/integrations/slack", content=body, headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["response_type"] == "in_channel"
    assert "pausa pranzo" in payload["text"].lower() or "60 minuti" in payload["text"]


def test_slack_webhook_rejects_an_invalid_signature(tmp_path, monkeypatch):
    client, store, library, test_cfg = _client(tmp_path, monkeypatch)
    body = b"text=ciao&channel_id=C1"
    headers = _slack_signed_headers("wrong-secret", body)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    response = client.post("/api/integrations/slack", content=body, headers=headers)
    assert response.status_code == 403


def test_slack_webhook_rejects_a_stale_timestamp(monkeypatch):
    """Una firma valida ma vecchia di piu' di 5 minuti deve essere rifiutata
    (protezione replay): senza questo controllo una richiesta intercettata una
    sola volta resterebbe valida per sempre."""
    from api.chat_webhooks import _verify_slack_signature
    monkeypatch.setattr("api.chat_webhooks.cfg", replace(cfg, SLACK_SIGNING_SECRET="some-secret"))

    body = b"text=ciao"
    stale_timestamp = str(int(time.time()) - 3600)
    basestring = f"v0:{stale_timestamp}:{body.decode('utf-8')}"
    signature = "v0=" + hmac.new(b"some-secret", basestring.encode(), hashlib.sha256).hexdigest()
    assert _verify_slack_signature(body, stale_timestamp, signature) is False


def test_teams_webhook_with_valid_hmac_answers_from_the_bound_library(tmp_path, monkeypatch):
    client, store, library, test_cfg = _client(tmp_path, monkeypatch)
    client.post(
        f"/api/libraries/{library['id']}/documents",
        files={"file": ("orari.txt", b"L'ufficio apre alle 9 del mattino.", "text/plain")},
    )
    client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "teams", "external_channel_id": "T1"})

    import json as jsonlib
    body = jsonlib.dumps({"text": "A che ora apre l'ufficio?", "conversation": {"id": "T1"}}).encode()
    headers = {"Authorization": _teams_authorization(test_cfg.TEAMS_WEBHOOK_SECRET, body), "Content-Type": "application/json"}
    response = client.post("/api/integrations/teams", content=body, headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "message"
    assert "9" in payload["text"] or "mattino" in payload["text"].lower()


def test_teams_webhook_rejects_basic_auth_the_legacy_scheme_is_not_accepted(tmp_path, monkeypatch):
    """Il vecchio modulo legacy verificava Basic Auth: non e' lo schema reale
    di un Outgoing Webhook Teams (che firma con HMAC), quindi non deve passare qui."""
    client, store, library, test_cfg = _client(tmp_path, monkeypatch)
    body = b'{"text": "ciao", "conversation": {"id": "T1"}}'
    basic = base64.b64encode(f":{test_cfg.TEAMS_WEBHOOK_SECRET}".encode()).decode()
    response = client.post("/api/integrations/teams", content=body, headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"})
    assert response.status_code == 403


def test_slack_webhook_refuses_every_request_when_no_secret_is_configured(tmp_path, monkeypatch):
    """Trovato debuggando il progetto, non nella revisione iniziale: con
    SLACK_SIGNING_SECRET vuoto (il default di fabbrica) la verifica veniva
    saltata invece di rifiutare la richiesta -- chiunque conoscesse un
    external_channel_id collegato poteva leggere il contenuto della
    biblioteca senza alcuna credenziale. Riprodotto con un documento
    confidenziale prima di correggere: vedi git blame per la PoC."""
    client, store, library, test_cfg = _client(tmp_path, monkeypatch, slack_secret="")
    client.post(
        f"/api/libraries/{library['id']}/documents",
        files={"file": ("segreto.txt", b"Stipendio CEO: 950000 EUR - CONFIDENZIALE", "text/plain")},
    )
    client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "slack", "external_channel_id": "PUBLIC"})

    attacker = TestClient(app)
    body = "text=Qual+e%27+lo+stipendio+del+CEO%3F&channel_id=PUBLIC"
    response = attacker.post("/api/integrations/slack", content=body, headers={"Content-Type": "application/x-www-form-urlencoded"})

    assert response.status_code == 503
    assert "CEO" not in response.text
    assert "950000" not in response.text


def test_teams_webhook_refuses_every_request_when_no_secret_is_configured(tmp_path, monkeypatch):
    client, store, library, test_cfg = _client(tmp_path, monkeypatch, teams_secret="")
    client.post(
        f"/api/libraries/{library['id']}/documents",
        files={"file": ("segreto.txt", b"Stipendio CEO: 950000 EUR - CONFIDENZIALE", "text/plain")},
    )
    client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "teams", "external_channel_id": "PUBLIC"})

    attacker = TestClient(app)
    body = b'{"text": "Qual e lo stipendio del CEO?", "conversation": {"id": "PUBLIC"}}'
    response = attacker.post("/api/integrations/teams", content=body, headers={"Content-Type": "application/json"})

    assert response.status_code == 503
    assert "CEO" not in response.text
    assert "950000" not in response.text


def test_teams_webhook_survives_a_null_conversation_field(tmp_path, monkeypatch):
    """Un payload malformato/malevolo con "conversation": null non deve
    far crashare l'handler con AttributeError (.get su None)."""
    client, store, library, test_cfg = _client(tmp_path, monkeypatch)
    body = b'{"text": "ciao", "conversation": null}'
    headers = {"Authorization": _teams_authorization(test_cfg.TEAMS_WEBHOOK_SECRET, body), "Content-Type": "application/json"}
    response = client.post("/api/integrations/teams", content=body, headers=headers)
    assert response.status_code == 200
    assert "non è collegato" in response.json()["text"]


def test_unbound_channel_gets_a_friendly_message_not_an_error(tmp_path, monkeypatch):
    client, store, library, test_cfg = _client(tmp_path, monkeypatch)
    body = b"text=ciao&channel_id=UNBOUND"
    headers = _slack_signed_headers(test_cfg.SLACK_SIGNING_SECRET, body)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    response = client.post("/api/integrations/slack", content=body, headers=headers)
    assert response.status_code == 200
    assert "non è collegato" in response.json()["text"]


def test_no_evidence_abstains_instead_of_guessing(tmp_path, monkeypatch):
    client, store, library, test_cfg = _client(tmp_path, monkeypatch)
    client.post(f"/api/libraries/{library['id']}/integrations", json={"platform": "slack", "external_channel_id": "C1"})

    body = b"text=Qual+e%27+la+capitale+della+Francia%3F&channel_id=C1"
    headers = _slack_signed_headers(test_cfg.SLACK_SIGNING_SECRET, body)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    response = client.post("/api/integrations/slack", content=body, headers=headers)

    assert response.status_code == 200
    assert "evidenza sufficiente" in response.json()["text"]
