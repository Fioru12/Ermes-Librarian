import logging
import time

from .base import BaseProvider

_logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider."""

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
            raise ValueError("Nessun modello specificato per Anthropic")

        base_url = (self.config.base_url or "https://api.anthropic.com").rstrip("/")
        url = f"{base_url}/v1/messages"

        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        messages = [{"role": "user", "content": prompt}]

        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": temp,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["extra_headers"] = {"anthropic-beta": "json-mode-2024-05-31"}

        last_error = None
        for retry in range(2):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                content_blocks = data.get("content", [])
                text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
                return "\n".join(text_parts)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (429, 502, 503, 504) or status >= 500:
                    _logger.warning("Anthropic: %s -> %s, retry in 2s", model_id, status)
                    last_error = e
                    time.sleep(2)
                    continue
                _logger.error("Anthropic error (%s): %s", model_id, e)
                last_error = e
                continue
            except Exception as e:
                _logger.warning("Anthropic: %s -> %s, retry", model_id, e)
                last_error = e
                time.sleep(1)
                continue

        raise last_error or RuntimeError(f"Nessuna risposta da Anthropic {self.config.name}")

    def test_connection(self) -> tuple[bool, str]:
        import httpx
        base_url = (self.config.base_url or "https://api.anthropic.com").rstrip("/")
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
        }
        try:
            resp = httpx.get(f"{base_url}/v1/models", headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            return True, f"OK: {len(models)} modelli disponibili"
        except Exception as e:
            return False, str(e)
