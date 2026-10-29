"""
api/health.py
Health check endpoint.
"""

import logging
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from config import cfg

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


# L'interfaccia sonda /health di continuo e Ollama puo' impiegare oltre 2 secondi
# a elencare i modelli: senza memoria ogni sondaggio pagava l'attesa intera.
# La risposta vale pochi secondi; un errore non viene memorizzato, cosi' il
# ritorno di Ollama si vede subito.
_OLLAMA_CACHE_TTL = 10.0
_ollama_cache: dict[str, tuple[float, tuple[bool, set[str], str]]] = {}


def _ollama_models() -> tuple[bool, set[str], str]:
    """(raggiungibile, modelli installati, messaggio). Un solo giro di rete
    per tutti i controlli che dipendono da un modello."""
    host = cfg.OLLAMA_HOST.rstrip("/")
    cached = _ollama_cache.get(host)
    if cached is not None and time.monotonic() - cached[0] < _OLLAMA_CACHE_TTL:
        return cached[1]
    try:
        response = httpx.get(f"{host}/api/tags", timeout=3)
        response.raise_for_status()
        names = {item.get("name", "") for item in response.json().get("models", [])}
        result = (True, names, "Ollama raggiungibile")
    except httpx.HTTPError as error:
        _ollama_cache.pop(host, None)
        return False, set(), f"Ollama non raggiungibile: {type(error).__name__}"
    _ollama_cache[host] = (time.monotonic(), result)
    return result


def check_ollama(model_id: str) -> tuple[bool, str]:
    """Lightweight check that does not import the legacy RAG stack."""
    reachable, names, message = _ollama_models()
    # Una lista vuota vuol dire "nessun modello installato" (e' lo stato di ogni contenitore di
    # Ollama appena creato), non "lista sconosciuta": il modello manca anche in quel caso.
    if reachable and model_id and model_id not in names:
        return True, f"Ollama raggiungibile; modello {model_id} non installato"
    return reachable, message


def _model_dependent_warnings(reachable: bool, names: set[str]) -> list[str]:
    """Le capacita' ATTIVATE che non possono funzionare con lo stato attuale.

    Il motivo di questa funzione: con il verificatore dell'evidenza acceso e il
    modello configurato non installato, questo endpoint rispondeva "healthy".
    Il verificatore degradava a "non controllato", l'astensione promessa non
    avveniva, e la sola traccia era un avviso nel log per ogni domanda. Un
    modello assente non e' un problema di per se' — in evidence_only non serve
    per scelta — ma lo diventa nel momento in cui qualcosa e' stato acceso
    contando su di lui. Questa funzione distingue i due casi.
    """
    avvisi: list[str] = []

    def manca(model_id: str) -> bool:
        # Prima: `bool(names) and ...`. Con Ollama raggiungibile ma vuoto (contenitore appena
        # creato) nessun modello risultava mancante e /health diceva "healthy" a ricerca semantica
        # spenta. Una lista vuota e' una risposta valida: nessun modello installato.
        return (not reachable) or (model_id not in names)

    verifier_model = getattr(cfg, "EVIDENCE_VERIFIER_MODEL", "") or cfg.DEFAULT_MODEL_ID
    if getattr(cfg, "EVIDENCE_VERIFIER_ENABLED", False) and manca(verifier_model):
        avvisi.append(
            "verifica dell'evidenza attiva ma non eseguibile "
            f"(modello {verifier_model}): le citazioni non vengono controllate e l'astensione "
            "torna al comportamento senza verifica"
        )
    if getattr(cfg, "CONVERSATION_MEMORY_ENABLED", False) and manca(verifier_model):
        avvisi.append(
            f"memoria conversazionale attiva ma non eseguibile (modello {verifier_model}): "
            "le domande di raffinamento non vengono riscritte"
        )
    embed_model = getattr(cfg, "EMBED_MODEL_ID", "")
    if getattr(cfg, "LIBRARY_SEMANTIC_SEARCH_ENABLED", False) and manca(embed_model):
        avvisi.append(
            f"ricerca semantica attiva ma non eseguibile (modello {embed_model}): il recupero e' solo per parole chiave"
        )
    # Stessa logica per l'OCR, che non dipende da un modello ma da un binario:
    # acceso di default, e se manca Tesseract ogni PDF scansionato viene
    # indicizzato vuoto. Senza questo avviso l'unico segnale era una riga di
    # log per documento.
    if getattr(cfg, "OCR_ENABLED", True):
        from core import ocr

        ocr_ok, ocr_reason = ocr.available()
        if not ocr_ok:
            avvisi.append(
                f"OCR attivo ma non eseguibile ({ocr_reason}): le pagine PDF scansionate non vengono indicizzate"
            )
    return avvisi


