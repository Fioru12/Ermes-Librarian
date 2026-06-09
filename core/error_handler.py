"""
error_handler.py
Gestione centralizzata degli errori critici del sistema.
Evita che l'app crashi e mostra messaggi chiari all'utente.
"""
import logging
import time
from enum import Enum
from typing import Any

from config import cfg

_logger = logging.getLogger(__name__)


class ErrorLevel(Enum):
    """Livelli di severità degli errori."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AppError(Exception):
    """Errore applicativo custom con context."""
    def __init__(self, message: str, level: ErrorLevel = ErrorLevel.ERROR, context: dict[str, Any] | None = None):
        self.message = message
        self.level = level
        self.context = context or {}
        super().__init__(self.message)


class OllamaError(AppError):
    """Errore legato a Ollama non disponibile."""
    pass


class RAGIndexError(AppError):
    """Errore nella generazione dell'indice RAG."""
    pass


class DocumentError(AppError):
    """Errore nel caricamento/parsing documenti."""
    pass


class ConfigError(AppError):
    """Errore nella configurazione."""
    pass


# ============================================================
# HANDLERS PER ERRORI SPECIFICI
# ============================================================

def handle_ollama_error(error: Exception) -> tuple[bool, str]:
    """
    Gestisce errori legati a Ollama.

    Returns:
        (success: bool, message: str)
    """
    error_str = str(error).lower()

    if "not found" in error_str or "connection refused" in error_str:
        msg = (
            "❌ Ollama non è in esecuzione.\n\n"
            "**Azione richiesta:**\n"
            "1. Apri Ollama (lo trovi nel menu Start)\n"
            "2. Attendi che avvii completamente\n"
            "3. Ricarica questa pagina"
        )
        _logger.warning("Ollama non disponibile: %s", error)
        return False, msg

    if "timeout" in error_str:
        msg = (
            "❌ Ollama non risponde (timeout).\n\n"
            "Possibili cause:\n"
            "• Ollama è sovraccarico\n"
            "• Problema di rete\n"
            "• Modelli non caricati\n\n"
            "**Azione:** Riprova tra 10 secondi"
        )
        _logger.warning("Ollama timeout: %s", error)
        return False, msg

    if "model" in error_str:
        msg = (
            "❌ Modello AI non trovato in Ollama.\n\n"
            "Modelli richiesti:\n"
            f"• {cfg.DEFAULT_MODEL_ID} (LLM)\n"
            f"• {cfg.EMBED_MODEL_ID} (Embeddings)\n\n"
            "**Azione:** Scarica i modelli da Ollama"
        )
        _logger.error("Modello mancante: %s", error)
        return False, msg

    msg = f"❌ Errore Ollama: {str(error)}"
    _logger.error("Errore Ollama generico: %s", error)
    return False, msg


def handle_index_error(error: Exception, modulo: str = "sconosciuto") -> tuple[bool, str]:
    """
    Gestisce errori nella generazione dell'indice.

    Returns:
        (success: bool, message: str)
    """
    error_str = str(error).lower()

    if "embedding" in error_str or "dimension" in error_str:
        msg = (
            f"❌ Errore generazione embeddings per '{modulo}'.\n\n"
            "Possibili cause:\n"
            "• Ollama non è in running\n"
            "• Modello embedding non caricato\n"
            "• Documenti corrotti\n\n"
            "**Azione:** Verifica Ollama e ricarica"
        )
        _logger.error("Embedding error per %s: %s", modulo, error)
        return False, msg

    if "disk" in error_str or "space" in error_str:
        msg = (
            "❌ Spazio disco insufficiente.\n\n"
            "**Azione richiesta:**\n"
            "1. Libera spazio sul disco\n"
            "2. Riprova l'operazione"
        )
        _logger.error("Spazio disco insufficiente: %s", error)
        return False, msg

    if "lock" in error_str or "timeout" in error_str:
        msg = (
            "❌ Operazione in timeout (DB bloccato).\n\n"
            "Possibili cause:\n"
            "• Altra operazione in corso\n"
            "• File system lento\n\n"
            "**Azione:** Riprova tra 10 secondi"
        )
        _logger.warning("DB lock timeout: %s", error)
        return False, msg

    msg = f"❌ Errore generazione indice: {str(error)}"
    _logger.error("Errore indice generico per %s: %s", modulo, error)
    return False, msg


