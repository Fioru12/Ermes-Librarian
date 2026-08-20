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


def check_ollama(model_id: str) -> tuple[bool, str]:
    """Lightweight check that does not import the legacy RAG stack."""
    try:
        response = httpx.get(f"{cfg.OLLAMA_HOST.rstrip('/')}/api/tags", timeout=3)
        response.raise_for_status()
        names = {item.get("name", "") for item in response.json().get("models", [])}
        if model_id and names and model_id not in names:
            return True, f"Ollama raggiungibile; modello {model_id} non installato"
        return True, "Ollama raggiungibile"
    except httpx.HTTPError as error:
        return False, f"Ollama non raggiungibile: {type(error).__name__}"


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


@router.get("/health", response_model=HealthResponse,
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
            ))
async def health_check():
    ollama_ok, ollama_msg = check_ollama(cfg.DEFAULT_MODEL_ID)

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
        library_storage_dir = getattr(cfg, "LIBRARY_STORAGE_DIR", os.path.join(getattr(cfg, "BASE_DIR", "."), "storage", "libraries"))
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
    )


@router.get("/v1/health", tags=["Health (v1)"],
            summary="[v1] Health check completo",
            description="Versione versionata dell'health check (disponibile anche su /health)")
async def health_check_v1():
    return await health_check()