class HealthResponse(BaseModel):
    """Response model per health check."""

    status: str
    ollama_ok: bool
    ollama_message: str
    openrouter_ok: bool = False
    openrouter_message: str = ""
    modules_available: list[str]
    chroma_ok: bool = True
    library_db_ok: bool = False
    library_storage_ok: bool = False
    disk_free_gb: float = 0.0
    # Capacita' attivate che non possono funzionare. Non vuoto => "degraded",
    # con la ragione leggibile da chi guarda il cruscotto.
    warnings: list[str] = []


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check completo del sistema",
    description=(
        "Esegue un controllo completo dello stato di salute del sistema.\n\n"
        "**Verifiche eseguite:**\n"
        "- **Ollama**: raggiungibilità e modelli installati (risposta memorizzata 10 secondi)\n"
        "- **Database delle biblioteche** e **storage dei documenti**\n"
        "- **Disco**: spazio libero (GB)\n"
        "- **Cloud autorizzato**: solo se l'uso è stato consentito esplicitamente\n\n"
        "**Stati possibili:**\n"
        "- `healthy`: database e storage rispondono e non ci sono avvisi\n"
        "- `degraded`: un componente non risponde, oppure è attiva una funzione che non può funzionare (es. verifica dell'evidenza con modello non installato); la ragione è in `warnings`\n\n"
        "`modules_available` e `chroma_ok` restano nella risposta solo per compatibilità con i client esistenti: sono costanti (`[]` e `true`)."
    ),
)
def health_check():
    # `def`, non `async def`: il corpo fa I/O sincrono (httpx verso Ollama, disco,
    # database). Dichiarato async girava SUL ciclo degli eventi e bloccava tutto
    # il server - file statici e API incluse - per tutta la durata del controllo
    # (oltre 2 secondi con Ollama lento), a ogni sondaggio dell'interfaccia.
    # Cosi' FastAPI lo esegue in un thread e le altre richieste proseguono.
    ollama_reachable, ollama_models, ollama_base_msg = _ollama_models()
    ollama_ok = ollama_reachable
    ollama_msg = ollama_base_msg
    if ollama_reachable and cfg.DEFAULT_MODEL_ID and ollama_models and cfg.DEFAULT_MODEL_ID not in ollama_models:
        ollama_msg = f"Ollama raggiungibile; modello {cfg.DEFAULT_MODEL_ID} non installato"
    warnings = _model_dependent_warnings(ollama_reachable, ollama_models)

    # External cloud is checked only when its use was explicitly authorised for
    # library generation. A configured credential alone must not create traffic.
    openrouter_ok = False
    openrouter_msg = ""
    if getattr(cfg, "LIBRARY_CLOUD_CONSENT", False) and getattr(cfg, "OPENROUTER_API_KEY", ""):
        try:
            from core.ai.llm_bridge import check_openrouter

            openrouter_ok, openrouter_msg = check_openrouter()
        except ImportError:
            openrouter_msg = "llm_bridge non disponibile"

    # `modules_available` e `chroma_ok` restano nella risposta per
    # compatibilita' con i client: appartenevano al motore WinSarp, rimosso
    # dal repository il 18 settembre 2026.
    modules: list[str] = []
    chroma_functional = True

    library_db_ok = False
    try:
        from api.libraries import get_library_store

        store = get_library_store()
        store._backend.execute("SELECT 1")
        library_db_ok = True
    except Exception as error:
        _logger.warning("Health check: database biblioteca non disponibile: %s", error)

    library_storage_ok = False
    try:
        from core.storage_provider import get_storage_provider

        storage_ok, storage_msg = get_storage_provider().check_health()
        library_storage_ok = storage_ok
        if not storage_ok:
            _logger.warning("Health check: storage biblioteca non disponibile: %s", storage_msg)
    except Exception as error:
        _logger.warning("Health check: storage biblioteca non disponibile: %s", error)
        library_storage_ok = False

    # Verifica spazio disco
    import shutil

    disk_usage = shutil.disk_usage(cfg.BASE_DIR)
    disk_free_gb = disk_usage.free / (1024**3)

    # Stato complessivo
    overall_status = "healthy" if library_db_ok and library_storage_ok else "degraded"
    # Una capacita' accesa che non puo' funzionare e' un degrado, anche se il
    # processo serve richieste: chi la ha accesa conta su di lei. Resta 200 —
    # una sonda di readiness non deve spegnere un'istanza che risponde — ma lo
    # stato lo dice, e la ragione e' in `warnings`.
    if warnings:
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        ollama_ok=ollama_ok,
        ollama_message=ollama_msg,
        openrouter_ok=openrouter_ok,
        openrouter_message=openrouter_msg,
        modules_available=modules,
        chroma_ok=chroma_functional,
        library_db_ok=library_db_ok,
        library_storage_ok=library_storage_ok,
        disk_free_gb=round(disk_free_gb, 2),
        warnings=warnings,
    )


@router.get(
    "/v1/health",
    tags=["Health (v1)"],
    summary="[v1] Health check completo",
    description="Versione versionata dell'health check (disponibile anche su /health)",
)
def health_check_v1():
    return health_check()
