import json
from pathlib import Path

from evaluation.run_library_eval import evaluate, GOLD_SET_PATH


def test_demo_gold_set_meets_retrieval_quality_bar():
    """Keyword baseline gate: the CI-safe mode (no Ollama required).

    Only the "direct" queries (worded close to the source text) are held to
    a hard bar — that is the retrieval mode every deployment gets by
    default. "paraphrase" queries are a deliberate stress test of what
    keyword-only matching cannot do (see docs/RETRIEVAL_EVALUATION.md);
    holding them to the same 0.9 bar would either make the gold set
    dishonestly easy or make CI red for a known, documented limitation.
    "abstention" queries assert the system doesn't fabricate a citation
    when the corpus has no real answer.
    """
    gold_set = json.loads(Path(GOLD_SET_PATH).read_text(encoding="utf-8"))

    report = evaluate(gold_set)

    assert len(gold_set) >= 16
    assert report["recall_at_3_direct"] >= 0.9
    assert report["citation_coverage"] >= 0.9
    # Soft floors on the harder slices: they should not regress to zero,
    # but are not expected to match the direct-query bar under keyword-only
    # search. Re-run with --semantic locally (requires Ollama) to see the
    # hybrid numbers these are meant to improve on.
    assert (report["recall_at_3_paraphrase"] or 0) > 0
    assert (report["abstention_accuracy"] or 0) > 0
