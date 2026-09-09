"""Controllo della configurazione all'avvio (config/validation.py).

Il caso che ha motivato il controllo e' stato misurato: con
`ERMES_OIDC_ENABLED=1` e nessun issuer ne' JWKS, l'applicazione si avviava
senza errori e `/health` rispondeva 200, quindi una sonda di readiness la
dichiarava sana, mentre ogni accesso via SSO era gia' destinato a fallire.

Ogni regola verificata qui corrisponde a un comportamento reale del codice,
non a una buona pratica generica.
"""

import pytest

import config
from config.validation import ConfigurationError, check_configuration, enforce


def _cfg(**overrides):
    base = {"API_KEY": "", "ADMIN_PASSWORD": "StrongPassword!123", "OIDC_ENABLED": False, "HOST": "127.0.0.1"}
    base.update(overrides)
    return config.cfg.replace(**base)


def _settings(problems):
    return {p.setting for p in problems}


def _severity(problems, setting):
    return next(p.severity for p in problems if p.setting == setting)


# ============================================================
# Bloccanti
# ============================================================


def test_no_authentication_at_all_is_fatal():
    """api/auth.py risponde 503 a ogni richiesta in questo stato."""
    problems = check_configuration(_cfg(ADMIN_PASSWORD="", API_KEY="", OIDC_ENABLED=False))

    assert _severity(problems, "ERMES_ADMIN_PASSWORD") == "fatal"


def test_sso_without_any_way_to_fetch_keys_is_fatal():
    """Il caso misurato: si avviava sano e nessuno poteva accedere."""
    problems = check_configuration(_cfg(OIDC_ENABLED=True, OIDC_ISSUER="", OIDC_JWKS_URL=""))

    assert _severity(problems, "ERMES_OIDC_ISSUER") == "fatal"


def test_an_issuer_alone_is_enough_because_discovery_finds_the_keys():
    problems = check_configuration(_cfg(OIDC_ENABLED=True, OIDC_ISSUER="https://sso.azienda.it", OIDC_AUDIENCE="ermes"))

    assert "ERMES_OIDC_ISSUER" not in _settings(problems)


def test_an_explicit_jwks_url_is_enough_without_an_issuer():
    problems = check_configuration(_cfg(OIDC_ENABLED=True, OIDC_ISSUER="", OIDC_JWKS_URL="https://sso/keys"))

    assert "ERMES_OIDC_ISSUER" not in _settings(problems)


# ============================================================
# Avvisi
# ============================================================


def test_sso_without_audience_is_a_warning_not_a_block():
    """core/oidc_keys.py disattiva verify_aud senza audience: un token emesso
    dallo stesso provider per un'altra applicazione verrebbe accettato."""
    problems = check_configuration(_cfg(OIDC_ENABLED=True, OIDC_ISSUER="https://sso.azienda.it", OIDC_AUDIENCE=""))

    assert _severity(problems, "ERMES_OIDC_AUDIENCE") == "warning"


def test_listening_on_every_interface_is_flagged():
    problems = check_configuration(_cfg(HOST="0.0.0.0"))

    assert _severity(problems, "ERMES_HOST") == "warning"


def test_a_placeholder_audit_secret_is_flagged():
    problems = check_configuration(_cfg(AUDIT_SECRET="CHANGE_ME_TO_AUDIT_SECRET"))

    assert _severity(problems, "ERMES_AUDIT_SECRET") == "warning"


def test_a_real_audit_secret_is_not_flagged():
    problems = check_configuration(_cfg(AUDIT_SECRET="9f2c1a7e4b8d0c3f5a6e2b9d4c7a1f8e"))

    assert "ERMES_AUDIT_SECRET" not in _settings(problems)


def test_cloud_mode_without_consent_is_flagged():
    problems = check_configuration(
        _cfg(LIBRARY_ASSISTANT_MODE="approved_openrouter", LIBRARY_CLOUD_CONSENT=False, OPENROUTER_API_KEY="")
    )

    assert _severity(problems, "ERMES_LIBRARY_ASSISTANT_MODE") == "warning"


# ============================================================
# Configurazione sana
# ============================================================


def test_a_sound_configuration_reports_nothing():
    problems = check_configuration(_cfg())

    assert problems == []


# ============================================================
# Comportamento all'avvio
# ============================================================


def test_enforce_refuses_to_start_on_a_fatal_problem():
    with pytest.raises(ConfigurationError) as errore:
        enforce(_cfg(OIDC_ENABLED=True, OIDC_ISSUER="", OIDC_JWKS_URL=""))

    # Il messaggio deve dire cosa impostare, non solo che qualcosa non va.
    assert "ERMES_OIDC_ISSUER" in str(errore.value)


def test_enforce_lets_warnings_through():
    problems = enforce(_cfg(HOST="0.0.0.0"))

    assert [p.severity for p in problems] == ["warning"]


def test_every_problem_says_what_to_do():
    """Un messaggio che descrive il sintomo senza l'azione fa perdere tempo
    esattamente a chi sta installando il sistema per la prima volta."""
    problems = check_configuration(
        _cfg(ADMIN_PASSWORD="", OIDC_ENABLED=True, OIDC_ISSUER="", HOST="0.0.0.0", AUDIT_SECRET="CHANGE_ME")
    )

    assert len(problems) >= 4
    for problem in problems:
        assert problem.fix.strip()
        assert problem.setting.startswith("ERMES_")


def test_fatal_problems_are_listed_first():
    problems = check_configuration(_cfg(ADMIN_PASSWORD="", HOST="0.0.0.0"))

    assert problems[0].severity == "fatal"
