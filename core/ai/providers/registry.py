import json
import logging
import os
import threading

from .anthropic import AnthropicProvider
from .base import BaseProvider, ProviderConfig
from .google import GoogleProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

_logger = logging.getLogger(__name__)

PROVIDER_TYPES = {
    "openai": OpenAICompatProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "ollama": OllamaProvider,
}


class ProviderRegistry:
    """Registry for managing LLM providers with automatic fallback."""

    def __init__(self, config_path: str | None = None):
        self._providers: dict[str, BaseProvider] = {}
        self._active_name: str | None = None
        self._config_path = config_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config", "providers.json",
        )
        self._lock = threading.Lock()

    # ---- Load / Save ----

    def load(self):
        with self._lock:
            self._providers.clear()
            self._active_name = None
            if not os.path.exists(self._config_path):
                _logger.info("File provider config non trovato: %s", self._config_path)
                return
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    data = json.load(f)
                for pdata in data.get("providers", []):
                    try:
                        provider = self._from_dict(pdata)
                        if provider:
                            self._providers[provider.config.name] = provider
                    except Exception as e:
                        _logger.warning("Errore caricamento provider %s: %s", pdata.get("name"), e)
                self._active_name = data.get("active")
                if self._active_name and self._active_name not in self._providers:
                    self._active_name = None
                _logger.info(
                    "Caricati %d provider (attivo: %s)",
                    len(self._providers), self._active_name or "nessuno",
                )
            except Exception as e:
                _logger.error("Errore caricamento config provider: %s", e)

    def save(self):
        with self._lock:
            data = {
                "providers": [p.to_dict() for p in self._providers.values()],
                "active": self._active_name,
            }
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    # ---- CRUD ----

    def add_provider(self, config: ProviderConfig) -> BaseProvider:
        provider_cls = PROVIDER_TYPES.get(config.type)
        if not provider_cls:
            raise ValueError(f"Tipo provider sconosciuto: {config.type}. Tipi supportati: {list(PROVIDER_TYPES.keys())}")
        provider = provider_cls(config)
        with self._lock:
            self._providers[config.name] = provider
        self.save()
        return provider

    def remove_provider(self, name: str):
        with self._lock:
            self._providers.pop(name, None)
            if self._active_name == name:
                self._active_name = None
        self.save()

    def get_provider(self, name: str) -> BaseProvider | None:
        return self._providers.get(name)

    def set_active(self, name: str | None):
        with self._lock:
            if name is not None and name not in self._providers:
                raise ValueError(f"Provider '{name}' non trovato")
            self._active_name = name
        self.save()

    def get_active(self) -> BaseProvider | None:
        if self._active_name:
            return self._providers.get(self._active_name)
        return None

    def list_providers(self) -> list[dict]:
        result = []
        for name, provider in self._providers.items():
            d = provider.to_dict()
            d.pop("api_key", None)
            d["is_active"] = name == self._active_name
            result.append(d)
        return result

    def get_active_name(self) -> str | None:
        return self._active_name

    # ---- Call LLM ----

    def call_llm(
        self,
        prompt: str,
        model_id: str | None = None,
        system_prompt: str | None = None,
        temp: float = 0.1,
        json_mode: bool = False,
        timeout: int = 120,
        provider_name: str | None = None,
    ) -> str:
        """Chiama l'LLM usando il provider specificato o quello attivo,
        con fallback sugli altri provider abilitati in caso di errore.

        Se non ci sono provider configurati, delegato al comportamento legacy
        (OPENROUTER_API_KEY → OpenRouter else Ollama).
        """
        providers_to_try = []
        if provider_name:
            p = self.get_provider(provider_name)
            if p and p.config.enabled:
                providers_to_try.append(p)
        else:
            active = self.get_active()
            if active and active.config.enabled:
                providers_to_try.append(active)
            for p in self._providers.values():
                if p.config.enabled and p.config.name != self._active_name:
                    providers_to_try.append(p)

        if not providers_to_try:
            return _legacy_call_llm(
                prompt, model_id or "", system_prompt, temp, json_mode, timeout,
            )

        last_error = None
        for provider in providers_to_try:
            try:
                result = provider.complete(
                    prompt=prompt,
                    model=model_id or provider.config.default_model or None,
                    system_prompt=system_prompt,
                    temp=temp,
                    json_mode=json_mode,
                    timeout=timeout,
                )
                if result:
                    return result
            except Exception as e:
                _logger.warning(
                    "Provider %s fallito: %s, provo successivo...",
                    provider.config.name, e,
                )
                last_error = e
                continue

        raise last_error or RuntimeError("Nessun provider disponibile per la chiamata LLM")

    # ---- Test ----

    def test_provider(self, config: ProviderConfig) -> tuple[bool, str]:
        provider_cls = PROVIDER_TYPES.get(config.type)
        if not provider_cls:
            return False, f"Tipo sconosciuto: {config.type}"
        provider = provider_cls(config)
        return provider.test_connection()

    # ---- Internals ----

    def _from_dict(self, data: dict) -> BaseProvider | None:
        ptype = data.get("type")
        provider_cls = PROVIDER_TYPES.get(ptype)
        if not provider_cls:
            return None
        return provider_cls(ProviderConfig.from_dict(data))


