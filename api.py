"""
api.py
Wrapper di retrocompatibilità — re-exporta l'app dal nuovo package api/.

Ora i moduli sono suddivisi in api/ per manutenibilità:
    api/auth.py       → Autenticazione JWT + RBAC + rate limiter
    api/health.py     → Health check
    api/query.py      → Query RAG, streaming, cache
    api/backup.py     → Backup management
    api/users.py      → User management
    api/audit.py      → Audit log
    api/formule.py    → Formula WinSarp generation, catalog, validation
    api/documents.py  → Document upload/delete/reindex
    api/models.py     → Models listing
    api/providers.py  → Provider management
    api/graph.py      → Knowledge graph
    api/integrations.py → Teams, Slack, Telegram webhook
    api/shutdown.py   → Shutdown endpoint
"""
import sys
import os

# Aggiungi la directory corrente al path se non già presente
_api_dir = os.path.dirname(os.path.abspath(__file__))
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

from api import app, _list_available_modules, _resolve_module_name

# Re-export per retrocompatibilità con codice che fa `from api import ...`
__all__ = ["app", "_list_available_modules", "_resolve_module_name"]

if __name__ == "__main__":
    import uvicorn
    from config import cfg
    uvicorn.run("api:app", host=cfg.HOST, port=cfg.PORT, reload=True)