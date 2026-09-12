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
import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from config import cfg
from core.governance import append_audit

_logger = logging.getLogger(__name__)

# ── Prometheus metrics ──
from core.metrics import HTTP_DURATION, HTTP_REQUESTS  # noqa: F401 — usati nel middleware

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
        d for d in os.listdir(cfg.DOCS_DIR) if os.path.isdir(os.path.join(cfg.DOCS_DIR, d)) and d.lower() != "libraries"
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
    # Prima di qualsiasi altra cosa: una configurazione inutilizzabile deve
    # impedire l'avvio, non trasformarsi in errori sparsi a runtime. Il caso
    # che ha motivato il controllo: SSO abilitato senza issuer ne' JWKS
    # faceva partire l'applicazione con /health a 200 mentre ogni accesso era
    # gia' destinato a fallire.
    from config.validation import enforce
    from core.logging_setup import configure_logging

    # Prima della validazione, altrimenti i problemi di configurazione
    # uscirebbero nel formato che si sta per sostituire.
    configure_logging(cfg)
    enforce(cfg, logger=_logger)

    # La credenziale memorizzata in security/users.json deve seguire
    # ERMES_ADMIN_PASSWORD a ogni avvio. Fino al 10 settembre 2026
    # `ensure_default_admin` era invocata SOLO sul ramo di fallimento di
    # `login` (api/auth.py): finche' qualcuno entrava con la password vecchia,
    # quella continuava a bastare e la nuova non veniva mai applicata. Chi
    # ruotava la password perche' era stata divulgata non revocava niente.
    # Dimostrato su un clone pulito: dopo aver generato una credenziale nuova,
    # `admin/CHANGE_ME` continuava a funzionare accanto a essa.
    # L'applicazione precedente (legacy_winsarp/app.py) lo faceva all'avvio;
    # nella riscrittura e' rimasto solo sul percorso d'errore.
    if cfg.ADMIN_PASSWORD:
        try:
            from core.governance import ensure_default_admin

            ensure_default_admin(cfg.USERS_FILE, cfg.ADMIN_USERNAME, cfg.ADMIN_PASSWORD)
        except OSError as errore:
            # Non fatale: un'installazione con OIDC o API key resta usabile.
            _logger.error("Impossibile allineare la credenziale amministrativa: %s", errore)

    # Metriche: etichette di sistema (una sola serie, idempotente).
    import platform
    from importlib import metadata

    from core.metrics import init_system_info

    try:
        app_version = metadata.version("ermes")
    except metadata.PackageNotFoundError:
        app_version = "unknown"
    init_system_info(
        version=app_version,
        python_version=platform.python_version(),
        environment=getattr(cfg, "ENVIRONMENT", "production"),
    )

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
            asyncio.create_task(
                asyncio.to_thread(process_ingestion_job, ingestion_store, job["id"], cfg.LIBRARY_STORAGE_DIR)
            )
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

    # ── Avvia Folder Watcher daemon thread ──
    _watcher_stop_event = threading.Event()
    _watcher_thread = None
    try:
        from api.libraries import get_library_store
        from core.folder_watcher import start_folder_watcher_thread

        _watcher_thread = start_folder_watcher_thread(
            store=get_library_store(),
            storage_dir=cfg.LIBRARY_STORAGE_DIR,
            interval_sec=getattr(cfg, "FOLDER_WATCHER_INTERVAL_SEC", 30),
            stop_event=_watcher_stop_event,
        )
        _logger.info("Folder Watcher daemon thread avviato con successo.")
    except Exception as watcher_err:
        _logger.warning("Impossibile avviare Folder Watcher thread: %s", watcher_err)

    yield

    if _watcher_stop_event is not None:
        _watcher_stop_event.set()
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


