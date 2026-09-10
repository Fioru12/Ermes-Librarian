"""Il webhook Telegram autentica come i due fratelli Slack e Teams.

`api/chat_webhooks.py` ha tre adattatori sopra la stessa risposta
evidence-first. I primi due rifiutano una richiesta non firmata e falliscono
chiusi se il segreto non e' configurato — il commento su `slack_webhook` dice
esplicitamente che il fallimento aperto era stato trovato "mentre si provava a
rompere la propria stessa integrazione". Il terzo, aggiunto dopo, fa il
contrario:

    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret_token and secret_token != cfg.TELEGRAM_BOT_TOKEN:
        raise HTTPException(403, ...)

`if secret_token and ...`: se l'header **manca**, il controllo non avviene.
Chiunque raggiunga la porta puo' interrogare la biblioteca collegata senza
alcuna credenziale — ne' sessione, ne' API key, ne' firma. L'unico test
esistente inviava sempre l'header, quindi il ramo aperto non era coperto.

Due difetti minori nello stesso confronto: il valore atteso era il **token del
bot**, cioe' la credenziale che permette di inviare messaggi come il bot,
invece del segreto dedicato del webhook che Telegram prevede
(`setWebhook(secret_token=...)`); e il confronto usava `!=` invece di
`hmac.compare_digest`, che i due fratelli usano entrambi.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.chat_webhooks
import api.libraries
import config
from api import app
from api.auth import session_store
from core.rate_limiter import get_rate_limiter

PASSWORD = "StrongPassword!123"
TOKEN_BOT = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
SEGRETO_WEBHOOK = "segreto-webhook-telegram-dedicato"
CHAT_ID = "987654321"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    campi = {
        "BASE_DIR": str(app_dir),
        "DATABASE_URL": "",
        "ADMIN_USERNAME": "capo",
        "ADMIN_PASSWORD": PASSWORD,
        "API_KEY": "",
        "TELEGRAM_BOT_TOKEN": TOKEN_BOT,
    }
    # Il segreto dedicato non esiste nella versione precedente della
    # configurazione: cosi' il file resta eseguibile contro quel codice e il
    # confronto prima/dopo produce fallimenti leggibili invece di errori.
    if hasattr(config.cfg, "TELEGRAM_WEBHOOK_SECRET"):
        campi["TELEGRAM_WEBHOOK_SECRET"] = SEGRETO_WEBHOOK
    test_cfg = config.cfg.replace(**campi)
    for percorso in ("config.cfg", "api.auth.cfg", "api.libraries.cfg", "api.chat_webhooks.cfg"):
        monkeypatch.setattr(percorso, test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
    session_store.clear()
    get_rate_limiter().reset()
    return test_cfg


@pytest.fixture
def canale(istanza):
    """Una biblioteca con un documento, collegata alla chat Telegram."""
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": "capo", "password": PASSWORD}).status_code == 200
    library_id = client.post("/api/libraries", json={"name": "Archivio", "visibility": "private"}).json()["id"]
    client.post(
        f"/api/libraries/{library_id}/documents",
        files={"file": ("pausa.txt", b"La pausa pranzo dura 60 minuti.", "text/plain")},
    )
    assert (
        client.post(
            f"/api/libraries/{library_id}/integrations",
            json={"platform": "telegram", "external_channel_id": CHAT_ID},
        ).status_code
        == 201
    )
    return client, library_id


def _aggiornamento(testo: str = "Quanto dura la pausa pranzo?") -> dict:
    return {"update_id": 1, "message": {"chat": {"id": int(CHAT_ID)}, "text": testo}}


def _invia(headers: dict | None = None, testo: str = "Quanto dura la pausa pranzo?"):
    return TestClient(app).post("/api/integrations/telegram", json=_aggiornamento(testo), headers=headers or {})


def _segreto_atteso(cfg_test) -> str:
    return getattr(cfg_test, "TELEGRAM_WEBHOOK_SECRET", None) or TOKEN_BOT


# ============================================================
# Il buco: l'autenticazione era facoltativa
# ============================================================


def test_a_request_without_the_secret_header_is_refused(istanza, canale):
    """Il caso non coperto: senza header, `if secret_token and ...` salta il
    controllo e la richiesta passa."""
    esito = _invia(headers={})

    assert esito.status_code == 403, f"richiesta senza credenziali accettata: {esito.status_code}"


def test_a_request_without_the_secret_header_leaks_no_library_content(istanza, canale):
    """La conseguenza, non solo il codice di stato: senza il controllo, il
    contenuto della biblioteca collegata torna a un chiamante anonimo."""
    esito = _invia(headers={})

    assert "60 minuti" not in esito.text, "contenuto della biblioteca esposto senza credenziali"


def test_a_wrong_secret_is_still_refused(istanza, canale):
    esito = _invia(headers={"X-Telegram-Bot-Api-Secret-Token": "sbagliato"})

    assert esito.status_code == 403


def test_the_route_fails_closed_when_no_webhook_secret_is_configured(istanza, canale, monkeypatch):
    """Stesso principio di Slack e Teams: senza segreto configurato nessuna
    richiesta e' verificabile, quindi la rotta rifiuta invece di lasciar
    passare tutto. Il default di fabbrica e' vuoto."""
    vuoto = {"TELEGRAM_WEBHOOK_SECRET": ""} if hasattr(istanza, "TELEGRAM_WEBHOOK_SECRET") else {}
    if not vuoto:
        pytest.skip("nessun segreto dedicato in questa versione della configurazione")
    monkeypatch.setattr(api.chat_webhooks, "cfg", istanza.replace(**vuoto))

    esito = _invia(headers={"X-Telegram-Bot-Api-Secret-Token": SEGRETO_WEBHOOK})

    assert esito.status_code == 503
    assert "TELEGRAM_WEBHOOK_SECRET" in esito.text


