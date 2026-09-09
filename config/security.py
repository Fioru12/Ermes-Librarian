"""
config/security.py
Configurazione sicurezza, autenticazione, OIDC, sessione.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SecurityConfig:
    # ---------------------------------------------------------
    # SICUREZZA GENERALE
    # ---------------------------------------------------------
    SECRET_KEY: str = field(
        default_factory=lambda: os.environ.get("ERMES_SECRET_KEY", "ermes-dev-secret-key-change-in-production")
    )
    ADMIN_PASSWORD: str = field(default_factory=lambda: os.environ.get("ERMES_ADMIN_PASSWORD", ""))
    ADMIN_USERNAME: str = field(default_factory=lambda: os.environ.get("ERMES_ADMIN_USERNAME", "admin"))
    API_KEY: str = field(default_factory=lambda: os.environ.get("ERMES_API_KEY", ""))
    # Token per l'endpoint /metrics (scraping Prometheus). Se vuoto: accesso
    # consentito solo da loopback (scrape locale su singolo nodo). Impostare
    # sempre un token quando Prometheus gira su un altro host.
    METRICS_TOKEN: str = field(default_factory=lambda: os.environ.get("ERMES_METRICS_TOKEN", ""))
    ADMIN_MAX_UPLOAD_MB: int = field(default_factory=lambda: int(os.environ.get("ERMES_ADMIN_MAX_UPLOAD_MB", "50")))
    # Tentativi di accesso falliti tollerati prima del blocco temporaneo
    # (core/login_guard.py). Il conteggio e' per IP e per coppia
    # IP+username, mai per solo username: bloccare un account da qualunque
    # provenienza permetterebbe a chiunque ne conosca il nome di lasciare
    # fuori un collega sbagliando la password apposta.
    LOGIN_MAX_ATTEMPTS: int = field(default_factory=lambda: int(os.environ.get("ERMES_LOGIN_MAX_ATTEMPTS", "10")))
    LOGIN_LOCKOUT_MINUTES: int = field(default_factory=lambda: int(os.environ.get("ERMES_LOGIN_LOCKOUT_MINUTES", "15")))
    PROVIDER_ALLOWED_HOSTS: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            host.strip().lower()
            for host in os.environ.get(
                "ERMES_PROVIDER_ALLOWED_HOSTS",
                "openrouter.ai,api.openai.com,api.groq.com,api.anthropic.com,generativelanguage.googleapis.com,localhost,127.0.0.1,ollama",
            ).split(",")
            if host.strip()
        )
    )
    AUDIT_SECRET: str = field(
        default_factory=lambda: os.environ.get("ERMES_AUDIT_SECRET", "ermes-audit-secret-change-in-production")
    )

    # ---------------------------------------------------------
    # SESSIONE
    # ---------------------------------------------------------
    SESSION_TTL_HOURS: int = field(default_factory=lambda: int(os.environ.get("ERMES_SESSION_TTL_HOURS", "24")))

    # ---------------------------------------------------------
    # ENTERPRISE SSO / OIDC
    # ---------------------------------------------------------
    OIDC_ENABLED: bool = field(
        default_factory=lambda: os.environ.get("ERMES_OIDC_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    )
    OIDC_ISSUER: str = field(default_factory=lambda: os.environ.get("ERMES_OIDC_ISSUER", ""))
    OIDC_CLIENT_ID: str = field(default_factory=lambda: os.environ.get("ERMES_OIDC_CLIENT_ID", ""))
    OIDC_CLIENT_SECRET: str = field(default_factory=lambda: os.environ.get("ERMES_OIDC_CLIENT_SECRET", ""))
    OIDC_AUDIENCE: str = field(default_factory=lambda: os.environ.get("ERMES_OIDC_AUDIENCE", ""))
    OIDC_ROLES_CLAIM: str = field(default_factory=lambda: os.environ.get("ERMES_OIDC_ROLES_CLAIM", "roles"))
    OIDC_GROUPS_CLAIM: str = field(default_factory=lambda: os.environ.get("ERMES_OIDC_GROUPS_CLAIM", "groups"))
    OIDC_JWKS_URL: str = field(default_factory=lambda: os.environ.get("ERMES_OIDC_JWKS_URL", ""))

    # ---------------------------------------------------------
    # ENTERPRISE DLP & AUDIT
    # ---------------------------------------------------------
    DLP_AUDIT_ENABLED: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_DLP_AUDIT_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        )
    )
    PII_FILTER_ENABLED: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_PII_FILTER_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        )
    )
