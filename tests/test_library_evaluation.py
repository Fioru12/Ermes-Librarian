import json
from pathlib import Path

from evaluation.run_library_eval import GOLD_SET_PATH, evaluate


def test_demo_gold_set_meets_retrieval_quality_bar():
    """Keyword baseline gate: the CI-safe mode (no Ollama required).

    Only the "direct" queries (worded close to the source text) are held to
    a hard bar — that is the retrieval mode every deployment gets by
    default. The other slices are floors at the measured value of the shipped
    configuration: the evaluation is deterministic, so any drop is a real
    regression, and any rise should be published (docs/RETRIEVAL_EVALUATION.md).
    """
    gold_set = json.loads(Path(GOLD_SET_PATH).read_text(encoding="utf-8"))

    report = evaluate(gold_set)

    # 16 direct, 20 paraphrase, 16 abstention since 25 September 2026. With
    # the earlier 3 abstention questions, one error was worth 33 points and
    # the published 1.000 turned out to be 0.375 on a sample of 16.
    assert len(gold_set) >= 52
    assert report["recall_at_3_direct"] >= 0.9
    assert report["citation_coverage"] >= 0.833
    # Paraphrase floor also guards a specific decision: the reranker used to
    # be enabled by default and made this slice worse, so re-enabling it
    # without first measuring an improvement turns this test red. Reproduce
    # with `python evaluation/run_library_eval.py --compare`.
    assert (report["recall_at_3_paraphrase"] or 0) >= 0.45
    # Keyword-only matching cites a passage whenever one term matches, so it
    # refuses correctly only 6 times out of 16. The remedy is evidence
    # verification (16/16), which needs a local model and is therefore not
    # what CI can run; this floor only stops the default from getting worse.
    assert (report["abstention_accuracy"] or 0) >= 0.375
