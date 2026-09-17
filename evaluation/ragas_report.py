"""Metriche di recupero nella definizione RAGAS, sul golden set del progetto.

`run_library_eval.py` risponde a una domanda binaria per quesito: la citazione
attesa e' fra le prime tre, oppure no. E' la misura giusta per l'astensione e
per confrontare le configurazioni di questo prodotto fra loro, ma non e'
confrontabile con nient'altro: gli altri progetti RAG pubblicano context
precision e context recall come le definisce RAGAS (Es et al., 2023). Questo
script calcola quelle, con le stesse formule, sullo stesso corpus e con lo
stesso motore di recupero — cosi' i numeri di Ermes si possono mettere
accanto a quelli altrui.

Cosa calcola (per quesito con una risposta attesa, poi media):

* context_precision@k — media pesata sui ranghi: per ogni posizione i in cui
  il contesto e' rilevante, precision@i; somma divisa per il numero di
  contesti rilevanti recuperati. Premia i rilevanti in alto.
* context_recall@k — contesti rilevanti recuperati / contesti rilevanti
  attesi. Il golden set ha un contesto atteso per quesito, quindi coincide
  con l'hit rate.
* mrr@k — 1 / rango del primo contesto rilevante.

Per i quesiti di astensione (nessun contesto rilevante esiste) riporta
abstention_precision (quante volte il sistema tace quando deve) e, come
controllo, quante volte tace quando NON deve (false_abstention_rate).

Cosa NON calcola, e perche': faithfulness e answer_relevancy giudicano una
risposta generata. Nella modalita' predefinita (evidence_only) non c'e'
generazione — la "risposta" sono i passaggi citati, la cui fedelta' al
contesto e' 1 per costruzione. Misurarle avrebbe senso solo con un modello
generatore E un modello giudice, ed e' una misura diversa da questa; va
fatta a parte, non infilata qui come numero decorativo.

Uso:
    python evaluation/ragas_report.py [--k 3] [--semantic] [--verify] [--output report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import cfg  # noqa: E402
from core.evidence_verifier import verify_citations  # noqa: E402
from evaluation.run_library_eval import build_demo_store  # noqa: E402

GOLD_SET = ROOT / "evaluation" / "library_gold_set.json"


def _is_relevant(result: dict, item: dict) -> bool:
    return result["filename"] == item["expected_filename"] and result["citation"]["locator"] == item["expected_locator"]


def context_precision(relevance: list[bool]) -> float:
    """RAGAS: sum_i(precision@i * rel_i) / (numero di rilevanti recuperati)."""
    hits = 0
    acc = 0.0
    for i, rel in enumerate(relevance, start=1):
        if rel:
            hits += 1
            acc += hits / i
    return acc / hits if hits else 0.0


def context_recall(relevance: list[bool], expected_relevant: int = 1) -> float:
    return min(sum(relevance), expected_relevant) / expected_relevant


def reciprocal_rank(relevance: list[bool]) -> float:
    for i, rel in enumerate(relevance, start=1):
        if rel:
            return 1.0 / i
    return 0.0


def evaluate(gold_set: list[dict], k: int = 3, semantic: bool = False, verify: bool = False) -> dict:
    # Stesse ragioni di run_library_eval.evaluate: i flag vanno imposti in
    # entrambe le direzioni, altrimenti un .env locale decide al posto
    # dell'opzione passata.
    object.__setattr__(cfg, "LIBRARY_SEMANTIC_SEARCH_ENABLED", semantic)
    object.__setattr__(cfg, "EVIDENCE_VERIFIER_ENABLED", verify)

    per_query: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="ermes-ragas-") as temp_dir:
        store, libraries = build_demo_store(Path(temp_dir) / "library.sqlite3")
        for item in gold_set:
            results, profile = store.search_with_profile(libraries[item["library"]], item["query"], limit=k)
            results, _ = verify_citations(item["query"], results)
            item_type = item.get("type", "direct")
            if item_type == "abstention":
                per_query.append(
                    {
                        "id": item["id"],
                        "type": item_type,
                        "retrieved": len(results),
                        "abstained": len(results) == 0,
                        "retrieval_mode": profile["mode"],
                    }
                )
                continue
            relevance = [_is_relevant(r, item) for r in results]
            per_query.append(
                {
                    "id": item["id"],
                    "type": item_type,
                    "retrieved": len(results),
                    "context_precision": round(context_precision(relevance), 3),
                    "context_recall": round(context_recall(relevance), 3),
                    "reciprocal_rank": round(reciprocal_rank(relevance), 3),
                    "abstained": len(results) == 0,
                    "retrieval_mode": profile["mode"],
                }
            )

    answerable = [q for q in per_query if q["type"] != "abstention"]
    abstention = [q for q in per_query if q["type"] == "abstention"]

    def mean(rows: list[dict], key: str) -> float | None:
        return round(sum(r[key] for r in rows) / len(rows), 3) if rows else None

    def by_type(kind: str, key: str) -> float | None:
        return mean([q for q in answerable if q["type"] == kind], key)

    return {
        "k": k,
        "queries": len(per_query),
        "answerable_queries": len(answerable),
        "abstention_queries": len(abstention),
        "context_precision": mean(answerable, "context_precision"),
        "context_recall": mean(answerable, "context_recall"),
        "mrr": mean(answerable, "reciprocal_rank"),
        "context_precision_direct": by_type("direct", "context_precision"),
        "context_precision_paraphrase": by_type("paraphrase", "context_precision"),
        "context_recall_direct": by_type("direct", "context_recall"),
        "context_recall_paraphrase": by_type("paraphrase", "context_recall"),
        "abstention_precision": (
            round(sum(q["abstained"] for q in abstention) / len(abstention), 3) if abstention else None
        ),
        "false_abstention_rate": (
            round(sum(q["abstained"] for q in answerable) / len(answerable), 3) if answerable else None
        ),
        "semantic_search_requested": semantic,
        "evidence_verification_requested": verify,
        "retrieval_modes": sorted({q["retrieval_mode"] for q in per_query}),
        "not_measured": {
            "faithfulness": "richiede una risposta generata e un modello giudice; in evidence_only non c'e' generazione",
            "answer_relevancy": "come faithfulness",
        },
        "per_query": per_query,
    }


def format_table(report: dict) -> str:
    k = report["k"]
    rows = [
        (f"context_precision@{k}", report["context_precision"]),
        (f"context_recall@{k}", report["context_recall"]),
        (f"mrr@{k}", report["mrr"]),
        (
            "  direct / paraphrase (precision)",
            f"{report['context_precision_direct']} / {report['context_precision_paraphrase']}",
        ),
        (
            "  direct / paraphrase (recall)",
            f"{report['context_recall_direct']} / {report['context_recall_paraphrase']}",
        ),
        ("abstention_precision", report["abstention_precision"]),
        ("false_abstention_rate", report["false_abstention_rate"]),
    ]
    width = max(len(name) for name, _ in rows)
    lines = [f"{name.ljust(width)}  {value}" for name, value in rows]
    lines.append("")
    lines.append("non misurate: " + "; ".join(f"{k} ({v})" for k, v in report["not_measured"].items()))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="RAGAS-style retrieval metrics on the Ermes golden set")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--semantic", action="store_true", help="enable local semantic search (needs Ollama)")
    parser.add_argument("--verify", action="store_true", help="enable evidence verification (needs Ollama)")
    parser.add_argument("--output", type=Path, help="write the full JSON report here")
    args = parser.parse_args()

    gold_set = json.loads(GOLD_SET.read_text(encoding="utf-8"))
    report = evaluate(gold_set, k=args.k, semantic=args.semantic, verify=args.verify)
    print(format_table(report))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nreport: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
