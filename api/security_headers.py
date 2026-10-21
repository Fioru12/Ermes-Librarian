"""Content-Security-Policy dell'applicazione.

L'interfaccia e' un'app statica che parla solo con questo server: niente
script, font, immagini o connessioni verso altri domini. La politica lo
impone al browser, cosi' un'eventuale iniezione di HTML non puo' caricare
codice esterno ne' mandare dati altrove.

- `style-src 'unsafe-inline'`: React scrive stili in linea (attributo `style`);
  gli script restano limitati a `'self'`, che e' la parte che conta.
- Il download di un documento (`.../documents/<id>/download`) puo' essere incorporato in
  un `<iframe>` della stessa interfaccia, per il visualizzatore PDF: li' `frame-ancestors`
  e' `'self'` invece di `'none'`. Il server serve "inline" solo PDF veri (vedi
  `api/libraries.py`), tutto il resto e' sempre un download.
- `/docs` e `/redoc` (Swagger UI e ReDoc generati da FastAPI) caricano
  JavaScript e CSS da jsDelivr: hanno una politica piu' larga, limitata a
  quelle due pagine, che servono a chi sviluppa e non fanno parte
  dell'interfaccia.
"""

from __future__ import annotations

import re

_APP_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

_DOCUMENT_DOWNLOAD_POLICY = _APP_POLICY.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
_DOCUMENT_DOWNLOAD_PATH = re.compile(r"^(/v1)?/api/libraries/[^/]+/documents/[^/]+/download$")

_API_DOCS_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "connect-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
    ]
)


def content_security_policy(path: str) -> str:
    if path in ("/docs", "/redoc") or path.startswith(("/docs/", "/redoc/")):
        return _API_DOCS_POLICY
    if _DOCUMENT_DOWNLOAD_PATH.match(path):
        return _DOCUMENT_DOWNLOAD_POLICY
    return _APP_POLICY
