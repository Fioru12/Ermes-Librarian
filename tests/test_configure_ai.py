"""Scelta del modello all'installazione (scripts/configure_ai.py) e modalita'
predefinita delle biblioteche nuove (core/library_store/base.py)."""

import json
import sys
from pathlib import Path

import pytest

import config

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import configure_ai  # noqa: E402
from configure_ai import SceltaNonValidaError, aggiorna_env, piano  # noqa: E402

# ============================================================
# Le regole della scelta
# ============================================================


def test_excerpts_only_needs_no_model_and_turns_cloud_and_verification_off():
    variabili, avvisi, da_scaricare = piano("estratti", verifica=True)

    assert variabili == {
        "ERMES_LIBRARY_ASSISTANT_MODE": "evidence_only",
        "ERMES_LIBRARY_CLOUD_CONSENT": "0",
        "ERMES_EVIDENCE_VERIFIER": "0",
    }
    assert da_scaricare == []
    assert avvisi, "chi chiede la verifica senza modello deve sapere che non e' stata attivata"


def test_local_mode_picks_the_lighter_model_on_a_small_machine():
    variabili, avvisi, da_scaricare = piano("locale", ram_gb=8, ollama=True)

    assert variabili["ERMES_LIBRARY_ASSISTANT_MODE"] == "local_ollama"
    assert variabili["ERMES_DEFAULT_MODEL_ID"] == configure_ai.MODELLO_LOCALE_PICCOLO
    assert da_scaricare == [configure_ai.MODELLO_LOCALE_PICCOLO]
    assert variabili["ERMES_LIBRARY_CLOUD_CONSENT"] == "0"
    assert avvisi


def test_local_mode_uses_the_larger_model_when_memory_allows():
    variabili, avvisi, _ = piano("locale", ram_gb=15.7, ollama=True)

    assert variabili["ERMES_DEFAULT_MODEL_ID"] == configure_ai.MODELLO_LOCALE_GRANDE
    assert avvisi == []


def test_local_mode_warns_on_too_little_memory_and_missing_ollama():
    _, avvisi, _ = piano("locale", ram_gb=4, ollama=False)

    testo = " ".join(avvisi)
    assert "4 GB" in testo
    assert "ollama.com" in testo


def test_verification_is_off_unless_asked_for():
    """Non misurata su domande realistiche: resta una scelta esplicita."""
    for modo, extra in (("locale", {}), ("cloud", {"consenso_cloud": True, "chiave": "sk-x", "modello": "m/x"})):
        variabili, _, _ = piano(modo, ram_gb=32, ollama=True, **extra)
        assert variabili["ERMES_EVIDENCE_VERIFIER"] == "0", modo


def test_local_verification_adds_the_small_model_once():
    variabili, _, da_scaricare = piano("locale", verifica=True, ram_gb=8, ollama=True)

    assert variabili["ERMES_EVIDENCE_VERIFIER"] == "1"
    assert variabili["ERMES_EVIDENCE_VERIFIER_MODEL"] == configure_ai.MODELLO_VERIFICA_LOCALE
    assert da_scaricare.count(configure_ai.MODELLO_VERIFICA_LOCALE) == 1


@pytest.mark.parametrize(
    "mancante",
    [
        {"consenso_cloud": False, "chiave": "sk-x", "modello": "m/x"},
        {"consenso_cloud": True, "chiave": "", "modello": "m/x"},
        {"consenso_cloud": True, "chiave": "sk-x", "modello": ""},
        {"consenso_cloud": True, "chiave": "sk x", "modello": "m/x"},
    ],
)
def test_cloud_mode_is_refused_without_consent_key_or_model(mancante):
    with pytest.raises(SceltaNonValidaError):
        piano("cloud", **mancante)


def test_cloud_mode_writes_consent_key_and_model_and_verifies_with_the_same_provider():
    variabili, _, da_scaricare = piano("cloud", verifica=True, consenso_cloud=True, chiave=" sk-x ", modello="m/x")

    assert variabili["ERMES_LIBRARY_ASSISTANT_MODE"] == "approved_openrouter"
    assert variabili["ERMES_LIBRARY_CLOUD_CONSENT"] == "1"
    assert variabili["OPENROUTER_API_KEY"] == "sk-x"
    assert variabili["OPENROUTER_MODEL"] == "m/x"
    assert variabili["ERMES_EVIDENCE_VERIFIER"] == "1"
    assert "ERMES_EVIDENCE_VERIFIER_MODEL" not in variabili
    assert da_scaricare == []


# ============================================================
# Il file .env
# ============================================================


def test_env_update_replaces_in_place_keeps_the_rest_and_appends_what_is_missing(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "ERMES_PORT=8000\n"
        "# Spiegazione della verifica\n"
        "# ERMES_EVIDENCE_VERIFIER=1\n"
        "ERMES_LIBRARY_CLOUD_CONSENT=1\n"
        "ERMES_LIBRARY_CLOUD_CONSENT=1\n",
        encoding="utf-8",
    )

    aggiorna_env(env, {"ERMES_EVIDENCE_VERIFIER": "0", "ERMES_LIBRARY_CLOUD_CONSENT": "0", "ERMES_NUOVA": "x"})

    righe = env.read_text(encoding="utf-8").splitlines()
    assert righe[0] == "ERMES_PORT=8000"
    assert righe[1] == "# Spiegazione della verifica"
    assert righe[2] == "ERMES_EVIDENCE_VERIFIER=0", "resta accanto alla sua spiegazione"
    assert righe[3] == "ERMES_LIBRARY_CLOUD_CONSENT=0"
    assert righe[4].startswith("# "), "una seconda riga attiva ridefinirebbe il consenso"
    assert righe[-1] == "ERMES_NUOVA=x"


