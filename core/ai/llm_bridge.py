"""
llm_bridge.py
Bridge LLM centralizzato che unifica Ollama e OpenRouter.

Questo modulo risolve il problema descritto nel Pillastro 3:
"Perché usare OpenRouter (o API) cambia tutto"

Il problema attuale:
  - api.py e rag_engine.py usano `Ollama` di llama_index direttamente
  - `call_llm()` in utils.py usa già OpenRouter, ma la chat engine non lo usa
  - Risultato: quando l'utente configura OPENROUTER_API_KEY, il retrieval RAG
    non ne beneficia, solo le chiamate esplicite a `call_llm()`.

Soluzione:
  - Forniamo un `get_llm()` centralizzato che sceglie automaticamente:
    * OpenRouter via API HTTP se OPENROUTER_API_KEY è configurata
    * Ollama locale come fallback se OpenRouter fallisce
  - Il wrapper implementa l'interfaccia `llama_index.core.llms.LLM` in modo che
    CustomChatEngine e tutto il resto funzioni senza modifiche.
"""

import logging
from typing import Any, Generator, Sequence

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
    MessageRole,
)
from llama_index.core.llms import LLM
from llama_index.llms.ollama import Ollama

from config import cfg

_logger = logging.getLogger(__name__)


# ============================================================
# OPENROUTER LLM WRAPPER
# ============================================================


class OpenRouterLLM(LLM):
    """Wrapper LLM compatibile con llama_index che usa OpenRouter via API.

    Implementa l'interfaccia llama_index.llms.LLM (metodi chat/complete/stream)
    traducendo le chiamate in richieste HTTP a OpenRouter.
    """

    def __init__(
        self,
        model: str = "deepseek/deepseek-chat",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        top_p: float = 0.9,
        request_timeout: float = 120.0,
        additional_kwargs: dict | None = None,
    ):
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            request_timeout=request_timeout,
            additional_kwargs=additional_kwargs or {},
        )
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._top_p = top_p
        self._timeout = request_timeout
        self._api_key = cfg.OPENROUTER_API_KEY
        self._base_url = cfg.OPENROUTER_BASE_URL.rstrip("/")

    # ---- Metadata (richiesto da llama_index) ----

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            model_name=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            context_window=65536,  # DeepSeek supporta 64K
            num_output=self._max_tokens,
            is_chat_model=True,
            is_function_calling_model=False,
        )

    # ---- Chat (usato da CustomChatEngine) ----

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        """Invia una conversazione chat a OpenRouter e ritorna la risposta."""
        payload = self._build_payload(messages, **kwargs)

        try:
            import httpx
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            finish_reason = choice.get("finish_reason", "stop")

            return ChatResponse(
                message=ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=content,
                ),
                raw=data,
                delta=content,
                additional_kwargs={"finish_reason": finish_reason},
            )

        except Exception as e:
            _logger.error("OpenRouter chat error: %s", e)
            return ChatResponse(
                message=ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=f"Errore chiamata OpenRouter: {e}",
                ),
                raw={},
            )

    def stream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponseGen:
        """Streaming chat non supportato via OpenRouter base — chiama chat normale."""
        # Per ora, fallback a chat normale (streaming richiederebbe SSE)
        resp = self.chat(messages, **kwargs)

        def gen() -> Generator[ChatResponse, None, None]:
            yield resp

        return gen()

    # ---- Complete (usato per query semplici) ----

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        """Completa un prompt singolo."""
        messages = [ChatMessage(role=MessageRole.USER, content=prompt)]
        chat_resp = self.chat(messages, **kwargs)
        return CompletionResponse(
            text=chat_resp.message.content or "",
            raw=chat_resp.raw,
        )

    def stream_complete(self, prompt: str, **kwargs: Any) -> CompletionResponseGen:
        """Streaming complete — fallback a complete normale."""
        resp = self.complete(prompt, **kwargs)

        def gen() -> Generator[CompletionResponse, None, None]:
            yield resp

        return gen()

    # ---- Helpers ----

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ProgettoRAG",
            "X-Title": "Ermes - Enterprise Knowledge Hub",
        }

    def _build_payload(self, messages: Sequence[ChatMessage], **kwargs: Any) -> dict:
        """Converte messaggi llama_index in payload OpenRouter."""
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": self._map_role(m.role),
                    "content": m.content,
                }
                for m in messages
            ],
            "temperature": kwargs.get("temperature", self._temperature),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "top_p": kwargs.get("top_p", self._top_p),
        }
        # Aggiungi eventuali additional_kwargs
        extra = {**self.additional_kwargs, **kwargs.get("additional_kwargs", {})}
        payload.update(extra)
        return payload

    @staticmethod
    def _map_role(role: MessageRole) -> str:
        """Mappa MessageRole a stringa OpenRouter."""
        mapping = {
            MessageRole.SYSTEM: "system",
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
            MessageRole.FUNCTION: "function",
            MessageRole.TOOL: "tool",
        }
        return mapping.get(role, "user")

    # ---- Async stubs (richiesti da llama_index LLM abstract) ----

    async def achat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        return self.chat(messages, **kwargs)

    async def acomplete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        return self.complete(prompt, **kwargs)

    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponseGen:
        return self.stream_chat(messages, **kwargs)

    async def astream_complete(self, prompt: str, **kwargs: Any) -> CompletionResponseGen:
        return self.stream_complete(prompt, **kwargs)

    # ---- Utilità per ispezione ----

    @property
    def model_name(self) -> str:
        return self._model


