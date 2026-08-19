import time

from core.ai.response_cache import ResponseCache


class TestResponseCache:
    def test_miss_on_empty(self):
        cache = ResponseCache(max_entries=10, ttl_seconds=3600)
        result = cache.get("query", "model", "module")
        assert result is None

    def test_set_and_get(self):
        cache = ResponseCache(max_entries=10, ttl_seconds=3600)
        cache.set("q", "m", "mod", "response123", ["src1"], "high", 0.95)
        entry = cache.get("q", "m", "mod")
        assert entry is not None
        assert entry.response == "response123"
        assert entry.sources == ["src1"]
        assert entry.confidence == "high"
        assert entry.confidence_score == 0.95

    def test_different_query_misses(self):
        cache = ResponseCache(max_entries=10, ttl_seconds=3600)
        cache.set("q1", "m", "mod", "resp1", [], "high", 0.9)
        result = cache.get("q2", "m", "mod")
        assert result is None

    def test_ttl_expiry(self):
        cache = ResponseCache(max_entries=10, ttl_seconds=0)
        cache.set("q", "m", "mod", "resp", [], "high", 0.9)
        time.sleep(0.01)
        result = cache.get("q", "m", "mod")
        assert result is None

    def test_cache_stats(self):
        cache = ResponseCache(max_entries=10, ttl_seconds=3600)
        assert cache._hits == 0
        assert cache._misses == 0
        cache.get("q", "m", "mod")
        assert cache._misses == 1
        cache.set("q", "m", "mod", "r", [], "high", 0.9)
        cache.get("q", "m", "mod")
        assert cache._hits == 1

    def test_max_entries_eviction(self):
        cache = ResponseCache(max_entries=3, ttl_seconds=3600)
        for i in range(4):
            cache.set(f"q{i}", "m", "mod", f"r{i}", [], "low", 0.5)
        # The oldest entry should be evicted
        assert cache.get("q0", "m", "mod") is None
        # Most recent should still be there
        assert cache.get("q3", "m", "mod") is not None

    def test_lru_move_to_end(self):
        cache = ResponseCache(max_entries=3, ttl_seconds=3600)
        for i in range(3):
            cache.set(f"q{i}", "m", "mod", f"r{i}", [], "low", 0.5)
        # Access q0, making it most recently used
        cache.get("q0", "m", "mod")
        # Now add a new entry - q1 should be evicted (least recently used)
        cache.set("q3", "m", "mod", "r3", [], "low", 0.5)
        assert cache.get("q1", "m", "mod") is None
        assert cache.get("q0", "m", "mod") is not None

    def test_update_existing_key(self):
        cache = ResponseCache(max_entries=10, ttl_seconds=3600)
        cache.set("q", "m", "mod", "old", [], "low", 0.5)
        cache.set("q", "m", "mod", "new", ["src"], "high", 0.99)
        entry = cache.get("q", "m", "mod")
        assert entry.response == "new"
        assert entry.confidence_score == 0.99

    def test_model_specificity(self):
        cache = ResponseCache(max_entries=10, ttl_seconds=3600)
        cache.set("q", "model-a", "mod", "resp-a", [], "high", 0.9)
        result = cache.get("q", "model-b", "mod")
        assert result is None

    def test_module_specificity(self):
        cache = ResponseCache(max_entries=10, ttl_seconds=3600)
        cache.set("q", "m", "winsarp", "win-resp", [], "high", 0.9)
        result = cache.get("q", "m", "generic")
        assert result is None
