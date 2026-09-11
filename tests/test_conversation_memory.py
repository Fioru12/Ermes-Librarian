"""Memoria conversazionale per riscrittura della domanda.

Ogni domanda a Ermes era isolata: "E l'anno scorso?" non poteva funzionare.
La memoria e' aggiunta nell'unico modo che non rompe la promessa del prodotto:
gli ultimi scambi servono a riscrivere la domanda in forma autonoma PRIMA del
recupero, e da li' in poi la pipeline e' quella di sempre. La storia non entra
mai nel prompt di risposta.

Il modello viene sostituito al confine HTTP (httpx.post in
core.question_rewriter), non nella funzione che lo chiama: e' l'unico punto in
cui una simulazione non nasconde un errore nel codice in prova — lezione
imparata quando il verificatore d'evidenza falliva con AttributeError su ogni
domanda e i suoi test, che simulavano la funzione chiamante, restavano verdi.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.libraries
import config
import core.question_rewriter as rewriter
from api import app

PASSWORD = "StrongPassword!123"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir),
        DATABASE_URL="",
        ADMIN_USERNAME="capo",
        ADMIN_PASSWORD=PASSWORD,
        API_KEY="",
        CONVERSATION_MEMORY_ENABLED=True,
        EVIDENCE_VERIFIER_ENABLED=False,
        LIBRARY_SEMANTIC_SEARCH_ENABLED=False,
        HYDE_ENABLED=False,
    )
    for percorso in ("config.cfg", "api.auth.cfg", "api.libraries.cfg"):
        monkeypatch.setattr(percorso, test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()
    return test_cfg


@pytest.fixture
def modello(monkeypatch):
    """Sostituisce Ollama al confine HTTP. Registra i prompt ricevuti e
    risponde con quanto il test decide."""
    stato = SimpleNamespace(prompts=[], risposta="", fallisce=False)

    def finto_post(url, json=None, timeout=None, **_):
        # httpx.post e' unico per tutto il processo: qui arrivano anche le
        # chiamate di embedding e di HyDE. Solo la riscrittura viene servita;
        # tutto il resto vede "Ollama assente" e degrada come farebbe davvero.
        if not (json and "Domanda riscritta:" in str(json.get("prompt", ""))):
            raise rewriter.httpx.ConnectError("Ollama non raggiungibile (simulato)")
        stato.prompts.append(json["prompt"])
        if stato.fallisce:
            raise rewriter.httpx.ConnectError("Ollama non raggiungibile (simulato)")
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"response": stato.risposta})

    monkeypatch.setattr(rewriter.httpx, "post", finto_post)
    return stato


@pytest.fixture
def biblioteca(istanza):
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": "capo", "password": PASSWORD}).status_code == 200
    library_id = client.post("/api/libraries", json={"name": "Regolamento", "visibility": "private"}).json()["id"]
    client.post(
        f"/api/libraries/{library_id}/documents",
        files={
            "file": (
                "ferie.txt",
                b"Le ferie per gli impiegati si richiedono con quindici giorni di anticipo. "
                b"Per i dirigenti l'anticipo richiesto e' di trenta giorni.",
                "text/plain",
            )
        },
    )
    return client, library_id


def _chiedi(client, library_id, question, history=None):
    corpo = {"question": question}
    if history is not None:
        corpo["history"] = history
    return client.post(f"/api/libraries/{library_id}/ask", json=corpo)


# ============================================================
# La promessa non si rompe
# ============================================================


def test_a_follow_up_outside_the_corpus_still_abstains(biblioteca, modello):
    """Il test piu' importante del file. Una memoria fatta male risponde dai
    turni precedenti; qui la domanda riscritta va al recupero e, se non c'e'
    evidenza, il sistema si astiene come sempre.

    La domanda riscritta non condivide termini con il documento: la prima
    versione di questo test usava "congedo parentale per gli impiegati", e il
    recupero citava il passaggio sulle ferie per la sola parola "impiegati".
    Quello e' il limite noto dell'astensione (RETRIEVAL_EVALUATION.md, T9),
    non un difetto della memoria — e infatti lo faceva anche senza storia. Il
    test successivo verifica proprio questo: la memoria e' neutra.
    """
    client, library_id = biblioteca
    modello.risposta = "Quali sono le regole per il rimborso delle spese di trasferta?"

    esito = _chiedi(
        client,
        library_id,
        "E per le trasferte?",
        history=[{"question": "Con quanto anticipo si chiedono le ferie?", "answer": "Quindici giorni."}],
    )

    assert esito.status_code == 200, esito.text
    assert esito.json()["citations"] == []
    assert esito.json()["meta"]["conversation"]["question_rewritten_to"] == modello.risposta


def test_memory_is_neutral_a_follow_up_gives_what_the_rewritten_question_gives(biblioteca, modello):
    """La garanzia esatta che la memoria offre: una domanda di raffinamento
    produce le stesse citazioni che produrrebbe la domanda riscritta posta da
    sola. Ne' piu' (rispondere dalla storia) ne' meno."""
    client, library_id = biblioteca
    riscritta = "Qual e' la politica sul congedo parentale per gli impiegati?"
    modello.risposta = riscritta

    con_memoria = _chiedi(
        client,
        library_id,
        "E per il congedo parentale?",
        history=[{"question": "Con quanto anticipo si chiedono le ferie?", "answer": "Quindici giorni."}],
    ).json()
    diretta = _chiedi(client, library_id, riscritta).json()

    assert [c["chunk_id"] for c in con_memoria["citations"]] == [c["chunk_id"] for c in diretta["citations"]]
    assert con_memoria["evidence"]["coverage"] == diretta["evidence"]["coverage"]


