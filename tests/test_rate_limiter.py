"""
test_rate_limiter.py
Test unitari per il rate limiter.
"""
import pytest

from core.rate_limiter import RateLimitConfig, RateLimiter


class TestRateLimiter:
    """Test per la classe RateLimiter."""

    def test_init_default_config(self):
        """Test inizializzazione con configurazione di default."""
        limiter = RateLimiter()
        assert limiter.config.max_requests_per_minute == 60
        assert limiter.config.max_uploads_per_hour == 20
        assert limiter.config.max_upload_mb_per_hour == 500

    def test_init_custom_config(self):
        """Test inizializzazione con configurazione personalizzata."""
        config = RateLimitConfig(
            max_requests_per_minute=10,
            max_uploads_per_hour=5,
            max_upload_mb_per_hour=100
        )
        limiter = RateLimiter(config)
        assert limiter.config.max_requests_per_minute == 10
        assert limiter.config.max_uploads_per_hour == 5
        assert limiter.config.max_upload_mb_per_hour == 100

    def test_check_request_rate_allowed(self):
        """Test che le richieste entro il limite sono permesse."""
        config = RateLimitConfig(max_requests_per_minute=5)
        limiter = RateLimiter(config)

        # Prime 5 richieste dovrebbero essere permesse
        for i in range(5):
            allowed, reason = limiter.check_request_rate("test_user")
            assert allowed, f"Richiesta {i+1} dovrebbe essere permessa"
            assert reason == ""

    def test_check_request_rate_exceeded(self):
        """Test che le richieste oltre il limite sono bloccate."""
        config = RateLimitConfig(max_requests_per_minute=3)
        limiter = RateLimiter(config)

        # Prime 3 richieste permesse
        for i in range(3):
            allowed, _ = limiter.check_request_rate("test_user")
            assert allowed

        # 4a richiesta dovrebbe essere bloccata
        allowed, reason = limiter.check_request_rate("test_user")
        assert not allowed
        assert "Rate limit" in reason

    def test_check_request_rate_different_identifiers(self):
        """Test che identificatori diversi hanno contatori separati."""
        config = RateLimitConfig(max_requests_per_minute=2)
        limiter = RateLimiter(config)

        # User1 fa 2 richieste
        allowed, _ = limiter.check_request_rate("user1")
        assert allowed
        allowed, _ = limiter.check_request_rate("user1")
        assert allowed

        # User1 bloccato
        allowed, _ = limiter.check_request_rate("user1")
        assert not allowed

        # User2 può ancora fare richieste
        allowed, _ = limiter.check_request_rate("user2")
        assert allowed

    def test_check_upload_rate_allowed(self):
        """Test che gli upload entro il limite sono permessi."""
        config = RateLimitConfig(max_uploads_per_hour=5, max_upload_mb_per_hour=100)
        limiter = RateLimiter(config)

        # Upload di 20MB dovrebbe essere permesso
        allowed, reason = limiter.check_upload_rate("test_user", 20.0)
        assert allowed
        assert reason == ""

    def test_check_upload_rate_size_exceeded(self):
        """Test che gli upload che superano la dimensione massima sono bloccati."""
        config = RateLimitConfig(max_uploads_per_hour=10, max_upload_mb_per_hour=50)
        limiter = RateLimiter(config)

        # Upload di 60MB dovrebbe essere bloccato
        allowed, reason = limiter.check_upload_rate("test_user", 60.0)
        assert not allowed
        assert "size limit" in reason

    def test_check_upload_rate_count_exceeded(self):
        """Test che gli upload che superano il numero massimo sono bloccati."""
        config = RateLimitConfig(max_uploads_per_hour=2, max_upload_mb_per_hour=1000)
        limiter = RateLimiter(config)

        # Primi 2 upload permessi
        allowed, _ = limiter.check_upload_rate("test_user", 10.0)
        assert allowed
        allowed, _ = limiter.check_upload_rate("test_user", 10.0)
        assert allowed

        # 3o upload bloccato
        allowed, reason = limiter.check_upload_rate("test_user", 10.0)
        assert not allowed
        assert "Upload limit" in reason

    def test_reset_identifier(self):
        """Test reset dei contatori per un identificatore specifico."""
        config = RateLimitConfig(max_requests_per_minute=1)
        limiter = RateLimiter(config)

        # Blocca l'utente
        limiter.check_request_rate("test_user")
        allowed, _ = limiter.check_request_rate("test_user")
        assert not allowed

        # Reset dell'utente
        limiter.reset("test_user")

        # Ora dovrebbe poter fare richieste di nuovo
        allowed, _ = limiter.check_request_rate("test_user")
        assert allowed

    def test_reset_all(self):
        """Test reset di tutti i contatori."""
        config = RateLimitConfig(max_requests_per_minute=1)
        limiter = RateLimiter(config)

        # Blocca entrambi gli utenti
        limiter.check_request_rate("user1")
        limiter.check_request_rate("user2")
        limiter.check_request_rate("user1")  # user1 bloccato
        limiter.check_request_rate("user2")  # user2 bloccato

        # Reset totale
        limiter.reset()

        # Entrambi dovrebbero poter fare richieste
        allowed, _ = limiter.check_request_rate("user1")
        assert allowed
        allowed, _ = limiter.check_request_rate("user2")
        assert allowed

    def test_get_upload_status(self):
        """Test che get_upload_status restituisce informazioni corrette."""
        config = RateLimitConfig(max_uploads_per_hour=10, max_upload_mb_per_hour=100)
        limiter = RateLimiter(config)

        # Nessun upload inizialmente
        status = limiter.get_upload_status("test_user")
        assert status["upload_count"] == 0
        assert status["total_size_mb"] == 0.0
        assert status["max_uploads"] == 10
        assert status["max_size_mb"] == 100.0

        # Dopo un upload
        limiter.check_upload_rate("test_user", 25.0)
        status = limiter.get_upload_status("test_user")
        assert status["upload_count"] == 1
        assert status["total_size_mb"] == 25.0


class TestRateLimitConfig:
    """Test per la classe RateLimitConfig."""

    def test_default_values(self):
        """Test che i valori di default sono corretti."""
        config = RateLimitConfig()
        assert config.max_requests_per_minute == 60
        assert config.max_uploads_per_hour == 20
        assert config.max_upload_mb_per_hour == 500
        assert config.cleanup_interval_seconds == 3600


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
