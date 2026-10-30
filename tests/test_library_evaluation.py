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


def test_pmi_gold_set_points_at_sections_the_parser_really_produces():
    """Il gold set PMI si riferisce a sezioni per nome: se un documento viene
    modificato o il parser cambia il modo di nominarle, una domanda attesa
    "a vuoto" verrebbe contata come errore di recupero invece che di dataset."""
    from core.document_parser import chunk_source_units, extract_source_units
    from evaluation.run_library_eval import PMI_CORPUS_DIR, PMI_GOLD_SET_PATH

    sections: dict[str, set[tuple[str, str]]] = {}
    for file in (f for f in PMI_CORPUS_DIR.rglob("*") if f.suffix in {".md", ".eml"}):
        chunks = chunk_source_units(extract_source_units(file.name, file.read_bytes()))
        sections.setdefault(file.parent.name, set()).update((file.name, locator) for _, locator in chunks)
    gold_set = json.loads(PMI_GOLD_SET_PATH.read_text(encoding="utf-8"))

    assert len(gold_set) >= 150
    assert len({item["id"] for item in gold_set}) == len(gold_set)
    for item in gold_set:
        assert item["library"] in sections, item["id"]
        if item["type"] == "abstention":
            assert item["expected_filename"] is None and item["expected_locator"] is None, item["id"]
            continue
        targets = [(item["expected_filename"], item["expected_locator"])]
        targets += [(alt["filename"], alt["locator"]) for alt in item.get("also_acceptable", [])]
        for target in targets:
            assert target in sections[item["library"]], (item["id"], target)


def test_pmi_suite_keyword_baseline_does_not_regress():
    """Soglie al valore misurato della configurazione di default (solo parole,
    nessun modello): come per il gold set storico, un calo e' una regressione
    e un aumento va pubblicato in docs/RETRIEVAL_EVALUATION.md.

    L'astensione bassa e' il dato, non un difetto del test: su un corpus con
    piu' documenti per biblioteca la corrispondenza per parole cita quasi
    sempre qualcosa. Il rimedio misurato e' la verifica dell'evidenza.
    """
    from evaluation.run_library_eval import PMI_GOLD_SET_PATH, build_pmi_store

    gold_set = json.loads(PMI_GOLD_SET_PATH.read_text(encoding="utf-8"))

    report = evaluate(gold_set, build_store=build_pmi_store)

    assert report["recall_at_3_direct"] >= 0.95
    assert (report["recall_at_3_paraphrase"] or 0) >= 0.56
    assert (report["abstention_accuracy"] or 0) >= 0.17
    assert set(report["by_tag"]) >= {"trap", "cross_library", "out_of_domain", "colloquial", "multi_doc", "numeric"}
