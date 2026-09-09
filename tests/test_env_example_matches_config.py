"""`.env.example` promette solo variabili che il codice legge davvero.

Questa classe di difetto si e' presentata tre volte in questo progetto:

- `ERMES_SCORE_LOW` / `ERMES_SCORE_MED`, rinominate dal refactor del config e
  rimaste documentate col vecchio nome: chi le impostava non cambiava niente;
- `ERMES_MODEL` ed `ERMES_EMBED_MODEL`, documentate **non commentate** come le
  prime impostazioni sostanziali del file, e lette da nessuna riga di codice —
  i nomi veri sono `ERMES_DEFAULT_MODEL_ID` ed `ERMES_EMBED_MODEL_ID`;
- `ERMES_COT_ENABLED`, che non corrispondeva ad alcun campo in nessuna forma.

Ogni volta il sintomo era lo stesso: l'utente configura, il sistema ignora, e
nulla lo segnala. Il file di esempio e' documentazione eseguibile, quindi puo'
essere verificato come tale.
"""

import re
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]


def _variabili_documentate() -> set[str]:
    testo = (RADICE / ".env.example").read_text(encoding="utf-8")
    return {m.group(1) for m in (re.match(r"^\s*#?\s*(ERMES_[A-Z0-9_]+)\s*=", r) for r in testo.splitlines()) if m}


def _variabili_lette() -> set[str]:
    lette: set[str] = set()
    for percorso in (RADICE / "config").glob("*.py"):
        sorgente = percorso.read_text(encoding="utf-8")
        # Lette direttamente da os.environ.get(...)
        lette |= set(re.findall(r'os\.environ\.get\(\s*"(ERMES_[A-Z0-9_]+)"', sorgente))
        # Nomi storici ancora onorati, dichiarati in una mappa
        lette |= set(re.findall(r'"(ERMES_[A-Z0-9_]+)"', sorgente))
    return lette


def test_every_documented_variable_is_actually_read():
    """La direzione pericolosa: documentata ma inerte.

    Il contrario — letta ma non documentata — e' solo poco scopribile, e non
    fa credere a nessuno di aver configurato qualcosa.
    """
    fantasma = sorted(_variabili_documentate() - _variabili_lette())

    assert fantasma == [], (
        "Variabili promesse da .env.example e mai lette dal codice: "
        + ", ".join(fantasma)
        + ". Chi le imposta non ottiene alcun effetto e nulla glielo segnala."
    )


def test_the_example_file_documents_the_settings_that_matter():
    """Le impostazioni senza le quali l'istanza non parte devono esserci."""
    documentate = _variabili_documentate()

    for indispensabile in ("ERMES_ADMIN_PASSWORD", "ERMES_HOST", "ERMES_DEFAULT_MODEL_ID"):
        assert indispensabile in documentate, f"{indispensabile} non e' documentata in .env.example"


@pytest.mark.parametrize(
    "rinominata,attuale",
    [
        ("ERMES_MODEL", "ERMES_DEFAULT_MODEL_ID"),
        ("ERMES_EMBED_MODEL", "ERMES_EMBED_MODEL_ID"),
        ("ERMES_LIBRARY_ASSISTANT_TIMEOUT", "ERMES_ASSISTANT_TIMEOUT_SEC"),
    ],
)
def test_the_old_names_do_not_come_back(rinominata, attuale):
    """Riesumare il nome vecchio riporterebbe il difetto senza che nulla lo dica."""
    documentate = _variabili_documentate()

    assert rinominata not in documentate, f"{rinominata} non e' letta da nessuno: usa {attuale}"