# ── Correlazione delle richieste ──
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Dà a ogni richiesta un identificativo che compare in tutte le sue righe.

    Se un reverse proxy ne fornisce gia' uno (`X-Request-ID`) viene rispettato,
    cosi' la stessa richiesta e' rintracciabile dal proxy fino ad Ermes; l'id
    torna anche nella risposta, cosi' un utente che segnala un errore puo'
    citarlo. Senza, correlare le righe di piu' richieste concorrenti sulla
    stessa istanza non e' possibile.
    """
    import time as _time
    import uuid as _uuid

    from core.logging_setup import actor_var, request_id_var

    incoming = request.headers.get("X-Request-ID", "").strip()
    # Un id fornito dall'esterno finisce nei log: limitato in lunghezza e
    # ripulito, per non farsi iniettare righe arbitrarie.
    request_id = "".join(c for c in incoming if c.isalnum() or c in "-_")[:64] or _uuid.uuid4().hex
    token = request_id_var.set(request_id)
    actor_token = actor_var.set(None)
    started = _time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
        actor_var.reset(actor_token)
    response.headers["X-Request-ID"] = request_id
    _logger.info(
        "%s %s -> %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((_time.perf_counter() - started) * 1000, 2),
            "request_id": request_id,
        },
    )
    return response


# ── Prometheus metrics middleware ──
@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    path = request.url.path
    if path == "/metrics":
        return await call_next(request)

    normalized_path = re.sub(r"/[0-9a-fA-F-]{36}", "/{uuid}", path)
    normalized_path = re.sub(r"/api/users/[a-zA-Z0-9_\-]+", "/api/users/{username}", normalized_path)
    normalized_path = re.sub(r"/api/documents/[a-zA-Z0-9_\-\.]+", "/api/documents/{filename}", normalized_path)
    normalized_path = re.sub(
        r"/api/formula/cancel/[a-zA-Z0-9_\-]+", "/api/formula/cancel/{request_id}", normalized_path
    )
    normalized_path = re.sub(
        r"/api/winsarp/catalog/[a-zA-Z0-9_\-]+", "/api/winsarp/catalog/{formula_id}", normalized_path
    )

    start_time = __import__("time").perf_counter()
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
        HTTP_REQUESTS.labels(method=method, path=normalized_path, status=str(status_code)).inc()
        HTTP_DURATION.labels(method=method, path=normalized_path).observe(duration)


@app.get("/metrics", tags=["Monitoring"], include_in_schema=True)
def prometheus_metrics(request: Request):
    """Espone le metriche Prometheus.

    Default-secure: con ERMES_METRICS_TOKEN impostato richiede
    Authorization: Bearer <token>; senza token, l'accesso è consentito
    solo dal loopback (scrape locale su singolo nodo).
    """
    from core.metrics import expose

    expected_token = getattr(cfg, "METRICS_TOKEN", "")
    if expected_token:
        authorization = request.headers.get("authorization", "")
        if authorization != f"Bearer {expected_token}":
            raise HTTPException(status_code=401, detail="Token metrics mancante o non valido")
    else:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(
                status_code=401, detail="Configurare ERMES_METRICS_TOKEN per l'accesso remoto a /metrics"
            )
    return Response(content=expose(), media_type="text/plain; version=0.0.4")


# ── Import moduli ──
from api.analytics import router as analytics_router
from api.audit import router as audit_router
from api.auth import router as auth_router
from api.backup import router as backup_router
from api.chat_webhooks import router as chat_webhooks_router
from api.connectors import router as connectors_router
from api.health import router as health_router
from api.libraries import router as libraries_router
from api.mcp_server import router as mcp_server_router
from api.models import router as models_router
from api.pii import router as pii_router
from api.privacy import router as privacy_router
from api.providers import router as providers_router
from api.shutdown import router as shutdown_router
from api.synonyms import router as synonyms_router
from api.users import router as users_router
from api.webhook_gateway import router as webhook_gateway_router

# Il vecchio motore WinSarp resta disponibile per sviluppo interno, ma non fa
# parte del percorso pubblico del bibliotecario. Si abilita esplicitamente solo
# quando serve lavorare sul modulo legacy.
formule_router: APIRouter | None = None
graph_router: APIRouter | None = None
query_router: APIRouter | None = None
documents_router: APIRouter | None = None
integrations_router: APIRouter | None = None
if getattr(cfg, "ENABLE_LEGACY_WINSARP", False):
    from api.documents import router as _documents_router
    from api.formule import router as _formule_router
    from api.graph import router as _graph_router
    from api.integrations import router as _integrations_router
    from api.query import router as _query_router

    documents_router = _documents_router
    formule_router = _formule_router
    graph_router = _graph_router
    integrations_router = _integrations_router
    query_router = _query_router

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(pii_router)
app.include_router(backup_router)
app.include_router(users_router)
app.include_router(audit_router)
app.include_router(analytics_router)
app.include_router(connectors_router)
app.include_router(models_router)
app.include_router(providers_router)
app.include_router(libraries_router)
app.include_router(chat_webhooks_router)
app.include_router(mcp_server_router)
app.include_router(privacy_router)
app.include_router(synonyms_router)
app.include_router(webhook_gateway_router)
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
            if (
                _path.startswith("/v1")
                or _path == "/"
                or _path.startswith("/docs")
                or _path.startswith("/openapi")
                or _path == "/metrics"
            ):
                continue
            _v1_path = f"/v1{_path}"
            if not any(isinstance(r, APIRoute) and r.path == _v1_path for r in app.routes):
                app.add_api_route(
                    _v1_path,
                    _route.endpoint,
                    methods=list(_route.methods) if _route.methods else None,
                    tags=[f"{t} (v1)" for t in _route.tags] if _route.tags else ["v1"],
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
        # La SPA deve servire solo le rotte dell'interfaccia: un path API
        # sconosciuto (es. typo o route mancante) deve restare un 404 JSON,
        # non l'HTML dell'app con status 200 — altrimenti i client API
        # ricevono risposte HTML "successful" anche quando qualcosa e' rotto.
        first = full_path.split("/", 1)[0].lower()
        if first in {"api", "v1", "metrics", "docs", "redoc", "openapi.json", "health"}:
            raise HTTPException(status_code=404, detail="Endpoint non trovato")
        idx = os.path.join(_frontend_dist, "index.html")
        if os.path.isfile(idx):
            return HTMLResponse(Path(idx).read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Ermes</h1><p>Frontend non trovato.</p>")