# ---- Legacy fallback (preserva il comportamento attuale) ----

def _legacy_call_llm(
    prompt: str,
    model_id: str,
    system_prompt: str | None = None,
    temp: float = 0.1,
    json_mode: bool = False,
    timeout: int = 120,
) -> str:
    import time as _time

    import httpx

    from config import cfg

    if not cfg.OPENROUTER_API_KEY:
        return _legacy_ollama(prompt, model_id, system_prompt, temp, json_mode, timeout)

    headers = {
        "Authorization": f"Bearer {cfg.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    _openrouter_free_models = [
        "google/gemma-4-31b-it:free",
        "tencent/hy3:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "openai/gpt-oss-120b:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
    ]

    is_openrouter_model = "/" in model_id and not model_id.startswith("hf.co/")
    if is_openrouter_model:
        models_to_try = [model_id] + [m for m in _openrouter_free_models if m != model_id]
    else:
        models_to_try = list(_openrouter_free_models)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_error = None
    for retry in range(2):
        for api_model in models_to_try:
            payload = {
                "model": api_model,
                "messages": messages,
                "temperature": temp,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            try:
                resp = httpx.post(
                    f"{cfg.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
                    headers=headers, json=payload, timeout=timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                msg = data["choices"][0]["message"]
                content = msg.get("content")
                if content is not None:
                    return content
                reasoning = msg.get("reasoning")
                if reasoning:
                    return reasoning
                return ""
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 400 and json_mode:
                    payload.pop("response_format", None)
                    try:
                        resp = httpx.post(
                            f"{cfg.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
                            headers=headers, json=payload, timeout=timeout,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        msg = data["choices"][0]["message"]
                        content = msg.get("content")
                        if content is not None:
                            return content
                        return ""
                    except Exception:
                        pass
                if status in (429, 502, 503, 504) or status >= 500:
                    last_error = e
                    _time.sleep(2)
                    continue
                last_error = e
                continue
            except Exception as e:
                last_error = e
                continue
        if retry == 0:
            _time.sleep(5)
        else:
            raise last_error or RuntimeError("Nessun modello OpenRouter disponibile")
    raise last_error or RuntimeError("Nessun modello OpenRouter disponibile")


def _legacy_ollama(prompt, model_id, system_prompt, temp, json_mode, timeout):
    import httpx

    from config import cfg
    url = f"{cfg.OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {
        "model": model_id,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temp},
    }
    if system_prompt:
        payload["system"] = system_prompt
    if json_mode:
        payload["format"] = "json"
    resp = httpx.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("response", "")


# ---- Istanza globale ----
_registry: ProviderRegistry | None = None
_registry_lock = threading.Lock()


def get_registry(config_path: str | None = None) -> ProviderRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ProviderRegistry(config_path)
                _registry.load()
    return _registry
