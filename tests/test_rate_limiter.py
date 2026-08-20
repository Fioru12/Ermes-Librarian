import time

from core.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_initial_allowed(self, rate_limiter: RateLimiter):
        ok, reason = rate_limiter.check_request_rate("test-user")
        assert ok is True
        assert reason == ""

    def test_rate_limit_exceeded(self, rate_limiter: RateLimiter):
        for _ in range(10):
            rate_limiter.check_request_rate("spammer")
        ok, reason = rate_limiter.check_request_rate("spammer")
        assert ok is False
        assert "Rate limit" in reason

    def test_different_identifiers_independent(self, rate_limiter: RateLimiter):
        for _ in range(10):
            rate_limiter.check_request_rate("user-a")
        ok_a, _ = rate_limiter.check_request_rate("user-a")
        assert ok_a is False
        ok_b, _ = rate_limiter.check_request_rate("user-b")
        assert ok_b is True

    def test_reset_single_identifier(self, rate_limiter: RateLimiter):
        for _ in range(10):
            rate_limiter.check_request_rate("reset-me")
        rate_limiter.reset("reset-me")
        ok, _ = rate_limiter.check_request_rate("reset-me")
        assert ok is True

    def test_reset_all(self, rate_limiter: RateLimiter):
        for _ in range(10):
            rate_limiter.check_request_rate("u1")
            rate_limiter.check_request_rate("u2")
        rate_limiter.reset()
        assert rate_limiter.check_request_rate("u1")[0] is True
        assert rate_limiter.check_request_rate("u2")[0] is True


class TestUploadRate:
    def test_upload_allowed(self, rate_limiter: RateLimiter):
        ok, reason = rate_limiter.check_upload_rate("uploader", 1.0)
        assert ok is True
        assert reason == ""

    def test_upload_count_exceeded(self, rate_limiter: RateLimiter):
        for _ in range(3):
            rate_limiter.check_upload_rate("bulk", 1.0)
        ok, reason = rate_limiter.check_upload_rate("bulk", 1.0)
        assert ok is False
        assert "Upload limit" in reason

    def test_upload_size_exceeded(self, rate_limiter: RateLimiter):
        rate_limiter.config.max_upload_mb_per_hour = 10
        ok, _ = rate_limiter.check_upload_rate("big", 8.0)
        assert ok is True
        ok, reason = rate_limiter.check_upload_rate("big", 5.0)
        assert ok is False
        assert "Upload size limit" in reason

    def test_get_upload_status(self, rate_limiter: RateLimiter):
        rate_limiter.check_upload_rate("monitored", 2.5)
        status = rate_limiter.get_upload_status("monitored")
        assert status["upload_count"] == 1
        assert status["total_size_mb"] == 2.5


class TestCleanup:
    def test_cleanup_old_entries_removes_stale(self, rate_limiter: RateLimiter):
        timestamps = [time.time() - 120, time.time() - 10]
        cleaned = rate_limiter._cleanup_old_entries(timestamps, 60)
        assert len(cleaned) == 1

    def test_cleanup_keeps_recent(self, rate_limiter: RateLimiter):
        now = time.time()
        cleaned = rate_limiter._cleanup_old_entries([now - 5, now], 60)
        assert len(cleaned) == 2
