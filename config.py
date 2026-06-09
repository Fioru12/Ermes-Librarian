"""
config.py
Configurazione centralizzata di Ermes.
Tutti i parametri leggibili da variabili d'ambiente o file .env.
Se la variabile non e' impostata, usa il valore di default.

Utilizzo:
    from config import cfg
    print(cfg.PORT)

Override da env (esempi PowerShell):
    $env:ERMES_PORT="8503"
    $env:ERMES_HOST="0.0.0.0"

Oppure crea un file .env nella root del progetto:
    ERMES_PORT=8503
    ERMES_HOST=0.0.0.0
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Carica variabili da file .env se presente
load_dotenv()


@dataclass(frozen=True)
class Config:

    # --------------------------------------------------------
    # SERVER
    # --------------------------------------------------------
    # HOST: 127.0.0.1 = solo localhost (sicuro per intranet).
    # Cambia in 0.0.0.0 SOLO se c'e' un reverse proxy davanti.
    HOST: str = field(default_factory=lambda: os.environ.get("ERMES_HOST", "127.0.0.1"))
    PORT: int = field(default_factory=lambda: int(os.environ.get("ERMES_PORT", "8502")))

    # --------------------------------------------------------
    # PATH
    # --------------------------------------------------------
    BASE_DIR:         str = field(default_factory=lambda: os.path.abspath(
        os.environ.get("ERMES_BASE_DIR", ".")))

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
    def LOGS_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "logs")

    @property
    def SECURITY_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "security")

    @property
    def USERS_FILE(self) -> str:
        return os.path.join(self.SECURITY_DIR, "users.json")

    @property
    def AUDIT_FILE(self) -> str:
        return os.path.join(self.LOGS_DIR, "audit_admin.jsonl")

    # --------------------------------------------------------
    # PROMPT / CHAT
    # --------------------------------------------------------
    PROMPT_MAX_CHARS:   int = field(default_factory=lambda: int(os.environ.get("ERMES_PROMPT_MAX_CHARS",   "2000")))
    TYPING_TIMEOUT_SEC: int = field(default_factory=lambda: int(os.environ.get("ERMES_TYPING_TIMEOUT",    "180")))
    TOKEN_TIMEOUT_SEC:  int = field(default_factory=lambda: int(os.environ.get("ERMES_TOKEN_TIMEOUT",     "600")))

    # --------------------------------------------------------
    # MODELLI
    # --------------------------------------------------------
    # Modello LLM per la generazione delle risposte
    DEFAULT_MODEL_ID: str = field(default_factory=lambda: os.environ.get("ERMES_MODEL", "qwen3:8b"))
    # Modello per embeddings (conversione documenti in vettori)
    EMBED_MODEL_ID:   str = field(default_factory=lambda: os.environ.get("ERMES_EMBED_MODEL", "bge-m3"))

    # --------------------------------------------------------
    # OLLAMA
    # --------------------------------------------------------
    # Ollama deve restare su localhost: non esporre mai in LAN.
    OLLAMA_HOST: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))

    # --------------------------------------------------------
    # RAG / RETRIEVAL
    # --------------------------------------------------------
    SCORE_THRESHOLD_LOW: float = field(default_factory=lambda: float(os.environ.get("ERMES_SCORE_LOW", "0.60")))
    SCORE_THRESHOLD_MED: float = field(default_factory=lambda: float(os.environ.get("ERMES_SCORE_MED", "0.70")))

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------
    LOG_RETENTION_DAYS: int = field(default_factory=lambda: int(os.environ.get("ERMES_LOG_RETENTION_DAYS", "30")))

    # --------------------------------------------------------
    # ADMIN / GOVERNANCE
    # --------------------------------------------------------
    # Se valorizzata, abilita il pannello admin protetto da password.
    # Se vuota, il pannello resta disponibile senza autenticazione.
    ADMIN_PASSWORD: str = field(default_factory=lambda: os.environ.get("ERMES_ADMIN_PASSWORD", ""))
    ADMIN_USERNAME: str = field(default_factory=lambda: os.environ.get("ERMES_ADMIN_USERNAME", "admin"))
    ADMIN_MAX_UPLOAD_MB: int = field(default_factory=lambda: int(os.environ.get("ERMES_ADMIN_MAX_UPLOAD_MB", "50")))

    # --------------------------------------------------------
    # FORMULA GENERATION
    # --------------------------------------------------------
    # Modalita' opzionale e separata dal catalogo ufficiale.
    ENABLE_FORMULA_GENERATION: bool = field(
        default_factory=lambda: os.environ.get("ERMES_ENABLE_FORMULA_GENERATION", "1").strip().lower()
        in {"1", "true", "yes", "on"}
    )

    # --------------------------------------------------------
    # API SECURITY
    # --------------------------------------------------------
    # API key per autenticazione REST API.
    # Se vuota, l'API è disabilitata per sicurezza.
    # Genera una key forte con: python -c "import secrets; print(secrets.token_urlsafe(32))"
    API_KEY: str = field(default_factory=lambda: os.environ.get("ERMES_API_KEY", ""))


# Istanza globale — importa questa in tutti i moduli.
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
