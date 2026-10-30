"""Verifica dell'evidenza (core/evidence_verifier.py).

Il modello viene simulato: questi test controllano il comportamento del
meccanismo — cosa passa, cosa viene scartato, cosa succede quando il modello
non risponde — non la bravura del modello, che e' stata misurata a parte sul
golden set (27 query, verificatore locale):

    | Configurazione            | recall@3 | dirette | parafrasi | astensione |
    | Lessicale (default)       |    0.852 |   1.000 |     0.500 |      1.000 |
    | Ibrida senza verifica     |    0.852 |   1.000 |     0.875 |      0.000 |
    | Ibrida + questa verifica  |    0.889 |   1.000 |     0.625 |      1.000 |
"""

import pytest

import config
import core.evidence_verifier as verificatore
from core.evidence_verifier import verify_citations
from tests.library_api_cfg import LIBRARIES_CFG_TARGETS


def _citazione(testo: str) -> dict:
    return {"excerpt": testo, "citation": {"filename": "policy.md"}}


@pytest.fixture
def attivo(monkeypatch):
    monkeypatch.setattr(config, "cfg", config.cfg.replace(EVIDENCE_VERIFIER_ENABLED=True))
    return config.cfg


def _risponde(monkeypatch, verdetti):
    """Simula il modello: un verdetto per passaggio.

    Con piu' passaggi i verdetti vanno dati per testo (dict): la verifica li
    esamina in parallelo, quindi l'ordine delle chiamate non e' quello delle
    citazioni, e una coda in ordine rendeva i test casuali.
    """
    coda = list(verdetti) if not isinstance(verdetti, dict) else []
    chiamate = []

    def finto(domanda, passaggio):
        chiamate.append((domanda, passaggio))
        return verdetti[passaggio] if isinstance(verdetti, dict) else coda.pop(0)

    monkeypatch.setattr(verificatore, "_passaggio_risponde", finto)
    return chiamate


# ============================================================
# Comportamento base
# ============================================================


def test_a_passage_the_model_rejects_is_dropped(attivo, monkeypatch):
    _risponde(monkeypatch, [False])

    superstiti, verificata = verify_citations("quanto dura la maternita'?", [_citazione("Le ferie si richiedono...")])

    assert superstiti == []
    assert verificata is True


def test_a_passage_the_model_accepts_survives(attivo, monkeypatch):
    _risponde(monkeypatch, [True])
    citazione = _citazione("Le ferie si richiedono con quindici giorni di anticipo.")

    superstiti, verificata = verify_citations("come chiedo le ferie?", [citazione])

    assert superstiti == [citazione]
    assert verificata is True


def test_only_the_relevant_passages_survive(attivo, monkeypatch):
    buona = _citazione("Le ferie si richiedono con quindici giorni di anticipo.")
    citazioni = [_citazione("Procedura di backup"), buona, _citazione("Non conformita'")]
    _risponde(monkeypatch, {"Procedura di backup": False, buona["excerpt"]: True, "Non conformita'": False})

    superstiti, _ = verify_citations("come chiedo le ferie?", citazioni)

    assert superstiti == [buona]


def test_every_candidate_is_examined(attivo, monkeypatch):
    """Fermarsi al primo SI lascerebbe passare gli altri due senza controllo."""
    chiamate = _risponde(monkeypatch, {"uno": True, "due": True, "tre": False})

    verify_citations("domanda", [_citazione("uno"), _citazione("due"), _citazione("tre")])

    assert len(chiamate) == 3


# ============================================================
# Quando non deve intervenire
# ============================================================


def test_nothing_happens_when_the_verifier_is_off(monkeypatch):
    monkeypatch.setattr(config, "cfg", config.cfg.replace(EVIDENCE_VERIFIER_ENABLED=False))
    citazioni = [_citazione("qualcosa")]

    def non_chiamare(domanda, passaggio):  # pragma: no cover - deve restare non chiamata
        raise AssertionError("il modello non va interrogato quando la verifica e' spenta")

    monkeypatch.setattr(verificatore, "_passaggio_risponde", non_chiamare)

    superstiti, verificata = verify_citations("domanda", citazioni)

    assert superstiti == citazioni
    assert verificata is False


def test_an_empty_result_is_left_alone(attivo):
    assert verify_citations("domanda", []) == ([], False)


