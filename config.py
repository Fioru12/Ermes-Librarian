"""
config.py
Configurazione centralizzata di Ermes.
Tutti i parametri leggibili da variabili d'ambiente o file .env.
Se la variabile non e' impostata, usa il valore di default.

Utilizzo:
    from config import cfg
    print(cfg.PORT)

Override da env (esempi PowerShell):
    $env:ERMES_PORT="8502"
    $env:ERMES_HOST="0.0.0.0"

Oppure crea un file .env nella root del progetto:
    ERMES_PORT=8502
    ERMES_HOST=0.0.0.0
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Carica variabili da file .env se presente (percorso assoluto)
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    try:
        load_dotenv(env_path, encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        # Fallback senza encoding specifico: un .env salvato con la codepage
        # di sistema invece che in UTF-8. Le altre eccezioni devono propagare.
        load_dotenv(env_path)


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
    def SEMANTIC_CACHE_FILE(self) -> str:
        return os.path.join(self.CHROMA_DIR, "semantic_cache.json")

    @property
    def LOGS_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "logs")

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

    @property
    def SECURITY_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, "security")

    @property
    def LIBRARY_DB_PATH(self) -> str:
        """Database locale del bibliotecario (sviluppo/MVP)."""
        return os.path.join(self.BASE_DIR, "data", "ermes_knowledge.sqlite3")

    @property
    def LIBRARY_STORAGE_DIR(self) -> str:
        """Archivio locale isolato dal percorso documentale legacy."""
        return os.path.join(self.BASE_DIR, "storage", "libraries")

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
    DEFAULT_MODEL_ID: str = field(default_factory=lambda: os.environ.get("ERMES_MODEL", "qwen3.5:4b"))
    # Modello per embeddings (conversione documenti in vettori)
    EMBED_MODEL_ID:   str = field(default_factory=lambda: os.environ.get("ERMES_EMBED_MODEL", "bge-m3"))
    # Semantic retrieval is opt-in during the SQLite MVP. It talks only to the
    # configured local Ollama endpoint and falls back to keyword retrieval.
    LIBRARY_SEMANTIC_SEARCH_ENABLED: bool = field(
        default_factory=lambda: os.environ.get("ERMES_LIBRARY_SEMANTIC_SEARCH", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )

    # --------------------------------------------------------
    # PROVIDER CONFIG PATH
    # --------------------------------------------------------
    PROVIDERS_CONFIG_PATH: str = field(default_factory=lambda: os.environ.get(
        "ERMES_PROVIDERS_CONFIG", os.path.join(os.path.dirname(__file__), "config", "providers.json")
    ))

    # --------------------------------------------------------
    # OLLAMA / OPENROUTER
    # --------------------------------------------------------
    # Ollama deve restare su localhost: non esporre mai in LAN.
    OLLAMA_HOST: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))

    # La chiave OpenRouter non abilita il cloud da sola: servono consenso globale
    # e policy esplicita sulla singola biblioteca.
    OPENROUTER_API_KEY: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    OPENROUTER_BASE_URL: str = field(default_factory=lambda: os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
    # Endpoint LLM ammessi per configurazione amministrativa. Per aggiungere
    # un gateway aziendale, inserire esplicitamente il suo hostname qui: non
    # accettiamo URL arbitrari dall'interfaccia web.
    PROVIDER_ALLOWED_HOSTS: tuple[str, ...] = field(default_factory=lambda: tuple(
        host.strip().lower() for host in os.environ.get(
            "ERMES_PROVIDER_ALLOWED_HOSTS",
            "openrouter.ai,api.openai.com,api.groq.com,api.anthropic.com,generativelanguage.googleapis.com,localhost,127.0.0.1,ollama",
        ).split(",") if host.strip()
    ))

    # Assistente della biblioteca: il default non invia mai contenuto a un LLM.
    # "local_ollama" usa esclusivamente OLLAMA_HOST; "approved_openrouter"
    # richiede sia questa scelta esplicita sia il consenso esplicito al cloud.
    LIBRARY_ASSISTANT_MODE: str = field(default_factory=lambda: os.environ.get(
        "ERMES_LIBRARY_ASSISTANT_MODE", "evidence_only"
    ).strip().lower())
    LIBRARY_CLOUD_CONSENT: bool = field(
        default_factory=lambda: os.environ.get("ERMES_LIBRARY_CLOUD_CONSENT", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    LIBRARY_ASSISTANT_TIMEOUT_SEC: int = field(
        default_factory=lambda: int(os.environ.get("ERMES_LIBRARY_ASSISTANT_TIMEOUT", "45"))
    )

    # --------------------------------------------------------
    # LANGFUSE (tracing LLM — opzionale)
    # --------------------------------------------------------
    LANGFUSE_PUBLIC_KEY: str = field(default_factory=lambda: os.environ.get("LANGFUSE_PUBLIC_KEY", ""))
    LANGFUSE_SECRET_KEY: str = field(default_factory=lambda: os.environ.get("LANGFUSE_SECRET_KEY", ""))
    LANGFUSE_HOST: str = field(default_factory=lambda: os.environ.get("LANGFUSE_HOST", "http://localhost:3000"))

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
    # Password per il primo amministratore locale. Se assente, la UI resta
    # fail-closed salvo una Bearer API key valida.
    ADMIN_PASSWORD: str = field(default_factory=lambda: os.environ.get("ERMES_ADMIN_PASSWORD", ""))
    ADMIN_USERNAME: str = field(default_factory=lambda: os.environ.get("ERMES_ADMIN_USERNAME", "admin"))
    ADMIN_MAX_UPLOAD_MB: int = field(default_factory=lambda: int(os.environ.get("ERMES_ADMIN_MAX_UPLOAD_MB", "50")))

    # --------------------------------------------------------
    # FORMULA GENERATION
    # --------------------------------------------------------
    # Modalita' opzionale e separata dal catalogo ufficiale.
    # DISABILITATA per default in produzione: generare codice WinSarp via LLM
    # senza review umana e' un rischio. Attivare esplicitamente impostando
    # ERMES_ENABLE_FORMULA_GENERATION=1 nel file .env.
    ENABLE_FORMULA_GENERATION: bool = field(
        default_factory=lambda: os.environ.get("ERMES_ENABLE_FORMULA_GENERATION", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )

    # Il modulo WinSarp è legacy rispetto al prodotto Ermes Knowledge.
    # Rimane disabilitato nel percorso pubblico finché non viene richiesto
    # esplicitamente per sviluppo o per un vertical pack futuro.
    ENABLE_LEGACY_WINSARP: bool = field(
        default_factory=lambda: os.environ.get("ERMES_ENABLE_LEGACY_WINSARP", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )

    # --------------------------------------------------------
    # API SECURITY
    # --------------------------------------------------------
    # API key per autenticazione REST API.
    # Se vuota, l'API è disabilitata per sicurezza.
    # Genera una key forte con: python -c "import secrets; print(secrets.token_urlsafe(32))"
    API_KEY: str = field(default_factory=lambda: os.environ.get("ERMES_API_KEY", ""))
    SESSION_TTL_HOURS: int = field(default_factory=lambda: int(os.environ.get("ERMES_SESSION_TTL_HOURS", "12")))
    CORS_ORIGINS: tuple[str, ...] = field(default_factory=lambda: tuple(
        origin.strip() for origin in os.environ.get(
            "ERMES_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",") if origin.strip()
    ))

    # --------------------------------------------------------
    # BACKUP / SCHEDULING
    # --------------------------------------------------------
    BACKUP_ENABLED: bool = field(
        default_factory=lambda: os.environ.get("ERMES_BACKUP_ENABLED", "1").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    BACKUP_INTERVAL_HOURS: int = field(
        default_factory=lambda: int(os.environ.get("ERMES_BACKUP_INTERVAL_HOURS", "24"))
    )

    # --------------------------------------------------------
    # PII FILTERING
    # --------------------------------------------------------
    PII_FILTER_ENABLED: bool = field(
        default_factory=lambda: os.environ.get("ERMES_PII_FILTER_ENABLED", "1").strip().lower()
        in {"1", "true", "yes", "on"}
    )

    # --------------------------------------------------------
    # EXTERNAL CHAT INTEGRATIONS (Teams, Slack, Telegram)
    # --------------------------------------------------------
    TEAMS_WEBHOOK_SECRET: str = field(default_factory=lambda: os.environ.get("ERMES_TEAMS_WEBHOOK_SECRET", ""))
    SLACK_SIGNING_SECRET: str = field(default_factory=lambda: os.environ.get("ERMES_SLACK_SIGNING_SECRET", ""))
    SLACK_BOT_TOKEN: str = field(default_factory=lambda: os.environ.get("ERMES_SLACK_BOT_TOKEN", ""))
    TELEGRAM_BOT_TOKEN: str = field(default_factory=lambda: os.environ.get("ERMES_TELEGRAM_BOT_TOKEN", ""))


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
