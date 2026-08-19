"""
api/query.py
Query RAG, streaming, cache.
"""
import json
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import cfg
from core.error_handler import ErrorLevel, handle_index_error, log_error
from legacy_winsarp.core.rag_engine import (
    build_chat_engine,
    get_index,
    get_source_nodes,
    score_to_confidence,
)
from legacy_winsarp.core.rag_engine import check_ollama_uncached as check_ollama

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Query"])


class SourceNode(BaseModel):
    """Modello per nodo sorgente recuperato."""
    source: str
    score: float
    text: str


class QueryRequest(BaseModel):
    """Request model per query RAG."""
    query: str = Field(..., min_length=1, max_length=2000, description="Domanda in linguaggio naturale")
    module: str = Field(..., description="Nome del modulo/document area")
    model: str | None = Field(default=None, description="Modello LLM (opzionale, usa default)")
    formula_only: bool | None = Field(default=False, description="Se true, ritorna solo la formula estratta (solo per WinSarp)")


class QueryResponse(BaseModel):
    """Response model per query RAG."""
    answer: str
    sources: list[SourceNode]
    confidence: str
    confidence_score: float
    model: str
    module: str
    elapsed_seconds: float


@router.post("/query", response_model=QueryResponse,
             summary="Esegue una query RAG sul modulo specificato",
             description="Esegue una query RAG sul modulo specificato.")
async def query(request: QueryRequest, req: Request, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from api.auth import _rate_limit, _verify_api_key
    from api import _get_modules, _resolve_module_name

    _rate_limit(req)
    start_time = time.time()
    try:
        # Verifica Ollama
        ollama_ok, ollama_message = check_ollama(cfg.DEFAULT_MODEL_ID)
        if not ollama_ok:
            log_error("API: Ollama non disponibile", level=ErrorLevel.ERROR, context={"detail": ollama_message})
            raise HTTPException(status_code=503, detail=f"Ollama non disponibile: {ollama_message}")

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

        # Costruisci chat engine e esegui query
        try:
            model_id = request.model or cfg.DEFAULT_MODEL_ID
            from api import _get_modules
            modules = _get_modules()

            # Check response cache first
            from core.ai.response_cache import get_response_cache
            cache = get_response_cache()
            cached = cache.get(request.query, model_id, module_name)
            if cached:
                _logger.info("Cache HIT per query: %s", request.query[:50])
                elapsed = time.time() - start_time
                return QueryResponse(
                    answer=cached.response,
                    sources=[
                        SourceNode(source=s.get("source", ""), score=s.get("score", 0), text=s.get("text", ""))
                        for s in (cached.sources if isinstance(cached.sources, list) else [])
                    ] if cached.sources else [],
                    confidence=cached.confidence,
                    confidence_score=cached.confidence_score,
                    model=cached.model,
                    module=cached.module,
                    elapsed_seconds=elapsed,
                )

            chat_engine = build_chat_engine(module_name, model_id, index, formula_only=getattr(request, "formula_only", False), modules=modules)
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

            # Cache the response
            cache.set(
                query=request.query,
                model=model_id,
                module=module_name,
                response=answer,
                sources=[{"source": s.source, "score": s.score, "text": s.text} for s in sources],
                confidence=confidence,
                confidence_score=top_score,
            )

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


@router.get("/modules", tags=["Modules"],
            summary="Elenco moduli documentali disponibili",
            description="Restituisce l'elenco di tutti i moduli documentali configurati.")
async def list_modules(_auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from api import _list_available_modules
    return {"modules": _list_available_modules()}


# ── Cache endpoints ──

@router.get("/cache/stats", tags=["Cache"],
            summary="Statistiche cache risposte",
            description="Restituisce le statistiche della cache risposte.")
async def cache_stats(_auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from core.ai.response_cache import get_response_cache
    return get_response_cache().stats()


@router.post("/cache/clear", tags=["Cache"],
             summary="Svuota la cache",
             description="Svuota completamente la cache delle risposte.")
async def cache_clear(_auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from core.ai.response_cache import get_response_cache
    cache = get_response_cache()
    cache.clear()
    return {"message": "Cache svuotata", "stats": cache.stats()}


# ── Streaming chat ──

@router.post("/api/chat/stream", tags=["Query"])
async def stream_query(request: QueryRequest, req: Request, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from api.auth import _rate_limit, _verify_api_key
    from api import _get_modules, _resolve_module_name, _list_available_modules

    _rate_limit(req)
    model_id = request.model or cfg.DEFAULT_MODEL_ID
    module_name = _resolve_module_name(request.module)
    index = get_index(module_name, model_id, cfg.DOCS_DIR, cfg.CHROMA_DIR, cfg.HASH_FILE)
    if index is None:
        raise HTTPException(status_code=404, detail="Nessun documento indicizzato per questo modulo")

    chat_engine = build_chat_engine(module_name, model_id, index, formula_only=getattr(request, "formula_only", False), modules=_get_modules())

    # INTEGRAZIONE SEMANTIC ROUTING PER WINSARP
    routing_result = None
    if module_name == "WinSarp":
        try:
            catalog = []
            try:
                import json
                cat_path = os.path.join(cfg.BASE_DIR, "data", "winsarp_catalog.json")
                if os.path.exists(cat_path):
                    with open(cat_path, "r", encoding="utf-8") as f:
                        catalog = json.load(f)
            except Exception as e:
                _logger.warning("Errore caricamento catalogo per routing: %s", e)

            from legacy_winsarp.core.intent_router import route_and_process
            routing_result = route_and_process(
                user_request=request.query,
                model_id=model_id,
                catalog_formulas=catalog,
            )
        except Exception as e:
            _logger.error("Errore semantic routing: %s", e)

    async def sse_generator():
        try:
            if routing_result and routing_result.get("action") in ["generation", "retrieval"]:
                _logger.info("Semantic router: azione '%s' eseguita", routing_result.get("action"))
                if routing_result.get("action") == "generation":
                    spec = routing_result.get("specifica_formula", {})
                    msg = f"Formula generata:\n{json.dumps(spec, indent=2, ensure_ascii=False)}"
                    yield f"data: {msg}\n\n"
                else:
                    f = routing_result.get("miglior_formula")
                    msg = f"Formula trovata nel catalogo:\n{f.get('codice', 'N/D')}\n\nSpiegazione: {f.get('spiegazione', '')}"
                    yield f"data: {msg}\n\n"
                yield "data: [DONE]\n\n"
                return

            response = chat_engine.stream_chat(request.query)
            for token_text in response.response_gen:
                yield f"data: {token_text}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")