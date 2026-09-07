"""
config/rag.py
Configurazione RAG: retrieval, reranker, embedding, chunking.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RAGConfig:
    # ---------------------------------------------------------
    # RETRIEVAL
    # ---------------------------------------------------------
    SCORE_THRESHOLD_LOW: float = field(
        default_factory=lambda: float(os.environ.get("ERMES_SCORE_THRESHOLD_LOW", "0.35"))
    )
    SCORE_THRESHOLD_MED: float = field(
        default_factory=lambda: float(os.environ.get("ERMES_SCORE_THRESHOLD_MED", "0.55"))
    )
    SCORE_THRESHOLD_HIGH: float = field(
        default_factory=lambda: float(os.environ.get("ERMES_SCORE_THRESHOLD_HIGH", "0.75"))
    )
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
    CHUNK_SIZE: int = field(default_factory=lambda: int(os.environ.get("ERMES_CHUNK_SIZE", "1000")))
    CHUNK_OVERLAP: int = field(default_factory=lambda: int(os.environ.get("ERMES_CHUNK_OVERLAP", "200")))

    # ---------------------------------------------------------
    # ENTERPRISE RERANKER
    # ---------------------------------------------------------
    RERANKER_ENABLED: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_RERANKER_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        )
    )
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
