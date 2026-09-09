"""
config/server.py
Configurazione server, path base e timeout.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServerConfig:
    # ---------------------------------------------------------
    # SERVER
    # ---------------------------------------------------------
    # HOST: 127.0.0.1 = solo localhost (sicuro per intranet).
    # Cambia in 0.0.0.0 SOLO se c'e' un reverse proxy davanti.
    HOST: str = field(default_factory=lambda: os.environ.get("ERMES_HOST", "127.0.0.1"))
    PORT: int = field(default_factory=lambda: int(os.environ.get("ERMES_PORT", "8502")))

    # ---------------------------------------------------------
    # LOGGING
    # ---------------------------------------------------------
    # "text" e' leggibile a schermo durante lo sviluppo; "json" produce una
    # riga per evento con campi separati, che e' cio' che un aggregatore
    # aziendale (SIEM, Loki, Elastic) sa interrogare. Vedi core/logging_setup.py.
    LOG_FORMAT: str = field(default_factory=lambda: os.environ.get("ERMES_LOG_FORMAT", "text").strip().lower())
    LOG_LEVEL: str = field(default_factory=lambda: os.environ.get("ERMES_LOG_LEVEL", "INFO").strip().upper())

    # ---------------------------------------------------------
    # PATH BASE
    # ---------------------------------------------------------
    BASE_DIR: str = field(default_factory=lambda: os.path.abspath(os.environ.get("ERMES_BASE_DIR", ".")))

    @property
    def DOCS_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "documenti")

    @property
    def CHROMA_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "chroma_db")

    @property
    def HASH_FILE(self) -> str:
        return os.path.join(self.CHROMA_DIR, "docs_hashes.json")

    @property
    def SEMANTIC_CACHE_FILE(self) -> str:
        return os.path.join(self.CHROMA_DIR, "semantic_cache.json")

    # ---------------------------------------------------------
    # LEGACY WINSARP (isolato, attivo solo con flag dev)
    # ---------------------------------------------------------
    @property
    def WINSARP_DIR(self) -> str:
        return os.path.join(self.DOCS_DIR, "WinSarp")

    @property
    def CATALOGO_PATH(self) -> str:
        return os.path.join(self.WINSARP_DIR, "WinSarp_Formule.txt")

    @property
    def CATALOGO_JSON_PATH(self) -> str:
        return os.path.join(self.WINSARP_DIR, "WinSarp_Formule.json")

    @property
    def GRAPH_PATH(self) -> str:
        return os.path.join(self.BASE_DIR, "legacy_winsarp", "data", "winsarp_graph.json")

    # ---------------------------------------------------------
    # CORS
    # ---------------------------------------------------------
    CORS_ORIGINS: tuple = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in os.environ.get("ERMES_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
            if origin.strip()
        )
    )

    @property
    def LOGS_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "logs")

    @property
    def SECURITY_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "security")

    # ---------------------------------------------------------
    # TIMEOUT E LIMITI
    # ---------------------------------------------------------
    LIBRARY_ASSISTANT_TIMEOUT_SEC: int = field(
        default_factory=lambda: int(os.environ.get("ERMES_ASSISTANT_TIMEOUT_SEC", "60"))
    )
    PROMPT_MAX_CHARS: int = field(default_factory=lambda: int(os.environ.get("ERMES_PROMPT_MAX_CHARS", "8000")))
    TYPING_TIMEOUT_SEC: int = field(default_factory=lambda: int(os.environ.get("ERMES_TYPING_TIMEOUT_SEC", "15")))
    TOKEN_TIMEOUT_SEC: int = field(default_factory=lambda: int(os.environ.get("ERMES_TOKEN_TIMEOUT_SEC", "2")))
    LOG_RETENTION_DAYS: int = field(default_factory=lambda: int(os.environ.get("ERMES_LOG_RETENTION_DAYS", "30")))
