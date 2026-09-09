"""Controllo della configurazione all'avvio.

Perche' esiste
--------------
Ermes partiva con qualunque configurazione. Il caso misurato: con
`ERMES_OIDC_ENABLED=1` ma senza issuer ne' JWKS, l'applicazione si avviava
senza errori e `/health` rispondeva 200 — quindi un bilanciatore o una sonda
di readiness la consideravano sana — mentre ogni tentativo di accesso era
destinato a fallire, perche' non c'era modo di recuperare le chiavi con cui
verificare i token. Il sistemista lo scopriva dagli utenti, non dal sistema.

Un software che qualcun altro deve installare non puo' comportarsi cosi'. Qui
i problemi vengono elencati all'avvio, con la variabile da impostare e cosa
fare, e quelli che rendono l'applicazione inutilizzabile ne impediscono la
partenza invece di trasformarsi in errori sparsi a runtime.

Ogni regola descrive un comportamento verificato nel codice, non una buona
pratica generica: accanto a ciascuna c'e' il punto che la produce.
"""

from __future__ import annotations

from dataclasses import dataclass

# Valori che sembrano configurazione ma sono segnaposto pubblici.
_PLACEHOLDERS = {"change_me", "changeme", "change_me_to_audit_secret", "ermes-audit-secret-change-in-production"}


@dataclass(frozen=True)
class ConfigProblem:
    """Un problema di configurazione, con l'azione che lo risolve."""

    severity: str  # "fatal" | "warning"
    setting: str
    problem: str
    fix: str

    def render(self) -> str:
        etichetta = "ERRORE " if self.severity == "fatal" else "AVVISO "
        return f"{etichetta}[{self.setting}] {self.problem} -> {self.fix}"


def _is_placeholder(value: str) -> bool:
    return value.strip().lower() in _PLACEHOLDERS


def check_configuration(cfg) -> list[ConfigProblem]:
    """Elenca i problemi della configurazione fornita, dai piu' gravi in giu'."""
    problems: list[ConfigProblem] = []

    # api/auth.py::_verify_api_key risponde 503 a ogni richiesta se non esiste
    # nessun modo di autenticarsi. Meglio dirlo all'avvio.
    if not cfg.API_KEY and not cfg.ADMIN_PASSWORD and not cfg.OIDC_ENABLED:
        problems.append(
            ConfigProblem(
                "fatal",
                "ERMES_ADMIN_PASSWORD",
                "nessun metodo di autenticazione configurato: ogni richiesta rispondera' 503",
                "imposta ERMES_ADMIN_PASSWORD, oppure ERMES_API_KEY, oppure abilita ERMES_OIDC_ENABLED",
            )
        )

    if cfg.OIDC_ENABLED:
        # core/oidc_keys.py::_resolve_jwks_url non ha da dove prendere le
        # chiavi pubbliche, quindi verify_signed_claims rifiuta ogni token.
        if not cfg.OIDC_ISSUER and not cfg.OIDC_JWKS_URL:
            problems.append(
                ConfigProblem(
                    "fatal",
                    "ERMES_OIDC_ISSUER",
                    "SSO abilitato ma non c'e' modo di recuperare le chiavi del provider: "
                    "ogni token verra' rifiutato e nessuno potra' accedere via SSO",
                    "imposta ERMES_OIDC_ISSUER (le chiavi vengono scoperte dal discovery) "
                    "oppure ERMES_OIDC_JWKS_URL se il provider non lo espone",
                )
            )
        # core/oidc_keys.py passa verify_aud=bool(cfg.OIDC_AUDIENCE): senza
        # audience un token emesso dallo stesso provider per un'altra
        # applicazione viene accettato da Ermes.
        if not cfg.OIDC_AUDIENCE:
            problems.append(
                ConfigProblem(
                    "warning",
                    "ERMES_OIDC_AUDIENCE",
                    "audience non impostata: un token emesso dallo stesso provider per un'altra "
                    "applicazione viene accettato",
                    "imposta ERMES_OIDC_AUDIENCE con il client id registrato per Ermes",
                )
            )

    # api/auth.py imposta secure=... escludendo 0.0.0.0, quindi il cookie di
    # sessione viaggia anche in chiaro.
    if cfg.HOST == "0.0.0.0":  # nosec B104: confronto, non binding
        problems.append(
            ConfigProblem(
                "warning",
                "ERMES_HOST",
                "in ascolto su tutte le interfacce e il cookie di sessione non e' marcato Secure",
                "metti un reverse proxy con TLS davanti all'applicazione (profilo Compose 'public')",
            )
        )

    # core/governance.py rifiuta i segnaposto e usa una chiave generata: qui
    # lo si dice, invece di lasciarlo in una riga di log.
    if cfg.AUDIT_SECRET and _is_placeholder(cfg.AUDIT_SECRET):
        problems.append(
            ConfigProblem(
                "warning",
                "ERMES_AUDIT_SECRET",
                "e' un valore segnaposto pubblico e verra' ignorato",
                "lascia la variabile non impostata per usare la chiave generata per questa "
                "installazione, oppure generane una con "
                'python -c "import secrets; print(secrets.token_hex(32))"',
            )
        )

    # core/evidence_assistant.py degrada silenziosamente senza consenso o chiave.
    if cfg.LIBRARY_ASSISTANT_MODE.startswith("approved") and (
        not cfg.LIBRARY_CLOUD_CONSENT or not cfg.OPENROUTER_API_KEY
    ):
        problems.append(
            ConfigProblem(
                "warning",
                "ERMES_LIBRARY_ASSISTANT_MODE",
                f"modalita' '{cfg.LIBRARY_ASSISTANT_MODE}' richiesta senza consenso cloud o senza "
                "chiave provider: l'assistente ricadra' sulla sola evidenza",
                "imposta ERMES_LIBRARY_CLOUD_CONSENT=1 e OPENROUTER_API_KEY, "
                "oppure riporta la modalita' a evidence_only",
            )
        )

    problems.extend(_legacy_variable_problems())
    problems.sort(key=lambda p: 0 if p.severity == "fatal" else 1)
    return problems


