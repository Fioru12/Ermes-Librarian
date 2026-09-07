"""
config/__init__.py
Package configurazione di Ermes - retrocompatibilità.

Mantiene `from config import cfg` per tutto il codice esistente.
I singoli moduli sono organizzati per responsabilità.

Utilizzo:
    from config import cfg
    print(cfg.PORT)
"""

import os as _os

from config.integrations import IntegrationsConfig
from config.rag import RAGConfig
from config.security import SecurityConfig
from config.server import ServerConfig
from config.storage import StorageConfig

# Carica variabili dal file .env nella root del progetto (come faceva
# config_legacy.py): senza questo, deployment che si affidano al .env
# perdono ADMIN_PASSWORD, segreti integrazioni, ecc.
try:
    from dotenv import load_dotenv as _load_dotenv

    _env_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), ".env")
    if _os.path.exists(_env_path):
        _load_dotenv(_env_path, encoding="utf-8")
        _load_dotenv(_env_path)  # fallback senza encoding specifico
except ImportError:
    pass


class Config:
    """Configurazione unifica - aggrega tutte le configurazioni.

    Mantiene la stessa interfaccia del config.py originale.
    Tutti i parametri sono leggibili da variabili d'ambiente o file .env.
    """

    def __init__(self):
        # Istanzia ogni configurazione
        self._server = ServerConfig()
        self._security = SecurityConfig()
        self._storage = StorageConfig()
        self._integrations = IntegrationsConfig()
        self._rag = RAGConfig()

    def __getattr__(self, name: str):
        """Delega l'accesso agli attributi alle sottoconfigurazioni."""
        # Cerca in ogni sottoconfigurazione
        for config in (self._server, self._security, self._storage, self._integrations, self._rag):
            if hasattr(config, name):
                return getattr(config, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __repr__(self) -> str:
        return f"Config(HOST={self.HOST!r}, PORT={self.PORT!r}, BASE_DIR={self.BASE_DIR!r})"

    def replace(self, **changes) -> "Config":
        """Crea una nuova istanza con modifiche selezionata.

        Supporta il pattern `replace(cfg, ATTR=value)` usato nei test.
        A differenza di una semplice risoluzione da env, preserva i valori
        correnti dell'istanza per ogni attributo NON esplicitamente
        modificato (comportamento equivalente a dataclasses.replace del
        config legacy, altrimenti i test perdono BASE_DIR ecc.).
        """
        import dataclasses
        import os

        # Raccogli i campi (non le property derivate) di ogni sottoconfig
        current: dict[str, object] = {}
        for sub in (self._server, self._security, self._storage, self._integrations, self._rag):
            for f in dataclasses.fields(sub):
                if hasattr(self, f.name):
                    current[f.name] = getattr(self, f.name)

        # Applica le modifiche come variabili d'ambiente
        original_env: dict[str, str | None] = {}
        env_values: dict[str, str] = {}
        for name, value in current.items():
            env_key = f"ERMES_{name}" if not name.startswith("ERMES_") else name
            env_values[env_key] = str(value)
        for key, value in changes.items():
            env_key = f"ERMES_{key}" if not key.startswith("ERMES_") else key
            env_values[env_key] = str(value)

        try:
            for env_key, value in env_values.items():
                original_env[env_key] = os.environ.get(env_key)
                os.environ[env_key] = value
            new_config = Config()
        finally:
            # Ripristina variabili d'ambiente originali
            for env_key, original_value in original_env.items():
                if original_value is None:
                    os.environ.pop(env_key, None)
                else:
                    os.environ[env_key] = original_value

        return new_config


# Istanza globale - importa questa in tutti i moduli.
cfg = Config()


# ============================================================
# SELF-CHECK (opzionale, eseguibile direttamente)
# ============================================================
if __name__ == "__main__":
    print("=== Ermes - Enterprise Knowledge Hub — Config attiva ===")
    print(f"  HOST             : {cfg.HOST}")
    print(f"  PORT             : {cfg.PORT}")
    print(f"  BASE_DIR         : {cfg.BASE_DIR}")
    print(f"  DOCS_DIR         : {cfg.DOCS_DIR}")
    print(f"  CHROMA_DIR       : {cfg.CHROMA_DIR}")
    print(f"  HASH_FILE        : {cfg.HASH_FILE}")
    print(f"  LOGS_DIR         : {cfg.LOGS_DIR}")
    print(f"  PROMPT_MAX_CHARS : {cfg.PROMPT_MAX_CHARS}")
    print(f"  TYPING_TIMEOUT   : {cfg.TYPING_TIMEOUT_SEC}s")
    print(f"  TOKEN_TIMEOUT    : {cfg.TOKEN_TIMEOUT_SEC}s")
    print(f"  DEFAULT_MODEL    : {cfg.DEFAULT_MODEL_ID}")
    print(f"  EMBED_MODEL      : {cfg.EMBED_MODEL_ID}")
    print(f"  OLLAMA_HOST      : {cfg.OLLAMA_HOST}")
    print(f"  SCORE_LOW        : {cfg.SCORE_THRESHOLD_LOW}")
    print(f"  SCORE_MED        : {cfg.SCORE_THRESHOLD_MED}")
    print(f"  LOG_RETENTION    : {cfg.LOG_RETENTION_DAYS}gg")
