"""Copertura del reranker neurale (cross-encoder) in core/reranker.py.

Il modello non viene mai scaricato nei test: si usa un finto cross-encoder
iniettato via reset_neural_model + monkeypatch, verificando blend,
fallback e profili di modalità.
"""

import pytest

from core import reranker as reranker_mod
from core.reranker import reset_neural_model, rerank_candidates


class FakeCrossEncoder:
    """Cross-encoder finto: score alto se l'estratto contiene la parola chiave."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs):
        self.calls.append(list(pairs))
        if self.fail:
            raise RuntimeError("OOM simulato")
        scores = []
        for query, text in pairs:
            tokens = [t for t in query.lower().split() if len(t) > 2]
            hit = any(t in text.lower() for t in tokens)
            scores.append(5.0 if hit else -5.0)
        return scores


@pytest.fixture(autouse=True)
def _reset_model_state():
    reset_neural_model()
    yield
    reset_neural_model()


CANDIDATES = [
    {"filename": "ferie.txt", "excerpt": "La pausa pranzo dura 60 minuti.", "relevance_score": 50.0},
    {"filename": "sicurezza.pdf", "excerpt": "Il Badge è obbligatorio negli accessi.", "relevance_score": 40.0},
]


def test_lexical_fallback_when_no_model(monkeypatch):
    monkeypatch.setattr(reranker_mod, "_load_neural_model", lambda: None)
    results = rerank_candidates(query="pausa pranzo", candidates=[dict(c) for c in CANDIDATES])
    assert results[0]["filename"] == "ferie.txt"
    assert results[0]["rerank_mode"] == "lexical"
    assert "neural_score" not in results[0]


def test_neural_blend_promotes_semantically_relevant_result(monkeypatch):
    model = FakeCrossEncoder()
    monkeypatch.setattr(reranker_mod, "_load_neural_model", lambda: model)

    # Il candidato "sbagliato" per il lessicale riceve un giudizio
    # neurale altissimo: il blend deve promuoverlo sopra l'altro.
    results = rerank_candidates(
        query="accessi",
        candidates=[dict(c) for c in CANDIDATES],
        min_score=0.0,
    )
    assert results[0]["rerank_mode"] == "neural"
    assert "neural_score" in results[0]
    # Il modello è stato chiamato con le coppie (query, excerpt)
    assert model.calls and model.calls[0][0][0] == "accessi"
    assert results[0]["rerank_score"] > results[1]["rerank_score"]


def test_blend_is_weighted_average(monkeypatch):
    monkeypatch.setattr(reranker_mod, "_load_neural_model", lambda: FakeCrossEncoder())
    item = {"filename": "x.txt", "excerpt": "pausa pranzo", "relevance_score": 0.0}
    lexical = reranker_mod.calculate_rerank_score("pausa pranzo", "x.txt", "pausa pranzo", 0.0)
    results = rerank_candidates("pausa pranzo", [dict(item)], min_score=0.0)
    expected = 0.6 * 1.0 + 0.4 * lexical  # keyword -> sigmoid(5) ≈ 0.9933
    assert results[0]["rerank_score"] == pytest.approx(expected, abs=0.01)


def test_inference_failure_falls_back_to_lexical(monkeypatch):
    model = FakeCrossEncoder(fail=True)
    monkeypatch.setattr(reranker_mod, "_load_neural_model", lambda: model)
    results = rerank_candidates(query="pausa pranzo", candidates=[dict(c) for c in CANDIDATES])
    assert results[0]["rerank_mode"] == "lexical"
    assert results[0]["filename"] == "ferie.txt"


def test_disabled_by_config_skips_model(monkeypatch):
    """Con ERMES_RERANKER_NEURAL=0 il loader non istanzia nulla e il flusso
    resta interamente lessicale."""
    monkeypatch.setattr(reranker_mod.cfg, "RERANKER_NEURAL_ENABLED", False)
    assert reranker_mod._load_neural_model() is None

    monkeypatch.setattr(reranker_mod, "_load_neural_model", lambda: None)
    results = rerank_candidates(query="pausa pranzo", candidates=[dict(c) for c in CANDIDATES])
    assert results[0]["rerank_mode"] == "lexical"
