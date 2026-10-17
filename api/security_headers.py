"""Content-Security-Policy dell'applicazione.

L'interfaccia e' un'app statica che parla solo con questo server: niente
script, font, immagini o connessioni verso altri domini. La politica lo
impone al browser, cosi' un'eventuale iniezione di HTML non puo' caricare
codice esterno ne' mandare dati altrove.

- `style-src 'unsafe-inline'`: React scrive stili in linea (attributo `style`);
  gli script restano limitati a `'self'`, che e' la parte che conta.
- `/docs` e `/redoc` (Swagger UI e ReDoc generati da FastAPI) caricano
  JavaScript e CSS da jsDelivr: hanno una politica piu' larga, limitata a
  quelle due pagine, che servono a chi sviluppa e non fanno parte
  dell'interfaccia.
"""

from __future__ import annotations

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
    return _APP_POLICY