def handle_document_error(error: Exception, filename: str = "sconosciuto") -> tuple[bool, str]:
    """
    Gestisce errori nel caricamento documenti.

    Returns:
        (success: bool, message: str)
    """
    error_str = str(error).lower()

    if "not found" in error_str or "no such file" in error_str:
        msg = f"❌ Documento non trovato: {filename}"
        _logger.warning("Documento non trovato: %s", filename)
        return False, msg

    if "permission" in error_str or "denied" in error_str:
        msg = (
            f"❌ Permessi insufficienti per leggere: {filename}\n\n"
            "**Azione:** Verifica i permessi del file"
        )
        _logger.error("Permission denied per %s: %s", filename, error)
        return False, msg

    if "corrupted" in error_str or "decode" in error_str or "encoding" in error_str:
        msg = (
            f"❌ Documento danneggiato o encoding non supportato: {filename}\n\n"
            "Formati supportati: PDF, DOCX, TXT (UTF-8)"
        )
        _logger.error("Documento corrotto %s: %s", filename, error)
        return False, msg

    msg = f"❌ Errore lettura documento '{filename}': {str(error)}"
    _logger.error("Errore documento generico per %s: %s", filename, error)
    return False, msg


def handle_config_error(error: Exception, config_key: str = "sconosciuto") -> tuple[bool, str]:
    """
    Gestisce errori di configurazione.

    Returns:
        (success: bool, message: str)
    """
    msg = (
        f"❌ Errore configurazione: {config_key}\n\n"
        f"Dettagli: {str(error)}\n\n"
        "**Azione:** Contatta l'amministratore"
    )
    _logger.error("Config error per %s: %s", config_key, error)
    return False, msg


# ============================================================
# RETRY UTILITY
# ============================================================

def retry_on_error(
    fn,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry=None,
):
    """
    Esegue fn con retry ed exponential backoff.

    Args:
        fn: Funzione da eseguire (zero-arg).
        max_attempts: Tentativi massimi (default 3).
        delay: Attesa iniziale in secondi (default 1.0).
        backoff: Fattore di moltiplicazione per delay (default 2.0).
        exceptions: Eccezioni su cui fare retry (default any Exception).
        on_retry: Callable(attempt, error) opzionale per logging.

    Returns:
        Risultato di fn().

    Raises:
        L'ultima eccezione incontrata dopo max_attempts fallimenti.
    """
    last_exc = None
    wait = delay
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except exceptions as e:
            last_exc = e
            if attempt == max_attempts:
                raise
            if on_retry:
                on_retry(attempt, e)
            _logger.warning("Retry %d/%d per %s: %s", attempt, max_attempts, fn.__name__, e)
            time.sleep(wait)
            wait *= backoff
    raise last_exc  # pragma: no cover


# ============================================================
# SAFE WRAPPERS PER OPERAZIONI CRITICHE
# ============================================================

def safe_call(
    fn,
    *args,
    error_handler=None,
    error_level: ErrorLevel = ErrorLevel.ERROR,
    default_return=None,
    **kwargs
) -> Any:
    """
    Wrapper per eseguire funzioni con error handling generico.

    Args:
        fn: Funzione da eseguire
        error_handler: Callback per custom handling
        error_level: Livello di log
        default_return: Valore di default se errore

    Returns:
        Risultato di fn() o default_return se errore
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if error_handler:
            error_handler(e)

        if error_level == ErrorLevel.CRITICAL:
            _logger.critical(f"Critical error in {fn.__name__}: {e}", exc_info=True)
        elif error_level == ErrorLevel.ERROR:
            _logger.error(f"Error in {fn.__name__}: {e}", exc_info=True)
        elif error_level == ErrorLevel.WARNING:
            _logger.warning(f"Warning in {fn.__name__}: {e}")
        else:
            _logger.info(f"Info in {fn.__name__}: {e}")

        return default_return


# ============================================================
# LOG UTILITIES
# ============================================================

def log_error(
    message: str,
    error: Exception | None = None,
    level: ErrorLevel = ErrorLevel.ERROR,
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Log centralizzato degli errori con context.

    Returns:
        Dict con error info
    """
    context = context or {}
    error_dict = {
        "message": message,
        "error": str(error) if error else None,
        "level": level.value,
        "context": context,
    }

    if level == ErrorLevel.CRITICAL:
        _logger.critical(message, exc_info=error, extra=context)
    elif level == ErrorLevel.ERROR:
        _logger.error(message, exc_info=error, extra=context)
    elif level == ErrorLevel.WARNING:
        _logger.warning(message, extra=context)
    else:
        _logger.info(message, extra=context)

    return error_dict
