"""
api/__init__.py
API REST FastAPI per integrazione Ermes - Enterprise Knowledge Hub.
Package suddiviso in moduli per manutenibilità.

Moduli:
    auth        → Autenticazione JWT + RBAC + rate limiter
    health      → Health check
    query       → Query RAG, streaming, cache
    backup      → Backup management
    users       → User management (admin)
    audit       → Audit log
    formule     → Formula WinSarp generation, catalog, validation
    documents   → Document upload/delete/reindex
    models      → Models listing
    providers   → Provider management
    graph       → Knowledge graph
    integrations → External chat integrations (Teams, Slack, Telegram)
    shutdown    → Shutdown endpoint
"""

import asyncio
import httpx
import logging
import os
import re
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from config import cfg
from core.governance import append_audit

_logger = logging.getLogger(__name__)

# ── Prometheus metrics ──
_metrics_lock = threading.Lock()
_request_counts = defaultdict(int)
_request_durations = defaultdict(float)

# ── HTTP client globale ──
_http_client: httpx.AsyncClient | None = None  # noqa: F821 — importato dopo

# ── Modules cache ──
modules_cache = None
_modules_lock = threading.Lock()


def _get_modules():
    global modules_cache
    if modules_cache is None:
        with _modules_lock:
            if modules_cache is None:
                from modules import discover_modules
                modules_cache = discover_modules()
    return modules_cache


def _list_available_modules() -> list[str]:
    if not os.path.exists(cfg.DOCS_DIR):
        return []
    return sorted(
        d for d in os.listdir(cfg.DOCS_DIR)
        if os.path.isdir(os.path.join(cfg.DOCS_DIR, d)) and d.lower() != "libraries"
    )


