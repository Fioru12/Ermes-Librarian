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


def test_search_library_two_stage_candidate_pool_expansion(tmp_path, monkeypatch):
    """Verifica che LibraryStore.search_library valuti un pool esteso di candidati
    prima di tagliare i risultati al limit richiesto dall'utente."""
    import config
    from core.library_store import LibraryStore

    test_cfg = config.cfg.replace(
        BASE_DIR=str(tmp_path),
        RERANKER_ENABLED=True,
    )
    monkeypatch.setattr("core.library_store.cfg", test_cfg)
    store = LibraryStore(tmp_path / "test_rag.sqlite3")
    lib = store.create_library("Policy Test", "Descrizione", "private", owner_id="owner")

    # Documento A: contiene la parola 'permesso' tante volte (alto punteggio lessicale stage 1)
    # ma senza la frase esatta
    store.add_document(
        library_id=lib["id"],
        filename="regolamento_generico.txt",
        media_type="text/plain",
        content=b"permesso permesso permesso permesso generico",
        storage_path=f"{lib['id']}/regolamento_generico.txt",
        extracted_text="permesso permesso permesso permesso generico",
        chunks=[("permesso permesso permesso permesso generico", "Sezione 1")],
    )

    # Documento B: contiene esattamente la query ricercata "permesso straordinario retribuito"
    # ma con minor ripetizione isolata
    doc_b = store.add_document(
        library_id=lib["id"],
        filename="permessi_speciali.txt",
        media_type="text/plain",
        content=b"La procedura per il permesso straordinario retribuito richiede il benestare del manager.",
        storage_path=f"{lib['id']}/permessi_speciali.txt",
        extracted_text="La procedura per il permesso straordinario retribuito richiede il benestare del manager.",
        chunks=[("La procedura per il permesso straordinario retribuito richiede il benestare del manager.", "Sezione 2")],
    )

    # Con limit=1, se il candidate pool tagliasse a limit=1 prima del reranker,
    # solo il documento con token ripetuti passerebbe.
    # Con il candidate pool allargato a Stage 2, doc_b con frase esatta viene promosso al top!
    results, profile = store.search_with_profile(
        library_id=lib["id"],
        query="permesso straordinario retribuito",
        limit=1,
    )

    assert len(results) == 1
    assert results[0]["document_id"] == doc_b["id"]
    assert "straordinario retribuito" in results[0]["excerpt"]