def _legacy_variable_problems() -> list[ConfigProblem]:
    """Variabili rinominate che qualcuno potrebbe ancora avere nel proprio .env.

    Il refactor del config ha rinominato ERMES_SCORE_LOW/_MED/_HIGH in
    ERMES_SCORE_THRESHOLD_*, ma .env.example ha continuato a documentare i
    vecchi nomi, non commentati: chi li impostava non otteneva alcun effetto e
    la soglia restava al default senza che nulla lo segnalasse. Il nome storico
    viene ancora onorato (config/rag.py), e qui lo si dice.
    """
    import os

    rinominate = {
        "ERMES_SCORE_LOW": "ERMES_SCORE_THRESHOLD_LOW",
        "ERMES_SCORE_MED": "ERMES_SCORE_THRESHOLD_MED",
        "ERMES_SCORE_HIGH": "ERMES_SCORE_THRESHOLD_HIGH",
    }
    trovate = []
    for vecchio, nuovo in rinominate.items():
        if os.environ.get(vecchio) is not None and os.environ.get(nuovo) is None:
            trovate.append(
                ConfigProblem(
                    "warning",
                    vecchio,
                    f"nome storico: la variabile e' stata rinominata in {nuovo}",
                    f"rinominala in {nuovo}; il vecchio nome funziona ancora ma non e' garantito",
                )
            )
    return trovate


def report(problems: list[ConfigProblem]) -> str:
    if not problems:
        return "Configurazione verificata: nessun problema."
    righe = [p.render() for p in problems]
    fatali = sum(1 for p in problems if p.severity == "fatal")
    intestazione = f"Configurazione: {len(problems)} problemi ({fatali} bloccanti)."
    return "\n".join([intestazione, *righe])


class ConfigurationError(RuntimeError):
    """L'applicazione non puo' servire richieste con questa configurazione."""


def enforce(cfg, *, logger=None) -> list[ConfigProblem]:
    """Registra tutti i problemi e solleva se ce n'e' almeno uno bloccante."""
    problems = check_configuration(cfg)
    if logger is not None:
        for problem in problems:
            if problem.severity == "fatal":
                logger.error(problem.render())
            else:
                logger.warning(problem.render())
    fatali = [p for p in problems if p.severity == "fatal"]
    if fatali:
        raise ConfigurationError(
            "Avvio interrotto: configurazione non utilizzabile.\n" + "\n".join(p.render() for p in fatali)
        )
    return problems


def main() -> int:
    """Controllo preliminare da riga di comando: `python -m config.validation`."""
    from config import cfg

    problems = check_configuration(cfg)
    print(report(problems))
    return 1 if any(p.severity == "fatal" for p in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