def test_a_citation_without_text_is_kept(attivo, monkeypatch):
    """Scartare per un campo mancante perderebbe evidenza valida a causa di un
    difetto di forma, non di contenuto."""
    _risponde(monkeypatch, [])
    senza_testo = {"citation": {"filename": "policy.md"}, "excerpt": ""}

    superstiti, _ = verify_citations("domanda", [senza_testo])

    assert superstiti == [senza_testo]


# ============================================================
# Quando il modello non risponde
# ============================================================


def test_an_unreachable_model_leaves_the_citations_untouched(attivo, monkeypatch):
    """Non e' un fail-open su una garanzia: e' il ritorno al comportamento
    documentato senza verifica. Ma deve essere dichiarato."""
    monkeypatch.setattr(verificatore, "_passaggio_risponde", lambda d, p: None)
    citazioni = [_citazione("uno"), _citazione("due")]

    superstiti, verificata = verify_citations("domanda", citazioni)

    assert superstiti == citazioni
    assert verificata is False


def test_a_failure_partway_through_does_not_drop_earlier_passages(attivo, monkeypatch):
    """Altrimenti un guasto a meta' produrrebbe una risposta amputata che
    sembra il risultato di un giudizio."""
    verdetti = {"uno": False, "due": None}
    monkeypatch.setattr(verificatore, "_passaggio_risponde", lambda d, p: verdetti[p])
    citazioni = [_citazione("uno"), _citazione("due")]

    superstiti, verificata = verify_citations("domanda", citazioni)

    assert superstiti == citazioni
    assert verificata is False


# ============================================================
# Percorso HTTP
# ============================================================


def test_the_answer_declares_whether_verification_ran(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import api.auth
    import api.libraries
    from api import app

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir), DATABASE_URL="", ADMIN_USERNAME="capo", ADMIN_PASSWORD="StrongPassword!123", API_KEY=""
    )
    monkeypatch.setattr(config, "cfg", test_cfg)
    monkeypatch.setattr(api.auth, "cfg", test_cfg)
    for target in LIBRARIES_CFG_TARGETS:
        monkeypatch.setattr(target, test_cfg)
    monkeypatch.setattr(api.libraries.common, "_store", None)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()

    client = TestClient(app)
    assert (
        client.post("/api/auth/login", json={"username": "capo", "password": "StrongPassword!123"}).status_code == 200
    )
    library_id = client.post("/api/libraries", json={"name": "Archivio", "visibility": "private"}).json()["id"]

    risposta = client.post(f"/api/libraries/{library_id}/ask", json={"question": "come chiedo le ferie?"})

    assert risposta.status_code == 200
    assert risposta.json()["meta"]["evidence_verified"] is False


# ============================================================
# Il banco di valutazione non deve mentire
# ============================================================


def test_the_evaluation_declares_when_verification_did_not_run(monkeypatch):
    """Senza modello raggiungibile i numeri sono quelli SENZA verifica.

    Riportarli come verificati sarebbe la stessa bugia che questo progetto ha
    gia' corretto per la ricerca semantica: un flag richiesto e un risultato
    che non lo riflette.
    """
    import json
    from pathlib import Path

    from evaluation.run_library_eval import GOLD_SET_PATH, evaluate

    monkeypatch.setattr(verificatore, "_passaggio_risponde", lambda d, p: None)
    gold = json.loads(Path(GOLD_SET_PATH).read_text(encoding="utf-8"))

    report = evaluate(gold, limit=4, verify=True)

    assert report["evidence_verification_requested"] is True
    assert report["evidence_verification_active"] is False


def test_the_evaluation_reports_verification_when_it_ran(monkeypatch):
    import json
    from pathlib import Path

    from evaluation.run_library_eval import GOLD_SET_PATH, evaluate

    monkeypatch.setattr(verificatore, "_passaggio_risponde", lambda d, p: True)
    gold = json.loads(Path(GOLD_SET_PATH).read_text(encoding="utf-8"))

    report = evaluate(gold, limit=4, verify=True)

    assert report["evidence_verification_active"] is True


# ============================================================
# Il percorso che i test simulavano, e che quindi era rotto
# ============================================================


