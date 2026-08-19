import logging
import time

from .base import BaseProvider

_logger = logging.getLogger(__name__)


class OpenAICompatProvider(BaseProvider):
    """OpenAI-compatible API provider (OpenAI, OpenRouter, Groq, Together, Azure, etc.)."""

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
            raise ValueError("Nessun modello specificato per il provider OpenAI-compatibile")

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        base_url = (self.config.base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base_url}/chat/completions"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temp,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error = None
        for retry in range(2):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
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
                        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
                        resp.raise_for_status()
                        data = resp.json()
                        msg = data["choices"][0]["message"]
                        content = msg.get("content")
                        if content is not None:
                            return content
                        return ""
                    except Exception as e2:
                        last_error = e2
                        continue
                if status in (429, 502, 503, 504) or status >= 500:
                    _logger.warning("OpenAICompat: %s -> status %s, retry in 2s", model_id, status)
                    last_error = e
                    time.sleep(2)
                    continue
                _logger.error("OpenAICompat error (%s): %s", model_id, e)
                last_error = e
                continue
            except Exception as e:
                _logger.warning("OpenAICompat: %s -> %s, retry", model_id, e)
                last_error = e
                time.sleep(1)
                continue

        raise last_error or RuntimeError(f"Nessuna risposta dal provider {self.config.name}")

    def test_connection(self) -> tuple[bool, str]:
        import httpx
        base_url = (self.config.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        try:
            resp = httpx.get(f"{base_url}/models", headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            return True, f"OK: {len(models)} modelli disponibili"
        except Exception as e:
            return False, str(e)
