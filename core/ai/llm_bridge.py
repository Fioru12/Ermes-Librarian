"""
llm_bridge.py
Utilita' OpenRouter: mappatura dei modelli locali su equivalenti gratuiti e
controllo di raggiungibilita', usate da core.ai.utils.call_llm.
"""

import logging

from config import cfg

_logger = logging.getLogger(__name__)


def _map_to_openrouter_model(local_model_id: str) -> str:
    """Mappa modelli locali su modelli OpenRouter gratuiti.

    I modelli locali Ollama (qwen3.5:*, bge-m3, ecc.) vengono mappati
    su modelli OpenRouter con suffisso :free per evitare costi.
    Se l'ID ha già formato provider/modello (:free o no), resta invariato.
    """
    model_lower = local_model_id.lower()

    # Già un modello OpenRouter valido? Lascialo com'è.
    if "/" in model_lower:
        return local_model_id

    # Modelli locali noti → mappa a free OpenRouter
    if "qwen" in model_lower:
        return "tencent/hy3:free"
    if "bge" in model_lower or "embed" in model_lower:
        return local_model_id  # embedding mai su OpenRouter

    # Default: prova tencent/hy3:free (miglior free per italiano)
    return "tencent/hy3:free"


def check_openrouter() -> tuple[bool, str]:
    """Verifica che OpenRouter sia raggiungibile con la API key configurata."""
    if not cfg.OPENROUTER_API_KEY:
        return False, "OPENROUTER_API_KEY non configurata"

    try:
        import httpx
        response = httpx.get(
            f"{cfg.OPENROUTER_BASE_URL.rstrip('/')}/models",
            headers={
                "Authorization": f"Bearer {cfg.OPENROUTER_API_KEY}",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        models = data.get("data", [])
        return True, f"OpenRouter OK: {len(models)} modelli disponibili"

    except Exception as e:
        return False, f"OpenRouter non raggiungibile: {e}"
