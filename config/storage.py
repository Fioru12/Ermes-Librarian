"""
config/storage.py
Configurazione storage, database, percorsi librerie.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StorageConfig:
    # ---------------------------------------------------------
    # STORAGE LIBRERIE
    # ---------------------------------------------------------
    BASE_DIR: str = field(default_factory=lambda: os.path.abspath(os.environ.get("ERMES_BASE_DIR", ".")))

    @property
    def LIBRARY_DB_PATH(self) -> str:
        """Database locale del bibliotecario (sviluppo/MVP).

        Usato SOLO quando DATABASE_URL non è impostato: in deploy multi-utente
        impostare ERMES_DATABASE_URL (es. postgresql://...) vedi
        docs/POSTGRES_MIGRATION_PLAN.md.
        """
        return os.path.join(self.BASE_DIR, "data", "ermes_knowledge.sqlite3")

    @property
    def SQLITE_PATH(self) -> str:
        """Alias di LIBRARY_DB_PATH per il factory del database backend."""
        return self.LIBRARY_DB_PATH

    # Backend database: vuoto = SQLite locale (default, zero-config);
    # "postgresql://user:pass@host:5432/ermes" = PostgreSQL multi-utente.
    # La selezione è documentata in docs/POSTGRES_MIGRATION_PLAN.md.
    DATABASE_URL: str = field(default_factory=lambda: os.environ.get("ERMES_DATABASE_URL", ""))

    @property
    def LIBRARY_STORAGE_DIR(self) -> str:
        """Archivio locale isolato dal percorso documentale legacy."""
        return os.path.join(self.BASE_DIR, "storage", "libraries")

    @property
    def SECURITY_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "security")

    @property
    def USERS_FILE(self) -> str:
        return os.path.join(self.SECURITY_DIR, "users.json")

    @property
    def LOGS_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "logs")

    @property
    def SYNONYMS_FILE(self) -> str:
        custom = os.environ.get("ERMES_SYNONYMS_FILE", "").strip()
        if custom:
            return custom
        return os.path.join(self.BASE_DIR, "config", "synonyms.json")

    BACKUP_ENABLED: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_BACKUP_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        )
    )
    BACKUP_INTERVAL_HOURS: int = field(default_factory=lambda: int(os.environ.get("ERMES_BACKUP_INTERVAL_HOURS", "24")))

    # ---------------------------------------------------------
    # PROVIDER LLM (allowlist endpoint approvati)
    # ---------------------------------------------------------
    PROVIDERS_CONFIG_PATH: str = field(
        default_factory=lambda: os.environ.get(
            "ERMES_PROVIDERS_CONFIG",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "providers.json"),
        )
    )

    @property
    def ANALYTICS_FILE(self) -> str:
        return os.path.join(self.LOGS_DIR, "analytics_events.jsonl")

    @property
    def AUDIT_FILE(self) -> str:
        return os.path.join(self.LOGS_DIR, "audit_admin.jsonl")

    # ---------------------------------------------------------
    # BACKUP
    # ---------------------------------------------------------
    BACKUP_DIR: str = field(default_factory=lambda: os.environ.get("ERMES_BACKUP_DIR", "backups"))
    BACKUP_RETENTION_COUNT: int = field(
        default_factory=lambda: int(os.environ.get("ERMES_BACKUP_RETENTION_COUNT", "10"))
    )
