"""
conftest.py
Fixtures e configurazione pytest per il progetto Ermes.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from core.rate_limiter import RateLimiter, RateLimitConfig


# ── Marker per test LLM-dipendenti ──
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "llm: mark test as LLM-dependent (requires Ollama or OpenRouter). "
        "Use --llm to run, or skip by default.",
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
        if old.get(k) is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = old[k]


@pytest.fixture
def temp_catalogo(temp_dir: Path) -> Generator[Path, None, None]:
    """
    Crea un catalogo WinSarp temporaneo per test isolati.
    Non tocca il catalogo reale (WinSarp_Formule.txt).
    """
    cat_path = temp_dir / "catalogo_test.txt"
    cat_path.write_text("""## [1](#1) | Formula Test | Inizio Giornata | inizio
**Scopo:** Formula di test
```
( 800 = '1' )
VF
```
""", encoding="utf-8")
    yield cat_path


@pytest.fixture
def golden_set() -> list[dict]:
    """Carica il golden set di valutazione."""
    gs_path = Path(__file__).parent.parent / "evaluation" / "gold_set.json"
    if not gs_path.exists():
        pytest.skip("gold_set.json non trovato")
    with open(gs_path, encoding="utf-8") as f:
        return json.load(f)