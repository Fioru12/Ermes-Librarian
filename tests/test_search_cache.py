"""Test per la cache semantica di ricerca."""
import time

import pytest

from core.search_cache import (
    SemanticSearchCache,
    reset_search_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_search_cache()
    yield
    reset_search_cache()


class TestSemanticSearchCache:
    def test_miss_returns_none(self):
        cache = SemanticSearchCache()
        result = cache.get("lib-1", "query test", 5)
        assert result is None

    def test_hit_after_put(self):
        cache = SemanticSearchCache()
        results = [{"id": "r1", "score": 0.9}]
        profile = {"mode": "keyword"}
        cache.put("lib-1", "query test", 5, results, profile)

        cached = cache.get("lib-1", "query test", 5)
        assert cached is not None
        assert cached[0] == results
        assert cached[1] == profile

    def test_invalidation_on_doc_count_change(self):
        cache = SemanticSearchCache()
        cache.put("lib-1", "query", 5, [{"id": "r1"}], {"mode": "keyword"})

        # Same query, same doc_count -> hit
        assert cache.get("lib-1", "query", 5) is not None

        # Doc count changed -> miss (invalidated)
        assert cache.get("lib-1", "query", 6) is None

    def test_ttl_expiration(self):
        cache = SemanticSearchCache(ttl_seconds=0.1)
        cache.put("lib-1", "query", 1, [{"id": "r1"}], {"mode": "keyword"})
        assert cache.get("lib-1", "query", 1) is not None

        time.sleep(0.15)
        assert cache.get("lib-1", "query", 1) is None

    def test_invalidate_library(self):
        cache = SemanticSearchCache()
        cache.put("lib-1", "query1", 1, [{"id": "r1"}], {})
        cache.put("lib-1", "query2", 1, [{"id": "r2"}], {})
        cache.put("lib-2", "query1", 1, [{"id": "r3"}], {})

        removed = cache.invalidate("lib-1")
        assert removed == 2
        assert cache.get("lib-1", "query1", 1) is None
        assert cache.get("lib-2", "query1", 1) is not None

    def test_max_entries_eviction(self):
        cache = SemanticSearchCache(max_entries=3)
        for i in range(5):
            cache.put("lib-1", f"query{i}", 1, [{"id": f"r{i}"}], {})

        stats = cache.stats
        assert stats["size"] <= 3
        assert stats["evictions"] == 2

    def test_disabled_cache(self):
        cache = SemanticSearchCache(enabled=False)
        cache.put("lib-1", "query", 1, [{"id": "r1"}], {})
        assert cache.get("lib-1", "query", 1) is None

    def test_stats(self):
        cache = SemanticSearchCache()
        cache.put("lib-1", "query", 1, [{"id": "r1"}], {})

        cache.get("lib-1", "query", 1)  # hit
        cache.get("lib-1", "query", 1)  # hit
        cache.get("lib-1", "missing", 1)  # miss

        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 2 / 3

    def test_case_insensitive_fingerprint(self):
        cache = SemanticSearchCache()
        cache.put("lib-1", "Query Test", 1, [{"id": "r1"}], {})

        # Different case, same normalized query -> hit
        assert cache.get("lib-1", "query test", 1) is not None
        assert cache.get("lib-1", "  QUERY   TEST  ", 1) is not None

    def test_different_libraries_isolated(self):
        cache = SemanticSearchCache()
        cache.put("lib-1", "query", 1, [{"id": "r1"}], {})
        cache.put("lib-2", "query", 1, [{"id": "r2"}], {})

        r1 = cache.get("lib-1", "query", 1)
        r2 = cache.get("lib-2", "query", 1)
        assert r1[0][0]["id"] == "r1"
        assert r2[0][0]["id"] == "r2"

    def test_same_query_different_scope_isolated(self):
        """Regressione: due utenti con ACL diverse non possono condividere
        la stessa entry di cache, altrimenti chi vede di meno contagia chi
        vede di più (falso negativo) e viceversa (leak)."""
        cache = SemanticSearchCache()
        cache.put("lib-1", "stipendi", 3, [{"id": "doc-bob"}], {}, scope="bob")
        cache.put("lib-1", "stipendi", 3, [{"id": "doc-carol"}], {}, scope="carol")

        assert cache.get("lib-1", "stipendi", 3, scope="bob")[0][0]["id"] == "doc-bob"
        assert cache.get("lib-1", "stipendi", 3, scope="carol")[0][0]["id"] == "doc-carol"
        # scope anonimo vuoto non collima con nessuno dei due
        assert cache.get("lib-1", "stipendi", 3) is None

    def test_scope_backward_compatible_default(self):
        """Il default scope vuoto (nessuna personalizzazione) resta coerente
        con la signature storica senza scope."""
        cache = SemanticSearchCache()
        cache.put("lib-1", "query", 1, [{"id": "r1"}], {})
        assert cache.get("lib-1", "query", 1) is not None
        assert cache.get("lib-1", "query", 1, scope="") is not None
