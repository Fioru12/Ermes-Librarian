"""
api/health.py
Health check endpoint.
"""

import logging
import os
import sqlite3

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from config import cfg

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


def _ollama_models() -> tuple[bool, set[str], str]:
    """(raggiungibile, modelli installati, messaggio). Un solo giro di rete
    per tutti i controlli che dipendono da un modello."""
    try:
        response = httpx.get(f"{cfg.OLLAMA_HOST.rstrip('/')}/api/tags", timeout=3)
        response.raise_for_status()
        names = {item.get("name", "") for item in response.json().get("models", [])}
        return True, names, "Ollama raggiungibile"
    except httpx.HTTPError as error:
        return False, set(), f"Ollama non raggiungibile: {type(error).__name__}"


def check_ollama(model_id: str) -> tuple[bool, str]:
    """Lightweight check that does not import the legacy RAG stack."""
    reachable, names, message = _ollama_models()
    if reachable and model_id and names and model_id not in names:
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
        return (not reachable) or (bool(names) and model_id not in names)

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
        "- **Ollama**: Connessione e disponibilità modelli (LLM + Embeddings)\n"
        "- **ChromaDB**: Esistenza directory + funzionalità lettura/scrittura collezioni\n"
        "- **Disco**: Spazio libero su disco (GB)\n"
        "- **Moduli**: Elenco moduli documentali disponibili\n\n"
        "**Stati possibili:**\n"
        "- `healthy`: Tutti i sistemi operativi\n"
        "- `degraded`: Alcuni componenti degradati (es. Ollama lento, ChromaDB read-only)"
    ),
)
async def health_check():
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

    modules: list[str] = []
    chroma_functional = False
    if getattr(cfg, "ENABLE_LEGACY_WINSARP", False):
        from api import _list_available_modules

        modules = _list_available_modules()
        try:
            import chromadb

            test_client = chromadb.PersistentClient(path=cfg.CHROMA_DIR)
            test_client.list_collections()
            chroma_functional = True
        except Exception as e:
            _logger.warning("Health check: ChromaDB esiste ma non funziona: %s", e)

    library_db_ok = False
    try:
        base_dir = getattr(cfg, "BASE_DIR", ".")
        database_path = getattr(cfg, "LIBRARY_DB_PATH", os.path.join(base_dir, "data", "ermes_knowledge.sqlite3"))
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            connection.execute("SELECT 1")
        library_db_ok = True
    except (OSError, sqlite3.Error) as error:
        _logger.warning("Health check: database biblioteca non disponibile: %s", error)

    try:
        library_storage_dir = getattr(
            cfg, "LIBRARY_STORAGE_DIR", os.path.join(getattr(cfg, "BASE_DIR", "."), "storage", "libraries")
        )
        os.makedirs(library_storage_dir, exist_ok=True)
        library_storage_ok = os.path.isdir(library_storage_dir) and os.access(library_storage_dir, os.W_OK)
    except OSError as error:
        _logger.warning("Health check: storage biblioteca non disponibile: %s", error)
        library_storage_ok = False

    # Verifica spazio disco
    import shutil

    disk_usage = shutil.disk_usage(cfg.BASE_DIR)
    disk_free_gb = disk_usage.free / (1024**3)

    # Stato complessivo
    if getattr(cfg, "ENABLE_LEGACY_WINSARP", False):
        overall_status = "healthy" if library_db_ok and library_storage_ok and chroma_functional else "degraded"
    else:
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
async def health_check_v1():
    return await health_check()
