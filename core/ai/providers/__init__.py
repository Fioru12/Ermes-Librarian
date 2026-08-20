"""Provider LLM multi-piattaforma (OpenAI, Anthropic, Google, Ollama).

Moduli:
    base        → ProviderConfig + BaseProvider (Astratta)
    openai_compat → Provider OpenAI-compatibile (OpenAI, OpenRouter, Groq, etc.)
    anthropic   → Provider Anthropic Claude
    google      → Provider Google Gemini
    ollama      → Provider Ollama locale
    registry    → ProviderRegistry (gestione, salvataggio, fallback)
"""

from .anthropic import AnthropicProvider
from .base import BaseProvider, ProviderConfig
from .google import GoogleProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider
from .registry import PROVIDER_TYPES, ProviderRegistry, get_registry


__all__ = [
    "BaseProvider",
    "ProviderConfig",
    "OpenAICompatProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "OllamaProvider",
    "ProviderRegistry",
    "get_registry",
    "PROVIDER_TYPES",
]
