"""Cache semantica per query di ricerca Ermes Knowledge.

Memoizza i risultati di search_with_profile per query identiche alla stessa
biblioteca, evitando di ricalcolare embedding e retrieval quando non sono
arrivati nuovi documenti.

Invalidazione:
- Per libreria: se cambia il numero di documenti (nuovo upload o delete)
- Per TTL: scadenza configurabile (default 5 minuti)
- Manuale: invalidate(library_id) o invalidate_all()

Thread-safe, memory-bound (max configurabile), con hit/miss stats.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass

from config import cfg

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    """Una entry nella cache."""
    results: list[dict]
    profile: dict
    cached_at: float
    doc_count: int
    query_hash: str
    library_id: str


@dataclass
class CacheStats:
    """Statistiche della cache."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0


class SemanticSearchCache:
    """Cache L1 in-memory per risultati di search_with_profile."""

    def __init__(
        self,
        ttl_seconds: float | None = None,
        max_entries: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._ttl = ttl_seconds if ttl_seconds is not None else getattr(cfg, "SEARCH_CACHE_TTL_SECONDS", 300.0)
        self._max_entries = max_entries if max_entries is not None else getattr(cfg, "SEARCH_CACHE_MAX_ENTRIES", 200)
        self._enabled = enabled if enabled is not None else getattr(cfg, "SEARCH_CACHE_ENABLED", True)
        self._lock = threading.Lock()
        self._entries: dict[str, _CacheEntry] = {}
        self._library_index: dict[str, set[str]] = {}  # library_id -> set of keys
        self._stats = CacheStats()

    def _fingerprint(self, library_id: str, query: str, scope: str = "") -> str:
        """Crea un fingerprint normalizzato per query e scope (utente).

        Lo scope separa gli utenti in cache: quando una biblioteca applica
        ACL, due utenti con permessi diversi devono vedere risultati diversi,
        quindi non possono condividere la stessa entry. Scope vuoto = nessuna
        personalizzazione (usi anonimi/globali).
        """
        normalized = " ".join(query.lower().split())
        raw = f"{library_id}:{scope}:{normalized}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


    def get(self, library_id: str, query: str, current_doc_count: int, scope: str = "") -> tuple[list[dict], dict] | None:
        """Ritorna i risultati in cache se validi, altrimenti None."""
        if not self._enabled:
            return None

        key = self._fingerprint(library_id, query, scope)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._stats.misses += 1
                return None

            # Verifica TTL
            age = time.time() - entry.cached_at
            if age > self._ttl:
                self._evict_key(key)
                self._stats.misses += 1
                return None

            # Verifica che il numero di documenti non sia cambiato
            if entry.doc_count != current_doc_count:
                self._evict_key(key)
                self._stats.misses += 1
                return None

            self._stats.hits += 1
            return entry.results, entry.profile

    def put(self, library_id: str, query: str, current_doc_count: int, results: list[dict], profile: dict, scope: str = "") -> None:
        """Memoizza i risultati per la query."""
        if not self._enabled:
            return

        key = self._fingerprint(library_id, query, scope)
        with self._lock:
            # Evict oldest if at capacity
            if len(self._entries) >= self._max_entries and key not in self._entries:
                oldest_key = min(self._entries, key=lambda k: self._entries[k].cached_at)
                self._evict_key(oldest_key)

            self._entries[key] = _CacheEntry(
                results=results,
                profile=dict(profile),
                cached_at=time.time(),
                doc_count=current_doc_count,
                query_hash=key,
                library_id=library_id,
            )
            # Update library index
            self._library_index.setdefault(library_id, set()).add(key)

    def _evict_key(self, key: str) -> None:
        """Rimuove una entry e aggiorna l'indice."""
        entry = self._entries.pop(key, None)
        if entry is not None:
            lib_idx = self._library_index.get(entry.library_id)
            if lib_idx is not None:
                lib_idx.discard(key)
                if not lib_idx:
                    del self._library_index[entry.library_id]
            self._stats.evictions += 1

    def invalidate(self, library_id: str) -> int:
        """Invalida tutte le entry per una libreria."""
        with self._lock:
            keys = self._library_index.get(library_id, set()).copy()
            for k in keys:
                self._evict_key(k)
            return len(keys)

    def invalidate_all(self) -> None:
        """Pulisce tutta la cache."""
        with self._lock:
            n = len(self._entries)
            self._entries.clear()
            self._library_index.clear()
            self._stats.evictions += n

    @property
    def stats(self) -> dict:
        """Ritorna le statistiche della cache."""
        with self._lock:
            total = self._stats.hits + self._stats.misses
            return {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "evictions": self._stats.evictions,
                "size": len(self._entries),
                "hit_rate": self._stats.hits / max(1, total),
            }


# Istanza globale (singleton)
_global_cache: SemanticSearchCache | None = None
_global_cache_lock = threading.Lock()


def get_search_cache() -> SemanticSearchCache:
    """Ritorna l'istanza globale della cache (lazy initialization)."""
    global _global_cache
    if _global_cache is None:
        with _global_cache_lock:
            if _global_cache is None:
                _global_cache = SemanticSearchCache()
    return _global_cache


def reset_search_cache() -> None:
    """Resetta la cache globale (per test)."""
    global _global_cache
    with _global_cache_lock:
        if _global_cache is not None:
            _global_cache.invalidate_all()