def test_previous_answers_never_reach_the_model(biblioteca, modello):
    """Solo le domande precedenti vanno al modello di riscrittura. Le risposte
    contengono testo dei documenti: mandarle farebbe uscire contenuto
    documentale verso un modello anche in modalita' evidence_only. Il client
    non le manda, e se le mandasse il server le ignora."""
    client, library_id = biblioteca
    modello.risposta = "Con quanto anticipo i dirigenti devono chiedere le ferie?"

    esito = client.post(
        f"/api/libraries/{library_id}/ask",
        json={
            "question": "E per i dirigenti?",
            "history": [{"question": "Con quanto anticipo si chiedono le ferie?", "answer": "TESTO-DEL-DOCUMENTO"}],
        },
    )

    assert esito.status_code == 200
    assert len(modello.prompts) == 1, "il modello di riscrittura va chiamato una volta"
    assert "Con quanto anticipo si chiedono le ferie?" in modello.prompts[0]
    assert "TESTO-DEL-DOCUMENTO" not in modello.prompts[0], "una risposta precedente e' arrivata al modello"


# ============================================================
# La memoria fa il suo lavoro
# ============================================================


def test_a_follow_up_is_rewritten_and_finds_the_evidence(biblioteca, modello):
    """ "E per i dirigenti?" da sola non trova niente di utile; riscritta trova
    il passaggio sui trenta giorni."""
    client, library_id = biblioteca
    modello.risposta = "Con quanto anticipo i dirigenti devono richiedere le ferie?"

    esito = _chiedi(
        client,
        library_id,
        "E per i dirigenti?",
        history=[{"question": "Con quanto anticipo si chiedono le ferie?", "answer": "Quindici giorni."}],
    )

    corpo = esito.json()
    assert corpo["citations"], "la domanda riscritta doveva trovare il passaggio sui dirigenti"
    assert "trenta" in corpo["citations"][0]["excerpt"]
    conversazione = corpo["meta"]["conversation"]
    assert conversazione["question_original"] == "E per i dirigenti?"
    assert conversazione["question_rewritten_to"] == modello.risposta
    assert conversazione["rewrite"] == "rewritten"


def test_without_history_the_model_is_not_called(biblioteca, modello):
    client, library_id = biblioteca

    esito = _chiedi(client, library_id, "Con quanto anticipo si chiedono le ferie?")

    assert esito.status_code == 200
    assert modello.prompts == []
    assert esito.json()["meta"]["conversation"]["rewrite"] == "no_history"


def test_with_the_feature_off_the_history_is_ignored(biblioteca, modello, monkeypatch):
    """Spenta di default, come il verificatore: richiede un modello."""
    client, library_id = biblioteca
    monkeypatch.setattr(config, "cfg", config.cfg.replace(CONVERSATION_MEMORY_ENABLED=False))

    esito = _chiedi(client, library_id, "E per i dirigenti?", history=[{"question": "ferie?", "answer": "15 gg"}])

    assert esito.status_code == 200
    assert modello.prompts == []
    assert esito.json()["meta"]["conversation"]["rewrite"] == "disabled"


# ============================================================
# I guasti degradano alla domanda originale, e lo dicono
# ============================================================


def test_when_the_model_is_unavailable_the_original_question_is_used(biblioteca, modello):
    client, library_id = biblioteca
    modello.fallisce = True

    esito = _chiedi(client, library_id, "E per i dirigenti?", history=[{"question": "ferie?", "answer": "15 gg"}])

    assert esito.status_code == 200, "un guasto della riscrittura non deve essere un errore per l'utente"
    conversazione = esito.json()["meta"]["conversation"]
    assert conversazione["rewrite"] == "model_unavailable"
    assert conversazione["question_rewritten_to"] is None


@pytest.mark.parametrize(
    "uscita_del_modello",
    [
        "",
        "Certo! Ecco la domanda riscritta:\nCon quanto anticipo i dirigenti chiedono le ferie?",
        "x" * 2001,
    ],
)
def test_an_output_that_is_not_a_question_is_rejected(biblioteca, modello, uscita_del_modello):
    """Il modello puo' ignorare le istruzioni: vuoto, spiegazione su piu'
    righe, o testo enorme non sono domande e non arrivano al recupero."""
    client, library_id = biblioteca
    modello.risposta = uscita_del_modello

    esito = _chiedi(client, library_id, "E per i dirigenti?", history=[{"question": "ferie?", "answer": "15 gg"}])

    assert esito.status_code == 200
    assert esito.json()["meta"]["conversation"]["rewrite"] == "rejected"


def test_more_than_three_turns_are_refused(biblioteca, modello):
    client, library_id = biblioteca

    esito = _chiedi(client, library_id, "E poi?", history=[{"question": f"d{i}", "answer": "r"} for i in range(4)])

    assert esito.status_code == 422


# ============================================================
# Cio' che va al modello passa dal filtro PII
# ============================================================


def test_personal_data_in_the_history_is_masked_before_reaching_the_model(biblioteca, modello, monkeypatch):
    client, library_id = biblioteca
    monkeypatch.setattr(config, "cfg", config.cfg.replace(PII_FILTER_ENABLED=True))
    modello.risposta = "Qual e' l'anticipo per le ferie?"

    _chiedi(
        client,
        library_id,
        "E per lui?",
        history=[{"question": "Ferie di Mario Rossi, mail mario.rossi@example.com?", "answer": "Quindici giorni."}],
    )

    assert modello.prompts, "il modello doveva essere chiamato"
    assert "mario.rossi@example.com" not in modello.prompts[0], "un indirizzo email e' arrivato al modello in chiaro"
