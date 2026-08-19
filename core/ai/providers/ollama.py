import logging
import time

from .base import BaseProvider

_logger = logging.getLogger(__name__)


class OllamaProvider(BaseProvider):
    """Ollama local LLM provider."""

    def complete(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        temp: float = 0.1,
        json_mode: bool = False,
        timeout: int = 120,
    ) -> str:
        import httpx
        model_id = model or self.config.default_model
        if not model_id:
            raise ValueError("Nessun modello specificato per Ollama")

        base_url = (self.config.base_url or "http://127.0.0.1:11434").rstrip("/")
        url = f"{base_url}/api/generate"

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

        last_error = None
        for retry in range(2):
            try:
                resp = httpx.post(url, json=payload, timeout=timeout)
                resp.raise_for_status()
                return resp.json().get("response", "")
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                _logger.error("Ollama error (%s): status %s", model_id, status)
                last_error = e
                time.sleep(1)
                continue
            except Exception as e:
                _logger.warning("Ollama: %s -> %s, retry", model_id, e)
                last_error = e
                time.sleep(1)
                continue

        raise last_error or RuntimeError(f"Nessuna risposta da Ollama {self.config.name}")

    def test_connection(self) -> tuple[bool, str]:
        import httpx
        base_url = (self.config.base_url or "http://127.0.0.1:11434").rstrip("/")
        try:
            resp = httpx.get(f"{base_url}/api/tags", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            names = [m.get("name", "") for m in models]
            return True, f"OK: {len(names)} modelli locali" + (f" ({', '.join(names[:5])})" if names else "")
        except Exception as e:
            return False, str(e)

    def get_models(self) -> list[str]:
        import httpx
        base_url = (self.config.base_url or "http://127.0.0.1:11434").rstrip("/")
        try:
            resp = httpx.get(f"{base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return self.config.models or []
