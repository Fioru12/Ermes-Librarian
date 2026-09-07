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
    DEFAULT_MODEL_ID: str = field(default_factory=lambda: os.environ.get("ERMES_DEFAULT_MODEL_ID", "llama3.2:latest"))
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

    # ---------------------------------------------------------
    # WEBHOOK GATEWAY
    # ---------------------------------------------------------
    WEBHOOK_RATE_LIMIT_PER_MIN: int = field(
        default_factory=lambda: int(os.environ.get("ERMES_WEBHOOK_RATE_LIMIT_PER_MIN", "60"))
    )
