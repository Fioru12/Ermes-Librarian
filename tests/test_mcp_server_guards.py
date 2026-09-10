"""Il server MCP applica le guardie delle rotte equivalenti.

`api/mcp_server.py` espone le stesse due operazioni costose delle rotte HTTP
normali — domanda con citazioni e ricerca — a un agente automatico
(Claude Desktop, Cursor, LangChain). Le rotte normali hanno tre guardie che
qui mancavano tutte:

  GET  /api/libraries/{id}/search   rate_limited, q di almeno 2 caratteri
  POST /api/libraries/{id}/ask      rate_limited, question 2..2000, top_k 1..10
  POST /api/mcp/call                nessuna
  POST /api/mcp/rpc                 nessuna

E' il caso peggiore in cui dimenticarle: il chiamante previsto di questa rotta
non e' una persona che clicca, ma un agente in ciclo, cioe' esattamente il
traffico per cui il limitatore esiste.

Il controllo di accesso invece c'era, ma scritto contro un contratto sbagliato:
`if not lib` dopo `store.get_library(...)`, che non ritorna None — solleva
`LibraryNotFoundError` o `LibraryAccessError`. Il ramo era codice morto e il
rifiuto arrivava al client come 500, indistinguibile da un guasto del server.

Ultimo difetto, funzionale e non di sicurezza: `/rpc` incapsulava il risultato
con `str(res)`, cioe' il repr Python di un dizionario — apici singoli, `True`
invece di `true`. Nessun client MCP puo' interpretarlo come JSON. La rotta
nativa non era mai stata esercitata da un client vero.
"""

import json

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.libraries
import api.mcp_server
import config
from api import app
from core.governance import create_or_update_user
from core.rate_limiter import get_rate_limiter

