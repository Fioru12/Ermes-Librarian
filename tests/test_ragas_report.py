"""Le formule RAGAS di evaluation/ragas_report.py, verificate a mano.

Sono le definizioni che rendono i numeri confrontabili con quelli di altri
progetti: se una formula fosse "quasi" quella di RAGAS, il confronto sarebbe
una bugia silenziosa. Piu' un run completo sul golden set, che deve
riprodurre gli stessi fatti del README senza modello.
"""

import json

import pytest

from evaluation import ragas_report as rr


@pytest.mark.parametrize(
    ("relevance", "precision", "recall", "rr_"),
    [
        ([True, False, False], 1.0, 1.0, 1.0),
        ([False, True, False], 0.5, 1.0, 0.5),
        ([False, False, True], 1 / 3, 1.0, 1 / 3),
        ([False, False, False], 0.0, 0.0, 0.0),
        ([], 0.0, 0.0, 0.0),
        # Due rilevanti ai ranghi 1 e 3: (1/1 + 2/3) / 2
        ([True, False, True], (1 + 2 / 3) / 2, 1.0, 1.0),
    ],
)
def test_ragas_formulas(relevance, precision, recall, rr_):
    assert rr.context_precision(relevance) == pytest.approx(precision)
    assert rr.context_recall(relevance) == pytest.approx(recall)
    assert rr.reciprocal_rank(relevance) == pytest.approx(rr_)


def test_full_report_on_the_golden_set_matches_the_published_facts(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    gold = json.loads(rr.GOLD_SET.read_text(encoding="utf-8"))
    report = rr.evaluate(gold, k=3)
    assert report["queries"] == len(gold) == 52
    # Gli stessi fatti di README "Measured, not claimed", shipped default.
    assert report["context_recall_direct"] == 1.0
    assert report["context_recall_paraphrase"] == 0.45
    assert report["abstention_precision"] == 0.375
    assert 0 < report["context_precision"] <= report["context_recall"]
    assert report["not_measured"]["faithfulness"]
    assert "hybrid_local" not in report["retrieval_modes"]
