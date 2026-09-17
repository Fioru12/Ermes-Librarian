"""Ogni variabile che docker-compose.yml passa al container deve essere letta.

`tests/test_env_example_matches_config.py` controlla `.env.example`, ma solo
le variabili `ERMES_*`. Le tre che non lo sono — `OLLAMA_HOST`,
`OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` — erano scritte da compose,
.env.example e CI con quel nome e lette dal config con il prefisso `ERMES_`:
in container Ollama puntava a localhost invece che al servizio `ollama`, e la
chiave OpenRouter nel .env non arrivava mai. Nessuno lo segnalava, perche'
senza modello la modalita' predefinita evidence_only e' "healthy" comunque.

Questo test legge il compose come documentazione eseguibile: ogni nome nel
blocco `environment` di `app` deve comparire in una `os.environ.get(...)` di
`config/` — con quel nome esatto, prefissato o no. Le variabili destinate ad
altri servizi (postgres, langfuse) sono escluse esplicitamente.
"""

import os
import re
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]

# Passate ad `app` ma consumate da un altro servizio o da una libreria che
# legge l'ambiente da sola. Ognuna con la ragione.
_NON_LETTE_DAL_CONFIG = {
    "POSTGRES_USER": "usata dal servizio postgres, non dall'app",
    "POSTGRES_PASSWORD": "come POSTGRES_USER",
    "POSTGRES_DB": "come POSTGRES_USER",
}


def _variabili_passate_ad_app() -> set[str]:
    testo = (RADICE / "docker-compose.yml").read_text(encoding="utf-8")
    blocco = testo.split("\n  app:\n", 1)[1].split("\n  postgres:\n", 1)[0]
    return {m.group(1) for m in re.finditer(r"^\s+- ([A-Z][A-Z0-9_]+)=", blocco, re.MULTILINE)}


def _variabili_lette_dal_config() -> set[str]:
    lette: set[str] = set()
    for percorso in (RADICE / "config").glob("*.py"):
        lette |= set(re.findall(r'"([A-Z][A-Z0-9_]+)"', percorso.read_text(encoding="utf-8")))
    return lette


def test_every_compose_variable_reaches_config():
    fantasma = sorted(_variabili_passate_ad_app() - _variabili_lette_dal_config() - set(_NON_LETTE_DAL_CONFIG))
    assert fantasma == [], (
        "docker-compose.yml passa al container variabili che config/ non legge con quel nome: "
        + ", ".join(fantasma)
        + ". In container l'impostazione non ha effetto e nulla lo segnala."
    )


@pytest.mark.parametrize(
    ("prefissata", "storica", "valore"),
    [
        ("ERMES_OLLAMA_HOST", "OLLAMA_HOST", "http://ollama:11434"),
        ("ERMES_OPENROUTER_API_KEY", "OPENROUTER_API_KEY", "sk-or-test"),
        ("ERMES_OPENROUTER_BASE_URL", "OPENROUTER_BASE_URL", "https://gateway.example/v1"),
    ],
)
def test_plain_name_is_honoured_and_prefixed_name_wins(monkeypatch, prefissata, storica, valore):
    from config.integrations import IntegrationsConfig

    monkeypatch.delenv(prefissata, raising=False)
    monkeypatch.setenv(storica, valore)
    assert getattr(IntegrationsConfig(), prefissata.removeprefix("ERMES_")) == valore

    monkeypatch.setenv(prefissata, valore + "-prefissato")
    assert getattr(IntegrationsConfig(), prefissata.removeprefix("ERMES_")) == valore + "-prefissato"

    assert os.environ[storica] == valore  # il nome storico non viene toccato
