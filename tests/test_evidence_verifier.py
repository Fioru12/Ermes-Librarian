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


def _citazione(testo: str) -> dict:
    return {"excerpt": testo, "citation": {"filename": "policy.md"}}


@pytest.fixture
def attivo(monkeypatch):
    monkeypatch.setattr(config, "cfg", config.cfg.replace(EVIDENCE_VERIFIER_ENABLED=True))
    return config.cfg


def _risponde(monkeypatch, verdetti):
    """Simula il modello: un verdetto per ogni passaggio, in ordine."""
    coda = list(verdetti)
    chiamate = []

    def finto(domanda, passaggio):
        chiamate.append((domanda, passaggio))
        return coda.pop(0)

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
    _risponde(monkeypatch, [False, True, False])

    superstiti, _ = verify_citations("come chiedo le ferie?", citazioni)

    assert superstiti == [buona]


def test_every_candidate_is_examined(attivo, monkeypatch):
    """Fermarsi al primo SI lascerebbe passare gli altri due senza controllo."""
    chiamate = _risponde(monkeypatch, [True, True, False])

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
    coda = [False, None]
    monkeypatch.setattr(verificatore, "_passaggio_risponde", lambda d, p: coda.pop(0))
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
    monkeypatch.setattr(api.libraries, "cfg", test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
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
