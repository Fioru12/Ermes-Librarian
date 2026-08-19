import logging
import time

from .base import BaseProvider

_logger = logging.getLogger(__name__)


class GoogleProvider(BaseProvider):
    """Google Gemini API provider."""

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
            raise ValueError("Nessun modello specificato per Google Gemini")

        api_key = self.config.api_key
        base_url = (self.config.base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        url = f"{base_url}/v1beta/models/{model_id}:generateContent?key={api_key}"

        contents = {"role": "user", "parts": [{"text": prompt}]}
        payload = {
            "contents": [contents],
            "generationConfig": {
                "temperature": temp,
            },
        }

        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        if json_mode:
            payload["generationConfig"]["response_mime_type"] = "application/json"

        last_error = None
        for retry in range(2):
            try:
                resp = httpx.post(url, json=payload, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text_parts = [p.get("text", "") for p in parts]
                    return "\n".join(text_parts)
                return data.get("text", "")
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (429, 502, 503, 504) or status >= 500:
                    _logger.warning("Google: %s -> %s, retry in 2s", model_id, status)
                    last_error = e
                    time.sleep(2)
                    continue
                _logger.error("Google error (%s): %s", model_id, e)
                last_error = e
                continue
            except Exception as e:
                _logger.warning("Google: %s -> %s, retry", model_id, e)
                last_error = e
                time.sleep(1)
                continue

        raise last_error or RuntimeError(f"Nessuna risposta da Google {self.config.name}")

    def test_connection(self) -> tuple[bool, str]:
        import httpx
        api_key = self.config.api_key
        base_url = (self.config.base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        url = f"{base_url}/v1beta/models?key={api_key}"
        try:
            resp = httpx.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            return True, f"OK: {len(models)} modelli disponibili"
        except Exception as e:
            return False, str(e)