PASSWORD_CAPO = "StrongPassword!123"
PASSWORD_OSPITE = "PasswordOspite!123"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir), DATABASE_URL="", ADMIN_USERNAME="capo", ADMIN_PASSWORD=PASSWORD_CAPO, API_KEY=""
    )
    for modulo in (config, api.auth, api.libraries, api.mcp_server):
        # Solo dove l'attributo esiste, cosi' il file resta eseguibile contro
        # la versione precedente del server MCP e il confronto prima/dopo
        # produce fallimenti leggibili invece di errori di raccolta.
        if hasattr(modulo, "cfg"):
            monkeypatch.setattr(modulo, "cfg", test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()
    get_rate_limiter().reset()
    return test_cfg


def _accedi(username: str, password: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return client


@pytest.fixture
def biblioteca(istanza):
    capo = _accedi("capo", PASSWORD_CAPO)
    library_id = capo.post("/api/libraries", json={"name": "Archivio", "visibility": "private"}).json()["id"]
    capo.post(
        "/api/integrations/automation/ingest",
        json={
            "library_id": library_id,
            "filename": "ferie.txt",
            "content": "Le ferie si richiedono con quindici giorni di anticipo al responsabile.",
            "is_base64": False,
        },
    )
    return capo, library_id


def _chiama(client: TestClient, nome: str, argomenti: dict):
    return client.post("/api/mcp/call", json={"name": nome, "arguments": argomenti})


def _rpc(client: TestClient, metodo: str, parametri: dict | None = None):
    return client.post("/api/mcp/rpc", json={"jsonrpc": "2.0", "id": 1, "method": metodo, "params": parametri or {}})


def _abbassa_il_limite(monkeypatch, massimo: int):
    limiter = get_rate_limiter()
    monkeypatch.setattr(limiter.config, "max_requests_per_minute", massimo)
    limiter.reset()


# ============================================================
# La guardia che manca: nessun limite sulle operazioni costose
# ============================================================


def test_the_mcp_tool_call_route_is_rate_limited_like_the_normal_ask(istanza, biblioteca, monkeypatch):
    capo, library_id = biblioteca
    _abbassa_il_limite(monkeypatch, 3)

    esiti = [_chiama(capo, "search_documents", {"library_id": library_id, "query": "ferie"}) for _ in range(6)]

    codici = [e.status_code for e in esiti]
    assert 429 in codici, f"nessun limite sulla rotta MCP piu' costosa: {codici}"


def test_the_mcp_jsonrpc_route_is_rate_limited_too(istanza, biblioteca, monkeypatch):
    """E' la rotta che un client MCP nativo usa davvero: se il limite vale solo
    su /call, l'agente in ciclo passa comunque."""
    capo, library_id = biblioteca
    _abbassa_il_limite(monkeypatch, 3)

    esiti = [
        _rpc(
            capo,
            "tools/call",
            {"name": "search_documents", "arguments": {"library_id": library_id, "query": "ferie"}},
        )
        for _ in range(6)
    ]

    codici = [e.status_code for e in esiti]
    assert 429 in codici, f"nessun limite sulla rotta JSON-RPC: {codici}"


def test_listing_the_tools_is_not_rate_limited(istanza, monkeypatch):
    """Il limite va sulle operazioni costose, non sulla scoperta: un client MCP
    interroga /tools a ogni connessione, e strozzarlo romperebbe il handshake
    senza proteggere nulla."""
    capo = _accedi("capo", PASSWORD_CAPO)
    _abbassa_il_limite(monkeypatch, 2)

    esiti = [capo.get("/api/mcp/tools").status_code for _ in range(6)]

    assert esiti == [200] * 6, esiti


# ============================================================
# Il controllo di accesso c'era, ma scritto contro il contratto sbagliato
# ============================================================


def test_a_denied_library_is_a_refusal_not_a_server_error(istanza, biblioteca):
    """`if not lib` era codice morto: get_library solleva, non ritorna None.
    Il rifiuto arrivava come 500."""
    _capo, library_id = biblioteca
    create_or_update_user(istanza.USERS_FILE, "ospite", "viewer", PASSWORD_OSPITE)
    ospite = _accedi("ospite", PASSWORD_OSPITE)

    esito = _chiama(ospite, "ask_library", {"library_id": library_id, "question": "Come si richiedono le ferie?"})

    assert esito.status_code == 404, f"atteso un rifiuto, ricevuto {esito.status_code}"


def test_a_denied_library_leaks_no_content_through_search(istanza, biblioteca):
    _capo, library_id = biblioteca
    create_or_update_user(istanza.USERS_FILE, "ospite", "viewer", PASSWORD_OSPITE)
    ospite = _accedi("ospite", PASSWORD_OSPITE)

    esito = _chiama(ospite, "search_documents", {"library_id": library_id, "query": "ferie"})

    assert esito.status_code == 404
    assert "anticipo" not in esito.text


def test_a_nonexistent_library_is_not_a_server_error(istanza):
    capo = _accedi("capo", PASSWORD_CAPO)

    esito = _chiama(capo, "search_documents", {"library_id": "non-esiste", "query": "ferie"})

    assert esito.status_code == 404


# ============================================================
# I limiti sugli argomenti, che le rotte normali hanno nel modello Pydantic
# ============================================================


def test_a_question_longer_than_the_normal_route_allows_is_refused(istanza, biblioteca):
    """`AskLibraryRequest` limita la domanda a 2000 caratteri. Da qui una
    domanda da megabyte finiva intera nel prompt del modello."""
    capo, library_id = biblioteca

    esito = _chiama(capo, "ask_library", {"library_id": library_id, "question": "ferie " * 20000})

    assert esito.status_code == 422, f"atteso un rifiuto, ricevuto {esito.status_code}"


def test_a_one_character_query_is_refused_as_on_the_normal_search(istanza, biblioteca):
    capo, library_id = biblioteca

    esito = _chiama(capo, "search_documents", {"library_id": library_id, "query": "a"})

    assert esito.status_code == 422


def test_a_non_numeric_top_k_is_refused_not_a_crash(istanza, biblioteca):
    """`int(args.get("top_k", 5))` sollevava ValueError: un argomento
    malformato di un agente diventava un errore del server."""
    capo, library_id = biblioteca

    esito = _chiama(capo, "search_documents", {"library_id": library_id, "query": "ferie", "top_k": "molti"})

    assert esito.status_code == 422, f"atteso un rifiuto, ricevuto {esito.status_code}"


# ============================================================
# Il protocollo: cosa riceve davvero un client MCP
# ============================================================


def test_the_jsonrpc_result_is_parseable_json_not_a_python_repr(istanza, biblioteca):
    """`str(res)` produceva un repr Python: apici singoli e `False` maiuscolo,
    che nessun client MCP puo' leggere."""
    capo, library_id = biblioteca

    esito = _rpc(
        capo,
        "tools/call",
        {"name": "search_documents", "arguments": {"library_id": library_id, "query": "ferie"}},
    )

    assert esito.status_code == 200, esito.text
    testo = esito.json()["result"]["content"][0]["text"]
    decodificato = json.loads(testo)  # falliva con JSONDecodeError
    assert decodificato["library_id"] == library_id


def test_the_initialized_notification_is_not_answered_with_an_error(istanza):
    """Dopo `initialize` ogni client MCP invia `notifications/initialized`, che
    non attende risposta. Rispondere `Method not found` a una notifica viola il
    protocollo e alcuni client abortiscono il handshake."""
    capo = _accedi("capo", PASSWORD_CAPO)

    esito = capo.post("/api/mcp/rpc", json={"jsonrpc": "2.0", "method": "notifications/initialized"})

    assert esito.status_code in (200, 202)
    assert "error" not in esito.json(), esito.text


def test_an_unknown_tool_inside_jsonrpc_is_a_protocol_error_not_a_leaked_exception(istanza):
    capo = _accedi("capo", PASSWORD_CAPO)

    esito = _rpc(capo, "tools/call", {"name": "rm_rf", "arguments": {}})

    corpo = esito.json()
    assert "error" in corpo
    assert "Traceback" not in json.dumps(corpo)


# ============================================================
# La funzionalita' legittima deve continuare a funzionare
# ============================================================


def test_an_agent_can_still_list_ask_and_search(istanza, biblioteca):
    capo, library_id = biblioteca

    elenco = _chiama(capo, "list_libraries", {})
    ricerca = _chiama(capo, "search_documents", {"library_id": library_id, "query": "ferie anticipo"})
    domanda = _chiama(capo, "ask_library", {"library_id": library_id, "question": "Come si richiedono le ferie?"})

    assert elenco.status_code == 200
    assert any(voce["id"] == library_id for voce in elenco.json()["libraries"])
    assert ricerca.status_code == 200, ricerca.text
    assert domanda.status_code == 200, domanda.text


def test_the_native_handshake_still_works(istanza):
    capo = _accedi("capo", PASSWORD_CAPO)

    inizio = _rpc(capo, "initialize")
    strumenti = _rpc(capo, "tools/list")

    assert inizio.json()["result"]["serverInfo"]["name"] == "ermes-knowledge-mcp"
    assert {s["name"] for s in strumenti.json()["result"]["tools"]} == {
        "list_libraries",
        "ask_library",
        "search_documents",
    }
