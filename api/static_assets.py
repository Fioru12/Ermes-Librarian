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
