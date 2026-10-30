"""Un Ollama raggiungibile ma SENZA modelli non e' "tutto a posto".

E' il primo giorno di ogni installazione in Docker: il contenitore di Ollama parte vuoto. Prima il
controllo considerava un modello "mancante" solo se la lista dei modelli non era vuota, quindi con la
lista vuota /health rispondeva "healthy" mentre la ricerca semantica era spenta (recupero solo per
parole chiave: domande in italiano su documenti in inglese senza risposta). Trovato preparando la
demo su Docker, 30 ottobre 2026.
"""

from api import health
from config import cfg


def _ollama(monkeypatch, names):
    monkeypatch.setattr(health, "_ollama_models", lambda: (True, set(names), "Ollama raggiungibile"))


def test_an_empty_ollama_is_reported_when_semantic_search_needs_a_model(monkeypatch):
    _ollama(monkeypatch, [])
    monkeypatch.setattr(cfg, "LIBRARY_SEMANTIC_SEARCH_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "EMBED_MODEL_ID", "embeddinggemma:latest", raising=False)
    avvisi = health._model_dependent_warnings(True, set())
    assert any("ricerca semantica" in a and "embeddinggemma:latest" in a for a in avvisi), avvisi


def test_check_ollama_says_the_model_is_missing_when_ollama_has_no_models(monkeypatch):
    _ollama(monkeypatch, [])
    ok, messaggio = health.check_ollama("embeddinggemma:latest")
    assert ok is True
    assert "non installato" in messaggio


def test_an_installed_model_gives_no_warning(monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_SEMANTIC_SEARCH_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "EMBED_MODEL_ID", "embeddinggemma:latest", raising=False)
    avvisi = health._model_dependent_warnings(True, {"embeddinggemma:latest"})
    assert not any("ricerca semantica" in a for a in avvisi)


def test_an_unreachable_ollama_still_counts_as_missing(monkeypatch):
    monkeypatch.setattr(cfg, "LIBRARY_SEMANTIC_SEARCH_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "EMBED_MODEL_ID", "embeddinggemma:latest", raising=False)
    avvisi = health._model_dependent_warnings(False, set())
    assert any("ricerca semantica" in a for a in avvisi)