def _resolve_module_name(module_name: str) -> str:
    from fastapi import HTTPException
    normalized = (module_name or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Nome modulo mancante")
    if any(sep in normalized for sep in ("/", "\\")) or ".." in normalized:
        raise HTTPException(status_code=400, detail="Nome modulo non valido")
    modules = _list_available_modules()
    if normalized not in modules:
        raise HTTPException(status_code=404, detail=f"Modulo '{normalized}' non trovato")
    return normalized


def _get_http_client() -> httpx.AsyncClient:  # noqa: F821
    global _http_client
    if _http_client is None:
        import httpx
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestisce il ciclo di vita dell'applicazione FastAPI."""
    if getattr(cfg, "ENABLE_LEGACY_WINSARP", False):
        _logger.warning(
            "ENABLE_LEGACY_WINSARP e' attivo: gli endpoint WinSarp legacy in legacy_winsarp/api/ "
            "sono esposti (nessun controllo ACL per libreria su quel percorso). Flag pensata solo "
            "per sviluppo/debug locale — non abilitarla in un deployment condiviso o in produzione. "
            "Vedi legacy_winsarp/README.md e docs/AUDIT_2026-08-19.md."
        )
        from legacy_winsarp.core.rag_engine import init_llama_settings
        init_llama_settings()

    # Recover uploads accepted before a local restart. Jobs are persisted in
    # SQLite and claimed atomically, so this also remains safe when a worker is
    # introduced later.
    try:
        from api.libraries import get_library_store
        from core.ingestion_service import process_ingestion_job
        ingestion_store = get_library_store()
        for job in ingestion_store.pending_ingestion_jobs():
            asyncio.create_task(asyncio.to_thread(process_ingestion_job, ingestion_store, job["id"], cfg.LIBRARY_STORAGE_DIR))
    except Exception as error:
        _logger.warning("Recupero job ingestion fallito: %s", error)

    # ── Rotazione log audit all'avvio ──
    try:
        from api.audit import _rotate_audit_logs
        _rotate_audit_logs(cfg.AUDIT_FILE, retention_days=90)
    except Exception as e:
        _logger.warning("Audit rotation startup fallita: %s", e)

    # ── Avvia backup scheduler se abilitato ──
    _backup_task: asyncio.Task | None = None

    async def _backup_scheduler():
        interval_hours = cfg.BACKUP_INTERVAL_HOURS
        _logger.info("Backup scheduler avviato (ogni %d ore)", interval_hours)
        while True:
            try:
                await asyncio.sleep(interval_hours * 3600)
                from core.backup_manager import create_backup
                result = create_backup(label="scheduled")
                _logger.info("Backup schedulato completato: %s", result.get("name", "?"))
                append_audit(cfg.AUDIT_FILE, "backup_scheduled", "system", {"name": result.get("name", "")})
            except asyncio.CancelledError:
                break
            except Exception as e:
                _logger.error("Backup schedulato fallito: %s", e)

    if cfg.BACKUP_ENABLED:
        _backup_task = asyncio.create_task(_backup_scheduler())

    yield

    if _backup_task is not None:
        _backup_task.cancel()
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


# ── App FastAPI ──
app = FastAPI(
    title="Ermes - Enterprise Knowledge Hub API",
    description="API REST per query RAG su documentazione aziendale",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # A conservative fallback also keeps small, isolated test/deployment
    # configurations usable while preserving the explicit production setting.
    allow_origins=list(getattr(cfg, "CORS_ORIGINS", ("http://localhost:3000",))),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Prometheus metrics middleware ──
@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    path = request.url.path
    if path == "/metrics":
        return await call_next(request)

    normalized_path = re.sub(r'/[0-9a-fA-F-]{36}', '/{uuid}', path)
    normalized_path = re.sub(r'/api/users/[a-zA-Z0-9_\-]+', '/api/users/{username}', normalized_path)
    normalized_path = re.sub(r'/api/documents/[a-zA-Z0-9_\-\.]+', '/api/documents/{filename}', normalized_path)
    normalized_path = re.sub(r'/api/formula/cancel/[a-zA-Z0-9_\-]+', '/api/formula/cancel/{request_id}', normalized_path)
    normalized_path = re.sub(r'/api/winsarp/catalog/[a-zA-Z0-9_\-]+', '/api/winsarp/catalog/{formula_id}', normalized_path)

    start_time = __import__('time').perf_counter()
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as e:
        status_code = 500
        raise e
    finally:
        import time
        duration = time.perf_counter() - start_time
        method = request.method
        with _metrics_lock:
            _request_counts[(method, normalized_path, str(status_code))] += 1
            _request_durations[(method, normalized_path)] += duration


@app.get("/metrics", tags=["Monitoring"], include_in_schema=True)
def prometheus_metrics():
    """Ritorna le metriche del sistema in formato Prometheus."""
    lines = []
    lines.append("# HELP ermes_http_requests_total Numero totale di richieste HTTP gestite.")
    lines.append("# TYPE ermes_http_requests_total counter")
    with _metrics_lock:
        for (method, path, status), count in sorted(_request_counts.items()):
            lines.append(f'ermes_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')
    lines.append("# HELP ermes_http_request_duration_seconds_sum Somma totale del tempo di risposta.")
    lines.append("# TYPE ermes_http_request_duration_seconds_sum counter")
    with _metrics_lock:
        for (method, path), total_time in sorted(_request_durations.items()):
            lines.append(f'ermes_http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {total_time:.6f}')
    lines.append("# HELP ermes_http_request_duration_seconds_count Numero totale di campioni.")
    lines.append("# TYPE ermes_http_request_duration_seconds_count counter")
    with _metrics_lock:
        path_counts = defaultdict(int)
        for (method, path, status), count in _request_counts.items():
            path_counts[(method, path)] += count
        for (method, path), count in sorted(path_counts.items()):
            lines.append(f'ermes_http_request_duration_seconds_count{{method="{method}",path="{path}"}} {count}')
    lines.append("# HELP ermes_system_info Metadati di sistema dell'istanza Ermes.")
    lines.append("# TYPE ermes_system_info gauge")
    lines.append(f'ermes_system_info{{version="2.1.0",python_version="3.11",environment="enterprise"}} 1')
    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# ── Import moduli ──
from api.auth import router as auth_router
from api.health import router as health_router
from api.backup import router as backup_router
from api.users import router as users_router
from api.audit import router as audit_router
from api.models import router as models_router
from api.providers import router as providers_router
from api.libraries import router as libraries_router
from api.shutdown import router as shutdown_router

# Il vecchio motore WinSarp resta disponibile per sviluppo interno, ma non fa
# parte del percorso pubblico del bibliotecario. Si abilita esplicitamente solo
# quando serve lavorare sul modulo legacy.
formule_router = None
graph_router = None
query_router = None
documents_router = None
integrations_router = None
if getattr(cfg, "ENABLE_LEGACY_WINSARP", False):
    from api.query import router as query_router
    from api.documents import router as documents_router
    from api.formule import router as formule_router
    from api.graph import router as graph_router
    from api.integrations import router as integrations_router

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(backup_router)
app.include_router(users_router)
app.include_router(audit_router)
app.include_router(models_router)
app.include_router(providers_router)
app.include_router(libraries_router)
app.include_router(shutdown_router)

if formule_router is not None:
    app.include_router(formule_router)
if graph_router is not None:
    app.include_router(graph_router)
if query_router is not None:
    app.include_router(query_router)
if documents_router is not None:
    app.include_router(documents_router)
if integrations_router is not None:
    app.include_router(integrations_router)

# ── v1 routing retrocompatibilità ──
try:
    from fastapi.routing import APIRoute
    _v1_routes_added = 0
    _current_routes = list(app.routes)
    for _route in _current_routes:
        if isinstance(_route, APIRoute):
            _path = _route.path
            if _path.startswith("/v1") or _path == "/" or _path.startswith("/docs") or _path.startswith("/openapi") or _path == "/metrics":
                continue
            _v1_path = f"/v1{_path}"
            if not any(r.path == _v1_path for r in app.routes):
                app.add_api_route(
                    _v1_path,
                    _route.endpoint,
                    methods=_route.methods,
                    tags=[t + " (v1)" for t in _route.tags] if _route.tags else ["v1"],
                    summary=_route.summary,
                    description=_route.description,
                    include_in_schema=_route.include_in_schema,
                    response_model=_route.response_model,
                )
                _v1_routes_added += 1
    _logger.info("Enterprise Routing: registrati %d endpoint con prefisso v1 per retrocompatibilità", _v1_routes_added)
except Exception as _e:
    _logger.error("Errore durante l'inizializzazione del routing v1: %s", _e)

# ── Frontend Static (SPA) ──
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def _serve_frontend(full_path: str = ""):
        idx = os.path.join(_frontend_dist, "index.html")
        if os.path.isfile(idx):
            return HTMLResponse(Path(idx).read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Ermes</h1><p>Frontend non trovato.</p>")
