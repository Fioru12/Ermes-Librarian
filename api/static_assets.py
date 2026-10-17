"""Serving dei file statici dell'interfaccia: compressione e cache.

Vite mette un hash del contenuto nel nome dei file JS e CSS
(`index-zW5trO8z.js`): un file con quel nome non cambia mai, quindi il browser
puo' tenerlo un anno. Gli altri file (immagini senza hash) si rivalidano:
StaticFiles manda gia' ETag e Last-Modified, quindi costano una risposta 304.

Senza queste intestazioni ogni apertura dell'applicazione riscaricava circa
300 kB di JavaScript non compresso.
"""

from __future__ import annotations

import re
from pathlib import Path

from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

# nome-HASH.js / nome-HASH.css, con l'hash di 8 caratteri di Vite
_HASHED = re.compile(r"-[A-Za-z0-9_-]{8}\.(?:js|css)$")


class HashedAssets(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            if _HASHED.search(path):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        return response


def assets_app(directory: str):
    """App ASGI pronta da montare su /assets: file statici, cache e gzip."""
    return GZipMiddleware(HashedAssets(directory=directory), minimum_size=1024)


_MEDIA_TYPES = {".webmanifest": "application/manifest+json"}


def resolve_frontend_file(dist: str, full_path: str) -> Path | None:
    """File reale dentro `dist` che corrisponde a `full_path`, oppure None.

    La catch-all della SPA rispondeva con index.html a QUALUNQUE percorso non
    API, quindi `/favicon.svg` e `/manifest.webmanifest` restituivano HTML con
    stato 200: icona rotta e app non installabile. Qui si risolvono i file
    veri; l'uscita da `dist` (`..`, percorsi assoluti, link simbolici) non e'
    mai consentita.
    """
    if not full_path or full_path.endswith("/"):
        return None
    radice = Path(dist).resolve()
    try:
        candidato = (radice / full_path).resolve()
    except (OSError, ValueError):
        return None
    if candidato.is_file() and candidato.is_relative_to(radice) and candidato.name != "index.html":
        return candidato
    return None


def media_type_for(path: Path) -> str | None:
    return _MEDIA_TYPES.get(path.suffix.lower())
