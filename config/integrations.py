"""
config/integrations.py
Configurazioni integrazioni esterne: LLM, chat, webhook.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class IntegrationsConfig:
    # ---------------------------------------------------------
    # LLM PROVIDER
    # ---------------------------------------------------------
    OLLAMA_HOST: str = field(default_factory=lambda: os.environ.get("ERMES_OLLAMA_HOST", "http://localhost:11434"))
    # Il valore predefinito deve essere il modello che la documentazione dice
    # di installare. Fino all'11 settembre 2026 era "llama3.2:latest" mentre
    # .env.example, il README e le slide indicano qwen3.5:9b: su
    # un'installazione fatta seguendo la documentazione ogni chiamata al
    # modello puntava a un modello assente, e il degrado era silenzioso —
    # l'assistente ripiegava sui soli passaggi, il verificatore dell'evidenza
    # rinunciava a verificare, e /health continuava a dichiarare "healthy"
    # limitandosi a segnalare il modello mancante in un campo secondario.
    # Verificato sul corpus dimostrativo: con il modello sbagliato la domanda
    # di astensione prevista da examples/demo-corpus/questions.md riceveva una
    # citazione al passaggio sulle ferie.
    DEFAULT_MODEL_ID: str = field(default_factory=lambda: os.environ.get("ERMES_DEFAULT_MODEL_ID", "qwen3.5:9b"))
    EMBED_MODEL_ID: str = field(
        default_factory=lambda: os.environ.get("ERMES_EMBED_MODEL_ID", "nomic-embed-text:latest")
    )

    # Cloud LLM (opt-in esplicito)
    LIBRARY_CLOUD_CONSENT: bool = field(
        default_factory=lambda: (
            os.environ.get("ERMES_LIBRARY_CLOUD_CONSENT", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
    )
    OPENROUTER_API_KEY: str = field(default_factory=lambda: os.environ.get("ERMES_OPENROUTER_API_KEY", ""))
    OPENROUTER_BASE_URL: str = field(
        default_factory=lambda: os.environ.get("ERMES_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )

    # ---------------------------------------------------------
    # LANGFUSE (opzionale)
    # ---------------------------------------------------------
    LANGFUSE_PUBLIC_KEY: str = field(default_factory=lambda: os.environ.get("LANGFUSE_PUBLIC_KEY", ""))
    LANGFUSE_SECRET_KEY: str = field(default_factory=lambda: os.environ.get("LANGFUSE_SECRET_KEY", ""))
    LANGFUSE_HOST: str = field(default_factory=lambda: os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"))

    # ---------------------------------------------------------
    # CHAT INTEGRATIONS
    # ---------------------------------------------------------
    TEAMS_WEBHOOK_SECRET: str = field(default_factory=lambda: os.environ.get("ERMES_TEAMS_WEBHOOK_SECRET", ""))
    SLACK_SIGNING_SECRET: str = field(default_factory=lambda: os.environ.get("ERMES_SLACK_SIGNING_SECRET", ""))
    SLACK_BOT_TOKEN: str = field(default_factory=lambda: os.environ.get("ERMES_SLACK_BOT_TOKEN", ""))
    TELEGRAM_BOT_TOKEN: str = field(default_factory=lambda: os.environ.get("ERMES_TELEGRAM_BOT_TOKEN", ""))
    # Segreto dedicato del webhook, quello registrato con
    # setWebhook(secret_token=...) e rimandato da Telegram nell'header
    # X-Telegram-Bot-Api-Secret-Token. Deve essere diverso dal token del bot:
    # il token del bot puo' inviare messaggi come il bot e leggere tutti gli
    # aggiornamenti, quindi non e' un valore da far viaggiare in un header a
    # ogni richiesta entrante. Vuoto = webhook Telegram disattivato, non
    # webhook senza verifica.
    TELEGRAM_WEBHOOK_SECRET: str = field(default_factory=lambda: os.environ.get("ERMES_TELEGRAM_WEBHOOK_SECRET", ""))

    # ---------------------------------------------------------
    # WEBHOOK GATEWAY
    # ---------------------------------------------------------
    WEBHOOK_RATE_LIMIT_PER_MIN: int = field(
        default_factory=lambda: int(os.environ.get("ERMES_WEBHOOK_RATE_LIMIT_PER_MIN", "60"))
    )
