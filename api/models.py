"""
api/models.py
Models listing endpoint.
"""
import logging

from fastapi import APIRouter, Depends

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Models"])

OPENROUTER_MODEL_LABELS: dict[str, str] = {
    "tencent/hy3:free": "Hy3 295B (free, migliore qualità)",
    "google/gemma-4-31b-it:free": "Gemma 4 31B (free, veloce)",
    "qwen/qwen3-next-80b-a3b-instruct:free": "Qwen3 80B MoE (free)",
    "meta-llama/llama-3.3-70b-instruct:free": "Llama 3.3 70B (free, buon italiano)",
    "openai/gpt-oss-120b:free": "GPT-OSS 120B (free)",
    "nousresearch/hermes-3-llama-3.1-405b:free": "Hermes 3 405B (free, massima qualità)",
}


@router.get("/api/models", summary="Elenco modelli disponibili")
async def list_models(_auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from config import cfg as _cfg

    models: list[str] = []
    model_groups: dict[str, list[dict[str, str]]] = {}

    # Provider registry: models grouped by provider
    try:
        from core.ai.providers.registry import get_registry
        registry = get_registry()
        providers = registry.list_providers()
    except Exception as error:
        # The library MVP must remain operable without the legacy RAG stack or
        # optional provider packages. The selected local model is still shown.
        _logger.info("Registry provider non disponibile: %s", error)
        providers = []
        registry = None

    if providers:
        for prov in providers:
            provider = registry.get_provider(prov["name"])
            if provider:
                provider_models = provider.get_models()
                group_key = prov["name"]
                group_label = f"{prov['name']} ({prov['type']})"
                if prov.get("is_active"):
                    group_label += " [ATTIVO]"

                group_items = []
                for m in provider_models:
                    if m not in models:
                        models.append(m)
                    group_items.append({"id": m, "display": m})
                if group_items:
                    model_groups[group_key] = group_items

    # Aggiungiamo SEMPRE OpenRouter se la chiave è presente
    if getattr(_cfg, "OPENROUTER_API_KEY", ""):
        from core.ai.utils import _OPENROUTER_FREE_MODELS as _FREE_MODELS
        openrouter_models = []
        for m in _FREE_MODELS:
            if m not in models:
                models.append(m)
            display = OPENROUTER_MODEL_LABELS.get(m, m)
            openrouter_models.append({"id": m, "display": display})
        if openrouter_models:
            model_groups["openrouter"] = openrouter_models

    # Fallback su Ollama
    if not models:
        ollama_models: list[str] = []
        if getattr(_cfg, "ENABLE_LEGACY_WINSARP", False):
            try:
                from legacy_winsarp.core.rag_engine import AVAILABLE_MODELS, fetch_ollama_models
                ollama_models = fetch_ollama_models() or list(AVAILABLE_MODELS.values())
            except Exception as error:
                _logger.info("Catalogo legacy Ollama non disponibile: %s", error)

        # The library mode deliberately avoids importing chromadb and LlamaIndex
        # merely to populate a model selector in the frontend.
        if not ollama_models:
            ollama_models = [getattr(_cfg, "DEFAULT_MODEL_ID", "qwen3.5:4b")]

        for m in ollama_models:
            models.append(m)
            display = m
            if getattr(_cfg, "ENABLE_LEGACY_WINSARP", False):
                try:
                    for key, val in AVAILABLE_MODELS.items():
                        if val == m:
                            display = f"{key}"
                            break
                except NameError:
                    pass
            model_groups.setdefault("ollama", []).append({"id": m, "display": display})

    return {"models": models, "model_groups": model_groups}
