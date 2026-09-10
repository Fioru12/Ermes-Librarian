"""
conftest.py
Fixtures e configurazione pytest per il progetto Ermes.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gc
import json
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import pytest

from core.rate_limiter import RateLimitConfig, RateLimiter


# ── Marker per test LLM-dipendenti ──
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "llm: mark test as LLM-dependent (requires Ollama or OpenRouter). Use --llm to run, or skip by default.",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--llm",
        action="store_true",
        default=False,
        help="Run LLM-dependent tests (skipped by default)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip LLM tests unless --llm flag is passed."""
    if config.getoption("--llm"):
        return  # run all tests
    skip_llm = pytest.mark.skip(reason="Use --llm to run LLM-dependent tests")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip_llm)


# ── Fixtures ──


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    tmp = Path(tempfile.mkdtemp())
    yield tmp
    gc.collect()
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def rate_limiter() -> RateLimiter:
    cfg = RateLimitConfig(
        max_requests_per_minute=10,
        max_uploads_per_hour=3,
        max_upload_mb_per_hour=50,
    )
    limiter = RateLimiter(cfg)
    limiter.reset()
    return limiter


@pytest.fixture
def sample_env(temp_dir: Path) -> Generator[dict, None, None]:
    """Fixture che imposta variabili d'ambiente per test isolati."""
    env = {
        "ERMES_PORT": "8502",
        "ERMES_HOST": "127.0.0.1",
        "OLLAMA_HOST": "http://127.0.0.1:11434",
        "ERMES_MODEL": "test-model",
        "ERMES_EMBED_MODEL": "test-embed",
        "ERMES_ENABLE_FORMULA_GENERATION": "1",
        "ERMES_API_KEY": "",
        "ERMES_ADMIN_USERNAME": "admin",
        "ERMES_ADMIN_PASSWORD": "test-pass",
        "ERMES_BASE_DIR": str(temp_dir),
    }
    old = {k: os.environ.get(k) for k in env}
    for k, v in env.items():
        os.environ[k] = v
    yield env
    for k in env:
        old_val = old.get(k)
        if old_val is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = old_val


@pytest.fixture
def temp_catalogo(temp_dir: Path) -> Generator[Path, None, None]:
    """
    Crea un catalogo WinSarp temporaneo per test isolati.
    Non tocca il catalogo reale (WinSarp_Formule.txt).
    """
    cat_path = temp_dir / "catalogo_test.txt"
    cat_path.write_text(
        """## [1](#1) | Formula Test | Inizio Giornata | inizio
**Scopo:** Formula di test
```
( 800 = '1' )
VF
```
""",
        encoding="utf-8",
    )
    yield cat_path


@pytest.fixture
def golden_set() -> list[dict[str, Any]]:
    """Carica il golden set di valutazione."""
    gs_path = Path(__file__).parent.parent / "evaluation" / "gold_set.json"
    if not gs_path.exists():
        pytest.skip("gold_set.json non trovato")
    with open(gs_path, encoding="utf-8") as f:
        data = json.load(f)
        return cast(list[dict[str, Any]], data)


# ── Provider OIDC simulato ──
#
# Esiste perche' la verifica della firma in core/oidc_keys.py e' reale. I test
# che "simulavano OIDC" costruendo token non firmati non stavano verificando
# l'integrazione: stavano asserendo il bypass che quella verifica ha chiuso.
# Un token di test deve essere firmato come lo firmerebbe un provider vero.

_TEST_OIDC_KEY = None


def _test_oidc_key():
    """Chiave RSA di test, generata una volta sola (2048 bit non sono gratis)."""
    global _TEST_OIDC_KEY
    if _TEST_OIDC_KEY is None:
        from cryptography.hazmat.primitives.asymmetric import rsa

        _TEST_OIDC_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return _TEST_OIDC_KEY


class FakeOidcProvider:
    """Emette token firmati e pubblica il JWKS corrispondente, senza rete."""

    kid = "chiave-di-test"

    def __init__(self, monkeypatch):
        self._monkeypatch = monkeypatch
        self.key = _test_oidc_key()
        self.cfg = None

    def _jwks(self) -> dict:
        import jwt

        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update({"kid": self.kid, "use": "sig", "alg": "RS256"})
        return {"keys": [jwk]}

    def install(self, test_cfg):
        """Fa credere a core/oidc_keys.py che questo sia il provider configurato."""
        import core.oidc_keys as keys

        published = self._jwks()

        def fake_get(url, timeout=None):
            return type(
                "_Response",
                (),
                {"raise_for_status": lambda self: None, "json": lambda self: published},
            )()

        self._monkeypatch.setattr(
            keys, "httpx", type("_Httpx", (), {"get": staticmethod(fake_get), "HTTPError": Exception})
        )
        self._monkeypatch.setattr(keys, "cfg", test_cfg)
        keys.reset_key_cache()
        self.cfg = test_cfg
        return test_cfg

    def sign(self, claims: dict, *, algorithm: str = "RS256", kid: str | None = None) -> str:
        import jwt

        return jwt.encode(claims, self.key, algorithm=algorithm, headers={"kid": kid or self.kid})


@pytest.fixture
def oidc_provider(monkeypatch):
    provider = FakeOidcProvider(monkeypatch)
    yield provider
    import core.oidc_keys as keys

    keys.reset_key_cache()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Azzera il limitatore fra un test e l'altro.

    Il limitatore e' un singleton di modulo: senza questo, le richieste di
    tutti i test si sommerebbero sullo stesso identificativo e prima o poi un
    test fallirebbe con 429 per colpa dei precedenti. E' isolamento fra test,
    non disattivazione della protezione: le rotte restano limitate, e
    tests/test_rate_limiting_applied.py lo verifica.
    """
    from core.rate_limiter import get_rate_limiter

    get_rate_limiter().reset()
    yield
    get_rate_limiter().reset()


@pytest.fixture(autouse=True)
def reset_pii_config():
    """Azzera la configurazione PII fra un test e l'altro.

    `core/pii_filter.py` la tiene in una variabile di modulo: un test che
    cambia le regole le lasciava cambiate per tutti i successivi. Il sintomo
    era subdolo — test_pii_filtering e test_dlp_detect_pii passavano da soli e
    fallivano nella suite completa — e dipendeva dall'ordine di esecuzione,
    quindi aggiungere un file di test in un'area non correlata bastava a far
    diventare rossa la suite.
    """
    from core.pii_filter import reset_pii_config_cache

    reset_pii_config_cache()
    yield
    reset_pii_config_cache()
