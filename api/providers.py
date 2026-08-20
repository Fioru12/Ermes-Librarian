"""
api/providers.py
Provider management (CRUD, detect, fetch-models).
"""
import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _require_role
from config import cfg

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Providers"])


class ProviderConfigRequest(BaseModel):
    name: str
    type: str
    api_key: str = ""
    base_url: str = ""
    default_model: str = ""
    models: list[str] = []
    enabled: bool = True
    extra: dict[str, str] = {}


class ProviderTestRequest(BaseModel):
    name: str = ""
    type: str
    api_key: str = ""
    base_url: str = ""
    default_model: str = ""
    models: list[str] = []
    extra: dict[str, str] = {}


class SetActiveProviderRequest(BaseModel):
    name: str | None = None


class DetectProviderRequest(BaseModel):
    api_key: str = Field(..., min_length=3, max_length=500, description="API key da analizzare")


class FetchModelsRequest(BaseModel):
    type: str = Field(default="openai", description="Tipo provider: openai, anthropic, google, ollama")
    base_url: str = Field(default="", description="Base URL del provider")
    api_key: str = Field(default="", description="API key (opzionale per provider pubblici)")


PROVIDER_SIGNATURES: list[tuple[str, str, str, str]] = [
    ("sk-or-", "openai", "https://openrouter.ai/api/v1", "tencent/hy3:free"),
    ("sk-ant-", "anthropic", "https://api.anthropic.com", "claude-3-5-haiku-latest"),
    ("sk-", "openai", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("AIza", "google", "https://generativelanguage.googleapis.com", "gemini-2.0-flash"),
    ("gsk_", "openai", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
]

_LOCAL_PROVIDER_HOSTS = {"localhost", "127.0.0.1", "::1", "ollama"}


def validate_provider_base_url(base_url: str) -> str:
    """Allow only explicitly approved provider hosts and safe URL schemes."""
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise HTTPException(400, "Base URL del provider obbligatorio")
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Base URL del provider non valida")
    allowed_hosts = set(getattr(cfg, "PROVIDER_ALLOWED_HOSTS", ()))
    if hostname not in allowed_hosts:
        raise HTTPException(403, "Endpoint provider non approvato: aggiungilo esplicitamente a ERMES_PROVIDER_ALLOWED_HOSTS")
    if hostname not in _LOCAL_PROVIDER_HOSTS and parsed.scheme != "https":
        raise HTTPException(400, "I provider esterni devono usare HTTPS")
    return normalized


@router.get("/api/providers")
async def list_providers(_auth: dict = Depends(_require_role("admin"))):
    from core.ai.providers.registry import get_registry
    registry = get_registry()
    return {"providers": registry.list_providers(), "active": registry.get_active_name()}


@router.post("/api/providers")
async def add_provider(request: ProviderConfigRequest, _auth: dict = Depends(_require_role("admin"))):
    from core.ai.providers.base import ProviderConfig
    from core.ai.providers.registry import get_registry
    registry = get_registry()
    base_url = validate_provider_base_url(request.base_url)
    config = ProviderConfig(
        name=request.name,
        type=request.type,
        api_key=request.api_key,
        base_url=base_url,
        default_model=request.default_model,
        models=request.models,
        enabled=request.enabled,
        extra=request.extra,
    )
    try:
        provider = registry.add_provider(config)
        return {"message": f"Provider '{request.name}' aggiunto", "provider": provider.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/providers/test")
async def test_provider(request: ProviderTestRequest, _auth: dict = Depends(_require_role("admin"))):
    from core.ai.providers.base import ProviderConfig
    from core.ai.providers.registry import get_registry
    registry = get_registry()
    base_url = validate_provider_base_url(request.base_url)
    config = ProviderConfig(
        name=request.name or "test",
        type=request.type,
        api_key=request.api_key,
        base_url=base_url,
        default_model=request.default_model,
        models=request.models,
        extra=request.extra,
    )
    ok, msg = registry.test_provider(config)
    return {"ok": ok, "message": msg}


@router.put("/api/providers/{name}")
async def update_provider(name: str, request: ProviderConfigRequest, _auth: dict = Depends(_require_role("admin"))):
    from core.ai.providers.base import ProviderConfig
    from core.ai.providers.registry import get_registry
    registry = get_registry()
    existing = registry.get_provider(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' non trovato")
    base_url = validate_provider_base_url(request.base_url or existing.config.base_url)
    config = ProviderConfig(
        name=request.name,
        type=request.type,
        api_key=request.api_key or existing.config.api_key,
        base_url=base_url,
        default_model=request.default_model or existing.config.default_model,
        models=request.models or existing.config.models,
        enabled=request.enabled,
        extra=request.extra or existing.config.extra,
    )
    registry.remove_provider(name)
    provider = registry.add_provider(config)
    return {"message": f"Provider '{request.name}' aggiornato", "provider": provider.to_dict()}


@router.delete("/api/providers/{name}")
async def delete_provider(name: str, _auth: dict = Depends(_require_role("admin"))):
    from core.ai.providers.registry import get_registry
    registry = get_registry()
    existing = registry.get_provider(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' non trovato")
    registry.remove_provider(name)
    return {"message": f"Provider '{name}' rimosso"}


@router.put("/api/providers/active")
async def set_active_provider(request: SetActiveProviderRequest, _auth: dict = Depends(_require_role("admin"))):
    from core.ai.providers.registry import get_registry
    registry = get_registry()
    try:
        registry.set_active(request.name)
        return {"message": f"Provider attivo impostato: {request.name}" if request.name else "Nessun provider attivo"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/providers/detect", summary="Rileva automaticamente tipo e configurazione da una API key")
async def detect_provider(request: DetectProviderRequest, _auth: dict = Depends(_require_role("admin"))):
    key = request.api_key.strip()
    detected = {"api_key": key, "type": "openai", "base_url": "", "default_model": "", "match": "unknown"}

    for prefix, ptype, base_url, default_model in PROVIDER_SIGNATURES:
        if key.startswith(prefix):
            detected["type"] = ptype
            detected["base_url"] = base_url
            detected["default_model"] = default_model
            detected["match"] = prefix
            break

    models: list[str] = []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    model_urls = []

    if detected["type"] == "openai":
        model_urls.append(f"{detected['base_url']}/models")
    elif detected["type"] == "anthropic":
        model_urls.append("https://api.anthropic.com/v1/models")
    elif detected["type"] == "google":
        model_urls.append("https://generativelanguage.googleapis.com/v1/models?key=" + key)

    for url in model_urls:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if "data" in data:
                        models = [m.get("id", "") for m in data["data"] if m.get("id")]
                    elif "models" in data:
                        models = [m.get("id") or m.get("name", "") for m in data["models"] if m.get("id") or m.get("name")]
                    models = [m for m in models if m]
                    break
        except Exception:
            continue

    detected["models"] = models[:50]
    return detected


@router.post("/api/providers/fetch-models", summary="Recupera la lista modelli da un provider")
async def fetch_models(request: FetchModelsRequest, _auth: dict = Depends(_require_role("admin"))):
    models: list[str] = []
    defaults = {
        "ollama": "http://127.0.0.1:11434",
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com",
        "google": "https://generativelanguage.googleapis.com",
    }
    url = validate_provider_base_url(request.base_url or defaults.get(request.type, ""))

    try:
        headers = {"Content-Type": "application/json"}
        if request.api_key:
            headers["Authorization"] = f"Bearer {request.api_key}"

        if request.type == "ollama":
            fetch_url = f"{url}/api/tags"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(fetch_url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        elif request.type in ("openai",):
            fetch_url = f"{url}/models"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(fetch_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        elif request.type == "anthropic":
            fetch_url = "https://api.anthropic.com/v1/models"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(fetch_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        elif request.type == "google":
            fetch_url = f"{url or 'https://generativelanguage.googleapis.com'}/v1/models?key={request.api_key}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(fetch_url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name", "").replace("models/", "") for m in data.get("models", []) if m.get("name")]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Errore connessione: {e}")

    return {"models": sorted(set(models))[:100], "count": len(models), "url": fetch_url if url else ""}
