"""Verifica crittografica dei token OIDC (firma + claim standard).

Perche' questo modulo esiste
----------------------------
La versione precedente di `api/auth.py::_validate_oidc_jwt` decodificava il
payload del token in base64 e si fidava del contenuto: controllava `exp`,
`iss` e `aud`, ma non verificava **mai** la firma. Un JWT e' testo firmato,
non testo cifrato: chiunque puo' scriverne il payload. Bastava quindi
costruire a mano `{"preferred_username": "chiunque", "roles": ["admin"]}`,
concatenare una firma qualsiasi e ottenere un amministratore. Verificato
empiricamente prima della correzione, non dedotto.

Due difetti minori, nascosti dal primo:

- `if exp and exp < time.time()` accettava un token **senza** `exp`, che
  quindi non scadeva mai;
- `OIDC_JWKS_URL` era dichiarato in `config/security.py` e non letto da
  nessuna parte: le chiavi del provider non venivano mai recuperate.

Scelte di sicurezza
-------------------
- **Solo algoritmi asimmetrici.** Accettare `HS*` insieme a `RS*` apre la
  confusione di algoritmo: l'attaccante firma con HMAC usando come segreto
  la chiave *pubblica* del provider, che e' pubblica per definizione. `none`
  e' rifiutato per la stessa ragione, a monte.
- **`exp` obbligatorio**, non piu' facoltativo.
- **Fail closed.** Se le chiavi non sono raggiungibili, se il `kid` non
  esiste, o se non c'e' modo di scoprire il JWKS, il token viene rifiutato.
  Non esiste percorso che ricada sulla decodifica non verificata.
- **Il recupero delle chiavi e' limitato nel tempo.** Un `kid` sconosciuto
  provoca al massimo un rinnovo ogni `_MIN_REFETCH_SECONDS`: altrimenti
  basterebbe inviare token con `kid` casuali per trasformare l'endpoint di
  login in un amplificatore di traffico verso il provider.
"""

import logging
import threading
import time

import httpx
import jwt

from config import cfg

_logger = logging.getLogger(__name__)

# Solo asimmetrici: vedi "confusione di algoritmo" nel docstring.
_ALLOWED_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"})

_CACHE_TTL_SECONDS = 3600.0
_MIN_REFETCH_SECONDS = 60.0
_HTTP_TIMEOUT_SECONDS = 5.0
_CLOCK_LEEWAY_SECONDS = 30.0

_lock = threading.Lock()
_jwks_url: str | None = None
_keys: dict[str, "jwt.PyJWK"] = {}
_fetched_at: float = 0.0
_last_attempt: float = 0.0


def reset_key_cache() -> None:
    """Svuota la cache delle chiavi. Usata dai test e dopo un cambio di configurazione."""
    global _jwks_url, _keys, _fetched_at, _last_attempt
    with _lock:
        _jwks_url = None
        _keys = {}
        _fetched_at = 0.0
        _last_attempt = 0.0


def _resolve_jwks_url() -> str | None:
    """URL del JWKS: esplicito se configurato, altrimenti dal discovery OIDC."""
    global _jwks_url
    if _jwks_url:
        return _jwks_url
    if cfg.OIDC_JWKS_URL:
        _jwks_url = cfg.OIDC_JWKS_URL
        return _jwks_url
    if not cfg.OIDC_ISSUER:
        return None
    discovery = cfg.OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration"
    try:
        response = httpx.get(discovery, timeout=_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        url = response.json().get("jwks_uri")
    except (httpx.HTTPError, ValueError, TypeError) as error:
        _logger.warning("OIDC: discovery non raggiungibile (%s): %s", discovery, error)
        return None
    if not url:
        _logger.warning("OIDC: il documento di discovery non dichiara jwks_uri")
        return None
    _jwks_url = str(url)
    return _jwks_url


def _fetch_keys() -> None:
    """Aggiorna la cache delle chiavi. Il chiamante deve tenere `_lock`."""
    global _keys, _fetched_at, _last_attempt
    _last_attempt = time.monotonic()
    url = _resolve_jwks_url()
    if not url:
        return
    try:
        response = httpx.get(url, timeout=_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        key_set = jwt.PyJWKSet.from_dict(response.json())
    except (httpx.HTTPError, ValueError, TypeError, jwt.PyJWKSetError, jwt.PyJWKError) as error:
        _logger.warning("OIDC: JWKS non recuperabile da %s: %s", url, error)
        return
    fetched = {key.key_id: key for key in key_set.keys if key.key_id}
    if not fetched:
        _logger.warning("OIDC: il JWKS di %s non contiene chiavi con kid", url)
        return
    _keys = fetched
    _fetched_at = time.monotonic()


def _key_for(kid: str) -> "jwt.PyJWK | None":
    """Chiave corrispondente al kid, rinnovando la cache quando serve."""
    with _lock:
        now = time.monotonic()
        stale = not _keys or (now - _fetched_at) > _CACHE_TTL_SECONDS
        if stale:
            _fetch_keys()
        key = _keys.get(kid)
        if key is None and (now - _last_attempt) > _MIN_REFETCH_SECONDS:
            # Il provider puo' aver ruotato le chiavi: un solo rinnovo,
            # limitato nel tempo per non farsi guidare da kid arbitrari.
            _fetch_keys()
            key = _keys.get(kid)
        return key


def verify_signed_claims(token: str) -> dict | None:
    """Restituisce i claim di un token OIDC valido, altrimenti None.

    "Valido" significa: firmato da una chiave pubblicata dal provider, con
    un algoritmo asimmetrico, non scaduto, e con `iss`/`aud` corrispondenti
    alla configurazione quando questa li specifica.
    """
    if not token:
        return None
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as error:
        _logger.warning("OIDC: intestazione del token illeggibile: %s", error)
        return None

    algorithm = header.get("alg")
    if algorithm not in _ALLOWED_ALGORITHMS:
        _logger.warning("OIDC: algoritmo '%s' rifiutato", algorithm)
        return None

    kid = header.get("kid")
    if not kid:
        _logger.warning("OIDC: token senza kid, chiave non individuabile")
        return None

    key = _key_for(str(kid))
    if key is None:
        _logger.warning("OIDC: nessuna chiave pubblicata per kid '%s'", kid)
        return None

    try:
        return jwt.decode(
            token,
            key.key,
            algorithms=[algorithm],
            audience=cfg.OIDC_AUDIENCE or None,
            issuer=cfg.OIDC_ISSUER or None,
            leeway=_CLOCK_LEEWAY_SECONDS,
            # `require: exp` e' il punto: la versione precedente trattava la
            # scadenza come facoltativa, quindi un token senza `exp` era
            # eterno.
            options={"require": ["exp"], "verify_aud": bool(cfg.OIDC_AUDIENCE)},
        )
    except jwt.PyJWTError as error:
        _logger.warning("OIDC: token rifiutato: %s", error)
        return None
