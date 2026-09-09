"""Deterministic evaluation of the local Ermes Knowledge retrieval contract.

No external model is required. The script creates an isolated temporary
library database from a fictional company corpus and reports recall@k plus
citation integrity. It is safe to run in CI.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import cfg
from core.library_embeddings import embed_texts
from core.library_store import LibraryStore

ROOT = Path(__file__).resolve().parent
GOLD_SET_PATH = ROOT / "library_gold_set.json"

# Configurazioni messe a confronto da --compare. L'ordine è quello in cui
# vengono stampate: si parte dal recupero più semplice e si aggiunge un
# componente alla volta, così la tabella si legge come "cosa cambia quando
# accendo questo pezzo".
COMPARISON_MATRIX: list[dict] = [
    {
        "label": "Lessicale (baseline)",
        "semantic": False,
        "env": {"ERMES_RERANKER_ENABLED": "0"},
    },
    {
        "label": "Lessicale + reranker neurale",
        "semantic": False,
        "env": {"ERMES_RERANKER_ENABLED": "1", "ERMES_RERANKER_NEURAL": "1"},
    },
    {
        "label": "Ibrida (keyword + embedding)",
        "semantic": True,
        "env": {"ERMES_RERANKER_ENABLED": "0"},
    },
    {
        "label": "Ibrida + reranker lessicale",
        "semantic": True,
        "env": {"ERMES_RERANKER_ENABLED": "1", "ERMES_RERANKER_NEURAL": "0"},
    },
    {
        "label": "Ibrida + reranker neurale",
        "semantic": True,
        "env": {"ERMES_RERANKER_ENABLED": "1", "ERMES_RERANKER_NEURAL": "1"},
    },
]

DEMO_CORPUS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "HR": (
        "policy-ferie.md",
        [
            (
                "Le richieste di ferie devono essere inviate al responsabile almeno cinque giorni lavorativi prima dell'inizio dell'assenza.",
                "Sezione: Richiesta ferie",
            ),
            (
                "In caso di malattia, il dipendente informa il responsabile diretto entro l'inizio dell'orario di lavoro e invia il certificato secondo le regole vigenti.",
                "Sezione: Assenze",
            ),
            (
                "Il permesso orario viene richiesto nel portale presenze prima dell'uscita e indica la motivazione prevista dal regolamento.",
                "Sezione: Permessi",
            ),
            (
                "Il nuovo assunto riceve credenziali aziendali e istruzioni di accesso il primo giorno lavorativo dall'ufficio IT.",
                "Sezione: Onboarding",
            ),
        ],
    ),
    "IT": (
        "runbook-backup.md",
        [
            (
                "I backup giornalieri dei sistemi critici sono conservati per trenta giorni; i backup mensili restano disponibili per dodici mesi.",
                "Sezione: Conservazione",
            ),
            (
                "Se si sospetta un ransomware, scollegare immediatamente il dispositivo dalla rete e contattare il servizio IT senza spegnere il computer.",
                "Sezione: Incidente",
            ),
            (
                "I responsabili applicativi verificano trimestralmente gli accessi ai sistemi e segnalano gli account non piu necessari.",
                "Sezione: Accessi",
            ),
            (
                "Per ripristinare un file, aprire una richiesta al service desk indicando percorso, data approssimativa e motivazione.",
                "Sezione: Ripristino",
            ),
        ],
    ),
    "Qualita": (
        "procedura-qualita.md",
        [
            (
                "Ogni non conformita deve essere registrata nel registro qualita entro un giorno lavorativo dalla rilevazione.",
                "Sezione: Non conformita",
            ),
            (
                "La revisione di una procedura richiede l'approvazione del responsabile qualita prima della pubblicazione.",
                "Sezione: Revisione documenti",
            ),
            (
                "La formazione su una nuova procedura viene registrata nel fascicolo formativo del personale interessato.",
                "Sezione: Formazione",
            ),
            (
                "I registri qualita sono conservati per cinque anni, salvo obblighi contrattuali o normativi piu lunghi.",
                "Sezione: Conservazione registri",
            ),
        ],
    ),
    "Amministrazione": (
        "nota-spese.md",
        [
            (
                "La nota spese va consegnata entro il quinto giorno lavorativo del mese successivo alla trasferta.",
                "Sezione: Scadenze",
            ),
            (
                "Ogni spesa deve includere ricevuta fiscale o fattura leggibile, data, importo e causale della trasferta.",
                "Sezione: Allegati",
            ),
            (
                "Un anticipo trasferta viene richiesto all'amministrazione almeno sette giorni prima della partenza.",
                "Sezione: Anticipi",
            ),
            (
                "Le spese superiori a cinquecento euro richiedono autorizzazione preventiva del responsabile di funzione.",
                "Sezione: Approvazioni",
            ),
        ],
    ),
}


def build_demo_store(database_path: Path) -> tuple[LibraryStore, dict[str, str]]:
    store = LibraryStore(database_path)
    libraries: dict[str, str] = {}
    for name, (filename, chunks) in DEMO_CORPUS.items():
        library = store.create_library(name, "Corpus dimostrativo fittizio", "shared", owner_id="demo")
        libraries[name] = library["id"]
        content = "\n".join(text for text, _ in chunks).encode("utf-8")
        document = store.add_document(
            library["id"], filename, "text/markdown", content, f"/demo/{filename}", chunks=chunks
        )
        # Mirrors core/ingestion_service.py: add_document only stores chunk text,
        # never embeddings. Without this, search_with_profile has no vector to
        # compare against and silently stays in keyword mode regardless of
        # --semantic or Ollama's availability — found while trying to actually
        # measure the semantic recall number this script was built to report.
        embeddings = embed_texts([text for text, _ in chunks])
        if embeddings:
            store.store_chunk_embeddings(library["id"], document["id"], embeddings, cfg.EMBED_MODEL_ID)
    return store, libraries


def _recall(details: list[dict], type_filter: str | None = None) -> float | None:
    subset = [d for d in details if type_filter is None or d["type"] == type_filter]
    if not subset:
        return None
    return round(sum(d["passed"] for d in subset) / len(subset), 3)


def evaluate(gold_set: list[dict], limit: int | None = None, semantic: bool = False) -> dict:
    cases = gold_set[:limit] if limit else gold_set
    # cfg is a frozen dataclass singleton shared with core.library_store /
    # core.library_embeddings; this is the standard way to flip one flag on an
    # already-constructed frozen instance without reconstructing it. Set
    # unconditionally, not just when semantic=True: a local .env with
    # ERMES_LIBRARY_SEMANTIC_SEARCH=1 (set for other manual testing) would
    # otherwise leak into the supposedly keyword-only default path, making
    # this "deterministic, safe for CI" evaluation silently depend on ambient
    # environment state instead of the --semantic flag actually passed.
    object.__setattr__(cfg, "LIBRARY_SEMANTIC_SEARCH_ENABLED", semantic)
    with tempfile.TemporaryDirectory(prefix="ermes-library-eval-") as temp_dir:
        store, libraries = build_demo_store(Path(temp_dir) / "library.sqlite3")
        details = []
        for item in cases:
            item_type = item.get("type", "direct")
            results, profile = store.search_with_profile(libraries[item["library"]], item["query"], limit=3)
            if item_type == "abstention":
                # Correct behaviour is to find nothing to cite, not to guess.
                passed = len(results) == 0
            else:
                passed = any(
                    result["filename"] == item["expected_filename"]
                    and result["citation"]["locator"] == item["expected_locator"]
                    for result in results
                )
            details.append(
                {
                    "id": item["id"],
                    "type": item_type,
                    "passed": passed,
                    "retrieval_mode": profile["mode"],
                    "top_result": results[0]["citation"] if results else None,
                    "expected": {"filename": item.get("expected_filename"), "locator": item.get("expected_locator")},
                }
            )
    evidence_expected = [d for d in details if d["type"] != "abstention"]
    citation_coverage = (
        round(sum(1 for d in evidence_expected if d["top_result"] is not None) / len(evidence_expected), 3)
        if evidence_expected
        else 0.0
    )
    semantic_queries_used = sum(1 for d in details if d["retrieval_mode"] == "hybrid_local")
    passed = sum(item["passed"] for item in details)
    return {
        "queries": len(details),
        "passed": passed,
        "recall_at_3": round(passed / len(details), 3) if details else 0.0,
        "recall_at_3_direct": _recall(details, "direct"),
        "recall_at_3_paraphrase": _recall(details, "paraphrase"),
        "abstention_accuracy": _recall(details, "abstention"),
        "citation_coverage": citation_coverage,
        "semantic_search_requested": semantic,
        "semantic_queries_used": semantic_queries_used,
        "semantic_search_active": semantic_queries_used > 0,
        "details": details,
    }


def _run_single_configuration(entry: dict, limit: int | None) -> dict | None:
    """Esegue una configurazione in un processo separato.

    Il sottoprocesso non è una precauzione generica: senza di esso il
    confronto sarebbe falsato da due stati condivisi reali. La cache di
    ricerca (core/search_cache.py) indicizza per biblioteca+query+utente ma
    NON per configurazione di recupero, quindi la seconda configurazione
    leggerebbe i risultati della prima; e core/reranker.py tiene il modello
    neurale in una variabile globale di modulo. Processi separati eliminano
    entrambi i problemi senza dover ricordare di azzerare stati sparsi.
    """
    with tempfile.TemporaryDirectory(prefix="ermes-compare-") as temp_dir:
        output_path = Path(temp_dir) / "report.json"
        command = [sys.executable, str(Path(__file__).resolve()), "--output", str(output_path)]
        if entry["semantic"]:
            command.append("--semantic")
        if limit:
            command += ["--limit", str(limit)]

        env = os.environ.copy()
        env.update(entry["env"])
        # Le barre di avanzamento del caricamento modello sommergerebbero la
        # tabella senza aggiungere informazione.
        env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        env.setdefault("TRANSFORMERS_VERBOSITY", "error")

        # Su Windows la creazione di processi in rapida successione puo'
        # fallire con WinError 5 quando l'antivirus tiene il handle
        # dell'eseguibile: e' transitorio, non un errore di configurazione,
        # e senza il ritentativo il confronto si interrompe a meta' tabella.
        for attempt in range(5):
            try:
                result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=1800)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(2 * (attempt + 1))
        if not output_path.exists():
            print(f"  ! configurazione '{entry['label']}' non ha prodotto un report", file=sys.stderr)
            if result.stderr:
                print(f"    {result.stderr.strip().splitlines()[-1]}", file=sys.stderr)
            return None
        return json.loads(output_path.read_text(encoding="utf-8"))


def _format_comparison_table(rows: list[tuple[str, dict]]) -> str:
    """Tabella in Markdown, pronta da incollare in README/documentazione."""
    header = (
        "| Configurazione | recall@3 | dirette | parafrasi | astensione | citation coverage |\n"
        "|---|---|---|---|---|---|"
    )
    lines = [header]
    for label, report in rows:
        lines.append(
            f"| {label} "
            f"| {report['recall_at_3']:.3f} "
            f"| {report['recall_at_3_direct']:.3f} "
            f"| {report['recall_at_3_paraphrase']:.3f} "
            f"| {report['abstention_accuracy']:.3f} "
            f"| {report['citation_coverage']:.3f} |"
        )
    return "\n".join(lines)


def run_comparison(limit: int | None = None) -> dict:
    """Misura ogni configurazione della matrice e restituisce il confronto."""
    rows: list[tuple[str, dict]] = []
    for entry in COMPARISON_MATRIX:
        print(f"-> {entry['label']} ...", file=sys.stderr)
        report = _run_single_configuration(entry, limit)
        if report is not None:
            rows.append((entry["label"], report))

    if not rows:
        return {"configurations": [], "table": ""}

    return {
        "configurations": [
            {
                "label": label,
                "recall_at_3": report["recall_at_3"],
                "recall_at_3_direct": report["recall_at_3_direct"],
                "recall_at_3_paraphrase": report["recall_at_3_paraphrase"],
                "abstention_accuracy": report["abstention_accuracy"],
                "citation_coverage": report["citation_coverage"],
                "semantic_search_active": report["semantic_search_active"],
            }
            for label, report in rows
        ],
        "table": _format_comparison_table(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Ermes Knowledge local retrieval")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Misura tutte le configurazioni di recupero (lessicale, ibrida, con e senza reranker) e stampa la tabella comparativa.",
    )
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Enable local hybrid (keyword+embedding) search via Ollama; degrades to keyword-only if Ollama is unreachable.",
    )
    args = parser.parse_args()

    if args.compare:
        comparison = run_comparison(args.limit)
        if not comparison["configurations"]:
            print("Nessuna configurazione misurata con successo.", file=sys.stderr)
            return 1
        print()
        print(comparison["table"])
        if args.output:
            args.output.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    gold_set = json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))
    report = evaluate(gold_set, args.limit, semantic=args.semantic)
    if args.semantic and not report["semantic_search_active"]:
        print(
            "AVVISO: --semantic richiesto ma nessuna query ha usato hybrid_local — "
            "Ollama non raggiungibile o embedding non generati. Risultati in modalita keyword.",
            file=sys.stderr,
        )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if (report["recall_at_3_direct"] or 0) >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
