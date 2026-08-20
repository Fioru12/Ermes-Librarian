"""
utils.py
Funzioni di supporto: hash documenti, validazione file,
log JSON/TXT, pulizia log vecchi, pulizia ChromaDB orfani.
Nessuna dipendenza da Streamlit o LlamaIndex.
"""
import contextlib
import logging

# ============================================================
# CONFIGURAZIONE
# ============================================================
LOG_RETENTION_DAYS = 30
_HASH_CHUNK_SIZE   = 65536  # 64 KB — lettura a blocchi, evita OOM su file grandi
_logger = logging.getLogger(__name__)


# ============================================================
# INTERFACCIA LLM CENTRALIZZATA (OPENROUTER / OLLAMA)
# ============================================================
# Modelli free su OpenRouter ordinati per potenza decrescente
# Aggiornati 2026-07-07: i nomi precedenti (gemini-2.0-flash-exp,
# qwen2.5-72b, llama-3.2-90b, deepseek-chat, mistral-small-3.1) davano 404.
# Se uno va in 429 (rate-limit) o fallisce, si passa al successivo.
_OPENROUTER_FREE_MODELS = [
    "google/gemma-4-31b-it:free",                      # 31B Gemma 4, più veloce (~1s)
    "tencent/hy3:free",                                # 295B MoE, multilingua, ottimo per italiano
    "qwen/qwen3-next-80b-a3b-instruct:free",           # 80B MoE Qwen3
    "meta-llama/llama-3.3-70b-instruct:free",          # 70B Llama, buon italiano
    "openai/gpt-oss-120b:free",                        # 120B open-weight
    "nousresearch/hermes-3-llama-3.1-405b:free",       # 405B, massima qualità (fallback)
]

# ============================================================
# LANGFUSE — TRACING LLM (OPZIONALE)
# ============================================================
_langfuse_client = None

def _get_langfuse():
    global _langfuse_client
    if _langfuse_client is None:
        try:
            from config import cfg as _cfg
            if _cfg.LANGFUSE_PUBLIC_KEY and _cfg.LANGFUSE_SECRET_KEY:
                from langfuse import Langfuse
                _langfuse_client = Langfuse(
                    public_key=_cfg.LANGFUSE_PUBLIC_KEY,
                    secret_key=_cfg.LANGFUSE_SECRET_KEY,
                    host=_cfg.LANGFUSE_HOST,
                )
        except Exception as e:
            _logger.debug("Langfuse non disponibile: %s", e)
    return _langfuse_client


