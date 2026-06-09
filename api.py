"""
api.py
API REST FastAPI per integrazione Ermes - Enterprise Knowledge Hub.
Permette query RAG via HTTP per integrazioni esterne (Teams, Slack, custom apps).
"""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from config import cfg
from core.error_handler import ErrorLevel, handle_index_error, log_error
from core.rag_engine import (
    build_chat_engine,
    get_index,
    get_source_nodes,
    init_llama_settings,
    score_to_confidence,
)
from core.rag_engine import (
    check_ollama_uncached as check_ollama,
)
from core.rate_limiter import get_rate_limiter
from modules import discover_modules

_logger = logging.getLogger(__name__)

modules_cache = None


def _get_modules():
    global modules_cache
    if modules_cache is None:
        modules_cache = discover_modules()
    return modules_cache


# Security
security = HTTPBearer()

# Pydantic models
class QueryRequest(BaseModel):
    """Request model per query RAG."""
    query: str = Field(..., min_length=1, max_length=2000, description="Domanda in linguaggio naturale")
    module: str = Field(..., description="Nome del modulo/document area")
    model: str | None = Field(default=None, description="Modello LLM (opzionale, usa default)")
    formula_only: bool | None = Field(default=False, description="Se true, ritorna solo la formula estratta (solo per WinSarp)")


class SourceNode(BaseModel):
    """Modello per nodo sorgente recuperato."""
    source: str
    score: float
    text: str


class QueryResponse(BaseModel):
    """Response model per query RAG."""
    answer: str
    sources: list[SourceNode]
    confidence: str
    confidence_score: float
    model: str
    module: str
    elapsed_seconds: float


class HealthResponse(BaseModel):
    """Response model per health check."""
    status: str
    ollama_ok: bool
    ollama_message: str
    modules_available: list[str]
    chroma_ok: bool = True
    disk_free_gb: float = 0.0


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inizializza LlamaIndex all'avvio."""
    init_llama_settings()
    yield


# FastAPI app
app = FastAPI(
    title="Ermes - Enterprise Knowledge Hub API",
    description="API REST per query RAG su documentazione aziendale",
    version="1.0.0",
    lifespan=lifespan,
)


# Rate limiter
rate_limiter = get_rate_limiter()


def _list_available_modules() -> list[str]:
    if not os.path.exists(cfg.DOCS_DIR):
        return []
    return sorted(
        d for d in os.listdir(cfg.DOCS_DIR)
        if os.path.isdir(os.path.join(cfg.DOCS_DIR, d))
    )