def test_the_fallback_model_actually_exists(attivo, monkeypatch):
    """Il ripiego era `cfg.MODEL`, che non esiste in questa configurazione.

    Abilitare il verificatore senza indicare un modello faceva fallire ogni
    domanda con AttributeError, e nessun test se ne accorgeva perche' tutti
    simulavano `_passaggio_risponde` — cioe' proprio la funzione che chiama il
    ripiego.
    """
    monkeypatch.setattr(config, "cfg", config.cfg.replace(EVIDENCE_VERIFIER_MODEL=""))

    assert verificatore._modello()


def test_an_explicit_model_wins_over_the_fallback(attivo, monkeypatch):
    monkeypatch.setattr(config, "cfg", config.cfg.replace(EVIDENCE_VERIFIER_MODEL="modello-scelto"))

    assert verificatore._modello() == "modello-scelto"


def test_an_unexpected_failure_never_breaks_the_answer(attivo, monkeypatch):
    """La verifica e' facoltativa: un suo guasto deve degradare, non far
    fallire la domanda dell'utente."""

    def esplode(*_args, **_kwargs):
        raise RuntimeError("guasto imprevisto")

    monkeypatch.setattr(verificatore.httpx, "post", esplode)
    citazioni = [_citazione("un passaggio qualunque")]

    superstiti, verificata = verify_citations("domanda", citazioni)

    assert superstiti == citazioni
    assert verificata is False


def test_the_whole_path_runs_without_stubbing_the_model_call(attivo, monkeypatch):
    """Esercita _passaggio_risponde per intero, sostituendo solo la rete.

    E' il test che mancava: tutti gli altri sostituivano la funzione, quindi
    non passavano mai da _modello() ne' dalla costruzione della richiesta.
    """

    class _RispostaFinta:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "SI"}

    catturato = {}

    def finta_post(url, json=None, timeout=None):
        catturato["url"] = url
        catturato["model"] = json["model"]
        return _RispostaFinta()

    monkeypatch.setattr(verificatore.httpx, "post", finta_post)
    citazione = _citazione("Le ferie si richiedono con quindici giorni di anticipo.")

    superstiti, verificata = verify_citations("come chiedo le ferie?", [citazione])

    assert superstiti == [citazione]
    assert verificata is True
    assert catturato["model"]
    assert catturato["url"].endswith("/api/generate")


# ============================================================
# Il testo che va al modello passa dal filtro PII
# ============================================================


def test_the_text_sent_to_the_model_is_pii_filtered(attivo, monkeypatch):
    """Ogni percorso che manda testo a un modello applica il filtro PII —
    core/evidence_assistant.py lo fa da sempre. Questo modulo, scritto il
    9 settembre 2026, non lo applicava: apriva una via per cui un codice
    fiscale in un documento raggiungeva il modello mentre la configurazione
    dichiarava di oscurarlo.
    """
    monkeypatch.setattr(config, "cfg", config.cfg.replace(EVIDENCE_VERIFIER_ENABLED=True, PII_FILTER_ENABLED=True))
    visto = {}

    def cattura(domanda, passaggio):
        visto["domanda"] = domanda
        visto["passaggio"] = passaggio
        return True

    monkeypatch.setattr(verificatore, "_passaggio_risponde", cattura)

    verify_citations(
        "il codice fiscale RSSMRA85M01H501Z ha diritto alle ferie?",
        [_citazione("Il dipendente RSSMRA85M01H501Z ha 26 giorni di ferie.")],
    )

    assert "RSSMRA85M01H501Z" not in visto["domanda"], "la domanda arriva al modello non filtrata"
    assert "RSSMRA85M01H501Z" not in visto["passaggio"], "il passaggio arriva al modello non filtrato"


# ============================================================
# Chi verifica: la politica della biblioteca
# ============================================================


def _cloud(monkeypatch, consenso: bool = True, chiave: str = "sk-test"):
    """Configurazione con verifica attiva e, se richiesto, consenso cloud."""
    import core.evidence_assistant as assistente

    nuova = config.cfg.replace(
        EVIDENCE_VERIFIER_ENABLED=True, LIBRARY_CLOUD_CONSENT=consenso, OPENROUTER_API_KEY=chiave
    )
    monkeypatch.setattr(config, "cfg", nuova)
    monkeypatch.setattr(assistente, "cfg", nuova)
    # Il percorso cloud non deve mai cadere su Ollama.
    monkeypatch.setattr(verificatore, "_passaggio_risponde", lambda d, p: pytest.fail("verifica finita su Ollama"))
    return assistente