# ============================================================
# FACTORY: get_llm() — sceglie automaticamente OpenRouter o Ollama
# ============================================================


def get_llm(
    model_id: str | None = None,
    temperature: float = 0.1,
    request_timeout: float = 120.0,
    context_window: int | None = None,
) -> LLM:
    """Restituisce un'istanza LLM con fallback automatico OpenRouter → Ollama.

    Regole:
    - Se OPENROUTER_API_KEY è configurata, prova OpenRouter PRIMA
    - Se OpenRouter fallisce (timeout, errore, etc.), fallback automatico su Ollama
    - Se OPENROUTER_API_KEY non è configurata, usa direttamente Ollama
    - Il model_id Qwen locale viene mappato su modelli OpenRouter equivalenti

    Args:
        model_id: Nome del modello (default: cfg.DEFAULT_MODEL_ID)
        temperature: Temperatura (default: 0.1)
        request_timeout: Timeout in secondi (default: 120)
        context_window: Finestra di contesto (default: auto)

    Returns:
        Istanza LLM compatibile llama_index
    """
    model_id = model_id or cfg.DEFAULT_MODEL_ID

    if cfg.OPENROUTER_API_KEY:
        # Prova OpenRouter come primary con fallback su Ollama
        api_model = _map_to_openrouter_model(model_id)
        _logger.info(
            "Tentativo OpenRouter (primary): modello richiesto=%s -> API model=%s",
            model_id, api_model,
        )

        try:
            # Verifica raggiungibilità OpenRouter prima di creare LLM
            ok, msg = check_openrouter()
            if ok:
                return OpenRouterLLM(
                    model=api_model,
                    temperature=temperature,
                    request_timeout=request_timeout,
                )
            else:
                _logger.warning("OpenRouter non raggiungibile: %s. Fallback su Ollama locale.", msg)
        except Exception as e:
            _logger.warning("OpenRouter check fallito: %s. Fallback su Ollama locale.", e)

    # Fallback Ollama locale (se OpenRouter non configurato o fallito)
    _logger.info("Fallback Ollama locale: modello=%s", model_id)
    return Ollama(
        model=model_id,
        request_timeout=request_timeout,
        temperature=temperature,
        context_window=context_window or 16384,
        base_url=_ollama_url(),
    )


def _ollama_url() -> str:
    """Costruisce URL Ollama dalla configurazione."""
    host = cfg.OLLAMA_HOST.strip()
    host = host.rstrip("/")
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    return host


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


# ============================================================
# VERIFICA DISPONIBILITÀ MODELLI
# ============================================================


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


def get_available_models() -> list[dict]:
    """Recupera la lista dei modelli disponibili su OpenRouter."""
    if not cfg.OPENROUTER_API_KEY:
        return []

    try:
        import httpx
        response = httpx.get(
            f"{cfg.OPENROUTER_BASE_URL.rstrip('/')}/models",
            headers={
                "Authorization": f"Bearer {cfg.OPENROUTER_API_KEY}",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return [
            {
                "id": m.get("id", ""),
                "name": m.get("name", ""),
                "pricing": m.get("pricing", {}).get("completion", "?"),
                "context_length": m.get("context_length", 0),
            }
            for m in data.get("data", [])
            if m.get("id")  # Filtra modelli senza ID
        ]
    except Exception as e:
        _logger.warning("get_available_models fallito: %s", e)
        return []