def test_an_old_prefixed_key_cannot_shadow_the_new_one(tmp_path, monkeypatch):
    """config/integrations.py legge ERMES_OPENROUTER_API_KEY prima di
    OPENROUTER_API_KEY: una chiave vecchia con prefisso vincerebbe."""
    env = tmp_path / ".env"
    env.write_text("ERMES_OPENROUTER_API_KEY=sk-vecchia\n", encoding="utf-8")

    aggiorna_env(env, {"OPENROUTER_API_KEY": "sk-nuova"})
    from dotenv import dotenv_values

    valori = dotenv_values(env)
    assert "ERMES_OPENROUTER_API_KEY" not in valori
    assert valori["OPENROUTER_API_KEY"] == "sk-nuova"


def test_env_update_starts_from_the_example_when_there_is_no_env(tmp_path):
    esempio = tmp_path / ".env.example"
    esempio.write_text("ERMES_PORT=8000\n# ERMES_LIBRARY_ASSISTANT_MODE=evidence_only\n", encoding="utf-8")
    env = tmp_path / ".env"

    aggiorna_env(env, {"ERMES_LIBRARY_ASSISTANT_MODE": "local_ollama"}, esempio)

    assert env.read_text(encoding="utf-8") == "ERMES_PORT=8000\nERMES_LIBRARY_ASSISTANT_MODE=local_ollama\n"


def test_the_written_env_is_what_config_reads(tmp_path, monkeypatch):
    """Nomi delle variabili sbagliati darebbero un setup che sembra riuscito
    e non cambia niente: e' gia' successo in questo progetto (ERMES_MODEL)."""
    env = tmp_path / ".env"
    variabili, _, _ = piano("cloud", verifica=True, consenso_cloud=True, chiave="sk-x", modello="m/x")
    aggiorna_env(env, variabili)
    from dotenv import dotenv_values

    for nome, valore in dotenv_values(env).items():
        monkeypatch.setenv(nome, valore or "")
    letto = config.cfg.__class__()

    assert letto.LIBRARY_ASSISTANT_MODE == "approved_openrouter"
    assert letto.LIBRARY_CLOUD_CONSENT is True
    assert letto.OPENROUTER_API_KEY == "sk-x"
    assert letto.OPENROUTER_MODEL == "m/x"
    assert letto.EVIDENCE_VERIFIER_ENABLED is True


def test_the_command_line_reads_the_key_from_the_environment_and_never_prints_it(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    monkeypatch.setenv(configure_ai.KEY_ENV_VAR, "sk-segreta")

    codice = configure_ai.main(["--modo", "cloud", "--modello", "m/x", "--consenso-cloud", "--env", str(env)])

    uscita = capsys.readouterr().out
    assert codice == 0
    assert "sk-segreta" not in uscita
    assert json.loads(uscita.strip().splitlines()[-1])["modo"] == "cloud"
    assert "OPENROUTER_API_KEY=sk-segreta" in env.read_text(encoding="utf-8").splitlines()


def test_a_refused_choice_leaves_the_env_untouched(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    env.write_text("ERMES_PORT=8000\n", encoding="utf-8")
    monkeypatch.delenv(configure_ai.KEY_ENV_VAR, raising=False)

    codice = configure_ai.main(["--modo", "cloud", "--modello", "m/x", "--env", str(env)])

    assert codice == 2
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["ok"] is False
    assert env.read_text(encoding="utf-8") == "ERMES_PORT=8000\n"


# ============================================================
# La scelta arriva alle biblioteche nuove
# ============================================================


@pytest.mark.parametrize(
    ("modo", "consenso", "chiave", "atteso"),
    [
        ("evidence_only", False, "", "evidence_only"),
        ("local_ollama", False, "", "local_ollama"),
        ("approved_openrouter", True, "sk-x", "approved_openrouter"),
        # Si chiude sul sicuro: senza consenso o chiave il cloud non vale.
        ("approved_openrouter", False, "sk-x", "evidence_only"),
        ("approved_openrouter", True, "", "evidence_only"),
        # Richiede un provider per nome: non puo' essere un default.
        ("approved_provider", True, "sk-x", "evidence_only"),
        ("qualcosa", True, "sk-x", "evidence_only"),
    ],
)
def test_a_new_library_gets_the_mode_chosen_at_install(tmp_path, monkeypatch, modo, consenso, chiave, atteso):
    from core.library_store import LibraryStore

    monkeypatch.setattr(
        config,
        "cfg",
        config.cfg.replace(LIBRARY_ASSISTANT_MODE=modo, LIBRARY_CLOUD_CONSENT=consenso, OPENROUTER_API_KEY=chiave),
    )
    store = LibraryStore(tmp_path / "ermes.sqlite3")

    creata = store.create_library("Amministrazione", owner_id="alice")

    assert creata["assistant_mode"] == atteso
    assert store.get_library(creata["id"])["assistant_mode"] == atteso
