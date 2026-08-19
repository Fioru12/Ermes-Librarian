"""
response_cache.py
Cache LRU con TTL per risposte RAG.
Stessa query + stesso modello + stesso modulo = risposta cachata (istantanea).
"""
import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Singola entry nella cache."""
    response: str
    sources: list
    confidence: str
    confidence_score: float
    model: str
    module: str
    created_at: float
    hit_count: int = 0


class ResponseCache:
    """
    Cache LRU con TTL per risposte RAG.

    - Chiave: hash(query + model + module)
    - TTL: 1 ora (configurabile)
    - Max entries: 500 (configurabile)
    - Thread-safe
    """

    def __init__(self, max_entries: int = 500, ttl_seconds: int = 3600):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _prompt_version() -> str:
        """Hash dei prompt attivi per invalidare cache quando cambiano."""
        try:
            from legacy_winsarp.modules.winsarp.prompts import PROMPT_WINSARP, PROMPT_WINSARP_GENERAZIONE
            raw = PROMPT_WINSARP + PROMPT_WINSARP_GENERAZIONE
            return hashlib.sha256(raw.encode()).hexdigest()[:8]
        except Exception:
            return "v0"

    def _make_key(self, query: str, model: str, module: str) -> str:
        """Genera chiave di cache univoca."""
        raw = f"{self._prompt_version()}|{query.strip().lower()}|{model}|{module}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Verifica se un'entry è scaduta."""
        return (time.time() - entry.created_at) > self.ttl_seconds

    def _evict_expired(self):
        """Rimuove tutte le entry scadute."""
        expired = [
            key for key, entry in self._cache.items()
            if self._is_expired(entry)
        ]
        for key in expired:
            del self._cache[key]
        if expired:
            _logger.debug("Cache: rimosse %d entry scadute", len(expired))

    def get(self, query: str, model: str, module: str) -> CacheEntry | None:
        """
        Cerca una risposta nella cache.
        Ritorna CacheEntry se trovata e non scaduta, None altrimenti.
        """
        key = self._make_key(query, model, module)

        with self._lock:
            self._evict_expired()

            if key in self._cache:
                entry = self._cache[key]
                if not self._is_expired(entry):
                    entry.hit_count += 1
                    self._hits += 1
                    # Sposta in fondo (LRU: più usato = meno cancellato)
                    self._cache.move_to_end(key)
                    _logger.debug("Cache HIT per query: %s", query[:50])
                    return entry
                else:
                    del self._cache[key]

            self._misses += 1
            _logger.debug("Cache MISS per query: %s", query[:50])
            return None

    def set(self, query: str, model: str, module: str,
            response: str, sources: list, confidence: str,
            confidence_score: float):
        """Inserisce una risposta nella cache."""
        key = self._make_key(query, model, module)

        with self._lock:
            # Se la chiave esiste, aggiorna
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key].response = response
                self._cache[key].sources = sources
                self._cache[key].confidence = confidence
                self._cache[key].confidence_score = confidence_score
                self._cache[key].created_at = time.time()
                return

            # Se la cache è piena, rimuovi il meno usato
            if len(self._cache) >= self.max_entries:
                self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(
                response=response,
                sources=sources,
                confidence=confidence,
                confidence_score=confidence_score,
                model=model,
                module=module,
                created_at=time.time(),
            )
            _logger.debug("Cache SET per query: %s", query[:50])

    def invalidate(self, query: str = None, model: str = None, module: str = None):
        """Invalida entries dalla cache."""
        with self._lock:
            if query and model and module:
                key = self._make_key(query, model, module)
                self._cache.pop(key, None)
            elif module:
                keys_to_remove = [
                    k for k, v in self._cache.items()
                    if v.module == module
                ]
                for k in keys_to_remove:
                    del self._cache[k]
            else:
                self._cache.clear()
            _logger.info("Cache invalidata (module=%s)", module)

    def stats(self) -> dict:
        """Statistiche della cache."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._cache),
                "max_entries": self.max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0,
                "ttl_seconds": self.ttl_seconds,
                "total_queries": total,
            }

    def clear(self):
        """Svuota completamente la cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            _logger.info("Cache svuotata")


# Istanza globale
_response_cache = ResponseCache()


def get_response_cache() -> ResponseCache:
    """Ritorna l'istanza globale della cache."""
    return _response_cache
