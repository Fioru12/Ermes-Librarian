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

    _SOTTOCONFIG = ("_server", "_security", "_storage", "_integrations", "_rag")

    def replace(self, **changes) -> "Config":
        """Nuova istanza con i campi indicati sostituiti, gli altri invariati.

        Sostituisce direttamente le sottoconfigurazioni invece di passare per
        le variabili d'ambiente. La versione precedente scriveva
        `ERMES_<NOME_CAMPO>` e ricostruiva tutto da li', il che funziona solo
        finche' il nome della variabile coincide con quello del campo: per gli
        otto campi dove non coincide — fra cui
        LIBRARY_SEMANTIC_SEARCH_ENABLED (ERMES_LIBRARY_SEMANTIC_SEARCH) e
        RERANKER_NEURAL_ENABLED (ERMES_RERANKER_NEURAL) — la sostituzione non
        aveva alcun effetto, e un test che la usava misurava il default
        credendo di aver configurato altro. Nessun test lo faceva ancora, ma
        era questione di tempo.

        Un nome sconosciuto ora solleva invece di essere ignorato: prima un
        refuso in un test passava inosservato.
        """
        import dataclasses

        nuovo = Config.__new__(Config)
        applicati: set[str] = set()
        for attributo in self._SOTTOCONFIG:
            sotto = getattr(self, attributo)
            nomi = {campo.name for campo in dataclasses.fields(sotto)}
            # Applicato a OGNI sottoconfigurazione che ha quel campo, non alla
            # prima: BASE_DIR esiste sia in ServerConfig sia in StorageConfig, e
            # assegnarlo solo alla prima lasciava LIBRARY_DB_PATH puntato al
            # database reale mentre il test credeva di lavorare in una
            # directory temporanea.
            miei = {nome: valore for nome, valore in changes.items() if nome in nomi}
            applicati |= set(miei)
            # Le sottoconfigurazioni sono frozen: se non cambia niente si puo'
            # riusare la stessa istanza invece di ricostruirla.
            setattr(nuovo, attributo, dataclasses.replace(sotto, **miei) if miei else sotto)

        rimasti = {nome: valore for nome, valore in changes.items() if nome not in applicati}
        if rimasti:
            raise TypeError(
                "Config.replace: campi inesistenti "
                + ", ".join(sorted(rimasti))
                + ". Le proprieta' derivate (DOCS_DIR, USERS_FILE, ...) non sono sostituibili: "
                "cambia il campo da cui derivano, per esempio BASE_DIR."
            )
        return nuovo


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