def test_a_cloud_library_is_verified_by_its_approved_openrouter_model(monkeypatch):
    """Chi non ha un modello locale ottiene la verifica dallo stesso provider
    a cui la biblioteca manda gia' i passaggi per la risposta."""
    assistente = _cloud(monkeypatch)
    chiamate = []

    def finto(system_prompt, prompt, temperature):
        chiamate.append((system_prompt, prompt, temperature))
        return "SI" if "quindici giorni" in prompt else "NO"

    monkeypatch.setattr(assistente, "openrouter_chat", finto)
    buona = _citazione("Le ferie si richiedono con quindici giorni di anticipo.")
    fuori_tema = _citazione("Il parcheggio est e' riservato ai visitatori.")

    superstiti, verificata = verify_citations("come chiedo le ferie?", [buona, fuori_tema], "approved_openrouter")

    assert superstiti == [buona]
    assert verificata is True
    assert len(chiamate) == 2
    assert all(temperatura == 0 for _, _, temperatura in chiamate), "il verdetto deve essere ripetibile"


def test_an_approved_provider_library_is_verified_by_that_provider(monkeypatch):
    assistente = _cloud(monkeypatch)
    nomi = []

    def finto(provider_name, system_prompt, prompt, temperature):
        nomi.append(provider_name)
        return "SI"

    monkeypatch.setattr(assistente, "approved_provider_chat", finto)

    _, verificata = verify_citations("domanda", [_citazione("uno")], "approved_provider", "Azienda Claude")

    assert verificata is True
    assert nomi == ["Azienda Claude"]


def test_without_cloud_consent_a_cloud_library_is_not_verified_and_says_so(monkeypatch):
    """Il consenso si controlla nel trasporto condiviso con la generazione:
    senza, niente parte e la risposta dichiara che la verifica non c'e' stata."""
    _cloud(monkeypatch, consenso=False)
    import core.evidence_assistant as assistente

    monkeypatch.setattr(assistente, "_get_http_client", lambda: pytest.fail("chiamata di rete senza consenso cloud"))
    citazioni = [_citazione("uno"), _citazione("due")]

    superstiti, verificata = verify_citations("domanda", citazioni, "approved_openrouter")

    assert superstiti == citazioni
    assert verificata is False


def test_a_local_library_keeps_using_the_local_model(attivo, monkeypatch):
    import core.evidence_assistant as assistente

    monkeypatch.setattr(assistente, "openrouter_chat", lambda *a: pytest.fail("biblioteca locale verificata nel cloud"))
    _risponde(monkeypatch, [True])

    _, verificata = verify_citations("domanda", [_citazione("uno")], "local_ollama")

    assert verificata is True


@pytest.mark.parametrize("stream", [False, True])
def test_the_answer_endpoints_hand_the_library_policy_to_the_verifier(tmp_path, monkeypatch, stream):
    """Senza questo passaggio la scelta cloud della biblioteca non arriverebbe
    al verificatore, che resterebbe su Ollama anche dove Ollama non c'e'."""
    import core.evidence_verifier
    from api.libraries import ask
    from core.library_store import LibraryStore

    store = LibraryStore(tmp_path / "ermes.sqlite3")
    library = store.create_library("Amministrazione", "", "private", owner_id="alice")
    store.add_document(
        library["id"],
        "spese.md",
        "text/markdown",
        b"x",
        "x/spese.md",
        chunks=[("La nota spese va consegnata entro il quinto giorno lavorativo.", "Sezione: Scadenze")],
    )
    store.set_assistant_policy(library["id"], "approved_provider", "Azienda Claude")
    visto = []

    def cattura(question, citations, mode="evidence_only", provider_name=""):
        visto.append((mode, provider_name))
        return citations, True

    monkeypatch.setattr(core.evidence_verifier, "verify_citations", cattura)
    monkeypatch.setattr(ask, "answer_from_evidence", lambda *a, **k: ("Entro il quinto giorno [1]", "supported", None))
    monkeypatch.setattr(ask, "append_audit", lambda *a, **k: None)
    alice = {"username": "alice", "role": "viewer"}

    if stream:
        list(ask._answer_question_stream(store, library["id"], "entro quando la nota spese?", 3, alice))
    else:
        ask._answer_question(store, library["id"], "entro quando la nota spese?", 3, alice)

    assert visto == [("approved_provider", "Azienda Claude")]