def test_the_bot_token_is_not_accepted_as_the_webhook_secret(istanza, canale):
    """Il token del bot puo' inviare messaggi come il bot e leggere tutti gli
    aggiornamenti: non e' il valore da far viaggiare in un header a ogni
    richiesta entrante. Telegram prevede un segreto dedicato."""
    if not hasattr(istanza, "TELEGRAM_WEBHOOK_SECRET"):
        pytest.skip("nessun segreto dedicato in questa versione della configurazione")

    esito = _invia(headers={"X-Telegram-Bot-Api-Secret-Token": TOKEN_BOT})

    assert esito.status_code == 403


# ============================================================
# Le guardie condivise dai tre adattatori
# ============================================================


def test_a_question_longer_than_the_normal_route_allows_is_refused(istanza, canale):
    """`_answer_question` viene chiamata direttamente, quindi salta il limite
    di 2000 caratteri di `AskLibraryRequest`: da qui una domanda di qualunque
    lunghezza finiva intera nel prompt del modello."""
    esito = _invia(headers={"X-Telegram-Bot-Api-Secret-Token": _segreto_atteso(istanza)}, testo="pausa " * 20000)

    assert esito.status_code == 200, esito.text
    assert "troppo lunga" in esito.json()["text"].lower(), esito.text


def test_the_expensive_path_is_rate_limited_per_channel(istanza, canale, monkeypatch):
    """I tre webhook chiamano l'operazione piu' costosa del sistema senza
    sessione utente, quindi il limitatore per utente non li copre: qui si conta
    per canale collegato."""
    limiter = get_rate_limiter()
    monkeypatch.setattr(limiter.config, "max_requests_per_minute", 3)
    limiter.reset()
    headers = {"X-Telegram-Bot-Api-Secret-Token": _segreto_atteso(istanza)}

    esiti = [_invia(headers=headers).status_code for _ in range(6)]

    assert 429 in esiti, f"nessun limite sul webhook: {esiti}"


def test_the_reply_stays_within_the_telegram_message_limit(istanza, canale):
    """Telegram rifiuta i messaggi oltre 4096 caratteri: una risposta lunga con
    l'elenco delle fonti non veniva consegnata affatto."""
    client, library_id = canale
    client.post(
        f"/api/libraries/{library_id}/documents",
        files={"file": ("lungo.txt", ("La pausa pranzo dura 60 minuti. " * 500).encode(), "text/plain")},
    )

    esito = _invia(headers={"X-Telegram-Bot-Api-Secret-Token": _segreto_atteso(istanza)})

    assert esito.status_code == 200
    assert len(esito.json()["text"]) <= 4096, len(esito.json()["text"])


# ============================================================
# La funzionalita' legittima deve continuare a funzionare
# ============================================================


def test_a_signed_request_still_answers_from_the_bound_library(istanza, canale):
    esito = _invia(headers={"X-Telegram-Bot-Api-Secret-Token": _segreto_atteso(istanza)})

    assert esito.status_code == 200, esito.text
    corpo = esito.json()
    assert corpo["method"] == "sendMessage"
    assert corpo["chat_id"] == CHAT_ID
    assert "60 minuti" in corpo["text"]


def test_an_unbound_chat_gets_a_courteous_message_not_an_error(istanza):
    esito = TestClient(app).post(
        "/api/integrations/telegram",
        json={"update_id": 1, "message": {"chat": {"id": 111}, "text": "Ciao"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": _segreto_atteso(istanza)},
    )

    assert esito.status_code == 200
    assert "collegato" in esito.json()["text"].lower()


def test_the_secret_comparison_is_constant_time(istanza):
    """I due fratelli usano `hmac.compare_digest`; questo usava `!=`. Un
    confronto byte per byte perde informazione sul segreto attraverso il tempo
    di risposta, ed e' l'unica cosa che protegge questa rotta."""
    sorgente = Path(api.chat_webhooks.__file__).read_text(encoding="utf-8")
    blocco = sorgente[sorgente.index("async def telegram_webhook") :]

    assert "compare_digest" in blocco, "il confronto del segreto Telegram non e' a tempo costante"
