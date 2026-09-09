"""
config/rag.py
Configurazione RAG: retrieval, reranker, embedding, chunking.
"""

import os
from dataclasses import dataclass, field

# I nomi ERMES_SCORE_LOW / _MED / _HIGH sono stati rinominati in
# ERMES_SCORE_THRESHOLD_* dal refactor del config, ma .env.example continuava
# a documentare i vecchi: chi li impostava non otteneva alcun effetto e la
# soglia restava al default, silenziosamente. Il nome storico viene quindi
# ancora onorato; config/validation.py lo segnala all'avvio, dove il logging
# e' gia' configurato.
_LEGACY_THRESHOLD_NAMES = {
    "ERMES_SCORE_THRESHOLD_LOW": "ERMES_SCORE_LOW",
    "ERMES_SCORE_THRESHOLD_MED": "ERMES_SCORE_MED",
    "ERMES_SCORE_THRESHOLD_HIGH": "ERMES_SCORE_HIGH",
}


def _threshold(name: str, default: str) -> float:
    raw = os.environ.get(name)
    if raw is None:
        raw = os.environ.get(_LEGACY_THRESHOLD_NAMES.get(name, ""), None)
    try:
        return float(raw) if raw is not None else float(default)
    except ValueError:
        return float(default)


@dataclass(frozen=True)
class RAGConfig:
    # ---------------------------------------------------------
    # RETRIEVAL
    # ---------------------------------------------------------
    SCORE_THRESHOLD_LOW: float = field(default_factory=lambda: _threshold("ERMES_SCORE_THRESHOLD_LOW", "0.35"))
    SCORE_THRESHOLD_MED: float = field(default_factory=lambda: _threshold("ERMES_SCORE_THRESHOLD_MED", "0.55"))
    SCORE_THRESHOLD_HIGH: float = field(default_factory=lambda: _threshold("ERMES_SCORE_THRESHOLD_HIGH", "0.75"))
    TOP_K_INITIAL: int = field(default_factory=lambda: int(os.environ.get("ERMES_TOP_K_INITIAL", "10")))
    TOP_K_FINAL: int = field(default_factory=lambda: int(os.environ.get("ERMES_TOP_K_FINAL", "3")))

    # ---------------------------------------------------------
    # EMBEDDING
    # ---------------------------------------------------------
    EMBEDDING_DIMENSION: int = field(default_factory=lambda: int(os.environ.get("ERMES_EMBEDDING_DIMENSION", "768")))
    EMBEDDING_BATCH_SIZE: int = field(default_factory=lambda: int(os.environ.get("ERMES_EMBEDDING_BATCH_SIZE", "32")))

    # ---------------------------------------------------------
    # CHUNKING
    # ---------------------------------------------------------
    # I default sono 900/140 perche' erano i valori cablati in
    # core/document_parser.py e realmente in vigore. Il config dichiarava
    # 1000/200 e non era letto da nessuno: collegarlo adottando quei numeri
    # avrebbe cambiato di straforo la dimensione dei chunk di ogni
    # installazione esistente, senza che nessuno l'avesse misurato.
    CHUNK_SIZE: int = field(default_factory=lambda: int(os.environ.get("ERMES_CHUNK_SIZE", "900")))
    CHUNK_OVERLAP: int = field(default_factory=lambda: int(os.environ.get("ERMES_CHUNK_OVERLAP", "140")))

    # ---------------------------------------------------------
    # ENTERPRISE RERANKER
    # ---------------------------------------------------------
    # Disattivato di default per una misura, non per una preferenza. Sul
    # golden set il reranker peggiora ogni configurazione, e il default che
    # veniva spedito (lessicale + reranker neurale) era la peggiore delle
    # due configurazioni lessicali: recall@3 0.815 contro 0.852, parafrasi
    # 0.375 contro 0.500. Riproducibile con
    # `python evaluation/run_library_eval.py --compare`; la tabella completa
    # e' in docs/RETRIEVAL_EVALUATION.md.
    # La funzionalita' resta disponibile: su un corpus reale, piu' grande e
    # meno sintetico di quello di prova, potrebbe comportarsi diversamente.
    # Va riattivata dopo averlo misurato, non prima.
    RERANKER_ENABLED: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_RERANKER_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
    )
    # ---------------------------------------------------------
    # VERIFICA DELL'EVIDENZA
    # ---------------------------------------------------------
    # Chiede a un modello se il passaggio recuperato risponda davvero alla
    # domanda, invece di fidarsi del solo punteggio di similarita'. E' l'unico
    # meccanismo misurato che migliora le parafrasi senza azzerare
    # l'astensione (vedi core/evidence_verifier.py per i numeri).
    # Spento di default: costa una chiamata al modello per passaggio, e nella
    # modalita' predefinita evidence_only un modello non c'e' per scelta.
    EVIDENCE_VERIFIER_ENABLED: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_EVIDENCE_VERIFIER", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
    )
    # Vuoto = usa ERMES_MODEL. Un modello piccolo basta: sul golden set
    # qwen3.5:4b e qwen3.5:9b danno lo stesso risultato.
    EVIDENCE_VERIFIER_MODEL: str = field(default_factory=lambda: os.environ.get("ERMES_EVIDENCE_VERIFIER_MODEL", ""))

    RERANKER_MIN_SCORE: float = field(default_factory=lambda: float(os.environ.get("ERMES_RERANKER_MIN_SCORE", "0.15")))
    RERANKER_MODEL: str = field(
        default_factory=lambda: os.environ.get("ERMES_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    )
    # Il reranking neurale (cross-encoder) richiede sentence-transformers:
    # se non installato o il modello non caricabile, si ripiega sul
    # reranker lessicale senza errori. Disattivabile con ERMES_RERANKER_NEURAL=0.
    RERANKER_NEURAL_ENABLED: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_RERANKER_NEURAL", "1").strip().lower() in {"1", "true", "yes", "on"}
        )
    )

    # ---------------------------------------------------------
    # HYDE (Hypothetical Document Embeddings)
    # ---------------------------------------------------------
    HYDE_ENABLED: bool = field(
        default_factory=lambda: os.environ.get("ERMES_HYDE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    )

    # ---------------------------------------------------------
    # RICERCA SEMANTICA LIBRERIE
    # ---------------------------------------------------------
    LIBRARY_SEMANTIC_SEARCH_ENABLED: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_LIBRARY_SEMANTIC_SEARCH", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
    )

    # ---------------------------------------------------------
    # ASSISTENTE LIBRERIE
    # ---------------------------------------------------------
    LIBRARY_ASSISTANT_MODE: str = field(
        default_factory=lambda: os.environ.get("ERMES_LIBRARY_ASSISTANT_MODE", "evidence_only").strip().lower()
    )

    # ---------------------------------------------------------
    # FEATURE FLAG LEGACY
    # ---------------------------------------------------------
    # La generazione formule richiede consenso esplicito via env.
    ENABLE_FORMULA_GENERATION: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_ENABLE_FORMULA_GENERATION", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
    )
    # Il modulo WinSarp è legacy rispetto al prodotto Ermes Knowledge.
    ENABLE_LEGACY_WINSARP: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_ENABLE_LEGACY_WINSARP", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
    )

    # ---------------------------------------------------------
    # SEMANTIC SEARCH CACHE
    # ---------------------------------------------------------
    # Cache L1 in-memory per risultati di search_with_profile. Evita di
    # ricalcolare embedding e retrieval per query identiche alla stessa
    # biblioteca quando non sono arrivati nuovi documenti.
    SEARCH_CACHE_ENABLED: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_SEARCH_CACHE_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        )
    )
    SEARCH_CACHE_TTL_SECONDS: float = field(
        default_factory=lambda: float(os.environ.get("ERMES_SEARCH_CACHE_TTL_SECONDS", "300"))
    )
    SEARCH_CACHE_MAX_ENTRIES: int = field(
        default_factory=lambda: int(os.environ.get("ERMES_SEARCH_CACHE_MAX_ENTRIES", "200"))
    )
