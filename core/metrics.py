"""
metrics.py
Metriche Prometheus native (prometheus_client) per Ermes Knowledge.

Sostituisce il contatore in-memory di api/__init__.py con:
- istogrammi di latenza con bucket standard (anziché sole somme)
- metriche di business RAG (domande, retriever, abstention)
- exposition sicura: l'endpoint /metrics richiede il token ERMES_METRICS_TOKEN

Il fallback in-memory resta come shim per i test esistenti che leggono
ermes_http_requests_total via /metrics.
"""

from __future__ import annotations

import contextlib

from prometheus_client import REGISTRY, Counter, Gauge, Histogram

# ── HTTP (middleware globale) ──────────────────────────────
HTTP_REQUESTS = Counter(
    "ermes_http_requests_total",
    "Numero totale di richieste HTTP gestite.",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "ermes_http_request_duration_seconds",
    "Tempo di risposta HTTP.",
    ["method", "path"],
    # Bucket più adatti a un API locale (ms..pochi s) del default di prometheus_client
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ── Business RAG ───────────────────────────────────────────
RAG_QUESTIONS = Counter(
    "ermes_rag_questions_total",
    "Domande poste al motore evidence.",
    ["library_id", "outcome"],  # answered | abstained | error
)
RAG_RETRIEVAL = Histogram(
    "ermes_rag_retrieval_results",
    "Numero di passaggi recuperati per domanda.",
    buckets=(0, 1, 3, 5, 10, 20),
)
RAG_RETRIEVAL_DURATION = Histogram(
    "ermes_rag_retrieval_duration_seconds",
    "Durata della fase di retrieval.",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
RAG_RERANK_MODE = Counter(
    "ermes_rag_rerank_mode_total",
    "Modalità del reranker usata nelle ricerche.",
    ["mode"],  # neural | lexical
)
# I due passaggi che dipendono da un modello locale e che, quando il modello
# manca, DEGRADANO IN SILENZIO al comportamento senza di loro: il verificatore
# torna "non controllato", la riscrittura torna alla domanda originale. Per
# chi guarda la risposta e' indistinguibile dal non averli. Trovato con il
# verificatore attivo e il modello configurato non installato: /health diceva
# "healthy" e l'astensione promessa non avveniva. Questi contatori sono l'unico
# posto in cui il degrado si accumula in modo osservabile.
EVIDENCE_VERIFIER = Counter(
    "ermes_evidence_verifier_total",
    "Esiti della verifica dell'evidenza per risposta.",
    ["outcome"],  # verified | unavailable | disabled
)
QUESTION_REWRITE = Counter(
    "ermes_question_rewrite_total",
    "Esiti della riscrittura conversazionale della domanda.",
    ["outcome"],  # rewritten | unchanged | no_history | disabled | model_unavailable | rejected
)

# ── Sistema ────────────────────────────────────────────────
INGESTION_JOBS = Counter(
    "ermes_ingestion_jobs_total",
    "Job di ingestione per stato finale.",
    ["status"],  # ready | failed
)
SYSTEM_INFO = Gauge(
    "ermes_system_info",
    "Metadati di sistema dell'istanza Ermes.",
    ["version", "python_version", "environment"],
)


def init_system_info(version: str, python_version: str, environment: str) -> None:
    SYSTEM_INFO.labels(version=version, python_version=python_version, environment=environment).set(1)


def expose() -> str:
    """Render in formato exposition di Prometheus (text/plain 0.0.4)."""
    from prometheus_client import generate_latest

    return generate_latest(REGISTRY).decode("utf-8")


def rag_question_recorded(library_id: str, outcome: str, result_count: int | None = None) -> None:
    RAG_QUESTIONS.labels(library_id=library_id, outcome=outcome).inc()
    if result_count is not None:
        RAG_RETRIEVAL.observe(min(result_count, 20))


def record_rerank_mode(mode: str) -> None:
    """Registra la modalità reranker usata dalla ricerca (best-effort)."""
    with contextlib.suppress(Exception):  # pragma: no cover
        RAG_RERANK_MODE.labels(mode=mode if mode in {"neural", "lexical"} else "unknown").inc()


def record_verifier_outcome(outcome: str) -> None:
    """verified | unavailable | disabled (best-effort)."""
    with contextlib.suppress(Exception):  # pragma: no cover
        EVIDENCE_VERIFIER.labels(outcome=outcome).inc()


def record_rewrite_outcome(outcome: str) -> None:
    """Uno dei reason di core.question_rewriter.Riscrittura (best-effort)."""
    with contextlib.suppress(Exception):  # pragma: no cover
        QUESTION_REWRITE.labels(outcome=outcome).inc()


def rag_retrieval_timer():
    """Context manager per misurare la durata della fase di retrieval."""
    return RAG_RETRIEVAL_DURATION.time()
