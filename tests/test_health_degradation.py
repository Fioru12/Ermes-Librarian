"""Un degrado silenzioso deve essere visibile da /health e da /metrics.

Il caso che ha motivato questo file, riprodotto alla lettera: verificatore
dell'evidenza attivo, modello configurato non installato. Il verificatore
degradava a "non controllato", l'astensione promessa non avveniva, e /health
rispondeva "healthy" limitandosi a nominare il modello mancante in un campo
secondario che nessun cruscotto guarda. Per chi osserva, un'istanza cosi' e'
indistinguibile da una che verifica davvero.

La distinzione che questi test fissano: un modello assente NON e' un degrado
di per se' (in evidence_only non serve, per scelta); lo diventa nel momento in
cui una capacita' e' stata accesa contando su di lui.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.health
import config
from api import app


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    base = config.cfg.replace(BASE_DIR=str(app_dir), DATABASE_URL="", ENABLE_LEGACY_WINSARP=False)

    def applica(**campi):
        nuovo = base.replace(**campi)
        monkeypatch.setattr(config, "cfg", nuovo)
        monkeypatch.setattr(api.health, "cfg", nuovo)
        return nuovo

    return applica


@pytest.fixture
def ollama(monkeypatch):
    """Sostituisce Ollama al confine HTTP di api.health: raggiungibile o no,
    e con quali modelli installati."""
    stato = SimpleNamespace(raggiungibile=True, modelli={"qwen3.5:9b", "qwen3.5:4b", "nomic-embed-text:latest"})

    def finto_get(url, timeout=None, **_):
        if not stato.raggiungibile:
            raise api.health.httpx.ConnectError("simulato")
        corpo = {"models": [{"name": nome} for nome in stato.modelli]}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: corpo)

    monkeypatch.setattr(api.health.httpx, "get", finto_get)
    return stato


# ============================================================
# Il caso di ieri
# ============================================================


def test_verifier_enabled_with_its_model_missing_is_degraded(istanza, ollama):
    istanza(EVIDENCE_VERIFIER_ENABLED=True, EVIDENCE_VERIFIER_MODEL="", DEFAULT_MODEL_ID="llama3.2:latest")

    esito = TestClient(app).get("/health")

    assert esito.status_code == 200, "una sonda di readiness non deve spegnere un'istanza che risponde"
    corpo = esito.json()
    assert corpo["status"] == "degraded"
    assert any("verifica dell'evidenza" in avviso for avviso in corpo["warnings"]), corpo["warnings"]
    assert any("llama3.2:latest" in avviso for avviso in corpo["warnings"])


def test_verifier_enabled_with_ollama_down_is_degraded(istanza, ollama):
    istanza(EVIDENCE_VERIFIER_ENABLED=True, EVIDENCE_VERIFIER_MODEL="qwen3.5:4b")
    ollama.raggiungibile = False

    corpo = TestClient(app).get("/health").json()

    assert corpo["status"] == "degraded"
    assert corpo["ollama_ok"] is False
    assert any("verifica dell'evidenza" in avviso for avviso in corpo["warnings"])


def test_conversation_memory_and_semantic_search_are_checked_the_same_way(istanza, ollama):
    istanza(
        EVIDENCE_VERIFIER_ENABLED=False,
        CONVERSATION_MEMORY_ENABLED=True,
        EVIDENCE_VERIFIER_MODEL="modello-che-non-esiste",
        LIBRARY_SEMANTIC_SEARCH_ENABLED=True,
        EMBED_MODEL_ID="embed-che-non-esiste",
    )

    corpo = TestClient(app).get("/health").json()

    assert corpo["status"] == "degraded"
    testo = " ".join(corpo["warnings"])
    assert "memoria conversazionale" in testo
    assert "ricerca semantica" in testo


# ============================================================
# Un modello assente da solo non e' un degrado
# ============================================================


def test_nothing_enabled_and_ollama_down_is_still_healthy(istanza, ollama):
    """In evidence_only il modello non serve per scelta: la sua assenza e'
    informativa (ollama_ok, ollama_message), non un degrado."""
    istanza(EVIDENCE_VERIFIER_ENABLED=False, CONVERSATION_MEMORY_ENABLED=False, LIBRARY_SEMANTIC_SEARCH_ENABLED=False)
    ollama.raggiungibile = False

    corpo = TestClient(app).get("/health").json()

    assert corpo["status"] == "healthy"
    assert corpo["ollama_ok"] is False
    assert corpo["warnings"] == []


def test_everything_enabled_and_available_is_healthy(istanza, ollama):
    istanza(
        EVIDENCE_VERIFIER_ENABLED=True,
        EVIDENCE_VERIFIER_MODEL="qwen3.5:4b",
        CONVERSATION_MEMORY_ENABLED=True,
        LIBRARY_SEMANTIC_SEARCH_ENABLED=True,
        EMBED_MODEL_ID="nomic-embed-text:latest",
    )

    corpo = TestClient(app).get("/health").json()

    assert corpo["status"] == "healthy", corpo["warnings"]
    assert corpo["warnings"] == []


# ============================================================
# Il degrado si accumula in un contatore osservabile
# ============================================================


def test_a_verifier_that_could_not_run_is_counted_on_metrics(istanza, monkeypatch):
    """Il log dice "non controllato" a ogni domanda; nessuno legge il log. Il
    contatore e' l'unico posto in cui il degrado si vede crescere."""
    from core import evidence_verifier, metrics

    istanza(EVIDENCE_VERIFIER_ENABLED=True, METRICS_TOKEN="")
    monkeypatch.setattr(evidence_verifier, "config", SimpleNamespace(cfg=config.cfg))
    monkeypatch.setattr(evidence_verifier, "_passaggio_risponde", lambda *_: None)  # modello assente
    prima = metrics.EVIDENCE_VERIFIER.labels(outcome="unavailable")._value.get()

    citazioni, eseguita = evidence_verifier.verify_citations("domanda", [{"excerpt": "un passaggio"}])

    assert eseguita is False
    assert metrics.EVIDENCE_VERIFIER.labels(outcome="unavailable")._value.get() == prima + 1
    esposto = TestClient(app).get("/metrics").text
    assert 'ermes_evidence_verifier_total{outcome="unavailable"}' in esposto