def _resolve_module_name(module_name: str) -> str:
    normalized = (module_name or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Nome modulo mancante")

    if any(sep in normalized for sep in ("/", "\\")) or ".." in normalized:
        raise HTTPException(status_code=400, detail="Nome modulo non valido")

    modules = _list_available_modules()
    if normalized not in modules:
        raise HTTPException(status_code=404, detail=f"Modulo '{normalized}' non trovato")

    return normalized


def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Verifica API key per autenticazione usando timing-safe comparison.

    L'API key deve essere configurata via ERMES_API_KEY in config.py o .env.
    Se non configurata, l'API è disabilitata per sicurezza.

    Usage:
        curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost:8503/query
    """
    import hmac

    api_key = cfg.API_KEY

    # Se API key non configurata, disabilita l'API per sicurezza
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="API disabilitata: configura ERMES_API_KEY per abilitare l'accesso"
        )

    provided_key = credentials.credentials

    # Verifica che la key corrisponda usando timing-safe comparison
    # Evita timing attack vulnerabilities
    if not hmac.compare_digest(provided_key, api_key):
        _logger.warning("API authentication failed: invalid key")
        raise HTTPException(
            status_code=401,
            detail="API key non valida"
        )

    return provided_key


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint migliorato.
    Fornisce stato completo del sistema per monitoring.
    Verifica reale funzionamento di Ollama e ChromaDB.

    Returns:
        HealthResponse: Stato del sistema (healthy/degraded)
    """
    ollama_ok, ollama_msg = check_ollama(cfg.DEFAULT_MODEL_ID)

    # Lista moduli disponibili
    modules = _list_available_modules()

    # Stato database ChromaDB
    chroma_ok = os.path.exists(cfg.CHROMA_DIR)

    # Verifica reale funzionamento ChromaDB se esiste
    chroma_functional = False
    if chroma_ok:
        try:
            import chromadb
            # Tenta di creare un client temporaneo per verificare funzionamento
            test_client = chromadb.PersistentClient(path=cfg.CHROMA_DIR)
            # Lista collezioni per verificare accesso
            test_client.list_collections()
            chroma_functional = True
        except Exception as e:
            _logger.warning("Health check: ChromaDB esiste ma non funziona: %s", e)
            chroma_ok = False

    # Spazio disco disponibile
    import shutil
    disk_usage = shutil.disk_usage(cfg.BASE_DIR)
    disk_free_gb = disk_usage.free / (1024**3)

    # Stato complessivo
    overall_status = "healthy" if ollama_ok and chroma_functional else "degraded"

    return HealthResponse(
        status=overall_status,
        ollama_ok=ollama_ok,
        ollama_message=ollama_msg,
        modules_available=modules,
        chroma_ok=chroma_functional,
        disk_free_gb=round(disk_free_gb, 2),
    )


@app.post("/query", response_model=QueryResponse, tags=["Query"])
async def query_rag(
    request: QueryRequest,
    token: str = Depends(verify_auth)
):
    """
    Endpoint principale per query RAG.

    Esegue una query sul modulo specificato e restituisce risposta + fonti.

    Args:
        request: QueryRequest con module, query, e model opzionale
        token: API key per autenticazione

    Returns:
        QueryResponse: Risposta con answer, sources, confidence, e metadata

    Raises:
        HTTPException: 401 se autenticazione fallita, 429 se rate limit, 503 se Ollama non disponibile
    """
    start_time = time.time()

    try:
        # Rate limiting check
        identifier = f"api_{token[:8]}"
        allowed, reason = rate_limiter.check_request_rate(identifier)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason)

        # Verifica Ollama
        ollama_ok, ollama_msg = check_ollama(cfg.DEFAULT_MODEL_ID)
        if not ollama_ok:
            log_error("API: Ollama non disponibile", level=ErrorLevel.ERROR, context={"detail": ollama_msg})
            raise HTTPException(status_code=503, detail=f"Ollama non disponibile: {ollama_msg}")

        # Verifica e risolvi modulo
        try:
            module_name = _resolve_module_name(request.module)
        except HTTPException:
            log_error(f"API: Modulo non valido: {request.module}", level=ErrorLevel.WARNING)
            raise

        # Ottieni indice con error handling
        try:
            model_id = request.model or cfg.DEFAULT_MODEL_ID
            index = get_index(
                module_name,
                model_id,
                cfg.DOCS_DIR,
                cfg.CHROMA_DIR,
                cfg.HASH_FILE,
            )

            if index is None:
                log_error(f"API: Nessun documento per modulo {module_name}", level=ErrorLevel.WARNING)
                raise HTTPException(
                    status_code=404,
                    detail=f"Nessun documento indicizzato per modulo '{module_name}'"
                )
        except HTTPException:
            raise
        except Exception as e:
            ok, msg = handle_index_error(e, module_name)
            log_error("API: Errore indice RAG", error=e, level=ErrorLevel.ERROR, context={"module": module_name})
            raise HTTPException(status_code=500, detail=msg if not ok else str(e))

        # Costruisci chat engine e esegui query con error handling
        try:
            chat_engine = build_chat_engine(module_name, model_id, index, formula_only=getattr(request, "formula_only", False), modules=_get_modules())
            response = chat_engine.chat(request.query)
            answer = response.response

            # If caller requested formula-only and module supports it, extract code
            formula_only = getattr(request, "formula_only", False)
            _mods = _get_modules()
            _mod = _mods.get(module_name)
            if formula_only and _mod is not None and _mod.has_formula_only():
                parsed = _mod.parse_response(answer)
                if parsed.get("code"):
                    answer = parsed["code"]
                else:
                    answer = "Nel catalogo non e' presente una formula per questo caso."

            # Recupera fonti
            sources_data = get_source_nodes(module_name, model_id, index, request.query)
            sources = [
                SourceNode(source=s["source"], score=s["score"], text=s["text"])
                for s in sources_data
            ]

            # Calcola confidenza
            top_score = max((s.get("score", 0.0) for s in sources_data), default=0.0)
            confidence = score_to_confidence(top_score)

            elapsed = time.time() - start_time

            return QueryResponse(
                answer=answer,
                sources=sources,
                confidence=confidence,
                confidence_score=top_score,
                model=model_id,
                module=module_name,
                elapsed_seconds=elapsed,
            )
        except Exception as e:
            log_error("API: Errore esecuzione query", error=e, level=ErrorLevel.ERROR,
                     context={"module": module_name, "query": request.query[:100]})
            raise HTTPException(status_code=500, detail=f"Errore query RAG: {str(e)[:100]}")

    except HTTPException:
        raise
    except Exception as e:
        log_error("API: Errore non gestito", error=e, level=ErrorLevel.CRITICAL)
        raise HTTPException(status_code=500, detail="Errore interno del server")


@app.get("/modules", tags=["Modules"])
async def list_modules(token: str = Depends(verify_auth)):
    """
    Lista tutti i moduli disponibili.

    Returns:
        Dict con lista dei nomi dei moduli disponibili
    """
    return {"modules": _list_available_modules()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=cfg.HOST, port=cfg.PORT + 1)  # Porta diversa da Streamlit
