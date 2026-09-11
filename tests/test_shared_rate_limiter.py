"""Il limitatore di frequenza conta fra le istanze, non per processo.

T8 dichiarava: "i contatori sono per processo, quindi piu' istanze
moltiplicano ogni soglia". Qui due limitatori distinti — l'equivalente di due
processi dietro un bilanciatore — condividono l'archivio e vedono lo stesso
conteggio. Il contatore in memoria, tenuto come alternativa esplicita, e' il
controllo negativo: due istanze sue non si vedono, ed e' esattamente il
difetto.
"""

import pytest

import config
from core.rate_limiter import RateLimitConfig, RateLimiter, get_rate_limiter
from core.shared_rate_limiter import SharedRateLimiter


@pytest.fixture
def archivio(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(BASE_DIR=str(app_dir), DATABASE_URL="")
    monkeypatch.setattr(config, "cfg", test_cfg)
    return test_cfg


def test_two_shared_instances_see_the_same_count(archivio):
    prima = SharedRateLimiter(RateLimitConfig(max_requests_per_minute=3))
    seconda = SharedRateLimiter(RateLimitConfig(max_requests_per_minute=3))

    assert prima.check_request_rate("user:anna")[0]
    assert seconda.check_request_rate("user:anna")[0]
    assert prima.check_request_rate("user:anna")[0]

    consentito, motivo = seconda.check_request_rate("user:anna")
    assert consentito is False, "la quarta richiesta, dall'altra istanza, deve essere rifiutata"
    assert "3 richieste" in motivo


def test_two_memory_instances_do_not_see_each_other(archivio):
    """Il controllo negativo: e' il comportamento che T8 dichiarava."""
    prima = RateLimiter(RateLimitConfig(max_requests_per_minute=3))
    seconda = RateLimiter(RateLimitConfig(max_requests_per_minute=3))
    for _ in range(3):
        prima.check_request_rate("user:anna")

    assert seconda.check_request_rate("user:anna")[0] is True, "in memoria ogni istanza ha la propria quota"


def test_upload_limits_are_shared_too(archivio):
    prima = SharedRateLimiter(RateLimitConfig(max_uploads_per_hour=2, max_upload_mb_per_hour=10))
    seconda = SharedRateLimiter(RateLimitConfig(max_uploads_per_hour=2, max_upload_mb_per_hour=10))

    assert prima.check_upload_rate("user:anna", 4.0)[0]
    assert seconda.check_upload_rate("user:anna", 4.0)[0]
    consentito, motivo = prima.check_upload_rate("user:anna", 1.0)

    assert consentito is False
    assert "2 upload" in motivo
    assert seconda.get_upload_status("user:anna")["upload_count"] == 2


def test_a_dedicated_quota_overrides_the_global_one(archivio):
    limiter = SharedRateLimiter(RateLimitConfig(max_requests_per_minute=100))

    for _ in range(2):
        assert limiter.check_request_rate("chat:telegram:1", max_per_minute=2)[0]

    assert limiter.check_request_rate("chat:telegram:1", max_per_minute=2)[0] is False


def test_reset_clears_for_every_instance(archivio):
    prima = SharedRateLimiter(RateLimitConfig(max_requests_per_minute=1))
    seconda = SharedRateLimiter(RateLimitConfig(max_requests_per_minute=1))
    prima.check_request_rate("user:anna")
    assert seconda.check_request_rate("user:anna")[0] is False

    prima.reset("user:anna")

    assert seconda.check_request_rate("user:anna")[0] is True


def test_the_application_uses_the_shared_one_by_default(archivio, monkeypatch):
    monkeypatch.setattr(config, "cfg", archivio.replace(RATE_LIMIT_BACKEND="shared"))
    assert isinstance(get_rate_limiter(), SharedRateLimiter)

    monkeypatch.setattr(config, "cfg", archivio.replace(RATE_LIMIT_BACKEND="memory"))
    assert isinstance(get_rate_limiter(), RateLimiter)