def call_llm(prompt: str, model_id: str, system_prompt: str = None, temp: float = 0.1, json_mode: bool = False, timeout: int = 120) -> str:
    """Helper centralizzato per chiamare LLM.

    Usa il provider registry se ci sono provider configurati;
    altrimenti comportamento legacy (OpenRouter se configurato, altrimenti Ollama locale).
    """
    import time as _time

    _lf = _get_langfuse()
    _lf_gen = None
    _lf_start = _time.time()
    _lf_model = model_id

    if _lf:
        try:
            _lf_gen = _lf.generation(
                name="call_llm",
                model=model_id,
                model_parameters={"temperature": temp, "json_mode": json_mode, "system_prompt": system_prompt},
                input=prompt,
            )
        except Exception:
            _lf_gen = None

    try:
        # Tenta via provider registry
        try:
            from core.ai.providers.registry import get_registry
            registry = get_registry()
            if registry.list_providers():
                result = registry.call_llm(
                    prompt=prompt,
                    model_id=model_id,
                    system_prompt=system_prompt,
                    temp=temp,
                    json_mode=json_mode,
                    timeout=timeout,
                )
                _lf_end_trace(_lf_gen, _lf_start, result, None)
                return result
        except Exception as registry_err:
            _logger.debug("Provider registry non disponibile, fallback legacy: %s", registry_err)

        # Legacy fallback
        import httpx as _httpx

        from config import cfg as _cfg

        if not _cfg.OPENROUTER_API_KEY:
            result = _call_ollama(prompt, model_id, system_prompt, temp, json_mode, timeout, _httpx, _cfg)
            _lf_end_trace(_lf_gen, _lf_start, result, None)
            return result

        headers = {
            "Authorization": f"Bearer {_cfg.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        is_openrouter_model = "/" in model_id and not model_id.startswith("hf.co/")
        if is_openrouter_model:
            models_to_try = [model_id] + [m for m in _OPENROUTER_FREE_MODELS if m != model_id]
        else:
            models_to_try = list(_OPENROUTER_FREE_MODELS)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None
        for retry in range(2):
            for attempt, api_model in enumerate(models_to_try):
                payload = {
                    "model": api_model,
                    "messages": messages,
                    "temperature": temp,
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}

                _lf_model = api_model
                try:
                    resp = _httpx.post(
                        f"{_cfg.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
                        headers=headers, json=payload, timeout=timeout,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    content = msg.get("content")
                    if content is not None:
                        if attempt > 0:
                            _logger.info("call_llm: %s -> %s (ok)", models_to_try[0], api_model)
                        _lf_end_trace(_lf_gen, _lf_start, content, None)
                        return content
                    reasoning = msg.get("reasoning")
                    if reasoning:
                        if attempt > 0:
                            _logger.info("call_llm: %s -> %s (reasoning ok)", models_to_try[0], api_model)
                        _lf_end_trace(_lf_gen, _lf_start, reasoning, None)
                        return reasoning
                    _lf_end_trace(_lf_gen, _lf_start, "", None)
                    return ""
                except _httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    if status == 400 and json_mode:
                        _logger.warning("json_mode non supportato da %s, riprovo senza", api_model)
                        payload.pop("response_format", None)
                        try:
                            resp = _httpx.post(
                                f"{_cfg.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
                                headers=headers, json=payload, timeout=timeout,
                            )
                            resp.raise_for_status()
                            data = resp.json()
                            msg = data["choices"][0]["message"]
                            content = msg.get("content")
                            if content is not None:
                                _lf_end_trace(_lf_gen, _lf_start, content, None)
                                return content
                            reasoning = msg.get("reasoning")
                            if reasoning:
                                _lf_end_trace(_lf_gen, _lf_start, reasoning, None)
                                return reasoning
                            _lf_end_trace(_lf_gen, _lf_start, "", None)
                            return ""
                        except Exception as e2:
                            _logger.warning("Ritentativo senza json_mode fallito (%s): %s", api_model, e2)
                            last_error = e2
                            continue
                    if status in (429, 502, 503, 504) or status >= 500:
                        _logger.warning("call_llm: %s -> %s (%s), provo prossimo modello", models_to_try[0], api_model, status)
                        last_error = e
                        _time.sleep(2)
                        continue
                    _logger.error("Errore chiamata OpenRouter (%s): %s", api_model, e)
                    last_error = e
                    continue
                except Exception as e:
                    _logger.warning("call_llm: %s -> %s (errore: %s), provo successivo", models_to_try[0], api_model, e)
                    last_error = e
                    continue

            if retry == 0:
                _logger.info("call_llm: tutti i modelli falliti, riprovo dopo 5s...")
                _time.sleep(5)
            else:
                exc = last_error or RuntimeError("Nessun modello OpenRouter disponibile")
                _lf_end_trace(_lf_gen, _lf_start, None, exc)
                raise exc
    except Exception as e:
        _lf_end_trace(_lf_gen, _lf_start, None, e)
        raise


def _lf_end_trace(gen, start, result, error):
    """Finalizza il trace Langfuse (se attivo). Silenzioso se fallisce."""
    if gen is None or start is None:
        return
    # Il tracing e' osservabilita' opzionale: se Langfuse non risponde, la
    # richiesta dell'utente non deve fallire per questo.
    with contextlib.suppress(Exception):
        gen.end(
            output=result,
            level="ERROR" if error else "DEFAULT",
            status_message=str(error) if error else None,
        )


def _call_ollama(prompt, model_id, system_prompt, temp, json_mode, timeout, _httpx, _cfg):
    url = f"{_cfg.OLLAMA_HOST.rstrip('/')}/api/generate"
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
    try:
        resp = _httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        _logger.error("Errore chiamata Ollama locale (%s): %s", model_id, e)
        raise e
